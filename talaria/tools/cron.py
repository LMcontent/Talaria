"""Scheduled tasks: standard 5-field cron expressions (minute hour
day-of-month month day-of-week), each paired with a prompt to run
unattended when due.

This module only owns the job list (add/list/remove/toggle, as agent
tools) and the cron-matching logic. Actually firing jobs on schedule is
talaria/cron_scheduler.py's job — a background thread started by the web
UI/CLI that polls this list, so jobs only fire while some Talaria process
is running (no OS-level cron/systemd entry yet — good enough for now).
"""

import json
import os
from datetime import datetime, timezone

from talaria.providers.base import ToolSpec

_FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
_FIELD_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


def _path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".cron.json")


def load_jobs(workspace_dir: str) -> list[dict]:
    path = _path(workspace_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_jobs(workspace_dir: str, jobs: list[dict]) -> None:
    path = _path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(jobs: list[dict], jid: int) -> dict | None:
    return next((j for j in jobs if j["id"] == jid), None)


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """Parses one cron field: '*', a number, 'a-b', '*/n', 'a-b/n', or a
    comma-separated list of any of those. Raises ValueError on anything
    it doesn't recognize."""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty field")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError("step must be positive")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if not (lo <= start <= hi and lo <= end <= hi and start <= end):
            raise ValueError(f"out of range {lo}-{hi}")
        values.update(range(start, end + 1, step))
    return values


def validate_cron_expression(expr: str) -> str | None:
    """Returns an error message, or None if `expr` is a valid 5-field
    cron expression."""
    parts = expr.split()
    if len(parts) != 5:
        return (
            "Cron schedule must have 5 space-separated fields: "
            "minute hour day-of-month month day-of-week (e.g. '0 9 * * 1-5' = 9am on weekdays)."
        )
    for part, name, (lo, hi) in zip(parts, _FIELD_NAMES, _FIELD_RANGES):
        try:
            if not _parse_field(part, lo, hi):
                return f"Invalid {name} field {part!r}: matches nothing."
        except ValueError as e:
            return f"Invalid {name} field {part!r}: {e}"
    return None


def cron_matches(expr: str, dt: datetime) -> bool:
    """Whether `dt` (assumed UTC, minute-resolution) falls due per `expr`.
    Follows standard cron semantics: if day-of-month AND day-of-week are
    both restricted (neither is '*'), a match on either is enough; if only
    one is restricted, that one alone decides."""
    parts = expr.split()
    if len(parts) != 5:
        return False
    minute_f, hour_f, dom_f, month_f, dow_f = parts
    try:
        minute = _parse_field(minute_f, 0, 59)
        hour = _parse_field(hour_f, 0, 23)
        dom = _parse_field(dom_f, 1, 31)
        month = _parse_field(month_f, 1, 12)
        dow = _parse_field(dow_f, 0, 6)
    except ValueError:
        return False

    if dt.minute not in minute or dt.hour not in hour or dt.month not in month:
        return False

    dom_restricted = dom_f.strip() != "*"
    dow_restricted = dow_f.strip() != "*"
    day_ok = dt.day in dom
    # Standard cron weekday numbering: 0=Sunday..6=Saturday. isoweekday()
    # is 1=Monday..7=Sunday, so 7 % 7 == 0 lines Sunday back up with 0.
    weekday_ok = (dt.isoweekday() % 7) in dow

    if dom_restricted and dow_restricted:
        return day_ok or weekday_ok
    return day_ok and weekday_ok


def cron_add(workspace_dir: str, schedule: str, prompt: str, name: str = "") -> str:
    """Add a scheduled job: `prompt` is run as an unattended agent turn
    whenever `schedule` (a 5-field cron expression, in UTC) is due."""
    sched = str(schedule).strip()
    err = validate_cron_expression(sched)
    if err:
        return f"Error: {err}"
    p = str(prompt).strip()
    if not p:
        return "Error: 'prompt' is required — what should the agent do when this fires?"

    jobs = load_jobs(workspace_dir)
    jid = max([j["id"] for j in jobs], default=0) + 1
    jobs.append({
        "id": jid,
        "name": str(name).strip(),
        "schedule": sched,
        "prompt": p,
        "enabled": True,
        "created": _now(),
        "last_run": None,
        "last_fired_minute": None,
    })
    save_jobs(workspace_dir, jobs)
    label = f" '{name}'" if str(name).strip() else ""
    return f"Added cron job #{jid}{label}: '{sched}' (UTC) — runs while a Talaria process is up."


def cron_list(workspace_dir: str) -> str:
    """List all scheduled jobs with their id, schedule, enabled state and last run time."""
    jobs = load_jobs(workspace_dir)
    if not jobs:
        return "(no cron jobs — use cron_add to schedule one)"
    lines = []
    for j in jobs:
        state = "enabled" if j.get("enabled", True) else "disabled"
        label = f" '{j['name']}'" if j.get("name") else ""
        last = j.get("last_run") or "never"
        lines.append(f"#{j['id']}{label} [{state}] '{j['schedule']}' — last run: {last}")
    return "\n".join(lines)


def cron_remove(workspace_dir: str, id: str) -> str:
    """Remove a scheduled job by id (see cron_list)."""
    try:
        jid = int(str(id).strip())
    except ValueError:
        return "Error: id must be a numeric job id."
    jobs = load_jobs(workspace_dir)
    job = _find(jobs, jid)
    if job is None:
        return f"Error: no cron job #{jid} (see cron_list)."
    jobs = [j for j in jobs if j["id"] != jid]
    save_jobs(workspace_dir, jobs)
    return f"Removed cron job #{jid}."


def cron_toggle(workspace_dir: str, id: str, enabled: str) -> str:
    """Enable or disable a scheduled job without deleting it (`enabled`: true/false)."""
    try:
        jid = int(str(id).strip())
    except ValueError:
        return "Error: id must be a numeric job id."
    en = str(enabled).strip().lower() in ("true", "1", "yes", "y", "on")
    jobs = load_jobs(workspace_dir)
    job = _find(jobs, jid)
    if job is None:
        return f"Error: no cron job #{jid} (see cron_list)."
    job["enabled"] = en
    save_jobs(workspace_dir, jobs)
    return f"Cron job #{jid} is now {'enabled' if en else 'disabled'}."


def make_cron_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="cron_add",
            description=(
                "Schedule a prompt to run automatically as an unattended agent "
                "turn, on a standard 5-field cron expression in UTC (minute "
                "hour day-of-month month day-of-week, e.g. '0 9 * * 1-5' = "
                "9am UTC on weekdays). Only fires while some Talaria process "
                "(web UI or CLI) is running — there's no OS-level scheduling "
                "yet. Unattended runs can't execute code, install packages, "
                "approve new skills, or delegate — same restriction as "
                "autonomous mode."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "schedule": {
                        "type": "string",
                        "description": "5-field cron expression in UTC, e.g. '0 9 * * 1-5' or '*/30 * * * *'.",
                    },
                    "prompt": {"type": "string", "description": "What the agent should do when this fires."},
                    "name": {"type": "string", "description": "Optional short label for this job."},
                },
                "required": ["schedule", "prompt"],
            },
            handler=lambda schedule, prompt, name="": cron_add(workspace_dir, schedule, prompt, name),
        ),
        ToolSpec(
            name="cron_list",
            description="List all scheduled cron jobs with their id, schedule, enabled state and last run time.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: cron_list(workspace_dir),
        ),
        ToolSpec(
            name="cron_remove",
            description="Permanently remove a scheduled cron job by id (see cron_list).",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Job id, from cron_list."}},
                "required": ["id"],
            },
            handler=lambda id: cron_remove(workspace_dir, id),
        ),
        ToolSpec(
            name="cron_toggle",
            description="Enable or disable a scheduled cron job without deleting it.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Job id, from cron_list."},
                    "enabled": {"type": "string", "description": "'true' to enable, 'false' to disable."},
                },
                "required": ["id", "enabled"],
            },
            handler=lambda id, enabled: cron_toggle(workspace_dir, id, enabled),
        ),
    ]
