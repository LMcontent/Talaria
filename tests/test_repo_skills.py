"""Exercises the actual skills/ directory shipped in this repo (not just
the synthetic fixtures in test_skills.py) — mainly to lock in that the
json_store migration (state now under WORKSPACE_DIR/state instead of a
cwd-relative ./state) really took for every skill that persists data.
"""

import json
import os

from talaria.skills import load_skills

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")


def test_repo_skills_load_without_errors(capsys):
    tools = load_skills(SKILLS_DIR)

    assert "failed to load" not in capsys.readouterr().out
    names = {t.name for t in tools}
    for expected in [
        "state_set", "state_get", "state_list", "state_delete",
        "errbook_add", "errbook_lookup", "errbook_list",
        "lab_hyp", "lab_exp", "lab_show", "lab_next",
        "shift_end", "shift_start",
        "feedback_rate", "feedback_report",
        "cache_put", "cache_get", "cache_list", "cache_clear",
        "task_add", "task_list", "task_tick", "task_done",
    ]:
        assert expected in names


def test_state_store_skill_persists_under_workspace_dir(monkeypatch, tmp_path):
    workspace = tmp_path / "myworkspace"
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))

    tools = {t.name: t for t in load_skills(SKILLS_DIR)}
    tools["state_set"].handler(key="k", value="v")

    assert tools["state_get"].handler(key="k") == "v"
    state_file = workspace / "state" / "store.json"
    assert state_file.is_file()
    with open(state_file, encoding="utf-8") as f:
        assert json.load(f) == {"k": "v"}


def test_errbook_skill_persists_under_workspace_dir(monkeypatch, tmp_path):
    workspace = tmp_path / "myworkspace"
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))

    tools = {t.name: t for t in load_skills(SKILLS_DIR)}
    tools["errbook_add"].handler(error_signature="ModuleNotFoundError: foo", solution="pip install foo")

    result = tools["errbook_lookup"].handler(query="ModuleNotFoundError foo")
    assert "pip install foo" in result
    assert (workspace / "state" / "errbook.json").is_file()


def test_two_workspace_dirs_stay_isolated(monkeypatch, tmp_path):
    """Different WORKSPACE_DIRs must never see each other's skill state —
    the whole point of moving off a shared cwd-relative ./state."""
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"

    monkeypatch.setenv("WORKSPACE_DIR", str(ws_a))
    tools = {t.name: t for t in load_skills(SKILLS_DIR)}
    tools["state_set"].handler(key="only_in_a", value="1")

    monkeypatch.setenv("WORKSPACE_DIR", str(ws_b))
    assert "Not found" in tools["state_get"].handler(key="only_in_a")
