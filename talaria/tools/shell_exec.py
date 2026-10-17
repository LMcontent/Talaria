"""Shell execution for build/test/git workflows run_python can't handle
(its 15s timeout and fresh-subprocess-per-call rule out anything beyond a
quick Python snippet — a real test suite, `pip install`-heavy build, or
`git clone` needs both a longer budget and an actual shell).

NOT an OS-level sandbox, same caveat as run_python: commands run with
Talaria's own OS-level permissions and full filesystem/network access —
only use this with a trusted model/provider. Unlike run_python it also
isn't routed through the isolated sandbox venv; this is a plain shell
rooted at workspace_dir.

"Persistent" here means only the working directory survives across
calls (tracked in a module-level dict keyed by workspace_dir), not a
live interactive process: each call is still its own `bash` subprocess,
started in whatever directory the previous call's own `cd` left behind.
That's a deliberate trade — no backgrounded dev server, no environment
variables surviving between calls — in exchange for never having to
manage a long-lived subprocess's lifetime (startup, zombies, concurrent
access) across arbitrarily many Agent instances (CLI, web, cron,
autonomous, every delegate_task sub-agent). A fresh process (new CLI/web
session, a new autonomous tick, ...) starts back at workspace_dir, same
as run_python already resets on every call; shell_reset does the same
within one process.
"""

import os
import subprocess
import tempfile

from talaria.providers.base import ToolSpec
from talaria.tools.confirmation import CONFIRMATION_LOCK, Confirmation, wants_confirmation as _wants_confirmation

_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 600
_MAX_CHARS = 8000
# A control character makes this effectively impossible for a command's
# own stdout to produce by accident, so splitting on it to recover the
# final $PWD (see run_shell) can't be confused with real output.
_CWD_MARKER = "\x01TALARIA_CWD\x01"

# workspace_dir (realpath) -> last known working directory. Deliberately
# in-memory only, not disk-backed: it's a convenience for "cd once, stay
# there for the next few calls within this run," not state meant to
# survive a restart.
_cwd_by_workspace: dict[str, str] = {}


def run_shell(
    workspace_dir: str, command: str = "", timeout_seconds: str = "", require_confirmation: Confirmation = True
) -> str:
    """Run a shell command via bash. cwd starts at workspace_dir (or
    wherever a previous call's `cd` left it) and the resulting directory
    is tracked for the next call."""
    command = str(command).strip()
    if not command:
        return "Error: 'command' must be a non-empty shell command."

    raw_timeout = str(timeout_seconds).strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else _DEFAULT_TIMEOUT
        if timeout <= 0:
            raise ValueError
    except ValueError:
        return "Error: timeout_seconds must be a positive number."
    timeout = min(timeout, _MAX_TIMEOUT)

    if _wants_confirmation(require_confirmation):
        with CONFIRMATION_LOCK:
            print("\n--- The model wants to run this shell command: ---")
            print(command)
            print("--- end of command ---")
            answer = input("Allow execution? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            return (
                "Execution declined by the user. Do not attempt to run this "
                "(or equivalent) command again without a clear reason and "
                "explaining first what it does and why it's needed."
            )

    base = os.path.realpath(workspace_dir)
    os.makedirs(base, exist_ok=True)
    start_dir = _cwd_by_workspace.get(base, base)
    if not os.path.isdir(start_dir):
        start_dir = base

    # The command runs as its own line(s) in a script rather than being
    # spliced into a one-liner, so nothing about its own quoting/braces
    # needs escaping on our end. The final printf (always reached, via
    # the captured exit code) is what lets a `cd` inside the command
    # actually carry over to the NEXT call despite each call being a
    # fresh subprocess - we read $PWD back out instead of trying to
    # parse "cd" out of the command text ourselves.
    script = (
        f'cd "{start_dir}" || exit 1\n'
        f"{command}\n"
        f"__talaria_rc=$?\n"
        f"printf '\\n{_CWD_MARKER}%s\\n' \"$PWD\"\n"
        f"exit $__talaria_rc\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout:.0f}s"
    except FileNotFoundError:
        return "Error: bash is not available on this system."
    finally:
        os.unlink(script_path)

    stdout = result.stdout
    new_cwd = start_dir
    marker_idx = stdout.rfind(_CWD_MARKER)
    if marker_idx != -1:
        new_cwd = stdout[marker_idx + len(_CWD_MARKER):].strip() or start_dir
        stdout = stdout[:marker_idx].rstrip("\n")
    _cwd_by_workspace[base] = new_cwd

    output = stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if result.returncode != 0:
        output += f"\n[exit code {result.returncode}]"
    if len(output) > _MAX_CHARS:
        output = output[:_MAX_CHARS] + f"... [truncated, {len(output)} chars total]"

    rel = os.path.relpath(new_cwd, base)
    cwd_label = "." if rel in ("", ".") else rel
    return f"[cwd: {cwd_label}]\n" + (output or "(no output)")


def shell_reset(workspace_dir: str) -> str:
    """Forget the tracked working directory, so the next run_shell call
    starts back at workspace_dir."""
    _cwd_by_workspace.pop(os.path.realpath(workspace_dir), None)
    return "Shell directory reset to the workspace root."


def make_shell_tool(workspace_dir: str, require_confirmation: Confirmation = True) -> ToolSpec:
    os.makedirs(workspace_dir, exist_ok=True)
    return ToolSpec(
        name="run_shell",
        description=(
            "Run a shell command (bash) directly - for git, build tools, "
            "test runners, package managers, or anything else run_python's "
            "15-second Python-only sandbox can't handle. Runs with "
            "Talaria's own OS-level permissions (full filesystem/network "
            "access), same caveat as run_python. The working directory "
            "persists across calls (a 'cd' in one call affects the next "
            "one); use shell_reset to go back to the workspace root. "
            "Default timeout 120s, override with timeout_seconds (max "
            "600). The user will be asked to approve the command before "
            "it runs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "timeout_seconds": {
                    "type": "string",
                    "description": "Optional timeout override in seconds, up to 600 (default 120).",
                },
            },
            "required": ["command"],
        },
        handler=lambda command="", timeout_seconds="": run_shell(
            workspace_dir, command, timeout_seconds, require_confirmation
        ),
    )


def make_shell_reset_tool(workspace_dir: str) -> ToolSpec:
    return ToolSpec(
        name="shell_reset",
        description="Reset run_shell's tracked working directory back to the workspace root.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=lambda: shell_reset(workspace_dir),
    )
