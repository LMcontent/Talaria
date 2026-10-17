import os
import subprocess

import pytest

from talaria.tools.git_tools import git_commit, git_diff, git_status, make_git_tools
from talaria.tools.shell_exec import run_shell, shell_reset


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)


@pytest.fixture
def repo(tmp_path):
    ws = str(tmp_path)
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "test@example.com")
    _git(ws, "config", "user.name", "Test")
    return ws


def test_status_outside_a_repo_is_an_error(tmp_path):
    result = git_status(str(tmp_path / "not-a-repo-ws"))
    assert "Error" in result
    assert "git" in result.lower()


def test_status_on_a_fresh_repo(repo):
    result = git_status(repo)
    assert "Error" not in result
    assert result  # at least a "## No commits yet on <branch>" line


def test_status_shows_an_untracked_file(repo):
    with open(os.path.join(repo, "new.txt"), "w") as f:
        f.write("hi")
    result = git_status(repo)
    assert "new.txt" in result


def test_status_can_be_scoped_to_a_path(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    with open(os.path.join(repo, "b.txt"), "w") as f:
        f.write("b")
    result = git_status(repo, path="a.txt")
    assert "a.txt" in result
    assert "b.txt" not in result


def test_diff_with_no_changes(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    assert "no unstaged changes" in git_diff(repo)


def test_diff_shows_unstaged_changes(repo):
    path = os.path.join(repo, "a.txt")
    with open(path, "w") as f:
        f.write("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    with open(path, "w") as f:
        f.write("a\nb\n")

    result = git_diff(repo)

    assert "+b" in result


def test_diff_staged_vs_unstaged(repo):
    path = os.path.join(repo, "a.txt")
    with open(path, "w") as f:
        f.write("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    with open(path, "w") as f:
        f.write("a\nb\n")
    _git(repo, "add", "-A")

    assert "+b" in git_diff(repo, staged="true")
    assert "no unstaged changes" in git_diff(repo, staged="false")


def test_commit_requires_a_message(repo):
    assert "Error" in git_commit(repo, message="")
    assert "Error" in git_commit(repo, message="   ")


def test_commit_requires_staged_changes(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    result = git_commit(repo, message="nothing staged")
    assert "Error" in result


def test_commit_add_all_stages_and_commits(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")

    result = git_commit(repo, message="first commit", add_all="true")

    assert "Error" not in result
    log = _git(repo, "log", "--oneline", "-1").stdout
    assert "first commit" in log
    assert "a.txt" not in git_status(repo)
    assert git_diff(repo) == "(no unstaged changes)"


def test_commit_only_commits_what_was_already_staged(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    with open(os.path.join(repo, "b.txt"), "w") as f:
        f.write("b")
    _git(repo, "add", "a.txt")

    git_commit(repo, message="only a")

    log = _git(repo, "show", "--stat", "--oneline", "-1").stdout
    assert "a.txt" in log
    assert "b.txt" not in log


def test_commit_message_with_quotes_backticks_and_newlines_survives_intact(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    tricky = 'Fix `foo` and "bar"\n\n- handles $HOME and $(whoami)\n- second paragraph'

    result = git_commit(repo, message=tricky, add_all="true")

    assert "Error" not in result
    full_message = _git(repo, "log", "-1", "--pretty=%B").stdout.strip()
    assert full_message == tricky


def test_make_git_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_git_tools(str(tmp_path))}
    assert names == {"git_status", "git_diff", "git_commit"}


def test_git_tools_follow_run_shells_tracked_cwd(repo):
    sub = os.path.join(repo, "sub")
    os.makedirs(sub)
    _git(repo, "add", "-A")
    with open(os.path.join(sub, "inner.txt"), "w") as f:
        f.write("x")

    run_shell(repo, "cd sub", require_confirmation=False)
    result = git_status(repo)

    assert "inner.txt" in result

    shell_reset(repo)
    result_after_reset = git_status(repo)
    assert "sub/inner.txt" in result_after_reset or "sub" in result_after_reset
