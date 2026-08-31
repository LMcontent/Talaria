"""Persistent goal/priority tree.

Lets the agent know what it's working toward across sessions instead of
starting cold every time, and — the actually useful part — picks one
concrete "focus" to work on right now rather than a vague umbrella goal:
goal_focus drills past any active goal that itself has active sub-goals,
since the real next action lives at the leaf, not the top-level objective.
"""

import json
import os
from datetime import datetime, timezone

from talaria.providers.base import ToolSpec

_PRIORITIES = {"low": 1, "medium": 2, "high": 3}
_STATUSES = {"active", "paused", "done", "dropped"}


def _path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".goals.json")


def _load(workspace_dir: str) -> list[dict]:
    path = _path(workspace_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(workspace_dir: str, goals: list[dict]) -> None:
    path = _path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(goals, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(goals: list[dict], gid: int) -> dict | None:
    return next((g for g in goals if g["id"] == gid), None)


def goal_add(workspace_dir: str, title: str = "", parent_id: str = "", priority: str = "medium") -> str:
    """Add a goal, optionally as a sub-goal of an existing one."""
    t = str(title).strip()
    if not t:
        return "Error: 'title' is required."
    pr = str(priority).strip().lower() or "medium"
    if pr not in _PRIORITIES:
        return "Error: priority must be one of low/medium/high."

    goals = _load(workspace_dir)
    parent = None
    if str(parent_id).strip():
        try:
            parent = int(str(parent_id).strip())
        except ValueError:
            return "Error: parent_id must be a numeric goal id."
        if _find(goals, parent) is None:
            return f"Error: no goal #{parent} to attach to (see goal_list)."

    gid = max([g["id"] for g in goals], default=0) + 1
    goals.append({
        "id": gid,
        "title": t,
        "parent_id": parent,
        "priority": pr,
        "status": "active",
        "created": _now(),
        "updated": _now(),
        "notes": [],
    })
    _save(workspace_dir, goals)
    under = f" under #{parent}" if parent is not None else ""
    return f"Added goal #{gid} '{t}' ({pr}){under}."


def goal_update(
    workspace_dir: str, id: str = "", status: str = "", priority: str = "", note: str = ""
) -> str:
    """Update a goal's status and/or priority, and/or append a progress note."""
    try:
        gid = int(str(id).strip())
    except ValueError:
        return "Error: id must be a numeric goal id."
    goals = _load(workspace_dir)
    g = _find(goals, gid)
    if g is None:
        return f"Error: no goal #{gid} (see goal_list)."

    st = str(status).strip().lower()
    pr = str(priority).strip().lower()
    nt = str(note).strip()
    if not st and not pr and not nt:
        return "Error: give at least one of status, priority or note to update."
    if st:
        if st not in _STATUSES:
            return "Error: status must be one of active/paused/done/dropped."
        g["status"] = st
    if pr:
        if pr not in _PRIORITIES:
            return "Error: priority must be one of low/medium/high."
        g["priority"] = pr
    if nt:
        g.setdefault("notes", []).append({"ts": _now(), "text": nt})
    g["updated"] = _now()
    _save(workspace_dir, goals)

    changes = ", ".join(
        p for p in [f"status={st}" if st else "", f"priority={pr}" if pr else "", "note added" if nt else ""] if p
    )
    return f"Updated goal #{gid} ({changes})."


def goal_list(workspace_dir: str, status: str = "") -> str:
    """Show the goal tree (children indented under parents, siblings
    ordered by priority), optionally filtered to one status."""
    goals = _load(workspace_dir)
    if not goals:
        return "(no goals yet)"
    flt = str(status).strip().lower()
    if flt and flt not in _STATUSES:
        return "Error: status filter must be one of active/paused/done/dropped."
    if flt and not any(g["status"] == flt for g in goals):
        return f"(no goals with status '{flt}')"

    by_parent: dict = {}
    for g in goals:
        by_parent.setdefault(g.get("parent_id"), []).append(g)
    for children in by_parent.values():
        children.sort(key=lambda g: -_PRIORITIES[g["priority"]])

    lines: list[str] = []

    def emit(parent_id, depth):
        for g in by_parent.get(parent_id, []):
            if not flt or g["status"] == flt:
                lines.append(
                    "{}#{} [{}] ({}) {}".format("  " * depth, g["id"], g["status"], g["priority"], g["title"])
                )
            # Always recurse at true tree depth, even past a goal that
            # itself didn't match the filter, so a filtered-in grandchild
            # still lines up under its real ancestry rather than jumping
            # to the top level.
            emit(g["id"], depth + 1)

    emit(None, 0)
    return "\n".join(lines)


def goal_focus(workspace_dir: str) -> str:
    """Pick the single most actionable active goal right now: the
    highest-priority active goal that has no active sub-goals of its own
    — drills past umbrella goals into whichever child is actually
    actionable next. Shows the ancestor chain for context."""
    goals = _load(workspace_dir)
    active = [g for g in goals if g["status"] == "active"]
    if not active:
        return "(no active goals — use goal_add to set one)"

    actionable = [g for g in active if not any(c["parent_id"] == g["id"] for c in active)]
    if not actionable:
        actionable = active  # every active goal has an active child; fall back to all

    actionable.sort(key=lambda g: (-_PRIORITIES[g["priority"]], g["created"]))
    focus = actionable[0]

    chain = [focus]
    cur = focus
    while cur.get("parent_id") is not None:
        parent = _find(goals, cur["parent_id"])
        if parent is None:
            break
        chain.append(parent)
        cur = parent
    chain.reverse()

    path = " > ".join(f"#{g['id']} {g['title']}" for g in chain)
    notes = focus.get("notes", [])[-3:]
    lines = [f"FOCUS: {path}", f"Priority: {focus['priority']}"]
    if notes:
        lines.append("Recent notes:")
        lines.extend(f"  - {n['text']}" for n in notes)
    return "\n".join(lines)


def make_goal_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="goal_add",
            description=(
                "Add a goal or sub-goal to the persistent goal tree, so it's "
                "still known next session without being restated. Use "
                "parent_id to attach it under an existing goal (see goal_list "
                "for ids)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "What the goal is."},
                    "parent_id": {"type": "string", "description": "Optional id of the goal this is a sub-goal of."},
                    "priority": {"type": "string", "description": "low, medium (default) or high."},
                },
                "required": ["title"],
            },
            handler=lambda title, parent_id="", priority="medium": goal_add(
                workspace_dir, title, parent_id, priority
            ),
        ),
        ToolSpec(
            name="goal_update",
            description=(
                "Update a goal's status (active/paused/done/dropped) and/or "
                "priority (low/medium/high), and/or append a progress note. "
                "Give at least one of status, priority or note."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Goal id, from goal_list."},
                    "status": {"type": "string", "description": "Optional new status."},
                    "priority": {"type": "string", "description": "Optional new priority."},
                    "note": {"type": "string", "description": "Optional progress note to append."},
                },
                "required": ["id"],
            },
            handler=lambda id, status="", priority="", note="": goal_update(
                workspace_dir, id, status, priority, note
            ),
        ),
        ToolSpec(
            name="goal_list",
            description="Show the goal tree with ids, statuses and priorities, optionally filtered to one status.",
            input_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Optional filter: active/paused/done/dropped."}
                },
                "required": [],
            },
            handler=lambda status="": goal_list(workspace_dir, status),
        ),
        ToolSpec(
            name="goal_focus",
            description=(
                "Pick what to actually work on right now: the highest-priority "
                "active goal that has no active sub-goals of its own, with its "
                "ancestor chain and recent notes for context. Call this at the "
                "start of a task with no explicit instruction, instead of "
                "asking what to do."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: goal_focus(workspace_dir),
        ),
    ]
