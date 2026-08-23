import os


class WorkspaceError(Exception):
    pass


def resolve_path(workspace_dir: str, relative_path: str) -> str:
    """Resolve relative_path inside workspace_dir, refusing to escape it."""
    os.makedirs(workspace_dir, exist_ok=True)
    base = os.path.realpath(workspace_dir)
    target = os.path.realpath(os.path.join(base, relative_path))
    if target != base and not target.startswith(base + os.sep):
        raise WorkspaceError(f"Path escapes workspace: {relative_path}")
    return target
