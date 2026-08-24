import os
import subprocess
import sys

from talaria.sandbox import ensure_sandbox, list_packages, sandbox_dir, sandbox_python


def test_sandbox_dir_is_a_hidden_subdir_of_the_workspace(tmp_path):
    assert sandbox_dir(str(tmp_path)) == os.path.join(str(tmp_path), ".sandbox")


def test_sandbox_python_path_shape(tmp_path):
    path = sandbox_python(str(tmp_path))
    assert path.startswith(sandbox_dir(str(tmp_path)))
    assert "python" in os.path.basename(path).lower()


def test_list_packages_before_creation():
    assert "not created yet" in list_packages("/nonexistent/workspace/for/this/test")


def test_ensure_sandbox_creates_a_working_python(sandbox_workspace):
    python_path = sandbox_python(sandbox_workspace)
    assert os.path.isfile(python_path)

    result = subprocess.run([python_path, "-c", "print(1 + 1)"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "2"


def test_ensure_sandbox_is_idempotent(sandbox_workspace):
    # Calling it again for the same workspace must not recreate the venv,
    # just return the same interpreter path immediately.
    assert ensure_sandbox(sandbox_workspace) == sandbox_python(sandbox_workspace)


def test_list_packages_after_creation_shows_pip(sandbox_workspace):
    output = list_packages(sandbox_workspace).lower()
    assert "pip" in output


def test_sandbox_python_is_not_talarias_own_interpreter(sandbox_workspace):
    python_path = sandbox_python(sandbox_workspace)
    assert os.path.realpath(python_path) != os.path.realpath(sys.executable)
