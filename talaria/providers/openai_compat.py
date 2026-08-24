import json
import threading
from typing import Callable

import httpx2
from openai import DefaultHttpxClient, OpenAI

from talaria.providers.base import Provider, ProviderResponse, ToolCall, ToolSpec


class OpenAICompatProvider(Provider):
    """Backend for any OpenAI-compatible chat-completions router
    (OrcaRouter, OpenRouter, etc.) — set OPENAI_COMPAT_BASE_URL / _API_KEY / _MODEL.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dns_pin: bool = False,
        dns_servers: list[str] | None = None,
    ):
        if dns_pin:
            from talaria.providers.dns_pin import pin_base_url

            ip = pin_base_url(base_url, dns_servers or [])
            print(f"[dns-pin] {base_url} -> {ip}")

        # Flaky routers/proxies can drop the connection mid-response — retry
        # a few times before giving up, and allow slow "stealth" models room
        # to respond instead of timing out early.
        #
        # max_keepalive_connections=0 disables HTTP keep-alive so every
        # request opens a fresh TCP/TLS connection instead of reusing one
        # from a pool. Some antivirus/network filters intercept and quietly
        # kill one specific reused connection mid-session — every request
        # after that keeps failing with a 4xx until the whole process
        # restarts (which happens to open a fresh pool). Fresh connections
        # per request avoid depending on any one connection staying good.
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=5,
            timeout=120.0,
            http_client=DefaultHttpxClient(
                limits=httpx2.Limits(max_keepalive_connections=0, max_connections=10)
            ),
        )
        self.model = model

    def chat(
        self,
        history: list[dict],
        system: str,
        tools: list[ToolSpec],
        on_chunk: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ProviderResponse:
        messages = [{"role": "system", "content": system}, *_to_openai_messages(history)]
        kwargs = dict(
            model=self.model,
            messages=messages,
            tools=[_to_openai_tool(t) for t in tools] if tools else None,
            stream=True,
        )
        try:
            # Asks the router to include a final usage-only chunk, needed to
            # track token spend. Not every OpenAI-compatible router accepts
            # this field — if it's rejected outright (rather than just
            # silently ignored), fall back to a plain request rather than
            # breaking chat entirely; that call just won't have usage data.
            stream = self.client.chat.completions.create(
                stream_options={"include_usage": True}, **kwargs
            )
        except Exception:
            stream = self.client.chat.completions.create(**kwargs)

        text_parts: list[str] = []
        tool_call_chunks: dict[int, dict] = {}
        usage: dict[str, int] | None = None
        cancelled = False

        for chunk in stream:
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            if getattr(chunk, "usage", None):
                usage = {
                    "input_tokens": chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens,
                }

            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                text_parts.append(delta.content)
                print(delta.content, end="", flush=True)
                if on_chunk:
                    on_chunk(delta.content)

            for tc_delta in delta.tool_calls or []:
                acc = tool_call_chunks.setdefault(
                    tc_delta.index, {"id": None, "name": None, "arguments": ""}
                )
                if tc_delta.id:
                    acc["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        acc["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        acc["arguments"] += tc_delta.function.arguments

        if cancelled:
            try:
                stream.close()
            except Exception:
                pass
            return ProviderResponse(text="".join(text_parts), tool_calls=[], cancelled=True)

        text = "".join(text_parts)
        tool_calls = [
            ToolCall(
                id=acc["id"],
                name=acc["name"],
                input=json.loads(acc["arguments"] or "{}"),
            )
            for _, acc in sorted(tool_call_chunks.items())
        ]
        return ProviderResponse(text=text, tool_calls=tool_calls, usage=usage)


def _to_openai_tool(tool: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _to_openai_messages(history: list[dict]) -> list[dict]:
    messages: list[dict] = []
    for entry in history:
        role = entry["role"]
        if role == "user":
            messages.append({"role": "user", "content": entry["content"]})
        elif role == "assistant":
            msg: dict = {"role": "assistant", "content": entry.get("content") or None}
            tool_calls = entry.get("tool_calls", [])
            if tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                    }
                    for tc in tool_calls
                ]
            messages.append(msg)
        elif role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": entry["tool_call_id"],
                    "content": entry["content"],
                }
            )
    return messages
