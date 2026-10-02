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

Before each check-in's own agent runs, _skill_context pulls in whatever
the optional errbook/idea_lab/feedback_loop skills (skills/errbook.py,
skills/idea_lab.py, skills/feedback_loop.py) already know that's relevant
to the current focus — a matching past error+solution, outstanding
iteration-lab advice, a feedback report flagging a weak area — and folds
it into the prompt. Those skills' own lookup tools (errbook_lookup,
lab_next, feedback_report) already existed and worked fine called by
hand, but nothing in the unattended loop ever called them on its own, so
whatever they'd learned sat there unread tick after tick. This is
deliberately duck-typed by tool name against whatever's actually in the
check-in's own (already EXCLUDED_TOOLS-filtered) tool list, not a hard
import of skills/ — those are optional plugins, and a deployment without
one (or without skills/ at all) just skips that piece.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

from talaria.agent import Agent
from talaria.config import Config, load_config
from talaria.providers import make_provider
from talaria.providers.base import Provider, ToolSpec
from talaria.roles import DEFAULT_ROLE, ROLES
from talaria.system_prompt import build_system
from talaria.tools.goals import goal_focus
from talaria.tools.registry import build_tools
from talaria.usage import UsageTracker
from talaria.workspace_log import append_log

# Tools that normally require an attended y/N confirmation, or that hand
# out the full unfiltered tool set again (delegate_task's sub-agents,
# run_procedure's internal loop — both are built from this agent's own
# tool list *before* filtering, so excluding them here is the only way to
# keep an unattended run from reaching run_python etc. through them) —
# never available on an unattended run. browser_click/browser_type are
# excluded too: they can act on a real, possibly-logged-in browser session
# (submit a form, send a message, spend money) with nobody watching to
# catch a mistake. Read-only browsing (browser_open/browser_state/
# browser_scroll/browser_back/browser_screenshot) stays available, same as
# web_fetch always has been.
EXCLUDED_TOOLS = {
    "run_python", "install_package", "propose_skill", "delegate_task", "run_procedure",
    "browser_click", "browser_type",
}

PROMPT_TEMPLATE = (
    "This is an unattended autonomous check-in — nobody is watching, so "
    "{excluded} are not available this turn (they need an attended "
    "session). Work toward the current focus using the tools you do have "
    "(documents, web, notes, goals, checkpoints, and any already-installed "
    "skill). Use goal_update to record progress, or change status/priority "
    "as you learn things.\n\n"
    "{focus}"
)


def _focus_query(focus: str) -> str:
    """Strips goal_focus()'s own scaffolding (the 'FOCUS:'/'Priority:'/
    'Recent notes:' labels) down to just the meaningful words — the goal's
    own title/ancestor chain and its note text — so errbook_lookup's
    coverage score isn't diluted by boilerplate that could never match a
    stored error signature."""
    parts = []
    for line in focus.splitlines():
        line = line.strip()
        if line.startswith("FOCUS:"):
            parts.append(line[len("FOCUS:"):].strip())
        elif line.startswith("- "):
            parts.append(line[2:].strip())
    return " ".join(parts)


def _skill_context(tools: list[ToolSpec], focus: str) -> str:
    """Pulls in whatever the optional errbook/idea_lab/feedback_loop
    skills already know that's relevant right now, so a check-in actually
    benefits from past lessons instead of them sitting unread in state —
    see the module docstring. Included only when there's something
    genuinely actionable (a real errbook match, lab hypotheses actually in
    play, a feedback report flagging a weak spot), not unconditionally on
    every tick — an empty lab or a clean feedback history isn't a signal
    worth spending prompt tokens on forever. Best-effort: a skill's
    handler raising (or not being installed at all) just means that piece
    is skipped, never a failed check-in."""
    by_name = {t.name: t for t in tools}
    parts = []

    errbook_lookup = by_name.get("errbook_lookup")
    if errbook_lookup is not None:
        try:
            result = errbook_lookup.handler(query=_focus_query(focus))
        except Exception:
            result = ""
        if result.startswith("MATCH"):
            parts.append("RELEVANT PAST LESSON (errbook):\n" + result)

    lab_next = by_name.get("lab_next")
    if lab_next is not None:
        try:
            result = lab_next.handler()
        except Exception:
            result = ""
        if result and not result.startswith("Лаборатория пуста"):
            parts.append("ITERATION LAB ADVICE:\n" + result)

    feedback_report = by_name.get("feedback_report")
    if feedback_report is not None:
        try:
            result = feedback_report.handler()
        except Exception:
            result = ""
        if "ATTENTION" in result:
            parts.append("FEEDBACK SIGNAL:\n" + result)

    return "\n\n".join(parts)


_LOG_FILENAME = ".autonomous_log.json"
# Written while a check-in is actually running, removed right after — this
# process is entirely separate from the web UI's (see module docstring), so
# the only way for that sidebar to know "a check-in is in progress right
# now" (rather than just seeing completed ones via the log above) is a
# small file it can poll, not an in-memory flag.
_STATUS_FILENAME = ".autonomous_status.json"


def _write_status(workspace_dir: str, data: dict | None) -> None:
    path = os.path.join(workspace_dir, _STATUS_FILENAME)
    if data is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(workspace_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
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

    started = datetime.now(timezone.utc).isoformat()
    print(f"\n[autonomous] check-in at {started}")
    print(f"[autonomous] {focus}")
    prompt = PROMPT_TEMPLATE.format(excluded=", ".join(sorted(EXCLUDED_TOOLS)), focus=focus)
    skill_context = _skill_context(tools, focus)
    if skill_context:
        print(f"[autonomous] relevant skill context:\n{skill_context}")
        prompt += "\n\n" + skill_context
    _write_status(config.workspace_dir, {"started": started, "focus": focus})
    try:
        reply = agent.run(prompt)
    finally:
        _write_status(config.workspace_dir, None)
    print()

    append_log(config.workspace_dir, _LOG_FILENAME, {
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
