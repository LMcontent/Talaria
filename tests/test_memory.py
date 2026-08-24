import os

from talaria.memory import clear_history, load_history, save_history
from talaria.providers.base import ToolCall


def test_load_history_missing_file_returns_empty(tmp_path):
    assert load_history(str(tmp_path / "nope.json")) == []


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "sub" / ".history.json")
    history = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "calling a tool",
            "tool_calls": [ToolCall(id="1", name="echo", input={"x": 1})],
        },
        {"role": "tool", "tool_call_id": "1", "name": "echo", "content": "1"},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]

    save_history(path, history)
    assert os.path.isfile(path)

    loaded = load_history(path)
    assert loaded[0] == {"role": "user", "content": "hi"}
    assert loaded[1]["tool_calls"][0] == ToolCall(id="1", name="echo", input={"x": 1})
    assert loaded[2] == {"role": "tool", "tool_call_id": "1", "name": "echo", "content": "1"}
    assert loaded[3]["tool_calls"] == []


def test_clear_history_removes_file_if_present(tmp_path):
    path = str(tmp_path / ".history.json")
    save_history(path, [{"role": "user", "content": "hi"}])
    assert os.path.isfile(path)
    clear_history(path)
    assert not os.path.isfile(path)


def test_clear_history_missing_file_is_a_noop(tmp_path):
    clear_history(str(tmp_path / "nope.json"))  # must not raise
