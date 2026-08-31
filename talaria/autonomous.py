"""Optional background loop: wakes on an interval with nobody watching,
checks the goal tree via goal_focus, and works on whatever's actionable.

OFF by default — set AUTONOMOUS_MODE=true in .env to enable, and
AUTONOMOUS_INTERVAL_MINUTES to control how often it wakes (default 60).
Runs as its own process (`python -m talaria.autonomous`), separate from
the CLI/web UI, so it's a plain toggle: run this process to turn it on,
stop it (or set AUTONOMOUS_MODE=false) to turn it off — independent of
whether you're also using the CLI or web UI elsewhere.

Deliberately excludes tools that can execute code, install packages,
author new skills, or delegate to a sub-agent (which would otherwise get
the full, unfiltered tool set again) — an unattended run with nobody to
answer the y/N confirmation those normally require must never be able to
silently run code or grab new capabilities on its own. It can still
read/write workspace files, and use the goal tree, notes, checkpoints,
and any already-installed skill (those were security-reviewed when
approved via propose_skill in an earlier, attended session).
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

from talaria.agent import Agent
from talaria.cli import build_system
from talaria.config import Config, load_config
from talaria.providers import make_provider
from talaria.providers.base import Provider, ToolSpec
from talaria.roles import DEFAULT_ROLE, ROLES
from talaria.tools.goals import goal_focus
from talaria.tools.registry import build_tools
from talaria.usage import UsageTracker

# Tools that normally require an attended y/N confirmation, or that hand
# out the full unfiltered tool set again (delegate_task's sub-agents) —
# never available on an unattended run.
EXCLUDED_TOOLS = {"run_python", "install_package", "propose_skill", "delegate_task"}

PROMPT_TEMPLATE = (
    "This is an unattended autonomous check-in — nobody is watching, so "
    "run_python, install_package, propose_skill and delegate_task are not "
    "available this turn (they need an attended session). Work toward the "
    "current focus using the tools you do have (documents, web, notes, "
    "goals, checkpoints, and any already-installed skill). Use goal_update "
    "to record progress, or change status/priority as you learn things.\n\n"
    "{focus}"
)


def _log_path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".autonomous_log.json")


def _append_log(workspace_dir: str, entry: dict) -> None:
    path = _log_path(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)
    entries = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []
    entries.append(entry)
    entries = entries[-200:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_autonomous_tools(config: Config, provider: Provider) -> list[ToolSpec]:
    return [t for t in build_tools(config, provider) if t.name not in EXCLUDED_TOOLS]


def tick(config: Config, provider: Provider, usage: UsageTracker) -> str | None:
    """Run one autonomous check-in. Returns the reply, or None if there
    was no active goal to work on (nothing is logged in that case)."""
    focus = goal_focus(config.workspace_dir)
    if focus.startswith("(no active goals"):
        print(f"[autonomous] {focus}")
        return None

    role = config.default_role if config.default_role in ROLES else DEFAULT_ROLE
    tools = build_autonomous_tools(config, provider)
    agent = Agent(
        provider, tools, system=build_system(role, config.notes_file),
        max_turns=config.max_turns, usage=usage,
    )

    print(f"\n[autonomous] check-in at {datetime.now(timezone.utc).isoformat()}")
    print(f"[autonomous] {focus}")
    reply = agent.run(PROMPT_TEMPLATE.format(focus=focus))
    print()

    _append_log(config.workspace_dir, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "focus": focus,
        "reply": reply,
    })
    return reply


def main() -> None:
    config = load_config()
    if not config.autonomous_mode:
        print(
            "AUTONOMOUS_MODE is not enabled (set AUTONOMOUS_MODE=true in .env "
            "to turn this on). Exiting without doing anything."
        )
        sys.exit(0)

    try:
        provider = make_provider(config)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    usage = UsageTracker(
        max_tokens=config.max_session_tokens,
        input_price_per_m=config.token_price_input_per_m,
        output_price_per_m=config.token_price_output_per_m,
    )
    interval_seconds = max(1.0, config.autonomous_interval_minutes) * 60

    print(
        f"Talaria autonomous mode running (provider={config.provider}) — "
        f"checking in every {config.autonomous_interval_minutes:.0f} minute(s). Ctrl+C to stop."
    )
    print(f"Excluded this run: {', '.join(sorted(EXCLUDED_TOOLS))} — those need an attended session.")

    while True:
        try:
            tick(config, provider, usage)
        except Exception as e:
            print(f"[autonomous] error during check-in: {e}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
