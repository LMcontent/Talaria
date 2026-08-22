import requests
from bs4 import BeautifulSoup

from mini_hermes.providers.base import ToolSpec

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mini-hermes/0.1)"}
_TIMEOUT = 10
_MAX_CHARS = 6000


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo's HTML endpoint (no API key required)."""
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


WEB_TOOLS = [
    ToolSpec(
        name="web_search",
        description="Search the internet and return a list of matching page titles, URLs and snippets.",
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
        handler=lambda query, max_results=5: web_search(query, max_results),
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
