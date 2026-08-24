from talaria.tools.code_exec import install_package, run_python


def test_run_python_declines_without_calling_the_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    result = run_python(str(tmp_path / "ws"), "print('hi')")

    assert "declined" in result
    # No sandbox should have been created for a declined run.
    assert not (tmp_path / "ws" / ".sandbox").exists()


def test_install_package_declines_without_calling_the_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    result = install_package(str(tmp_path / "ws"), "requests")

    assert "declined" in result
    assert not (tmp_path / "ws" / ".sandbox").exists()


def test_install_package_rejects_empty_package_name(tmp_path):
    result = install_package(str(tmp_path / "ws"), "   ", require_confirmation=False)
    assert "Error" in result


def test_run_python_executes_in_the_sandbox_and_returns_stdout(sandbox_workspace):
    result = run_python(sandbox_workspace, "print(2 + 2)", require_confirmation=False)
    assert result.strip() == "4"


def test_run_python_reports_a_traceback_and_nonzero_exit(sandbox_workspace):
    result = run_python(sandbox_workspace, "raise ValueError('boom')", require_confirmation=False)
    assert "ValueError" in result
    assert "boom" in result
    assert "[exit code" in result


def test_run_python_cannot_import_talarias_own_packages(sandbox_workspace):
    # The sandbox is a clean venv — Talaria's own third-party dependencies
    # (e.g. flask, anthropic) must NOT leak into it, since the whole point
    # is that the agent's installs stay isolated from Talaria's own.
    result = run_python(sandbox_workspace, "import flask", require_confirmation=False)
    assert "ModuleNotFoundError" in result or "[exit code" in result
