# -*- coding: utf-8 -*-
"""Shift log: structured WORKING-CONTEXT handoff between sessions.

Unlike long-term memory (durable facts), the shift log carries the state of
unfinished business: where you stopped, what's next, what's unresolved.
Stored in ./state/shifts.json (last 30 shifts kept).
"""
from datetime import datetime, timezone

from talaria.json_store import load_json, save_json
from talaria.providers.base import ToolSpec

_FILE = "shifts.json"
_UTC = timezone.utc


def _now_iso():
    return datetime.now(_UTC).isoformat()


def _load():
    d = load_json(_FILE)
    if not isinstance(d, dict) or not isinstance(d.get("shifts"), list):
        return {"shifts": []}
    return d


def _save(db):
    save_json(_FILE, db)


def _to_items(v):
    raw = str(v).replace(";", "\n").split("\n")
    return [p.strip(" -") for p in raw if p.strip(" -")]


def shift_end(summary: str = "", next_steps: str = "", open_questions: str = "", wins: str = "") -> str:
    """Close the current work shift: save a structured handoff for the next session."""
    s = str(summary).strip()
    if not s:
        return "Error: 'summary' (where did you stop?) is required."
    db = _load()
    sid = max([x.get("id", 0) for x in db["shifts"]], default=0) + 1
    db["shifts"].append({
        "id": sid,
        "ended_at": _now_iso(),
        "summary": s,
        "next_steps": _to_items(next_steps),
        "open_questions": _to_items(open_questions),
        "wins": _to_items(wins),
    })
    db["shifts"] = db["shifts"][-30:]
    _save(db)
    return "Shift #{} closed at {} UTC. Next session starts with shift_start().".format(sid, _now_iso()[:16].replace("T", " "))


def shift_start(key: str = "") -> str:
    """Open the latest shift report to pick up working context instantly."""
    db = _load()
    if not db["shifts"]:
        return "(no previous shifts - fresh start)"
    sh = db["shifts"][-1]
    lines = ["== SHIFT #{} (closed {}) UTC ==" .format(sh["id"], str(sh["ended_at"])[:16].replace("T", " "))]
    lines.append("WHERE I STOPPED:\n  " + sh["summary"])
    if sh["next_steps"]:
        lines.append("NEXT STEPS:")
        lines.extend("  - " + s for s in sh["next_steps"])
    if sh["open_questions"]:
        lines.append("OPEN QUESTIONS:")
        lines.extend("  ? " + s for s in sh["open_questions"])
    if sh["wins"]:
        lines.append("WINS:")
        lines.extend("  + " + s for s in sh["wins"])
    older = len(db["shifts"]) - 1
    if older:
        lines.append("({} earlier shift(s) archived)".format(older))
    return "\n".join(lines)


TOOLS = [
    ToolSpec(
        name="shift_end",
        description="Close the current work shift: save where you stopped, next steps, open questions and wins for the next session.",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Where you stopped (required)."},
                "next_steps": {"type": "string", "description": "What to do next (newline or ; separated)."},
                "open_questions": {"type": "string", "description": "Unresolved questions."},
                "wins": {"type": "string", "description": "What was achieved."},
            },
            "required": ["summary"],
        },
        handler=shift_end,
    ),
    ToolSpec(
        name="shift_start",
        description="Open the latest shift report to instantly restore working context at session start.",
        input_schema={"type": "object", "properties": {}},
        handler=shift_start,
    ),
]
