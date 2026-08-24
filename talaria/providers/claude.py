from typing import Callable

import anthropic
import httpx2
from anthropic import DefaultHttpxClient

from talaria.providers.base import Provider, ProviderResponse, ToolCall, ToolSpec


class ClaudeProvider(Provider):
    def __init__(self, api_key: str, model: str):
        # max_keepalive_connections=0: fresh TCP/TLS connection per request
        # instead of a reused pooled one — see the identical comment in
        # openai_compat.py for why (a filter that kills one specific
        # long-lived connection mid-session, only cleared by restarting).
        self.client = anthropic.Anthropic(
            api_key=api_key,
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
    ) -> ProviderResponse:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=_to_anthropic_messages(history),
            tools=[_to_anthropic_tool(t) for t in tools] if tools else anthropic.NOT_GIVEN,
        ) as stream:
            for text_chunk in stream.text_stream:
                print(text_chunk, end="", flush=True)
                if on_chunk:
                    on_chunk(text_chunk)
            response = stream.get_final_message()

        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        return ProviderResponse(text=text, tool_calls=tool_calls)


def _to_anthropic_tool(tool: ToolSpec) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _to_anthropic_messages(history: list[dict]) -> list[dict]:
    """Convert the neutral history into Anthropic's content-block format.

    Anthropic requires every tool_result for one assistant turn to be
    delivered together in a single user message, so consecutive "tool"
    entries in the neutral history are merged into one user message.
    """
    messages: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results():
        if pending_tool_results:
            messages.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for entry in history:
        role = entry["role"]

        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": entry["tool_call_id"],
                    "content": entry["content"],
                }
            )
            continue

        flush_tool_results()

        if role == "user":
            messages.append({"role": "user", "content": entry["content"]})
        elif role == "assistant":
            content: list[dict] = []
            if entry.get("content"):
                content.append({"type": "text", "text": entry["content"]})
            for tc in entry.get("tool_calls", []):
                content.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
            messages.append({"role": "assistant", "content": content})

    flush_tool_results()
    return messages
