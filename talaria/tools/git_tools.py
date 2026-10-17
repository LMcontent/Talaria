"""Human-friendly wrappers around the handful of git operations that are
either genuinely awkward or genuinely risky to get right through
run_shell's raw command string:

- git_commit: a commit message gets written to a temp file and passed via
  `git commit -F <file>`, never interpolated into a shell command string
  at all. A message containing quotes, backticks, `$variables`, or
  newlines is exactly the kind of thing that silently breaks or
  misbehaves inside a one-line `git commit -m "..."` run through a shell
  - this sidesteps that class of bug entirely rather than trying to
  escape it correctly.
- git_status / git_diff: save the model from re-deriving the right flags
  (--short --branch, --staged) every time, with the same truncation other
  tools already apply to possibly-huge output.

This is deliberately NOT a general git CLI wrapper - clone, branch,
push, pull, log, reset, and everything else stay on run_shell, which
already handles them fine as plain commands with no quoting hazard.
Commands here are built as argv lists (never through a shell), so
there's no shell-injection surface at all, unlike run_shell.

All three operate on the same tracked working directory run_shell/
shell_reset maintain (talaria.tools.shell_exec.tracked_dir) - a `cd` via
run_shell carries over here too, instead of each tool guessing its own
notion of "the current repo."

No confirmation gate, unlike run_python/run_shell/install_package: these
are fixed, non-arbitrary git subcommands (not model-written code run
with OS permissions), git_status/git_diff are read-only, and git_commit
is no riskier than write_document - a committed change is trivially
reversible with another commit. Available in Autonomous mode/cron for
the same reason write_document/goal_update are.
"""

import os
import subprocess
import tempfile

from talaria.providers.base import ToolSpec
from talaria.tools.shell_exec import tracked_dir

_TIMEOUT = 30
_MAX_CHARS = 8000


def _run_git(workspace_dir: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=tracked_dir(workspace_dir),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


def _git_error(result: subprocess.CompletedProcess, label: str) -> str:
    detail = (result.stderr or result.stdout).strip()
    return f"Error: git {label} failed (exit {result.returncode}): {detail}"


def git_status(workspace_dir: str, path: str = "") -> str:
    """Show a short, branch-aware working tree status. Untracked files are
    listed individually (--untracked-files=all) rather than collapsed
    into a single '?? some_dir/' entry for an entirely-untracked
    directory - knowing exactly which files are new is the whole point
    of asking, for a model deciding what to add/commit."""
    args = ["status", "--short", "--branch", "--untracked-files=all"]
    path = str(path).strip()
    if path:
        args += ["--", path]
    try:
        result = _run_git(workspace_dir, args)
    except FileNotFoundError:
        return "Error: git is not available on this system."
    except subprocess.TimeoutExpired:
        return "Error: git status timed out."
    if result.returncode != 0:
        return _git_error(result, "status")
    return result.stdout.strip() or "(nothing to show)"


def git_diff(workspace_dir: str, path: str = "", staged: str = "false") -> str:
    """Show unstaged changes by default, or staged changes if staged is
    set, optionally scoped to one path. Truncated for the same reason
    run_python/run_shell's output is - a huge diff is still useful
    context even cut short."""
    is_staged = str(staged).strip().lower() in ("1", "true", "yes", "on")
    args = ["diff", "--staged"] if is_staged else ["diff"]
    path = str(path).strip()
    if path:
        args += ["--", path]
    try:
        result = _run_git(workspace_dir, args)
    except FileNotFoundError:
        return "Error: git is not available on this system."
    except subprocess.TimeoutExpired:
        return "Error: git diff timed out."
    if result.returncode != 0:
        return _git_error(result, "diff")

    out = result.stdout
    if not out.strip():
        return "(no staged changes)" if is_staged else "(no unstaged changes)"
    if len(out) > _MAX_CHARS:
        out = out[:_MAX_CHARS] + (
            f"\n... [truncated, {len(out)} chars total - narrow with 'path', "
            "or commit in smaller chunks]"
        )
    return out


def git_commit(workspace_dir: str, message: str = "", add_all: str = "false") -> str:
    """Stage (if add_all) and commit with the given message. The message
    goes through a temp file and `git commit -F`, not a shell string, so
    quotes/backticks/`$`/newlines in it are never a hazard."""
    if not message.strip():
        return "Error: 'message' must be non-empty."
    stage_all = str(add_all).strip().lower() in ("1", "true", "yes", "on")

    try:
        if stage_all:
            add_result = _run_git(workspace_dir, ["add", "-A"])
            if add_result.returncode != 0:
                return _git_error(add_result, "add")

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(message)
            msg_path = f.name
        try:
            result = _run_git(workspace_dir, ["commit", "-F", msg_path])
        finally:
            os.unlink(msg_path)
    except FileNotFoundError:
        return "Error: git is not available on this system."
    except subprocess.TimeoutExpired:
        return "Error: git commit timed out."

    if result.returncode != 0:
        return _git_error(result, "commit")
    return result.stdout.strip() or "Committed."


def make_git_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="git_status",
            description=(
                "Show a short, branch-aware git status (staged/unstaged/untracked "
                "files) for the current directory (see run_shell for changing it)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional: scope to one file/directory."}
                },
                "required": [],
            },
            handler=lambda path="": git_status(workspace_dir, path),
        ),
        ToolSpec(
            name="git_diff",
            description=(
                "Show a git diff: unstaged changes by default, staged changes if "
                "staged='true', optionally scoped to one path."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional: scope to one file/directory."},
                    "staged": {"type": "string", "description": "'true' to show staged changes instead of unstaged (default 'false')."},
                },
                "required": [],
            },
            handler=lambda path="", staged="false": git_diff(workspace_dir, path, staged),
        ),
        ToolSpec(
            name="git_commit",
            description=(
                "Commit with the given message - safe for multi-line messages or "
                "ones containing quotes/backticks/$variables, since it never goes "
                "through a shell string. Set add_all='true' to stage every change "
                "first (git add -A); otherwise only what's already staged is committed."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message."},
                    "add_all": {"type": "string", "description": "'true' to 'git add -A' before committing (default 'false')."},
                },
                "required": ["message"],
            },
            handler=lambda message="", add_all="false": git_commit(workspace_dir, message, add_all),
        ),
    ]
