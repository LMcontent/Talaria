"""A real, persistent browser session (Playwright/Chromium) the agent can
navigate, click, and type into — not just a one-shot page fetch. The point
is to close the gap between "sites web_fetch can read" and "sites a human
can actually use": JS-rendered pages, multi-step flows (search box ->
results -> article), and anything gated behind a login.

Login persistence is the key piece: cookies/localStorage are saved to
`WORKSPACE_DIR/.browser_state.json` after every action and reloaded the
next time a page opens for that same workspace — including across process
restarts. Combined with `BROWSER_HEADLESS=false` (see talaria/config.py),
a human can log into a site once in a real, visible browser window (typing
a password, clicking through 2FA, solving a CAPTCHA — none of which the
agent can do itself) and the agent's session then stays logged in for
every future automated visit, the same way a human's own browser would.
Requires `playwright install chromium` to have been run once.

Not a bypass for strong anti-bot protection or CAPTCHAs the agent hits on
its own — those still need a human, via the mechanism above.

Elements are exposed to the model as a numbered list (a "set of marks"),
since the model doesn't see pixels — browser_click/browser_type act on an
element by the index shown in the most recent snapshot (from browser_open,
browser_state, or the snapshot any of these tools returns after acting).
The list is rebuilt after every action, so indices can change between
calls — always act on the index from the *latest* snapshot, not a
remembered one from several actions ago.

Some pages never put the data you actually want (price, stock, rating...)
into the rendered text at all — a storefront's price often only exists in
a JSON response its JavaScript fetched from an internal API, not in the
page's own HTML/DOM. browser_network_log is the DevTools-Network-tab
equivalent for that: every XHR/fetch call the page made since the last
browser_open, with a preview of JSON/text response bodies, so the model
can spot the actual pricing endpoint and call it directly (via web_fetch
or run_python) instead of trying to scrape it out of rendered text.
"""

import atexit
import os
import time

from talaria.providers.base import ToolSpec

_MAX_TEXT_CHARS = 3000
_MAX_ELEMENTS = 40
_MAX_RAW_HANDLES = 300
_NAV_TIMEOUT_MS = 30000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_INTERACTIVE_SELECTOR = (
    "a[href], button, input, textarea, select, [role=button], [role=link], [onclick]"
)
_NETWORK_RESOURCE_TYPES = ("xhr", "fetch")
_MAX_NETWORK_ENTRIES = 200
_MAX_BODY_PREVIEW = 800

_playwright = None
_browser = None
_browser_headless = None
_context = None
_page = None
_context_key = None  # (workspace_dir, headless) the current _context was built for
_elements: list = []
_network_log: list = []


def _state_path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".browser_state.json")


def _ensure_page(workspace_dir: str, headless: bool):
    global _playwright, _browser, _browser_headless, _context, _page, _context_key, _elements

    from playwright.sync_api import sync_playwright

    if _playwright is None:
        _playwright = sync_playwright().start()

    if _browser is None or _browser_headless != headless:
        if _browser is not None:
            _browser.close()
        launch_kwargs = {"headless": headless, "args": ["--disable-blink-features=AutomationControlled"]}
        # A pre-installed Chromium (e.g. this repo's own dev sandbox) may
        # live outside Playwright's own version-pinned browsers.json
        # registry — PLAYWRIGHT_CHROMIUM_EXECUTABLE lets that be pointed at
        # explicitly instead of failing to resolve one automatically.
        executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        # requests (web_fetch/web_search) honors HTTPS_PROXY/HTTP_PROXY
        # automatically; Playwright's browser does not unless told to —
        # without this, a network that needs a proxy for plain HTTP would
        # silently work for web_fetch but fail for every browser_* tool.
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") \
            or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if proxy_url:
            no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
            proxy_config = {"server": proxy_url}
            if no_proxy:
                proxy_config["bypass"] = no_proxy
            launch_kwargs["proxy"] = proxy_config
        _browser = _playwright.chromium.launch(**launch_kwargs)
        _browser_headless = headless
        _context = None  # force a fresh context under the new browser

    key = (os.path.abspath(workspace_dir), headless)
    if _context is None or _context_key != key:
        if _context is not None:
            _context.close()
        state_path = _state_path(workspace_dir)
        storage_state = state_path if os.path.isfile(state_path) else None
        _context = _browser.new_context(
            user_agent=_USER_AGENT,
            storage_state=storage_state,
            viewport={"width": 1280, "height": 900},
        )
        _page = _context.new_page()
        _page.on("response", _on_response)
        _context_key = key
        _elements = []
    return _page


def _on_response(response) -> None:
    """Records every XHR/fetch response the page makes, so
    browser_network_log can show the model what API calls actually
    happened — including ones whose data never makes it into the rendered
    page text. Registered once per page (see _ensure_page); best-effort —
    any failure here must never break navigation itself."""
    try:
        request = response.request
        if request.resource_type not in _NETWORK_RESOURCE_TYPES:
            return
        content_type = ""
        try:
            content_type = response.headers.get("content-type", "")
        except Exception:
            pass
        entry = {
            "method": request.method,
            "url": response.url,
            "status": response.status,
            "content_type": content_type,
        }
        if "json" in content_type or "text" in content_type:
            try:
                body = response.text()
                if len(body) > _MAX_BODY_PREVIEW:
                    body = body[:_MAX_BODY_PREVIEW] + f"... [truncated, {len(body)} chars total]"
                entry["body_preview"] = body
            except Exception:
                pass
        _network_log.append(entry)
        if len(_network_log) > _MAX_NETWORK_ENTRIES:
            del _network_log[: len(_network_log) - _MAX_NETWORK_ENTRIES]
    except Exception:
        pass


def _save_state(workspace_dir: str) -> None:
    if _context is not None:
        try:
            os.makedirs(workspace_dir, exist_ok=True)
            _context.storage_state(path=_state_path(workspace_dir))
        except Exception:
            pass  # best-effort — a failed save just means the next open re-logs in


def _cleanup() -> None:
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
    if _browser is not None:
        _browser.close()
    if _playwright is not None:
        _playwright.stop()


atexit.register(_cleanup)


def _element_label(handle) -> str:
    for attr in ("aria-label", "placeholder", "alt", "title"):
        try:
            val = handle.get_attribute(attr)
        except Exception:
            val = None
        if val and val.strip():
            return val.strip()
    try:
        text = handle.inner_text().strip()
    except Exception:
        text = ""
    if text:
        return text
    try:
        value = handle.evaluate("el => el.value || ''")
    except Exception:
        value = ""
    return (value or "").strip()


def _snapshot(page) -> tuple[str, list]:
    """Builds the numbered element list + visible text the model sees
    after every navigation/action. Returns (summary_text, element_handles)
    — element_handles becomes the module's `_elements`, indexed the same
    way the summary text shows them."""
    try:
        handles = page.query_selector_all(_INTERACTIVE_SELECTOR)
    except Exception:
        handles = []

    elements: list = []
    lines: list[str] = []
    for handle in handles[:_MAX_RAW_HANDLES]:
        try:
            if not handle.is_visible():
                continue
        except Exception:
            continue
        try:
            tag = handle.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            continue
        try:
            el_type = handle.get_attribute("type") or ""
        except Exception:
            el_type = ""
        label = " ".join(_element_label(handle).split())[:80]
        # An unlabeled link/button is useless to act on and just noise —
        # but an unlabeled input/textarea/select is still a real field
        # worth showing (it may only have a visual placeholder image, or
        # be labeled by a separate <label> element we didn't look for).
        if not label and tag not in ("input", "textarea", "select"):
            continue
        idx = len(elements)
        elements.append(handle)
        kind = f"{tag}[{el_type}]" if el_type else tag
        lines.append(f"[{idx}] {kind} {label!r}" if label else f"[{idx}] {kind}")
        if len(elements) >= _MAX_ELEMENTS:
            break

    try:
        body_text = page.inner_text("body")
    except Exception:
        body_text = ""
    body_text = " ".join(body_text.split())
    if len(body_text) > _MAX_TEXT_CHARS:
        body_text = body_text[:_MAX_TEXT_CHARS] + f"... [truncated, {len(body_text)} chars total]"

    more_note = ""
    if len(handles) > len(elements) and len(elements) >= _MAX_ELEMENTS:
        more_note = (
            f"\n... ({len(handles) - len(elements)}+ more interactive elements not "
            "shown — scroll, or narrow down what you're looking for)"
        )

    try:
        url, title = page.url, page.title()
    except Exception:
        url, title = "", ""

    summary = (
        f"URL: {url}\nTitle: {title}\n\n"
        f"Visible text:\n{body_text or '(no visible text)'}\n\n"
        "Interactive elements (act on one with its [index] via browser_click/browser_type):\n"
        + ("\n".join(lines) if lines else "(none found)")
        + more_note
    )
    return summary, elements


def _no_page_open() -> str:
    return "Error: no page open yet — call browser_open(url) first."


def browser_open(workspace_dir: str, url: str, headless: bool, wait_ms: int = 1000) -> str:
    global _elements, _network_log
    try:
        page = _ensure_page(workspace_dir, headless)
    except Exception as e:
        return (
            f"Error: could not start the browser ({e}). "
            "Run 'playwright install chromium' once and try again."
        )
    # Reset here, not on every click/type/scroll — so the log covers
    # everything from this open through whatever actions follow it, until
    # the next browser_open starts a new page.
    _network_log = []
    try:
        page.goto(url, timeout=_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(max(0, wait_ms))
    except Exception as e:
        return f"Error: browser_open failed for {url} ({e})"
    summary, _elements = _snapshot(page)
    _save_state(workspace_dir)
    return summary


def browser_state(workspace_dir: str, headless: bool) -> str:
    global _elements
    if _page is None:
        return _no_page_open()
    page = _ensure_page(workspace_dir, headless)
    summary, _elements = _snapshot(page)
    return summary


def browser_click(workspace_dir: str, ref, headless: bool) -> str:
    global _elements
    if _page is None:
        return _no_page_open()
    try:
        ref = int(ref)
    except (TypeError, ValueError):
        return "Error: ref must be the integer index of an element from the last snapshot."
    page = _ensure_page(workspace_dir, headless)
    if ref < 0 or ref >= len(_elements):
        return f"Error: no element [{ref}] in the current snapshot — call browser_state to refresh it."
    handle = _elements[ref]
    try:
        handle.click(timeout=5000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(400)
    except Exception as e:
        return f"Error: click on [{ref}] failed ({e})"
    summary, _elements = _snapshot(page)
    _save_state(workspace_dir)
    return summary


def browser_type(workspace_dir: str, ref, text: str, submit: bool, headless: bool) -> str:
    global _elements
    if _page is None:
        return _no_page_open()
    try:
        ref = int(ref)
    except (TypeError, ValueError):
        return "Error: ref must be the integer index of an element from the last snapshot."
    page = _ensure_page(workspace_dir, headless)
    if ref < 0 or ref >= len(_elements):
        return f"Error: no element [{ref}] in the current snapshot — call browser_state to refresh it."
    handle = _elements[ref]
    try:
        tag = handle.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            handle.select_option(label=text)
        else:
            handle.fill(text)
            if submit:
                handle.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(300)
    except Exception as e:
        return f"Error: typing into [{ref}] failed ({e})"
    summary, _elements = _snapshot(page)
    _save_state(workspace_dir)
    return summary


def browser_scroll(workspace_dir: str, direction: str, headless: bool) -> str:
    global _elements
    if _page is None:
        return _no_page_open()
    page = _ensure_page(workspace_dir, headless)
    delta = -800 if str(direction).strip().lower() == "up" else 800
    try:
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(400)
    except Exception as e:
        return f"Error: scroll failed ({e})"
    summary, _elements = _snapshot(page)
    return summary


def browser_back(workspace_dir: str, headless: bool) -> str:
    global _elements
    if _page is None:
        return _no_page_open()
    page = _ensure_page(workspace_dir, headless)
    try:
        page.go_back(timeout=10000)
        page.wait_for_timeout(300)
    except Exception as e:
        return f"Error: back navigation failed ({e})"
    summary, _elements = _snapshot(page)
    return summary


def browser_screenshot(workspace_dir: str, headless: bool) -> str:
    if _page is None:
        return _no_page_open()
    page = _ensure_page(workspace_dir, headless)
    screenshots_dir = os.path.join(workspace_dir, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    filename = f"browser_{int(time.time() * 1000)}.png"
    path = os.path.join(screenshots_dir, filename)
    try:
        page.screenshot(path=path)
    except Exception as e:
        return f"Error: screenshot failed ({e})"
    rel = f"screenshots/{filename}"
    return (
        f"Saved a screenshot of the current page to {rel}. "
        f"Reference it in your reply as ![screenshot]({rel}) to show it inline in the web UI."
    )


def browser_network_log(workspace_dir: str, headless: bool, contains: str = "") -> str:
    if _page is None:
        return _no_page_open()
    _ensure_page(workspace_dir, headless)  # no-op if already current; keeps state consistent
    needle = str(contains).strip().lower()
    entries = _network_log
    if needle:
        entries = [
            e for e in entries
            if needle in e["url"].lower() or needle in e.get("body_preview", "").lower()
        ]
    if not entries:
        return (
            "(no matching XHR/fetch calls captured since the last browser_open)"
            if needle else
            "(no XHR/fetch calls captured since the last browser_open — the page may load its "
            "data server-side, or you may need to browser_click/browser_scroll to trigger it)"
        )

    lines = []
    for e in entries:
        lines.append(f"[{e['method']} {e['status']}] {e['url']}")
        if e.get("content_type"):
            lines.append(f"  content-type: {e['content_type']}")
        if e.get("body_preview"):
            lines.append(f"  body: {e['body_preview']}")
    text = "\n".join(lines)
    if len(text) > _MAX_TEXT_CHARS * 2:
        text = text[: _MAX_TEXT_CHARS * 2] + f"... [truncated, {len(text)} chars total — narrow with `contains`]"
    return text


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y", "on")


def make_browser_tools(workspace_dir: str, headless: bool = True) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="browser_open",
            description=(
                "Open a URL in a real browser session that renders JavaScript and "
                "keeps cookies/login between calls (and across restarts) — use this "
                "for JS-heavy pages web_fetch can't render, or any site you're "
                "logged into. Returns the page's visible text plus a numbered list "
                "of clickable/fillable elements to act on next with browser_click "
                "or browser_type."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open."},
                    "wait_ms": {
                        "type": "integer",
                        "description": "Extra milliseconds to wait after navigation for JS content to load (default 1000).",
                    },
                },
                "required": ["url"],
            },
            handler=lambda url, wait_ms=1000: browser_open(workspace_dir, url, headless, wait_ms),
        ),
        ToolSpec(
            name="browser_click",
            description=(
                "Click an element on the currently open page, by the [index] shown "
                "in the most recent browser_open/browser_state/browser_* result. "
                "Returns an updated snapshot afterwards (indices can change — always "
                "use the index from the latest one)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Element index from the latest snapshot."}
                },
                "required": ["ref"],
            },
            handler=lambda ref: browser_click(workspace_dir, ref, headless),
        ),
        ToolSpec(
            name="browser_type",
            description=(
                "Type text into an input/textarea/select on the currently open "
                "page, by [index] from the latest snapshot. Set submit=true to "
                "press Enter afterwards (e.g. to submit a search box)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Element index from the latest snapshot."},
                    "text": {"type": "string", "description": "Text to type (or option label, for a <select>)."},
                    "submit": {
                        "type": "string",
                        "description": "'true' to press Enter after typing (default 'false').",
                    },
                },
                "required": ["ref", "text"],
            },
            handler=lambda ref, text, submit="false": browser_type(
                workspace_dir, ref, text, _truthy(submit), headless
            ),
        ),
        ToolSpec(
            name="browser_scroll",
            description=(
                "Scroll the currently open page up or down — needed for content "
                "that only loads once scrolled into view (infinite scroll, lazy-"
                "loaded images) and to reach elements further down a long page."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'down' (default) or 'up'."}
                },
                "required": [],
            },
            handler=lambda direction="down": browser_scroll(workspace_dir, direction, headless),
        ),
        ToolSpec(
            name="browser_back",
            description="Go back to the previous page in the browser session's history.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: browser_back(workspace_dir, headless),
        ),
        ToolSpec(
            name="browser_state",
            description=(
                "Re-show the current page's visible text and numbered element list "
                "without navigating — use this to recover the current snapshot "
                "(e.g. after losing track of it) instead of guessing indices."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: browser_state(workspace_dir, headless),
        ),
        ToolSpec(
            name="browser_screenshot",
            description=(
                "Save a screenshot of the currently open page to the workspace and "
                "get back the image markdown to show it in the web UI — useful when "
                "the text/element snapshot isn't enough to tell what's on screen "
                "(layout, a chart, a CAPTCHA, canvas content)."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: browser_screenshot(workspace_dir, headless),
        ),
        ToolSpec(
            name="browser_network_log",
            description=(
                "List the XHR/fetch API calls the current page made (since the last "
                "browser_open), with a preview of JSON/text response bodies — the "
                "DevTools Network tab equivalent. Use this when data you need (price, "
                "stock, rating...) doesn't show up in browser_open's visible text: "
                "many sites load it from a separate API call rather than putting it "
                "in the page's own HTML. Once you spot the right URL here, call it "
                "directly with web_fetch (or run_python, if it needs a POST/headers) "
                "instead of re-rendering the whole page every time you need it again. "
                "Optionally filter with `contains` (matched against the URL and body)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "contains": {
                        "type": "string",
                        "description": "Optional substring to filter by (e.g. 'price', 'api/product').",
                    }
                },
                "required": [],
            },
            handler=lambda contains="": browser_network_log(workspace_dir, headless, contains),
        ),
    ]
