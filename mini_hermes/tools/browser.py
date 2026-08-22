"""A real headless browser tool (Playwright) for JS-heavy pages that
web_fetch (raw HTTP) can't render. Requires `playwright install chromium`
to have been run once. Not a bypass for strong anti-bot protection —
some sites will still block or serve a challenge page to a headless
browser.
"""

import atexit

from mini_hermes.providers.base import ToolSpec

_MAX_CHARS = 6000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_playwright = None
_browser = None


def _get_browser():
    global _playwright, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright

        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
    return _browser


def _cleanup():
    if _browser is not None:
        _browser.close()
    if _playwright is not None:
        _playwright.stop()


atexit.register(_cleanup)


def browser_fetch(url: str, wait_ms: int = 2000) -> str:
    """Open a URL in a real headless browser (renders JavaScript) and
    return the visible page text."""
    try:
        browser = _get_browser()
    except Exception as e:
        return (
            f"Error: could not start the browser ({e}). "
            "Run 'playwright install chromium' once and try again."
        )

    try:
        page = browser.new_page(user_agent=_USER_AGENT)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(max(0, wait_ms))
            text = page.inner_text("body")
        finally:
            page.close()
    except Exception as e:
        return f"Error: browser_fetch failed for {url} ({e})"

    text = " ".join(text.split())
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + f"... [truncated, {len(text)} chars total]"
    return text or "(page had no visible text)"


BROWSER_TOOLS = [
    ToolSpec(
        name="browser_fetch",
        description=(
            "Open a URL in a real headless browser that executes JavaScript, "
            "unlike web_fetch which only downloads raw HTML. Use this when "
            "web_fetch returns empty/garbled content on a JS-heavy site. "
            "Slower than web_fetch, and strong anti-bot protection may still "
            "block it — it is not a guaranteed bypass."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to open."},
                "wait_ms": {
                    "type": "integer",
                    "description": "Extra milliseconds to wait after navigation for JS content to load (default 2000).",
                },
            },
            "required": ["url"],
        },
        handler=lambda url, wait_ms=2000: browser_fetch(url, wait_ms),
    ),
]
