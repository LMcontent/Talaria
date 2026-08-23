import subprocess
import sys
import tempfile

from talaria.providers.base import ToolSpec

_TIMEOUT = 15
_MAX_CHARS = 4000


def run_python(workspace_dir: str, code: str, require_confirmation: bool = True) -> str:
    """Run a Python snippet in a subprocess and return its stdout/stderr.

    Runs with the workspace directory as cwd, under a wall-clock timeout.
    This is NOT a sandbox — the snippet runs with the same OS-level
    permissions as Talaria itself, so only use this with a trusted model
    and be mindful of what code you let it execute.
    """
    if require_confirmation:
        print("\n--- The model wants to run this Python code: ---")
        print(code)
        print("--- end of code ---")
        answer = input("Allow execution? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            return (
                "Execution declined by the user. Do not attempt to run this "
                "(or equivalent) code again without a clear reason and "
                "explaining first what it does and why it's needed."
            )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        script_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, script_path],
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
        import os

        os.unlink(script_path)

    if len(output) > _MAX_CHARS:
        output = output[:_MAX_CHARS] + f"... [truncated, {len(output)} chars total]"
    return output or "(no output)"


def make_code_tool(workspace_dir: str, require_confirmation: bool = True) -> ToolSpec:
    import os

    os.makedirs(workspace_dir, exist_ok=True)
    return ToolSpec(
        name="run_python",
        description=(
            "Execute a Python code snippet and return its stdout/stderr. "
            "Runs in the workspace directory. Use for calculations, data "
            "processing, or generating files with libraries like pandas. "
            "The user will be asked to approve the code before it runs."
        ),
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python source code to run."}},
            "required": ["code"],
        },
        handler=lambda code: run_python(workspace_dir, code, require_confirmation),
    )
