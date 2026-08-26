# -*- coding: utf-8 -*-
"""Query Wolfram Alpha for computational/factual answers.

Requires a free Wolfram Alpha "AppID" (get one at
https://products.wolframalpha.com/api) set as WOLFRAM_APPID in .env. This
is a separate quota from Talaria's own LLM provider — not covered by
MAX_SESSION_TOKENS or the Usage sidebar/CLI command.
"""
import json
import os
import urllib.parse
import urllib.request

from talaria.providers.base import ToolSpec

_API_URL = "https://api.wolframalpha.com/v2/query"


def wolfram_query(query: str = "") -> str:
    """Query Wolfram Alpha and return a readable plain-text answer."""
    appid = os.environ.get("WOLFRAM_APPID", "").strip()
    if not appid:
        return (
            "Error: WOLFRAM_APPID is not set in .env. Get a free AppID at "
            "https://products.wolframalpha.com/api and add it to .env."
        )

    q = str(query).strip()
    if not q:
        return "Error: empty query"

    url = _API_URL + "?" + urllib.parse.urlencode(
        {"appid": appid, "input": q, "output": "JSON"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("queryresult", {})
    except Exception as e:
        return f"Error: request failed ({type(e).__name__}: {e})"

    if not data.get("success"):
        err = data.get("error") or {}
        if err.get("msg"):
            return f"Wolfram error: {err['msg']}"
        if data.get("recalculate") is False:
            return "No result: AppID quota may be exceeded."
        return "No result: Wolfram could not interpret the query."

    lines = []
    skip_titles = {"number name", "input interpretation"}
    for pod in data.get("pods", []):
        title = pod.get("title", "")
        if title.lower() in skip_titles:
            continue
        texts = []
        for sub in pod.get("subpods", []):
            pt = (sub.get("plaintext") or "").strip()
            if pt:
                texts.append(pt)
        if texts:
            lines.append(f"{title}: {' | '.join(texts)}")
        if len(lines) >= 6:
            break

    if not lines:
        return "Wolfram returned no text pods (result may be graphical only)."
    return "\n".join(lines)[:4000]


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="wolfram_query",
        description="Ask Wolfram Alpha a computational or factual question (math, units, physics, chemistry, dates, conversions) and get a plain-text answer. Examples: 'integrate x^2 dx', 'distance from Earth to Mars', '30 USD to EUR'.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language or mathematical query for Wolfram Alpha.",
                }
            },
            "required": ["query"],
        },
        handler=wolfram_query,
    )
]
