"""_to_openai_messages() converts Talaria's neutral history into the
OpenAI wire format. Regression coverage for a real bug: an assistant turn
with tool_calls and no text sent `content: null`, which the official
OpenAI API accepts but at least one real OpenAI-compatible backend
("Decart" via a router) rejected outright with "content must be a string
or an array of content parts."
"""

from talaria.providers.base import ToolCall
from talaria.providers.openai_compat import OpenAICompatProvider, _to_openai_messages


def test_timeout_seconds_defaults_to_120():
    provider = OpenAICompatProvider(api_key="x", base_url="http://example.invalid", model="x")
    assert provider.client.timeout == 120.0


def test_timeout_seconds_is_configurable():
    # Regression coverage: a local server (LM Studio, Ollama, ...) on
    # consumer hardware reprocesses the whole prompt from scratch every
    # request, which can genuinely take minutes on a large conversation —
    # the fixed 120s the client used to hardcode was too short for that.
    provider = OpenAICompatProvider(
        api_key="x", base_url="http://example.invalid", model="x", timeout_seconds=600.0
    )
    assert provider.client.timeout == 600.0


def test_user_message_passthrough():
    history = [{"role": "user", "content": "hi"}]
    assert _to_openai_messages(history) == [{"role": "user", "content": "hi"}]


def test_tool_message_passthrough():
    history = [{"role": "tool", "tool_call_id": "1", "name": "echo", "content": "result"}]
    assert _to_openai_messages(history) == [
        {"role": "tool", "tool_call_id": "1", "content": "result"}
    ]


def test_assistant_message_with_text_and_no_tool_calls():
    history = [{"role": "assistant", "content": "hi there", "tool_calls": []}]
    messages = _to_openai_messages(history)
    assert messages == [{"role": "assistant", "content": "hi there"}]


def test_assistant_tool_calls_only_sends_empty_string_content_not_null():
    # This is the exact shape a real ClaudeProvider/OpenAICompatProvider
    # response has when the model goes straight to a tool call with no
    # preamble text: content is "" (from "".join([])), which is falsy —
    # the bug was `entry.get("content") or None` turning that into a
    # JSON `null`, which a strict backend rejected.
    history = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [ToolCall(id="1", name="echo", input={"x": "y"})],
        }
    ]

    messages = _to_openai_messages(history)

    assert len(messages) == 1
    assert messages[0]["content"] == ""
    assert messages[0]["content"] is not None
    assert messages[0]["tool_calls"] == [
        {"id": "1", "type": "function", "function": {"name": "echo", "arguments": '{"x": "y"}'}}
    ]


def test_full_tool_round_trip_never_produces_null_content():
    history = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [ToolCall(id="1", name="echo", input={})],
        },
        {"role": "tool", "tool_call_id": "1", "name": "echo", "content": "ok"},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]

    messages = _to_openai_messages(history)

    for m in messages:
        if "content" in m:
            assert m["content"] is not None
