import threading
import time

from talaria.tools import goals as goals_mod
from talaria.tools.goals import goal_add, goal_focus, goal_list, goal_update


def test_add_creates_goal_with_defaults(tmp_path):
    msg = goal_add(str(tmp_path), title="Earn money")
    assert "Added goal #1 'Earn money' (medium)" in msg


def test_add_requires_title(tmp_path):
    msg = goal_add(str(tmp_path), title="  ")
    assert "Error" in msg


def test_add_rejects_bad_priority(tmp_path):
    msg = goal_add(str(tmp_path), title="X", priority="urgent")
    assert "Error" in msg


def test_add_subgoal_under_parent(tmp_path):
    goal_add(str(tmp_path), title="Earn money", priority="high")
    msg = goal_add(str(tmp_path), title="Research niches", parent_id="1")
    assert "Added goal #2 'Research niches' (medium) under #1" in msg


def test_add_rejects_nonexistent_parent(tmp_path):
    msg = goal_add(str(tmp_path), title="X", parent_id="99")
    assert "Error" in msg
    assert "#99" in msg


def test_list_empty(tmp_path):
    assert goal_list(str(tmp_path)) == "(no goals yet)"


def test_list_shows_tree_with_indentation(tmp_path):
    goal_add(str(tmp_path), title="Earn money", priority="high")
    goal_add(str(tmp_path), title="Research niches", parent_id="1", priority="medium")
    goal_add(str(tmp_path), title="Sell product", parent_id="1", priority="low")

    out = goal_list(str(tmp_path))
    lines = out.split("\n")
    assert lines[0] == "#1 [active] (high) Earn money"
    # Children indented and ordered by priority (medium before low).
    assert lines[1] == "  #2 [active] (medium) Research niches"
    assert lines[2] == "  #3 [active] (low) Sell product"


def test_list_filters_by_status(tmp_path):
    goal_add(str(tmp_path), title="A")
    goal_add(str(tmp_path), title="B")
    goal_update(str(tmp_path), id="2", status="done")

    out = goal_list(str(tmp_path), status="active")
    assert "A" in out
    assert "B" not in out


def test_list_rejects_bad_status_filter(tmp_path):
    goal_add(str(tmp_path), title="A")
    msg = goal_list(str(tmp_path), status="urgent")
    assert "Error" in msg


def test_list_reports_no_match_for_valid_but_absent_status(tmp_path):
    goal_add(str(tmp_path), title="A")
    assert goal_list(str(tmp_path), status="dropped") == "(no goals with status 'dropped')"


def test_update_changes_status_priority_and_note(tmp_path):
    goal_add(str(tmp_path), title="A", priority="low")
    msg = goal_update(str(tmp_path), id="1", status="paused", priority="high", note="waiting on X")
    assert "status=paused" in msg
    assert "priority=high" in msg
    assert "note added" in msg

    out = goal_list(str(tmp_path))
    assert "[paused] (high)" in out


def test_update_requires_a_field(tmp_path):
    goal_add(str(tmp_path), title="A")
    msg = goal_update(str(tmp_path), id="1")
    assert "Error" in msg


def test_update_unknown_id(tmp_path):
    msg = goal_update(str(tmp_path), id="5", status="done")
    assert "Error" in msg


def test_update_rejects_bad_status(tmp_path):
    goal_add(str(tmp_path), title="A")
    msg = goal_update(str(tmp_path), id="1", status="urgent")
    assert "Error" in msg


def test_focus_with_no_goals(tmp_path):
    assert "no active goals" in goal_focus(str(tmp_path))


def test_focus_picks_highest_priority_leaf(tmp_path):
    goal_add(str(tmp_path), title="Low prio", priority="low")
    goal_add(str(tmp_path), title="High prio", priority="high")

    out = goal_focus(str(tmp_path))
    assert "FOCUS: #2 High prio" in out


def test_focus_drills_past_umbrella_into_active_child(tmp_path):
    goal_add(str(tmp_path), title="Earn money", priority="high")
    goal_add(str(tmp_path), title="Research niches", parent_id="1", priority="low")

    out = goal_focus(str(tmp_path))
    # The parent has an active child, so it's not itself actionable — the
    # child is the real next step even though its own priority is lower.
    assert "FOCUS: #1 Earn money > #2 Research niches" in out


def test_focus_falls_back_to_parent_once_children_are_done(tmp_path):
    goal_add(str(tmp_path), title="Earn money", priority="high")
    goal_add(str(tmp_path), title="Research niches", parent_id="1", priority="low")
    goal_update(str(tmp_path), id="2", status="done")

    out = goal_focus(str(tmp_path))
    assert "FOCUS: #1 Earn money" in out
    assert ">" not in out


def test_focus_shows_recent_notes(tmp_path):
    goal_add(str(tmp_path), title="A")
    goal_update(str(tmp_path), id="1", note="tried approach X, didn't work")

    out = goal_focus(str(tmp_path))
    assert "tried approach X" in out


def test_concurrent_goal_add_does_not_lose_an_update_or_collide_ids(tmp_path, monkeypatch):
    # Regression test for the exact race STATE_LOCK exists to prevent: two
    # goal_add calls firing in the same turn (tool calls can now run in
    # parallel, see talaria/agent.py) must not both read the same stale
    # max-id and each save their own version over the other's. Widen the
    # load-to-save window with an artificial sleep so the race would
    # actually manifest if the lock were missing.
    ws = str(tmp_path)
    original_load = goals_mod._load

    def slow_load(workspace_dir):
        data = original_load(workspace_dir)
        time.sleep(0.05)
        return data

    monkeypatch.setattr(goals_mod, "_load", slow_load)

    threads = [
        threading.Thread(target=goal_add, args=(ws,), kwargs={"title": f"Goal {i}"}) for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    saved = original_load(ws)
    assert len(saved) == 5
    assert {g["id"] for g in saved} == {1, 2, 3, 4, 5}
