# -*- coding: utf-8 -*-
"""Meaning cache v2: reuse expensive results (web searches, page parses).
Fuzzy lookup via token-Jaccard similarity with LIGHT RU/EN STEMMING + TTL.
v2 fix: Russian morphology defeated exact-token matching ('metallov' vs
'metally'), so tokens are now stemmed before comparison. ё is normalized."""
import re
from datetime import datetime, timedelta, timezone

from talaria.json_store import load_json, save_json
from talaria.providers.base import ToolSpec

_FILE = "cache.json"

_STOP = {"the", "a", "an", "of", "in", "on", "at", "for", "to",
         "i", "v", "na", "po", "dlya", "s", "pro", "kak", "chto"}

# Суффиксы для грубого стемминга (длинные первыми); режем один, оставляя >= 3 букв
_SUFFIXES = [
    "иями", "ями", "ами", "иях", "ях", "ов", "ев", "ей", "ой", "ый", "ий",
    "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ому", "ему", "ыми",
    "ими", "ую", "юю", "ом", "ем", "ах", "ях", "ость", "ости", "сти",
    "ния", "ние", "тия", "тие", "ок", "ек", "ик", "ам", "ям", "ть", "ся",
    "у", "ю", "а", "я", "о", "е", "и", "ы", "ь",
]


def _stem(w):
    w = str(w).replace("ё", "е")
    if len(w) <= 4:
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: len(w) - len(suf)]
    return w


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def _parse_iso(s):
    try:
        dt = datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _tokens(q):
    words = re.findall(r"[a-zа-яё0-9]+", str(q).lower())
    out = []
    for w in words:
        if w in _STOP:
            continue
        st = _stem(w)
        if st:
            out.append(st)
    return out


def _key_of(tokens):
    return " ".join(sorted(tokens))


def _jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _load():
    d = load_json(_FILE)
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        return {"entries": []}
    return d


def _save(db):
    save_json(_FILE, db)


def cache_put(query: str = "", value: str = "", ttl_hours: str = "24") -> str:
    """Cache an expensive result under a query (re-caching same query overwrites)."""
    q = str(query).strip()
    v = str(value).strip()
    if not q or not v:
        return "Error: 'query' and 'value' are required."
    try:
        ttl = float(str(ttl_hours).strip() or 24)
        if ttl <= 0:
            raise ValueError
    except ValueError:
        return "Error: ttl_hours must be a positive number."

    toks = _tokens(q)
    if not toks:
        return "Error: query has no usable tokens."
    db = _load()
    now = _now()
    key = _key_of(toks)
    db["entries"] = [e for e in db["entries"] if e.get("key") != key]
    db["entries"].append({
        "key": key,
        "query": q,
        "tokens": toks,
        "value": v,
        "created": _iso(now),
        "expires": _iso(now + timedelta(hours=ttl)),
        "hits": 0,
    })
    db["entries"] = sorted(db["entries"], key=lambda e: e.get("created", ""))[-100:]
    _save(db)
    return "Cached '{}' (stems: {}) TTL {}h until {} UTC. Entries: {}".format(
        q, ",".join(toks), int(ttl),
        _iso(now + timedelta(hours=ttl))[:16].replace("T", " "), len(db["entries"]))


def cache_get(query: str = "", min_score: str = "0.55") -> str:
    """Fuzzy-lookup the cache: best stemmed-similarity match that is still fresh."""
    qt = _tokens(query)
    if not qt:
        return "Error: empty query."
    try:
        thr = float(str(min_score).strip() or 0.55)
    except ValueError:
        thr = 0.55

    db = _load()
    now = _now()
    best, best_score = None, 0.0
    alive = []
    changed = False
    for e in db["entries"]:
        exp = _parse_iso(e.get("expires"))
        if exp is not None and exp <= now:
            changed = True
            continue
        alive.append(e)
        sc = _jaccard(qt, e.get("tokens", []))
        if sc > best_score:
            best, best_score = e, sc
    if changed:
        db["entries"] = alive
        _save(db)

    if best is None or best_score < thr:
        return "CACHE MISS (best score {}; query stems: {}).".format(
            round(best_score, 2), ",".join(qt))

    best["hits"] = int(best.get("hits", 0)) + 1
    _save(db)
    created = _parse_iso(best.get("created"))
    age_h = max(0.0, (now - created).total_seconds() / 3600.0) if created else -1
    head = "CACHE HIT (similarity {:.2f}, cached {}h ago, original query: '{}')".format(
        best_score, round(age_h, 1), best.get("query", ""))
    body = str(best.get("value", ""))
    if len(body) > 2000:
        body = body[:2000] + "...[truncated]"
    return head + "\n" + body


def cache_list(key: str = "") -> str:
    """List cached entries with age, expiry and hit counts."""
    db = _load()
    now = _now()
    if not db["entries"]:
        return "(cache is empty)"
    lines = []
    for e in db["entries"]:
        exp = _parse_iso(e.get("expires"))
        left = "expired" if (exp and exp <= now) else "fresh"
        cr = _parse_iso(e.get("created"))
        age = ", age {}h".format(round((now - cr).total_seconds() / 3600, 1)) if cr else ""
        lines.append("- '{}' [{}]{} hits={} val={} chars".format(
            e.get("query", "?"), left, age, e.get("hits", 0), len(str(e.get("value", "")))))
    return "\n".join(lines)


def cache_clear(mode: str = "expired") -> str:
    """Clear cache: mode='expired' drops stale entries only, 'all' empties it."""
    db = _load()
    m = str(mode).strip().lower()
    if m == "all":
        n = len(db["entries"])
        db["entries"] = []
        _save(db)
        return "Cleared all ({} entries).".format(n)
    now = _now()
    kept, dropped = [], 0
    for e in db["entries"]:
        exp = _parse_iso(e.get("expires"))
        if exp is not None and exp <= now:
            dropped += 1
        else:
            kept.append(e)
    db["entries"] = kept
    _save(db)
    return "Dropped {} expired entries, kept {} fresh.".format(dropped, len(kept))


TOOLS = [
    ToolSpec(name="cache_put",
             description="Cache an expensive result (search, parsed page, computation) under a query with TTL hours.",
             input_schema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "The request this answer belongs to."},
                 "value": {"type": "string", "description": "Result to cache."},
                 "ttl_hours": {"type": "string", "description": "Freshness window in hours (default 24)."}},
                 "required": ["query", "value"]},
             handler=cache_put),
    ToolSpec(name="cache_get",
             description="Fuzzy-lookup the meaning cache: returns freshest similar result or CACHE MISS.",
             input_schema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Lookup request (fuzzy matched)."},
                 "min_score": {"type": "string", "description": "Similarity threshold 0..1 (default 0.55)."}},
                 "required": ["query"]},
             handler=cache_get),
    ToolSpec(name="cache_list",
             description="List cached entries with freshness, age and hit counts.",
             input_schema={"type": "object", "properties": {}},
             handler=cache_list),
    ToolSpec(name="cache_clear",
             description="Clear cache: 'expired' drops stale entries, 'all' empties the cache.",
             input_schema={"type": "object", "properties": {
                 "mode": {"type": "string", "description": "'expired' (default) or 'all'."}}},
             handler=cache_clear),
]
