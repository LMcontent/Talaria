# -*- coding: utf-8 -*-
"""Error book: signature -> working solution, indexed over BOTH fields.

Promoted from skills/errbook.py into core so every Talaria deployment gets
this learning tool out of the box — talaria/autonomous.py's check-in loop
already looks up errbook_lookup by name and degrades gracefully if it's
missing, so making it a core tool just removes that "if installed" gap.

Metric: QUERY COVERAGE ('how many of my query terms does this entry
contain?') rather than symmetric Jaccard - paraphrase-tolerant in the
direction that matters. RU/EN stopwords filtered; light stemmer (ё->е).
"""
import json
import os
import re

from talaria.providers.base import ToolSpec
from talaria.tools.state_lock import STATE_LOCK

_SUFFIXES = [
    "иями", "ями", "ами", "иях", "ях", "ов", "ев", "ей", "ой", "ый", "ий",
    "ая", "яя", "ое", "ее", "ые", "ие", "ых", "их", "ому", "ему", "ыми",
    "ими", "ую", "юю", "ом", "ем", "ах", "ях", "ость", "ости", "сти",
    "ния", "ние", "тия", "тие", "ок", "ек", "ик", "ам", "ям", "ть", "ся",
    "у", "ю", "а", "я", "о", "е", "и", "ы", "ь",
]

_STOP = {
    "и", "в", "на", "по", "для", "с", "к", "про", "как", "что", "не", "нет",
    "при", "или", "из", "за", "то", "же", "бы", "это", "этот", "она", "они",
    "the", "a", "an", "of", "to", "for", "in", "on", "at", "is", "are", "not",
    "with", "from", "and", "or", "it", "its",
}


def _stem(w):
    w = str(w).replace("ё", "е")
    if len(w) <= 4:
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: len(w) - len(suf)]
    return w


def _tokens(text):
    out = []
    for w in re.findall(r"[a-zа-яё0-9]+", str(text).lower()):
        if w in _STOP:
            continue
        st = _stem(w)
        if st and st not in _STOP:
            out.append(st)
    return out


def _path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".errbook.json")


def _load(workspace_dir: str) -> dict:
    """Load and lazily migrate entries (tokens = signature + solution)."""
    path = _path(workspace_dir)
    entries = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = raw.get("entries", []) or [] if isinstance(raw, dict) else []
        except Exception:
            entries = []
    migrated = False
    for e in entries:
        want = sorted(set(_tokens(e.get("signature", "")) + _tokens(e.get("solution", ""))))
        if e.get("tokens") != want:
            e["tokens"] = want
            migrated = True
    db = {"entries": entries}
    if migrated:
        _save(workspace_dir, db)
    return db


def _save(workspace_dir: str, db: dict) -> None:
    path = _path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def errbook_add(workspace_dir: str, error_signature: str = "", solution: str = "") -> str:
    """Save a solved problem: error signature + what fixed it. Same signature updates the entry."""
    sig = str(error_signature).strip()
    sol = str(solution).strip()
    if not sig or not sol:
        return "Error: both 'error_signature' and 'solution' are required."
    toks = sorted(set(_tokens(sig) + _tokens(sol)))
    if not toks:
        return "Error: entry has no usable tokens."
    with STATE_LOCK:
        db = _load(workspace_dir)
        sig_key = " ".join(sorted(set(_tokens(sig)))) or sig.lower()
        for e in db["entries"]:
            if e.get("sig_key") == sig_key or " ".join(e.get("tokens", [])[:6]) == sig_key:
                e["solution"] = sol
                e["tokens"] = toks
                e["saves"] = int(e.get("saves", 1)) + 1
                _save(workspace_dir, db)
                return "Updated existing entry '{}' (saves={}).".format(sig[:80], e["saves"])
        eid = max([x.get("id", 0) for x in db["entries"]], default=0) + 1
        db["entries"].append({
            "id": eid,
            "sig_key": sig_key,
            "signature": sig,
            "solution": sol,
            "tokens": toks,
            "uses": 0,
        })
        db["entries"] = db["entries"][-200:]
        _save(workspace_dir, db)
    return "ErrEntry #{} saved ({} index terms): '{}'".format(eid, len(toks), sig[:80])


def errbook_lookup(workspace_dir: str, query: str = "", min_score: str = "0.45") -> str:
    """Fuzzy-find a known solution. Score = share of query terms covered by the entry."""
    qt = _tokens(query)
    if not qt:
        return "Error: empty query."
    try:
        thr = float(str(min_score).strip() or 0.45)
    except ValueError:
        thr = 0.45

    with STATE_LOCK:
        db = _load(workspace_dir)
        best, best_cov, best_hits_n = None, 0.0, 0
        for e in db["entries"]:
            etoks = set(e.get("tokens", []))
            hits = [t for t in qt if t in etoks]
            cov = float(len(hits)) / float(len(qt))
            if cov > best_cov or (cov == best_cov and len(hits) > best_hits_n):
                best, best_cov, best_hits_n = e, cov, len(hits)

        enough_terms = best_hits_n >= 2 or len(qt) == 1
        if best is None or best_cov < thr or not enough_terms:
            return ("NO MATCH (coverage {}, query stems: {}). Если проблема новая - решите и "
                    "зафиксируйте через errbook_add().").format(round(best_cov, 2), ",".join(qt))

        best["uses"] = int(best.get("uses", 0)) + 1
        _save(workspace_dir, db)
    return ("MATCH #{id} (coverage {cov}, {n}/{q} query terms):\nERROR: {sig}\nSOLUTION: {sol}\n"
            "(used {uses}x)").format(id=best["id"], cov=round(best_cov, 2),
                                     n=best_hits_n, q=len(qt),
                                     sig=best.get("signature"), sol=best.get("solution"),
                                     uses=best.get("uses", 0))


def errbook_list(workspace_dir: str, key: str = "") -> str:
    """List all learned lessons with usage counts."""
    db = _load(workspace_dir)
    if not db["entries"]:
        return "(errbook is empty)"
    return "\n".join("- #{} [{}x] {}: {}".format(
        e["id"], e.get("uses", 0),
        str(e.get("signature", ""))[:60], str(e.get("solution", ""))[:60])
        for e in db["entries"])


def make_errbook_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(name="errbook_add",
                 description="Save a solved problem to the error book: error signature + working solution.",
                 input_schema={"type": "object", "properties": {
                     "error_signature": {"type": "string", "description": "Short description of the error/problem."},
                     "solution": {"type": "string", "description": "What actually fixed it."}},
                     "required": ["error_signature", "solution"]},
                 handler=lambda error_signature="", solution="": errbook_add(
                     workspace_dir, error_signature, solution)),
        ToolSpec(name="errbook_lookup",
                 description="Fuzzy-search the error book for a known solution (paraphrased descriptions work).",
                 input_schema={"type": "object", "properties": {
                     "query": {"type": "string", "description": "Description of the problem you are facing."},
                     "min_score": {"type": "string", "description": "Coverage threshold 0..1 (default 0.45)."}},
                     "required": ["query"]},
                 handler=lambda query="", min_score="0.45": errbook_lookup(
                     workspace_dir, query, min_score)),
        ToolSpec(name="errbook_list",
                 description="List all lessons in the error book with usage counts.",
                 input_schema={"type": "object", "properties": {}},
                 handler=lambda: errbook_list(workspace_dir)),
    ]
