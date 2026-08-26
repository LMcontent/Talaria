"""ClaudeProvider.chat() exercised against a fake anthropic stream object
(context manager + event iterator + get_final_message()), so its event-loop
logic — text vs. thinking deltas, cancel_event, usage extraction — is
verified without a real API key or network call.
"""

import threading
from types import SimpleNamespace

import pytest

from talaria.providers.claude import ClaudeProvider


def _event(type_, delta_type=None, **delta_fields):
    ev = SimpleNamespace(type=type_)
    if delta_type is not None:
        ev.delta = SimpleNamespace(type=delta_type, **delta_fields)
    return ev


class FakeStream:
    def __init__(self, events, final_message):
        self._events = events
        self._final_message = final_message

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final_message


def _final_message(text="", tool_uses=(), input_tokens=10, output_tokens=5, **usage_extra):
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    for tu in tool_uses:
        content.append(SimpleNamespace(type="tool_use", id=tu["id"], name=tu["name"], input=tu["input"]))
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens, **usage_extra)
    return SimpleNamespace(content=content, usage=usage)


@pytest.fixture
def provider(monkeypatch):
    p = ClaudeProvider(api_key="x", model="claude-opus-5")
    monkeypatch.setattr(p, "client", SimpleNamespace(messages=SimpleNamespace(stream=None)))
    return p


def _wire_stream(provider, events, final_message):
    calls = []

    def fake_stream(**kwargs):
        calls.append(kwargs)
        return FakeStream(events, final_message)

    provider.client.messages.stream = fake_stream
    return calls


def test_text_only_reply(provider, capsys):
    events = [
        _event("message_start"),
        _event("content_block_start"),
        _event("content_block_delta", "text_delta", text="Hello"),
        _event("content_block_delta", "text_delta", text=", world"),
        _event("content_block_stop"),
        _event("message_stop"),
    ]
    calls = _wire_stream(provider, events, _final_message(text="Hello, world"))

    chunks = []
    response = provider.chat([], system="sys", tools=[], on_chunk=chunks.append)

    assert response.text == "Hello, world"
    assert response.tool_calls == []
    assert response.cancelled is False
    assert chunks == ["Hello", ", world"]
    assert "thinking" not in calls[0]
    assert "output_config" not in calls[0]


def test_usage_folds_cache_tokens_into_input(provider):
    events = [_event("message_stop")]
    _wire_stream(
        provider,
        events,
        _final_message(
            text="ok", input_tokens=100, output_tokens=20,
            cache_creation_input_tokens=5, cache_read_input_tokens=7,
        ),
    )

    response = provider.chat([], system="sys", tools=[])

    assert response.usage == {"input_tokens": 112, "output_tokens": 20}


def test_tool_calls_extracted():
    provider = ClaudeProvider(api_key="x", model="claude-opus-5")
    events = [_event("message_stop")]
    final = _final_message(tool_uses=[{"id": "1", "name": "echo", "input": {"x": "y"}}])
    calls = []

    def fake_stream(**kwargs):
        calls.append(kwargs)
        return FakeStream(events, final)

    provider.client = SimpleNamespace(messages=SimpleNamespace(stream=fake_stream))

    response = provider.chat([], system="sys", tools=[])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "echo"
    assert response.tool_calls[0].input == {"x": "y"}


def test_cancel_event_cuts_stream_short_and_skips_get_final_message(provider):
    events = [
        _event("content_block_delta", "text_delta", text="partial "),
        _event("content_block_delta", "text_delta", text="should not appear"),
    ]

    class TrackingFinalMessage:
        def __getattr__(self, name):
            raise AssertionError("get_final_message() must not be called once cancelled")

    calls = _wire_stream(provider, events, TrackingFinalMessage())

    cancel_event = threading.Event()

    def on_chunk(t):
        # Cancel right after the first chunk streams — the loop checks
        # cancel_event once per event, after handling it.
        if t == "partial ":
            cancel_event.set()

    response = provider.chat([], system="sys", tools=[], on_chunk=on_chunk, cancel_event=cancel_event)

    assert response.cancelled is True
    assert response.text == "partial "
    assert response.tool_calls == []
    assert len(calls) == 1


def test_show_thinking_requests_adaptive_display_and_prints_markers(monkeypatch, capsys):
    provider = ClaudeProvider(api_key="x", model="claude-opus-5", show_thinking=True)
    events = [
        _event("content_block_delta", "thinking_delta", thinking="pondering..."),
        _event("content_block_delta", "text_delta", text="answer"),
    ]
    calls = _wire_stream(provider, events, _final_message(text="answer"))

    response = provider.chat([], system="sys", tools=[])

    assert response.text == "answer"
    assert calls[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    out = capsys.readouterr().out
    assert "[thinking]" in out
    assert "pondering..." in out
    assert "[/thinking]" in out
    # The thinking marker must close before the real answer text is printed.
    assert out.index("[/thinking]") < out.index("answer")


def test_show_thinking_false_never_sends_thinking_param(provider):
    calls = _wire_stream(provider, [_event("message_stop")], _final_message(text="ok"))
    provider.chat([], system="sys", tools=[])
    assert "thinking" not in calls[0]


def test_effort_sets_output_config(monkeypatch):
    provider = ClaudeProvider(api_key="x", model="claude-opus-5", effort="xhigh")
    calls = _wire_stream(provider, [_event("message_stop")], _final_message(text="ok"))
    provider.chat([], system="sys", tools=[])
    assert calls[0]["output_config"] == {"effort": "xhigh"}


def test_no_effort_omits_output_config(provider):
    calls = _wire_stream(provider, [_event("message_stop")], _final_message(text="ok"))
    provider.chat([], system="sys", tools=[])
    assert "output_config" not in calls[0]
