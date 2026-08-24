import os
import subprocess
import tempfile

from talaria.providers.base import ToolSpec
from talaria.sandbox import ensure_sandbox

_TIMEOUT = 15
_INSTALL_TIMEOUT = 300
_MAX_CHARS = 4000


def run_python(workspace_dir: str, code: str, require_confirmation: bool = True) -> str:
    """Run a Python snippet in the sandbox venv (talaria/sandbox.py) and
    return its stdout/stderr.

    The sandbox isolates *installed packages* from Talaria's own
    environment — only the standard library is available until
    install_package adds something. It is NOT an OS-level sandbox: the
    snippet still runs with the same OS-level permissions as Talaria
    itself (full filesystem/network access), so only use this with a
    trusted model/provider and be mindful of what you approve.
    """
    if require_confirmation:
        print("\n--- The model wants to run this Python code (in its sandbox venv): ---")
        print(code)
        print("--- end of code ---")
        answer = input("Allow execution? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            return (
                "Execution declined by the user. Do not attempt to run this "
                "(or equivalent) code again without a clear reason and "
                "explaining first what it does and why it's needed."
            )

    try:
        python_path = ensure_sandbox(workspace_dir)
    except RuntimeError as e:
        return f"Error: {e}"

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        script_path = f.name

    try:
        result = subprocess.run(
            [python_path, script_path],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code {result.returncode}]"
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {_TIMEOUT}s"
    finally:
        os.unlink(script_path)

    if len(output) > _MAX_CHARS:
        output = output[:_MAX_CHARS] + f"... [truncated, {len(output)} chars total]"
    return output or "(no output)"


def install_package(workspace_dir: str, package: str, require_confirmation: bool = True) -> str:
    """Install a pip package into the sandbox venv so run_python can import
    it afterwards. Never touches Talaria's own environment — an install
    that goes wrong is contained to the sandbox, which can just be deleted.
    """
    package = package.strip()
    if not package:
        return "Error: package must be a non-empty pip requirement, e.g. 'requests' or 'pandas==2.2.0'."

    if require_confirmation:
        print(f"\n--- The model wants to install into its sandbox venv: {package} ---")
        answer = input("Allow installation? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            return (
                "Installation declined by the user. Do not attempt to install "
                "this (or an equivalent) package again without a clear reason."
            )

    try:
        python_path = ensure_sandbox(workspace_dir)
    except RuntimeError as e:
        return f"Error: {e}"

    try:
        result = subprocess.run(
            [python_path, "-m", "pip", "install", "--", package],
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"Error: installation timed out after {_INSTALL_TIMEOUT}s"

    output = result.stdout[-_MAX_CHARS:]
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr[-_MAX_CHARS:]}"

    if result.returncode != 0:
        return f"Failed to install {package!r} (exit code {result.returncode}):\n{output}"
    return f"Installed {package!r} into the sandbox.\n{output}"


def make_code_tool(workspace_dir: str, require_confirmation: bool = True) -> ToolSpec:
    os.makedirs(workspace_dir, exist_ok=True)
    return ToolSpec(
        name="run_python",
        description=(
            "Execute a Python code snippet in an isolated sandbox virtual "
            "environment (separate from Talaria's own) and return its "
            "stdout/stderr. Only the standard library is available until "
            "you install_package whatever else you need. Runs in the "
            "workspace directory. The user will be asked to approve the "
            "code before it runs."
        ),
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python source code to run."}},
            "required": ["code"],
        },
        handler=lambda code: run_python(workspace_dir, code, require_confirmation),
    )


def make_install_package_tool(workspace_dir: str, require_confirmation: bool = True) -> ToolSpec:
    os.makedirs(workspace_dir, exist_ok=True)
    return ToolSpec(
        name="install_package",
        description=(
            "Install a pip package (e.g. 'pandas' or 'requests==2.32.0') "
            "into run_python's isolated sandbox virtual environment so it "
            "can be imported afterwards. Never touches Talaria's own "
            "environment. The user will be asked to approve the install "
            "before it runs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "A pip requirement specifier, e.g. 'requests' or 'pandas==2.2.0'.",
                }
            },
            "required": ["package"],
        },
        handler=lambda package: install_package(workspace_dir, package, require_confirmation),
    )
