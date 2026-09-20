"""Shared fixtures for the test suite: a scriptable fake Provider that never
hits a real network/API, so tests exercise Talaria's own logic (agent loop,
history handling, skill gating, web endpoints) deterministically and fast.
"""

import os
import threading

import pytest

from talaria.providers.base import Provider, ProviderResponse

# Some dev/CI sandboxes pre-install Chromium outside Playwright's own
# version-pinned registry (see talaria/tools/browser.py's
# PLAYWRIGHT_CHROMIUM_EXECUTABLE support) — point at it automatically here
# if present and nothing more specific was already set, so `pytest` for
# tests/test_browser.py works out of the box in such a sandbox without
# every dev needing to know this env var exists. A no-op on a normal
# machine that just ran `playwright install chromium` (no /opt/pw-browsers).
if "PLAYWRIGHT_CHROMIUM_EXECUTABLE" not in os.environ and os.path.exists("/opt/pw-browsers/chromium"):
    os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE"] = "/opt/pw-browsers/chromium"


class ScriptedProvider(Provider):
    """A Provider whose chat() replies pop off a pre-queued script, in
    order. Each entry is either a ProviderResponse or a callable taking
    (history, system, tools) and returning one. Records every call it
    received so tests can assert on what was sent to the "model".
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, history, system, tools, on_chunk=None, on_event=None, cancel_event=None):
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

    def chat(self, history, system, tools, on_chunk=None, on_event=None, cancel_event=None):
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

    def chat(self, history, system, tools, on_chunk=None, on_event=None, cancel_event=None):
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


@pytest.fixture(scope="session")
def sandbox_workspace(tmp_path_factory):
    """A real sandbox venv (talaria/sandbox.py), built once for the whole
    test run and shared by every test that needs one — creation takes a
    few real seconds, so this avoids paying that cost per test.
    """
    from talaria.sandbox import ensure_sandbox

    workspace = str(tmp_path_factory.mktemp("sandbox-workspace"))
    ensure_sandbox(workspace)
    return workspace
