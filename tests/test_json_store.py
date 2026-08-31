import os

from talaria.json_store import load_json, save_json, state_dir, state_path


def test_state_dir_uses_workspace_dir_env_var(monkeypatch, tmp_path):
    ws = str(tmp_path / "ws")
    monkeypatch.setenv("WORKSPACE_DIR", ws)
    assert state_dir() == os.path.join(ws, "state")


def test_state_dir_defaults_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    assert state_dir() == os.path.join("./workspace", "state")


def test_state_path_joins_filename_under_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    assert state_path("thing.json") == os.path.join(str(tmp_path), "state", "thing.json")


def test_load_json_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    assert load_json("nope.json") is None


def test_load_json_corrupt_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    path = state_path("bad.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert load_json("bad.json") is None


def test_save_then_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    save_json("thing.json", {"a": 1, "b": [1, 2, 3]})
    assert load_json("thing.json") == {"a": 1, "b": [1, 2, 3]}


def test_save_creates_state_dir_if_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    assert not os.path.isdir(state_dir())
    save_json("x.json", [])
    assert os.path.isdir(state_dir())


def test_save_overwrites_existing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    save_json("x.json", {"v": 1})
    save_json("x.json", {"v": 2})
    assert load_json("x.json") == {"v": 2}
