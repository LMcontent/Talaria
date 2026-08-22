import json

from openai import OpenAI

from mini_hermes.providers.base import Provider, ProviderResponse, ToolCall, ToolSpec


class OpenAICompatProvider(Provider):
    """Backend for any OpenAI-compatible chat-completions router
    (OrcaRouter, OpenRouter, etc.) — set OPENAI_COMPAT_BASE_URL / _API_KEY / _MODEL.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        # Flaky routers/proxies can drop the connection mid-response — retry
        # a few times before giving up, and allow slow "stealth" models room
        # to respond instead of timing out early.
        self.client = OpenAI(
            api_key=api_key, base_url=base_url, max_retries=5, timeout=120.0
        )
        self.model = model

    def chat(self, history: list[dict], system: str, tools: list[ToolSpec]) -> ProviderResponse:
        messages = [{"role": "system", "content": system}, *_to_openai_messages(history)]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[_to_openai_tool(t) for t in tools] if tools else None,
        )

        choice = response.choices[0].message
        text = choice.content or ""
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                input=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.tool_calls or [])
        ]
        return ProviderResponse(text=text, tool_calls=tool_calls)


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
