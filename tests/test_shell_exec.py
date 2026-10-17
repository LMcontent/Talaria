import os

from talaria.tools.shell_exec import make_shell_reset_tool, make_shell_tool, run_shell, shell_reset


def test_rejects_empty_command(tmp_path):
    result = run_shell(str(tmp_path), "   ", require_confirmation=False)
    assert "Error" in result


def test_rejects_bad_timeout(tmp_path):
    result = run_shell(str(tmp_path), "echo hi", timeout_seconds="nope", require_confirmation=False)
    assert "Error" in result


def test_runs_a_command_and_returns_stdout(tmp_path):
    result = run_shell(str(tmp_path), "echo hello", require_confirmation=False)
    assert "hello" in result
    assert "[cwd: .]" in result


def test_nonzero_exit_code_is_reported(tmp_path):
    result = run_shell(str(tmp_path), "exit 7", require_confirmation=False)
    assert "[exit code 7]" in result


def test_stderr_is_included(tmp_path):
    result = run_shell(str(tmp_path), "echo oops 1>&2", require_confirmation=False)
    assert "oops" in result
    assert "[stderr]" in result


def test_command_runs_inside_the_workspace_by_default(tmp_path):
    (tmp_path / "marker.txt").write_text("x")
    result = run_shell(str(tmp_path), "ls", require_confirmation=False)
    assert "marker.txt" in result


def test_cd_persists_to_the_next_call(tmp_path):
    os.makedirs(tmp_path / "sub")
    (tmp_path / "sub" / "inner.txt").write_text("x")

    first = run_shell(str(tmp_path), "cd sub", require_confirmation=False)
    assert "[cwd: sub]" in first

    second = run_shell(str(tmp_path), "ls", require_confirmation=False)
    assert "inner.txt" in second
    assert "[cwd: sub]" in second


def test_shell_reset_returns_to_workspace_root(tmp_path):
    os.makedirs(tmp_path / "sub")
    run_shell(str(tmp_path), "cd sub", require_confirmation=False)

    shell_reset(str(tmp_path))

    result = run_shell(str(tmp_path), "pwd", require_confirmation=False)
    assert "[cwd: .]" in result


def test_two_workspaces_track_cwd_independently(tmp_path):
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    os.makedirs(ws_a / "sub")
    os.makedirs(ws_b / "other")

    run_shell(str(ws_a), "cd sub", require_confirmation=False)
    run_shell(str(ws_b), "cd other", require_confirmation=False)

    result_a = run_shell(str(ws_a), "pwd", require_confirmation=False)
    result_b = run_shell(str(ws_b), "pwd", require_confirmation=False)

    assert "[cwd: sub]" in result_a
    assert "[cwd: other]" in result_b


def test_timeout_is_enforced(tmp_path):
    result = run_shell(str(tmp_path), "sleep 5", timeout_seconds="1", require_confirmation=False)
    assert "Error" in result
    assert "timed out" in result


def test_long_output_is_truncated(tmp_path):
    result = run_shell(str(tmp_path), "head -c 9000 /dev/zero | tr '\\0' 'x'", require_confirmation=False)
    assert "truncated" in result


def test_declines_without_running(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    marker = tmp_path / "should_not_exist.txt"

    result = run_shell(str(tmp_path), f"touch {marker.name}")

    assert "declined" in result
    assert not marker.exists()


def test_resolves_a_callable_confirmation_on_every_call(tmp_path, monkeypatch):
    safe = {"on": True}
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    declined = run_shell(str(tmp_path), "echo hi", require_confirmation=lambda: safe["on"])
    assert "declined" in declined

    safe["on"] = False
    result = run_shell(str(tmp_path), "echo hi", require_confirmation=lambda: safe["on"])
    assert "hi" in result


def test_make_shell_tool_exposes_expected_name(tmp_path):
    tool = make_shell_tool(str(tmp_path), require_confirmation=False)
    assert tool.name == "run_shell"
    assert "hi" in tool.handler(command="echo hi")


def test_make_shell_reset_tool_exposes_expected_name(tmp_path):
    tool = make_shell_reset_tool(str(tmp_path))
    assert tool.name == "shell_reset"
    assert "reset" in tool.handler().lower()
