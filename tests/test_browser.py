import functools
import http.server
import mimetypes
import os
import re
import threading

import pytest

# Some platforms don't map .json -> application/json by default in
# mimetypes, which the network-log tests rely on to prove the captured
# response really was JSON (matching a real API's Content-Type header).
mimetypes.add_type("application/json", ".json")

from talaria.tools import browser as browser_mod
from talaria.tools.browser import (
    browser_back,
    browser_click,
    browser_network_log,
    browser_open,
    browser_reset,
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

# Simulates the real-world case this tool exists for: a storefront whose
# price is never in the page's own HTML at all, only in a JSON response
# its JavaScript fetches from an internal API afterwards.
_PRICE_PAGE = """<!doctype html><html><body>
<h1>Product X</h1>
<div id="price">Loading price...</div>
<script>
fetch('/api/price.json').then(r => r.json()).then(function(data) {
  document.getElementById('price').innerText = 'Price: ' + data.price + ' RUB';
});
</script>
</body></html>"""

_FINGERPRINT_PAGE = """<!doctype html><html><body>
<div id="fingerprint"></div>
<script>
document.getElementById('fingerprint').innerText =
  'webdriver=' + navigator.webdriver +
  ' lang=' + navigator.language +
  ' tz=' + Intl.DateTimeFormat().resolvedOptions().timeZone;
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


def test_browser_open_normalizes_the_automation_fingerprint(site, tmp_path):
    # navigator.webdriver should read as undefined (not true, which is
    # Chromium's default under automation control) and locale/timezone
    # should match BROWSER_LOCALE/BROWSER_TIMEZONE (default ru-RU/
    # Europe/Moscow) rather than Chromium's own en-US/UTC default —
    # neither defeats real bot-detection, but a blank/automated-looking
    # fingerprint is itself a tell that's cheap to not have.
    base, directory = site
    _write(directory, "fingerprint.html", _FINGERPRINT_PAGE)

    result = browser_open(str(tmp_path), f"{base}/fingerprint.html", True)

    assert "webdriver=undefined" in result
    assert "lang=ru-RU" in result
    assert "tz=Europe/Moscow" in result


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


def test_browser_reset_clears_state_and_next_open_still_works(site, tmp_path):
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    assert browser_mod._page is not None

    result = browser_reset()

    assert "reset" in result.lower()
    assert browser_mod._page is None
    assert browser_mod._browser is None
    assert browser_mod._context is None

    reopened = browser_open(ws, f"{base}/index.html", True)
    assert "Hello World" in reopened


def test_browser_open_recovers_from_a_crashed_browser_process(site, tmp_path):
    # The scenario this whole mechanism exists for: Chromium dies
    # underneath the module (killed for memory, crashed) between two
    # calls — the next browser_open must self-heal instead of failing
    # forever until the whole Talaria process restarts.
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    browser_mod._browser.close()
    assert not browser_mod._browser.is_connected()

    result = browser_open(ws, f"{base}/index.html", True)
    assert "Hello World" in result


def test_browser_open_recovers_from_a_closed_page(site, tmp_path):
    # A narrower case than a whole crashed browser: just this page closed
    # (e.g. the site's own JS called window.close()) while the browser
    # process itself is still fine.
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/index.html", True)
    browser_mod._page.close()
    assert browser_mod._page.is_closed()

    result = browser_open(ws, f"{base}/index.html", True)
    assert "Hello World" in result


def test_browser_open_retries_once_after_a_connection_error_mid_navigation(site, tmp_path, monkeypatch):
    # Different from the two tests above: here the crash happens *during*
    # the call itself (page.goto raises), which _ensure_page's liveness
    # check at the top of the *next* call can't have caught yet — this is
    # what browser_open's own one-shot retry covers.
    base, directory = site
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    real_ensure_page = browser_mod._ensure_page
    calls = {"n": 0}

    class FakePage:
        def goto(self, *a, **k):
            raise Exception("Target page, context or browser has been closed")

    def fake_ensure_page(workspace_dir, headless):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakePage()
        return real_ensure_page(workspace_dir, headless)

    monkeypatch.setattr(browser_mod, "_ensure_page", fake_ensure_page)

    result = browser_open(ws, f"{base}/index.html", True)

    assert calls["n"] == 2
    assert "Hello World" in result


def test_browser_network_log_captures_the_api_call_behind_async_data(site, tmp_path):
    # The real-world motivating case: a price that only exists in a JSON
    # API response, never in the page's own rendered text.
    base, directory = site
    api_dir = directory / "api"
    api_dir.mkdir()
    (api_dir / "price.json").write_text('{"price": 12990, "currency": "RUB"}', encoding="utf-8")
    _write(directory, "product.html", _PRICE_PAGE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/product.html", True)
    log = browser_network_log(ws, True)

    assert "api/price.json" in log
    assert "12990" in log
    assert "application/json" in log


def test_browser_network_log_contains_filter_narrows_results(site, tmp_path):
    base, directory = site
    api_dir = directory / "api"
    api_dir.mkdir()
    (api_dir / "price.json").write_text('{"price": 12990}', encoding="utf-8")
    _write(directory, "product.html", _PRICE_PAGE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/product.html", True)

    assert "price.json" in browser_network_log(ws, True, "price")
    assert "no matching" in browser_network_log(ws, True, "does-not-exist")


def test_browser_network_log_resets_on_each_new_open(site, tmp_path):
    base, directory = site
    api_dir = directory / "api"
    api_dir.mkdir()
    (api_dir / "price.json").write_text('{"price": 12990}', encoding="utf-8")
    _write(directory, "product.html", _PRICE_PAGE)
    _write(directory, "index.html", _PAGE_ONE)
    ws = str(tmp_path)

    browser_open(ws, f"{base}/product.html", True)
    assert "price.json" in browser_network_log(ws, True)

    # A plain page with no fetch/XHR calls — the previous page's captured
    # traffic must not still be sitting in the log.
    browser_open(ws, f"{base}/index.html", True)
    assert "price.json" not in browser_network_log(ws, True)


def test_browser_network_log_before_any_open_reports_a_clear_error(tmp_path):
    browser_mod._page = None
    assert "call browser_open" in browser_network_log(str(tmp_path), True)


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
        "browser_network_log",
        "browser_reset",
    }
