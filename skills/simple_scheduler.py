# -*- coding: utf-8 -*-
"""Simple task scheduler: a persistent task queue with due times.

Limitation handled honestly: the agent cannot wake itself up. Tasks become
actionable when a session runs `task_tick` (e.g. at the start of a dialog):
it returns due tasks with their instructions for immediate execution.
Recurring tasks reschedule themselves by an hourly interval.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import talaria.providers.base as base
ToolSpec = base.ToolSpec

_TASKS_DIR = os.path.join(".", "state")
_TASKS_FILE = os.path.join(_TASKS_DIR, "tasks.json")
_UTC = timezone.utc


def _now():
    return datetime.now(_UTC)


def _iso(dt):
    return dt.isoformat()


def _parse_when(s):
    s = str(s).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(_UTC)


def _load():
    if not os.path.isfile(_TASKS_FILE):
        return []
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(tasks):
    os.makedirs(_TASKS_DIR, exist_ok=True)
    tmp = _TASKS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _TASKS_FILE)


def task_add(name: str = "", instruction: str = "", interval_hours: str = "", due_iso: str = "") -> str:
    """Add a task. Either interval_hours (recurring) or due_iso (one-time), or both."""
    n = str(name).strip()
    instr = str(instruction).strip()
    if not n or not instr:
        return "Error: 'name' and 'instruction' are required."

    rec = None
    if str(interval_hours).strip():
        try:
            rec = float(interval_hours)
            if rec <= 0:
                raise ValueError
        except ValueError:
            return "Error: interval_hours must be a positive number."

    now = _now()
    nxt = _parse_when(due_iso)
    if due_iso.strip() and nxt is None:
        return "Error: bad due_iso format, use ISO like 2026-08-25T09:00."
    if nxt is None:
        nxt = now + timedelta(hours=rec) if rec else now

    tasks = _load()
    tid = max([t.get("id", 0) for t in tasks], default=0) + 1
    tasks.append({
        "id": tid,
        "name": n,
        "instruction": instr,
        "interval_hours": rec,
        "created": _iso(now),
        "last_run": None,
        "next_run": _iso(nxt),
        "status": "active",
    })
    _save(tasks)
    kind = "recurring every {}h".format(rec) if rec else "one-time"
    return "Task #{} '{}' added ({}). First run due: {}".format(tid, n, kind, _iso(nxt))


def task_list(key: str = "") -> str:
    """List all tasks with statuses; mark overdue ones."""
    tasks = _load()
    if not tasks:
        return "(no tasks)"
    now = _now()
    lines = []
    for t in sorted(tasks, key=lambda x: x.get("id", 0)):
        nxt = _parse_when(t.get("next_run", ""))
        flag = ""
        if t.get("status") == "active" and nxt and nxt <= now:
            flag = " [OVERDUE]"
        elif t.get("status") != "active":
            flag = " [{}]".format(t.get("status"))
        rec = ", every {}h".format(t["interval_hours"]) if t.get("interval_hours") else ""
        lines.append("#{}{}: {} | next: {}{}".format(
            t.get("id"), flag, t.get("name"),
            str(t.get("next_run"))[:16].replace("T", " "), rec))
    return "\n".join(lines)


def task_tick(key: str = "") -> str:
    """Return DUE tasks with instructions for execution; reschedule recurring ones."""
    tasks = _load()
    if not tasks:
        return "(no tasks)"
    now = _now()
    due_lines = []
    changed = False
    for t in tasks:
        if t.get("status") != "active":
            continue
        nxt = _parse_when(t.get("next_run", ""))
        if nxt is None or nxt > now:
            continue
        due_lines.append("[#{}] {}\nINSTRUCTION: {}".format(t.get("id"), t.get("name"), t.get("instruction")))
        t["last_run"] = _iso(now)
        rec = t.get("interval_hours")
        if rec:
            step = timedelta(hours=float(rec))
            new_nxt = nxt + step
            while new_nxt <= now:
                new_nxt += step
            t["next_run"] = _iso(new_nxt)
        else:
            t["status"] = "ran"
        changed = True
    if changed:
        _save(tasks)
    if not due_lines:
        upcoming = [t for t in tasks if t.get("status") == "active"]
        if upcoming:
            soonest = min(upcoming, key=lambda x: x.get("next_run", ""))
            return "No tasks due now. Next: '{}' at {}".format(soonest.get("name"), str(soonest.get("next_run"))[:16])
        return "No active tasks."
    header = "{} task(s) DUE - execute these now:\n\n".format(len(due_lines))
    return header + "\n\n".join(due_lines)


def task_done(task_id: str = "") -> str:
    """Remove a finished task by id (archives it from the queue)."""
    try:
        tid = int(str(task_id).strip())
    except ValueError:
        return "Error: task_id must be an integer."
    tasks = _load()
    kept = [t for t in tasks if t.get("id") != tid]
    if len(kept) == len(tasks):
        return "Not found: task #{}".format(tid)
    _save(kept)
    return "Task #{} removed.".format(tid)


TOOLS = [
    ToolSpec(
        name="task_add",
        description="Add a scheduled task: recurring (interval_hours) or one-time (due_iso). Instruction is what the agent should do when the task is due.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short task name."},
                "instruction": {"type": "string", "description": "What to do when due."},
                "interval_hours": {"type": "string", "description": "Optional recurrence interval in hours, e.g. '24'. Empty for one-time."},
                "due_iso": {"type": "string", "description": "Optional first due time in ISO, e.g. '2026-08-25T09:00'. Empty = now."},
            },
            "required": ["name", "instruction"],
        },
        handler=task_add,
    ),
    ToolSpec(
        name="task_list",
        description="Show all scheduled tasks with statuses and overdue markers.",
        input_schema={"type": "object", "properties": {}},
        handler=task_list,
    ),
    ToolSpec(
        name="task_tick",
        description="Check for DUE tasks: returns their instructions for immediate execution and reschedules recurring ones. Call at session start.",
        input_schema={"type": "object", "properties": {}},
        handler=task_tick,
    ),
    ToolSpec(
        name="task_done",
        description="Remove a finished task by its numeric id.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Numeric id of the task."},
            },
            "required": ["task_id"],
        },
        handler=task_done,
    ),
]
