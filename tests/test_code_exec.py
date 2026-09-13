import threading
import time

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


def test_run_python_resolves_a_callable_confirmation_on_every_call(sandbox_workspace, monkeypatch):
    # require_confirmation can be a live callable (the web UI's Safe/Extreme
    # toggle) rather than a fixed bool, so flipping it must take effect on
    # the very next call with no rebuild involved.
    safe = {"on": True}
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    declined = run_python(sandbox_workspace, "print(1)", require_confirmation=lambda: safe["on"])
    assert "declined" in declined

    safe["on"] = False
    result = run_python(sandbox_workspace, "print(1)", require_confirmation=lambda: safe["on"])
    assert result.strip() == "1"


def test_install_package_resolves_a_callable_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    result = install_package(str(tmp_path / "ws"), "requests", require_confirmation=lambda: True)
    assert "declined" in result
    assert not (tmp_path / "ws" / ".sandbox").exists()


def test_concurrent_confirmations_are_serialized_not_interleaved(tmp_path, monkeypatch):
    # Regression test for the exact race CONFIRMATION_LOCK exists to
    # prevent: with tool calls now able to run in parallel (see
    # talaria/agent.py), two run_python confirmation prompts firing at
    # once must not race for the same input() — they should queue up one
    # at a time. Track how many fake input() calls are "in flight"
    # simultaneously; a fully-serialized run never sees more than one.
    active = {"count": 0, "max": 0}
    guard = threading.Lock()

    def fake_input(prompt=""):
        with guard:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.05)
        with guard:
            active["count"] -= 1
        return "n"

    monkeypatch.setattr("builtins.input", fake_input)

    threads = [
        threading.Thread(target=run_python, args=(str(tmp_path / f"ws{i}"), "print(1)"))
        for i in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert active["max"] == 1
