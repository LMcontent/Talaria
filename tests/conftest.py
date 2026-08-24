"""Shared fixtures for the test suite: a scriptable fake Provider that never
hits a real network/API, so tests exercise Talaria's own logic (agent loop,
history handling, skill gating, web endpoints) deterministically and fast.
"""

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

    def chat(self, history, system, tools, on_chunk=None):
        self.calls.append({"history": list(history), "system": system, "tools": tools})
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

    def chat(self, history, system, tools, on_chunk=None):
        raise self.exc
