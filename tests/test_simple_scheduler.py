import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(REPO_ROOT, "skills", "simple_scheduler.py")


@pytest.fixture
def scheduler(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("talaria_skill_simple_scheduler_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules.pop(spec.name, None)
    return module


def test_add_requires_name_and_instruction(scheduler):
    assert "Error" in scheduler.task_add(name="", instruction="x")
    assert "Error" in scheduler.task_add(name="x", instruction="")


def test_add_rejects_bad_interval(scheduler):
    assert "Error" in scheduler.task_add(name="n", instruction="i", interval_hours="-1")
    assert "Error" in scheduler.task_add(name="n", instruction="i", interval_hours="abc")


def test_add_rejects_bad_due_iso(scheduler):
    assert "Error" in scheduler.task_add(name="n", instruction="i", due_iso="not-a-date")


def test_add_one_time_task_is_due_immediately(scheduler):
    scheduler.task_add(name="ping", instruction="say hi")
    result = scheduler.task_tick()
    assert "1 task(s) DUE" in result
    assert "say hi" in result


def test_tick_marks_one_time_task_ran_and_does_not_redue(scheduler):
    scheduler.task_add(name="ping", instruction="say hi")
    scheduler.task_tick()
    second = scheduler.task_tick()
    assert "No active tasks" in second
    assert "[ran]" in scheduler.task_list()


def test_recurring_task_reschedules_instead_of_completing(scheduler):
    scheduler.task_add(name="heartbeat", instruction="check in", interval_hours="1", due_iso="2020-01-01T00:00")
    first = scheduler.task_tick()
    assert "1 task(s) DUE" in first
    listing = scheduler.task_list()
    assert "every 1.0h" in listing
    assert "[ran]" not in listing


def test_tick_on_empty_queue(scheduler):
    assert scheduler.task_tick() == "(no tasks)"


def test_tick_reports_next_upcoming_when_nothing_due(scheduler):
    scheduler.task_add(name="later", instruction="do it", due_iso="2099-01-01T00:00")
    assert "No tasks due now" in scheduler.task_tick()
    assert "later" in scheduler.task_tick()


def test_done_removes_task(scheduler):
    scheduler.task_add(name="ping", instruction="say hi")
    msg = scheduler.task_done(task_id="1")
    assert "Task #1 removed" in msg
    assert scheduler.task_list() == "(no tasks)"


def test_done_rejects_bad_id_and_unknown_id(scheduler):
    assert "Error" in scheduler.task_done(task_id="abc")
    assert "Not found" in scheduler.task_done(task_id="99")


def test_tools_expose_expected_names(scheduler):
    names = {t.name for t in scheduler.TOOLS}
    assert names == {"task_add", "task_list", "task_tick", "task_done"}
