"""Snapshot/restore the agent's persistent state around a risky experiment.

Two roots get captured together, because both can end up polluted by a bad
experiment: `workspace_dir` (conversation history, notes, written files) and
`./state` (relative to the process's cwd — where most skills persist their
own JSON, e.g. errbook/feedback_loop/meaning_cache). Restoring only one of
the two would leave stale "lessons" from the bad run in the other.
"""

import os
import re
import shutil
import time

from talaria.providers.base import ToolSpec

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SKIP = {".checkpoints", ".sandbox"}


def _state_dir() -> str:
    # Matches skills' own os.path.join(".", "state") resolution.
    return os.path.abspath("state")


def _checkpoints_root(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, ".checkpoints")


def _validate_name(name: str) -> str | None:
    if not _NAME_RE.match(str(name or "")):
        return "Error: name must be 1-64 characters, letters/digits/underscore/dash only."
    return None


def checkpoint_save(workspace_dir: str, name: str = "") -> str:
    """Snapshot workspace_dir and ./state under a named checkpoint."""
    err = _validate_name(name)
    if err:
        return err

    dest = os.path.join(_checkpoints_root(workspace_dir), name)
    overwritten = os.path.isdir(dest)
    if overwritten:
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    ws_dest = os.path.join(dest, "workspace")
    os.makedirs(ws_dest, exist_ok=True)
    n_files = 0
    if os.path.isdir(workspace_dir):
        for entry in os.listdir(workspace_dir):
            if entry in _SKIP:
                continue
            src = os.path.join(workspace_dir, entry)
            dst = os.path.join(ws_dest, entry)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
                n_files += sum(len(files) for _, _, files in os.walk(dst))
            else:
                shutil.copy2(src, dst)
                n_files += 1

    state_src = _state_dir()
    had_state = os.path.isdir(state_src)
    if had_state:
        shutil.copytree(state_src, os.path.join(dest, "state"))
        n_files += sum(len(files) for _, _, files in os.walk(os.path.join(dest, "state")))

    verb = "Overwrote" if overwritten else "Saved"
    return (
        f"{verb} checkpoint '{name}': {n_files} file(s) "
        f"(workspace{' + state' if had_state else ', no state dir found'}). "
        "Restore it later with checkpoint_restore if the experiment goes badly."
    )


def checkpoint_restore(workspace_dir: str, name: str = "") -> str:
    """Restore workspace_dir and ./state from a named checkpoint, discarding
    everything written since it was saved."""
    err = _validate_name(name)
    if err:
        return err

    src = os.path.join(_checkpoints_root(workspace_dir), name)
    if not os.path.isdir(src):
        return f"Error: no checkpoint named '{name}' (see checkpoint_list)."

    ws_src = os.path.join(src, "workspace")
    if os.path.isdir(workspace_dir):
        for entry in os.listdir(workspace_dir):
            if entry in _SKIP:
                continue
            path = os.path.join(workspace_dir, entry)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    os.makedirs(workspace_dir, exist_ok=True)
    if os.path.isdir(ws_src):
        for entry in os.listdir(ws_src):
            s, d = os.path.join(ws_src, entry), os.path.join(workspace_dir, entry)
            shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)

    state_dst = _state_dir()
    if os.path.isdir(state_dst):
        shutil.rmtree(state_dst)
    state_src = os.path.join(src, "state")
    if os.path.isdir(state_src):
        shutil.copytree(state_src, state_dst)

    return (
        f"Restored checkpoint '{name}'. Files on disk are back to that point. "
        "IMPORTANT: this session's in-memory conversation still holds the "
        "bad experiment's turns — run /reset (or start a new conversation) "
        "so the restored history actually takes effect."
    )


def checkpoint_list(workspace_dir: str) -> str:
    """List saved checkpoints with when they were saved."""
    root = _checkpoints_root(workspace_dir)
    if not os.path.isdir(root):
        return "(no checkpoints saved)"
    names = sorted(os.listdir(root))
    if not names:
        return "(no checkpoints saved)"
    lines = []
    for n in names:
        mtime = os.path.getmtime(os.path.join(root, n))
        lines.append(f"- {n} (saved {time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))})")
    return "\n".join(lines)


def checkpoint_discard(workspace_dir: str, name: str = "") -> str:
    """Delete a saved checkpoint once it's no longer needed."""
    err = _validate_name(name)
    if err:
        return err
    dest = os.path.join(_checkpoints_root(workspace_dir), name)
    if not os.path.isdir(dest):
        return f"Error: no checkpoint named '{name}' (see checkpoint_list)."
    shutil.rmtree(dest)
    return f"Discarded checkpoint '{name}'."


def make_checkpoint_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="checkpoint_save",
            description=(
                "Snapshot the agent's current persistent state (conversation "
                "history, notes, workspace files, and skills' saved state) "
                "under a name, before a risky/experimental task. Restore it "
                "with checkpoint_restore if the experiment goes badly, to "
                "discard everything written since."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short id for this checkpoint, e.g. 'before-bom-experiment'."}
                },
                "required": ["name"],
            },
            handler=lambda name: checkpoint_save(workspace_dir, name),
        ),
        ToolSpec(
            name="checkpoint_restore",
            description=(
                "Restore persistent state from a named checkpoint, discarding "
                "all history/notes/files/skill-state written since it was "
                "saved. Tell the user to /reset afterwards so the live "
                "conversation reflects the rollback too."
            ),
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Checkpoint name, from checkpoint_list."}},
                "required": ["name"],
            },
            handler=lambda name: checkpoint_restore(workspace_dir, name),
        ),
        ToolSpec(
            name="checkpoint_list",
            description="List saved checkpoints with their save time.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: checkpoint_list(workspace_dir),
        ),
        ToolSpec(
            name="checkpoint_discard",
            description="Delete a saved checkpoint that's no longer needed.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Checkpoint name, from checkpoint_list."}},
                "required": ["name"],
            },
            handler=lambda name: checkpoint_discard(workspace_dir, name),
        ),
    ]
