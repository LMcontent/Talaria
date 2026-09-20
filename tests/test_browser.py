import functools
import http.server
import os
import re
import threading

import pytest

from talaria.tools import browser as browser_mod
from talaria.tools.browser import (
    browser_back,
    browser_click,
    browser_open,
    browser_screenshot,
    browser_scroll,
    browser_state,
    browser_type,
    make_browser_tools,
)


@pytest.fixture
def site(tmp_path):
    """A tiny local HTTP server serving files written into the returned
    directory — real HTTP (not file://), so cookies/JS behave the same way
    they would against a real site, without any real network dependency.
    """
    directory = tmp_path / "site"
    directory.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}", directory
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _write(directory, name, html):
    (directory / name).write_text(html, encoding="utf-8")


_PAGE_ONE = """<!doctype html><html><body>
<h1>Hello World</h1>
<p>This is a test page for Talaria's browser tools.</p>
<a href="page2.html">Go to page two</a>
<button onclick="document.getElementById('out').innerText='clicked!'">Click me</button>
<div id="out"></div>
<input type="text" id="search" placeholder="Search box"
       oninput="document.getElementById('echo').innerText=this.value">
<div id="echo"></div>
</body></html>"""

_PAGE_TWO = """<!doctype html><html><body>
<h1>Page Two</h1>
<p>You arrived at page two.</p>
</body></html>"""

_SCROLL_PAGE = """<!doctype html><html><body style="height:3000px;">
<div id="content">Original content only.</div>
<script>
window.addEventListener('scroll', function() {
  if (window.scrollY > 400 && !window.__loaded) {
    window.__loaded = true;
    document.getElementById('content').innerText += ' MORE CONTENT APPEARED';
  }
});
</script>
</body></html>"""

_LOGIN_PAGE = """<!doctype html><html><body>
<script>document.cookie = "session=abc123; path=/;";</script>
<p>Logged in.</p>
</body></html>"""

_CHECK_LOGIN_PAGE = """<!doctype html><html><body>
<p id="cookie-status"></p>
<script>
document.getElementById('cookie-status').innerText =
  document.cookie.includes('session=abc123') ? 'LOGGED IN' : 'NOT LOGGED IN';
</script>
</body></html>"""


def _ref_for(snapshot: str, label: str) -> int:
    """Pulls the [index] out of a snapshot line whose element label
    contains `label`, the way a model would read it off the tool result."""
    for line in snapshot.splitlines():
        if label in line:
            m = re.match(r"\[(\d+)\]", line)
            if m:
                return int(m.group(1))
    raise AssertionError(f"no element labeled {label!r} in snapshot:\n{snapshot}")


def test_browser_open_returns_visible_text_and_elements(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)

    result = browser_open(str(tmp_path), f"{base}/index.html", True)

    assert "Hello World" in result
    assert "test page for Talaria" in result
    assert "Go to page two" in result
    assert "Click me" in result
    assert "Search box" in result


def test_browser_click_triggers_page_javascript(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    snapshot = browser_open(ws, f"{base}/index.html", True)
    ref = _ref_for(snapshot, "Click me")

    result = browser_click(ws, ref, True)

    assert "clicked!" in result


def test_browser_type_fills_input_and_page_reflects_it_live(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    snapshot = browser_open(ws, f"{base}/index.html", True)
    ref = _ref_for(snapshot, "Search box")

    result = browser_type(ws, ref, "hello world", False, True)

    assert "hello world" in result


def test_browser_click_navigates_and_browser_back_returns(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    _write(directory, "page2.html", _PAGE_TWO)
    ws = str(tmp_path)

    snapshot = browser_open(ws, f"{base}/index.html", True)
    ref = _ref_for(snapshot, "Go to page two")

    after_click = browser_click(ws, ref, True)
    assert "Page Two" in after_click
    assert "You arrived at page two" in after_click

    after_back = browser_back(ws, True)
    assert "Hello World" in after_back


def test_browser_scroll_reveals_lazily_loaded_content(site, tmp_path):
    base, directory = site
    _write(directory, "scroll.html", _SCROLL_PAGE)
    ws = str(tmp_path)

    initial = browser_open(ws, f"{base}/scroll.html", True)
    assert "Original content only" in initial
    assert "MORE CONTENT APPEARED" not in initial

    after_scroll = browser_scroll(ws, "down", True)
    assert "MORE CONTENT APPEARED" in after_scroll


def test_browser_state_reshows_current_page_without_navigating(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    result = browser_state(ws, True)

    assert "Hello World" in result


def test_browser_screenshot_saves_a_png_under_the_workspace(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    result = browser_screenshot(ws, True)

    assert "screenshots/" in result
    assert "![screenshot](screenshots/" in result

    files = list((tmp_path / "screenshots").glob("*.png"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0


def test_browser_click_rejects_an_out_of_range_ref(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    result = browser_click(ws, 999, True)

    assert "Error" in result
    assert "999" in result


def test_actions_before_any_open_report_a_clear_error(tmp_path):
    # Force the "nothing open yet" state regardless of what earlier tests
    # in this session left the module in — the module-level browser/page
    # are reused across tests (launching Chromium is expensive), but each
    # tool checks `_page is None` before touching anything else.
    browser_mod._page = None
    ws = str(tmp_path)

    assert "call browser_open" in browser_state(ws, True)
    assert "call browser_open" in browser_click(ws, 0, True)
    assert "call browser_open" in browser_type(ws, 0, "x", False, True)
    assert "call browser_open" in browser_scroll(ws, "down", True)
    assert "call browser_open" in browser_back(ws, True)
    assert "call browser_open" in browser_screenshot(ws, True)


def test_login_session_persists_across_a_simulated_restart(site, tmp_path):
    # The whole point of saving storage_state to disk: a session set up in
    # one process (or one call) is still there after everything in-memory
    # is torn down and rebuilt, the same way a human's browser stays
    # logged in after being closed and reopened.
    base, directory = site
    _write(directory, "login.html", _LOGIN_PAGE)
    _write(directory, "check.html", _CHECK_LOGIN_PAGE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/login.html", True)
    state_path = os.path.join(ws, ".browser_state.json")
    assert os.path.isfile(state_path)

    # Simulate a fresh process: tear down the in-memory context (but keep
    # the browser itself running, same as the real module would across
    # calls within one process — only the saved file matters here).
    browser_mod._context.close()
    browser_mod._context = None
    browser_mod._context_key = None
    browser_mod._page = None

    result = browser_open(ws, f"{base}/check.html", True)
    assert "LOGGED IN" in result
    assert "NOT LOGGED IN" not in result


def test_make_browser_tools_names(tmp_path):
    names = {t.name for t in make_browser_tools(str(tmp_path))}
    assert names == {
        "browser_open",
        "browser_click",
        "browser_type",
        "browser_scroll",
        "browser_back",
        "browser_state",
        "browser_screenshot",
    }
