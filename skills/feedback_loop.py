# -*- coding: utf-8 -*-
"""Feedback loop: human ratings per task type - the ONLY external learning
signal the agent has. Aggregated means make weak spots visible, closing the
otherwise self-referential improvement loop."""
from datetime import datetime, timezone

from talaria.json_store import load_json, save_json
from talaria.providers.base import ToolSpec

_FILE = "feedback.json"


def _load():
    d = load_json(_FILE)
    if not isinstance(d, dict) or not isinstance(d.get("ratings"), list):
        return {"ratings": []}
    return d


def _save(db):
    save_json(_FILE, db)


def _mean(xs):
    return round(sum(xs) / float(len(xs)), 2) if xs else 0.0


def feedback_rate(score: str = "", task_type: str = "", note: str = "") -> str:
    """Rate the result of the last task: score 1-5 (required), optional task_type and note."""
    try:
        s = int(str(score).strip())
    except ValueError:
        return "Error: score must be an integer 1-5."
    if not 1 <= s <= 5:
        return "Error: score must be between 1 and 5."
    tt = str(task_type).strip().lower() or "general"
    db = _load()
    db["ratings"].append({
        "score": s,
        "type": tt,
        "note": str(note).strip(),
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    db["ratings"] = db["ratings"][-500:]
    _save(db)
    extra = ' Note: "{}"'.format(str(note).strip()) if str(note).strip() else ""
    return "Saved rating {}: {}.{}".format(s, tt, extra)


def feedback_report(task_type: str = "") -> str:
    """Aggregate ratings: overall mean, per-type means (worst first), recent notes."""
    db = _load()
    rs = list(db["ratings"])
    if not rs:
        return "(no ratings yet)"
    if str(task_type).strip():
        tt = str(task_type).strip().lower()
        rs = [r for r in rs if r.get("type") == tt]
        if not rs:
            return "(no ratings for type '{}')".format(tt)
    by_type = {}
    for r in rs:
        by_type.setdefault(r.get("type", "general"), []).append(int(r.get("score", 0)))
    lines = ["== FEEDBACK REPORT ({} rating(s)) ==".format(len(rs))]
    lines.append("Overall mean: {}".format(_mean([int(r.get("score", 0)) for r in rs])))
    rows = sorted(by_type.items(), key=lambda kv: _mean(kv[1]))
    lines.append("")
    lines.append("By type (worst first):")
    for t, scores in rows:
        lines.append("  {:<24} n={} mean={}".format(t, len(scores), _mean(scores)))
    if rows and _mean(rows[0][1]) < 4.0:
        lines.append("")
        lines.append("ATTENTION: weakest area '{}' - change approach there first.".format(rows[0][0]))
    notes = [r for r in rs if r.get("note")][-3:]
    if notes:
        lines.append("")
        lines.append("Recent notes:")
        lines.extend('  [{}] {} - "{}"'.format(r.get("score"), r.get("type"), r.get("note")) for r in notes)
    return "\n".join(lines)


TOOLS = [
    ToolSpec(name="feedback_rate",
             description="Rate the result of the last task 1-5 (human feedback - the agent's external learning signal).",
             input_schema={"type": "object", "properties": {
                 "score": {"type": "string", "description": "Rating 1-5."},
                 "task_type": {"type": "string", "description": "Category like 'research', 'code', 'report'. Default 'general'."},
                 "note": {"type": "string", "description": "Optional short comment."}},
                 "required": ["score"]},
             handler=feedback_rate),
    ToolSpec(name="feedback_report",
             description="Show aggregated feedback: overall mean, per-type means (worst first) and recent notes.",
             input_schema={"type": "object", "properties": {
                 "task_type": {"type": "string", "description": "Optional filter by category."}}},
             handler=feedback_report),
]
