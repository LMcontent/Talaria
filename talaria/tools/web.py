import requests
from bs4 import BeautifulSoup

from talaria.providers.base import ToolSpec
from talaria.user_agent import USER_AGENT

# A real Chrome UA (shared with talaria/tools/browser.py) plus the other
# headers a real browser sends on a plain page request — the previous
# "Talaria/0.1" UA announced this as a bot to any site that looks, which
# some block outright regardless of what else about the request looks
# fine. This doesn't help against sites that gate on more than headers
# (TLS/HTTP2 fingerprinting, a JS challenge) — see browser_open for that.
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
_TIMEOUT = 10
_MAX_CHARS = 6000
_GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def web_search(
    query: str,
    max_results: int = 5,
    google_api_key: str | None = None,
    google_cx: str | None = None,
) -> str:
    """Search the web. Uses Google's official Custom Search JSON API when
    both google_api_key and google_cx are configured (see
    make_web_tools/talaria/config.py) — generally richer, more reliable
    snippets than scraping, and a sanctioned API rather than a scrape.
    Falls back to DuckDuckGo's HTML endpoint otherwise (no key needed, but
    thinner snippets).

    Worth trying before giving up on a page that came back blocked/403
    (browser_open, web_fetch): a search engine has often already indexed
    the page's price/title/description, so the answer can show up in the
    result snippet directly, without needing to fetch the blocked page at
    all.
    """
    if google_api_key and google_cx:
        return _web_search_google(query, max_results, google_api_key, google_cx)
    return _web_search_duckduckgo(query, max_results)


def _web_search_google(query: str, max_results: int, api_key: str, cx: str) -> str:
    try:
        resp = requests.get(
            _GOOGLE_CSE_URL,
            params={"key": api_key, "cx": cx, "q": query, "num": max(1, min(max_results, 10))},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return f"Error: Google search failed ({e})"
    except ValueError as e:
        return f"Error: Google search returned an unreadable response ({e})"

    items = data.get("items") or []
    if not items:
        return "No results found."
    results = []
    for item in items[: max(1, min(max_results, 10))]:
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = " ".join((item.get("snippet") or "").split())
        results.append(f"- {title}\n  {link}\n  {snippet}")
    return "\n".join(results)


def _web_search_duckduckgo(query: str, max_results: int) -> str:
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error: web search failed ({e})"

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for link in soup.select("a.result__a")[: max(1, min(max_results, 10))]:
        title = link.get_text(strip=True)
        href = link.get("href", "")
        snippet_el = link.find_parent("div", class_="result__body")
        snippet = ""
        if snippet_el:
            snippet_tag = snippet_el.select_one(".result__snippet")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
        results.append(f"- {title}\n  {href}\n  {snippet}")

    if not results:
        return "No results found."
    return "\n".join(results)


def web_fetch(url: str) -> str:
    """Fetch a URL and return its main text content."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error: could not fetch {url} ({e})"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + f"... [truncated, {len(text)} chars total]"
    return text or "(page had no extractable text)"


def make_web_tools(google_search_api_key: str | None = None, google_search_cx: str | None = None) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="web_search",
            description=(
                "Search the internet and return a list of matching page titles, "
                "URLs and snippets. If a specific page came back blocked/403 or "
                "empty (browser_open, web_fetch), try this before giving up: "
                "search for the product/topic name (e.g. add 'цена'/'price') — "
                "a search engine has often already indexed the page, so the "
                "answer can show up directly in the result snippet without "
                "needing to fetch the blocked page at all."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
            handler=lambda query, max_results=5: web_search(
                query, max_results, google_search_api_key, google_search_cx
            ),
        ),
        ToolSpec(
            name="web_fetch",
            description="Fetch a web page by URL and return its extracted text content.",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to fetch."}},
                "required": ["url"],
            },
            handler=lambda url: web_fetch(url),
        ),
    ]
