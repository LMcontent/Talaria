"""A dedicated virtual environment that run_python/install_package use,
kept separate from the environment Talaria itself runs in.

This isolates *installed packages* only: a pip install here can't corrupt
or fight with Talaria's own dependencies, and a bad/unwanted install is
contained to a throwaway environment you can wipe by deleting this
directory. It is NOT an OS-level sandbox — code still runs with your
normal user permissions and full filesystem/network access, same as
Talaria itself. See the run_python docstring in tools/code_exec.py.
"""

import os
import subprocess
import venv

_SANDBOX_DIRNAME = ".sandbox"


def sandbox_dir(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, _SANDBOX_DIRNAME)


def sandbox_python(workspace_dir: str) -> str:
    """Path to the sandbox venv's python executable — may not exist yet,
    see ensure_sandbox()."""
    base = sandbox_dir(workspace_dir)
    if os.name == "nt":
        return os.path.join(base, "Scripts", "python.exe")
    return os.path.join(base, "bin", "python")


def ensure_sandbox(workspace_dir: str) -> str:
    """Create the sandbox venv on first use if it doesn't exist yet, and
    return the path to its python executable.

    Raises RuntimeError with a clear message on failure — deliberately not
    falling back to running code in Talaria's own environment, which would
    silently defeat the whole point of keeping installs isolated.
    """
    python_path = sandbox_python(workspace_dir)
    if os.path.isfile(python_path):
        return python_path

    base = sandbox_dir(workspace_dir)
    print(f"[sandbox] setting up isolated environment at {base} (first use, may take a few seconds)...")
    try:
        venv.create(base, with_pip=True)
    except Exception as e:
        raise RuntimeError(
            f"could not create sandbox venv at {base}: {e}. On some Linux "
            "distros this needs a separate 'python3-venv' package installed."
        ) from e

    if not os.path.isfile(python_path):
        raise RuntimeError(f"sandbox venv created at {base} but its python executable is missing")

    print("[sandbox] ready.")
    return python_path


def list_packages(workspace_dir: str) -> str:
    """List packages installed in the sandbox — used by /venv in the CLI."""
    python_path = sandbox_python(workspace_dir)
    if not os.path.isfile(python_path):
        return "(sandbox not created yet — nothing installed)"
    result = subprocess.run(
        [python_path, "-m", "pip", "list", "--format=freeze"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() or "(no packages installed)"
