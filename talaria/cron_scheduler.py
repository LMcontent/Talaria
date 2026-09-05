"""Fires cron jobs (talaria/tools/cron.py) while a Talaria process (web UI
or CLI) is running — a background daemon thread, checked once a minute.
No OS-level cron/systemd entry, so jobs simply don't fire while nothing is
running — good enough for now; can graduate to a persistent scheduler
later if that turns out to matter.
"""

import threading
import time
from datetime import datetime, timezone

from talaria.agent import Agent
from talaria.config import Config
from talaria.providers.base import Provider, ToolSpec
from talaria.roles import DEFAULT_ROLE, ROLES
from talaria.system_prompt import build_system
from talaria.tools.cron import cron_matches, load_jobs, save_jobs
from talaria.tools.registry import build_tools
from talaria.usage import UsageTracker
from talaria.workspace_log import append_log

# Same rationale as talaria/autonomous.py: nobody is watching a cron job
# fire, so it must never reach code execution, package installs, new-skill
# approval, or the full unfiltered tool set delegate_task/run_procedure
# would otherwise hand back out.
EXCLUDED_TOOLS = {"run_python", "install_package", "propose_skill", "delegate_task", "run_procedure"}

_CHECK_INTERVAL_SECONDS = 30
_LOG_FILENAME = ".cron_log.json"


def build_cron_tools(config: Config, provider: Provider) -> list[ToolSpec]:
    return [t for t in build_tools(config, provider) if t.name not in EXCLUDED_TOOLS]


def _run_job(config: Config, provider: Provider, usage: UsageTracker, job: dict) -> None:
    role = config.default_role if config.default_role in ROLES else DEFAULT_ROLE
    tools = build_cron_tools(config, provider)
    agent = Agent(
        provider, tools, system=build_system(role, config.notes_file),
        max_turns=config.max_turns, usage=usage,
    )
    label = job.get("name") or job["schedule"]
    print(f"\n[cron] running job #{job['id']} ({label})")
    try:
        reply = agent.run(job["prompt"])
    except Exception as e:
        reply = f"Error: {e}"
    print()

    append_log(config.workspace_dir, _LOG_FILENAME, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "job_id": job["id"],
        "name": job.get("name", ""),
        "schedule": job["schedule"],
        "reply": reply,
    })


def _tick(config: Config, provider: Provider, usage: UsageTracker, now: datetime | None = None) -> None:
    now = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    minute_key = now.isoformat()
    jobs = load_jobs(config.workspace_dir)
    if not jobs:
        return

    due = [
        j for j in jobs
        if j.get("enabled", True)
        and j.get("last_fired_minute") != minute_key
        and cron_matches(j["schedule"], now)
    ]
    if not due:
        return

    for job in due:
        job["last_fired_minute"] = minute_key
        job["last_run"] = minute_key
    save_jobs(config.workspace_dir, jobs)

    # Run after saving, so a job that raises (or a process crash mid-run)
    # can't cause the same minute to fire it twice.
    for job in due:
        _run_job(config, provider, usage, job)


def start_cron_scheduler(config: Config, provider: Provider, usage: UsageTracker) -> None:
    """Starts the background cron-checking thread. Daemon — dies with the
    process; safe to call unconditionally, since it's a cheap no-op loop
    whenever there are no jobs."""

    def loop():
        while True:
            try:
                _tick(config, provider, usage)
            except Exception as e:
                print(f"[cron] error during check: {e}")
            time.sleep(_CHECK_INTERVAL_SECONDS)

    threading.Thread(target=loop, daemon=True).start()
