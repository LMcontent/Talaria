"""Shared JSON persistence for skills.

Skills are loaded as standalone files (talaria/skills.py) with no config
object handed to them, so each one previously resolved its own state
directory independently — and every one of them did it the same wrong
way: `os.path.join(".", "state")`, relative to the process's current
working directory rather than the configured workspace. That's harmless
as long as everything is launched from the same directory, but silently
diverges the moment it isn't (e.g. `python -m talaria.autonomous` started
from a different cwd than the CLI/web UI) — exactly the kind of drift
that breaks continuity for the skills (errbook, feedback_loop, ...) that
autonomous mode most depends on.

This resolves the same WORKSPACE_DIR env var talaria/config.py itself
defaults from, so a skill's state directory always matches
`Config.workspace_dir` regardless of where the process happens to be
launched from.
"""

import json
import os


def state_dir() -> str:
    workspace_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
    return os.path.join(workspace_dir, "state")


def state_path(filename: str) -> str:
    return os.path.join(state_dir(), filename)


def load_json(filename: str):
    """Return the parsed JSON from state_dir()/filename, or None if the
    file doesn't exist or isn't valid JSON — callers apply their own
    default shape and validation on None/wrong-type, same as before."""
    path = state_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(filename: str, data) -> None:
    """Atomically write data as JSON to state_dir()/filename."""
    path = state_path(filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
