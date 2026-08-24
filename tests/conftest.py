"""Shared fixtures for the test suite: a scriptable fake Provider that never
hits a real network/API, so tests exercise Talaria's own logic (agent loop,
history handling, skill gating, web endpoints) deterministically and fast.
"""

import threading

from talaria.providers.base import Provider, ProviderResponse


class ScriptedProvider(Provider):
    """A Provider whose chat() replies pop off a pre-queued script, in
    order. Each entry is either a ProviderResponse or a callable taking
    (history, system, tools) and returning one. Records every call it
    received so tests can assert on what was sent to the "model".
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, history, system, tools, on_chunk=None, cancel_event=None):
        self.calls.append(
            {
                "history": list(history),
                "system": system,
                "tools": tools,
                "cancel_event": cancel_event,
            }
        )
        if not self._responses:
            raise AssertionError("ScriptedProvider ran out of scripted responses")
        resp = self._responses.pop(0)
        if callable(resp) and not isinstance(resp, ProviderResponse):
            resp = resp(history, system, tools)
        if on_chunk and resp.text:
            on_chunk(resp.text)
        return resp


class RaisingProvider(Provider):
    """A Provider whose chat() always raises — for testing failure paths
    like the security-review call itself failing.
    """

    def __init__(self, exc: Exception):
        self.exc = exc

    def chat(self, history, system, tools, on_chunk=None, cancel_event=None):
        raise self.exc


class InterruptibleProvider(Provider):
    """Streams `chunks` one at a time, pausing after the first one until a
    test releases it — giving a test a deterministic window to trigger
    cancellation (e.g. via the web UI's stop endpoint) and observe that the
    provider actually stops mid-stream, the same way a real provider's
    streaming loop checks cancel_event between chunks.
    """

    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.first_chunk_sent = threading.Event()
        self.may_continue = threading.Event()

    def chat(self, history, system, tools, on_chunk=None, cancel_event=None):
        text_parts: list[str] = []
        for i, chunk in enumerate(self.chunks):
            if cancel_event and cancel_event.is_set():
                return ProviderResponse(text="".join(text_parts), tool_calls=[], cancelled=True)
            text_parts.append(chunk)
            if on_chunk:
                on_chunk(chunk)
            if i == 0:
                self.first_chunk_sent.set()
                self.may_continue.wait(timeout=5)
        return ProviderResponse(text="".join(text_parts), tool_calls=[])
