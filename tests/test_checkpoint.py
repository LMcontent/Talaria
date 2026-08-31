import os

from talaria.tools.checkpoint import (
    checkpoint_discard,
    checkpoint_list,
    checkpoint_restore,
    checkpoint_save,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_save_invalid_name_returns_error(tmp_path):
    msg = checkpoint_save(str(tmp_path / "workspace"), "bad name!")
    assert "Error" in msg


def test_restore_missing_checkpoint_returns_error(tmp_path):
    msg = checkpoint_restore(str(tmp_path / "workspace"), "nope")
    assert "Error" in msg
    assert "no checkpoint" in msg


def test_list_empty_when_no_checkpoints(tmp_path):
    assert checkpoint_list(str(tmp_path / "workspace")) == "(no checkpoints saved)"


def test_save_and_restore_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, ".history.json"), '[{"role": "user", "content": "hi"}]')
    _write("state/errbook.json", '{"entries": []}')

    msg = checkpoint_save(ws, "before-experiment")
    assert "Saved checkpoint 'before-experiment'" in msg
    assert "state" in msg

    # Pollute both roots, as a bad experiment would.
    _write(os.path.join(ws, ".history.json"), '[{"role": "assistant", "content": "wrong"}]')
    _write(os.path.join(ws, "new_junk.txt"), "should be removed on restore")
    _write("state/errbook.json", '{"entries": ["bad lesson"]}')
    _write("state/new_state_file.json", "should also be removed on restore")

    msg = checkpoint_restore(ws, "before-experiment")
    assert "Restored checkpoint 'before-experiment'" in msg
    assert "/reset" in msg

    with open(os.path.join(ws, ".history.json"), encoding="utf-8") as f:
        assert f.read() == '[{"role": "user", "content": "hi"}]'
    assert not os.path.exists(os.path.join(ws, "new_junk.txt"))

    with open("state/errbook.json", encoding="utf-8") as f:
        assert f.read() == '{"entries": []}'
    assert not os.path.exists("state/new_state_file.json")


def test_save_skips_its_own_checkpoints_dir_and_sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, "keep.txt"), "keep me")
    _write(os.path.join(ws, ".sandbox", "venv_marker"), "big venv stuff")

    checkpoint_save(ws, "first")
    second_msg = checkpoint_save(ws, "second")

    # The second checkpoint's snapshot must not contain a nested copy of the
    # first checkpoint or the sandbox venv.
    second_ws = os.path.join(ws, ".checkpoints", "second", "workspace")
    assert not os.path.exists(os.path.join(second_ws, ".checkpoints"))
    assert not os.path.exists(os.path.join(second_ws, ".sandbox"))
    assert "Saved" in second_msg


def test_save_overwrites_existing_checkpoint_of_same_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, "a.txt"), "v1")
    checkpoint_save(ws, "cp")

    _write(os.path.join(ws, "a.txt"), "v2")
    msg = checkpoint_save(ws, "cp")
    assert "Overwrote checkpoint 'cp'" in msg

    _write(os.path.join(ws, "a.txt"), "v3-live")
    checkpoint_restore(ws, "cp")
    with open(os.path.join(ws, "a.txt"), encoding="utf-8") as f:
        assert f.read() == "v2"


def test_discard_removes_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, "a.txt"), "x")
    checkpoint_save(ws, "cp")
    assert "cp" in checkpoint_list(ws)

    msg = checkpoint_discard(ws, "cp")
    assert "Discarded checkpoint 'cp'" in msg
    assert checkpoint_list(ws) == "(no checkpoints saved)"

    msg = checkpoint_discard(ws, "cp")
    assert "Error" in msg


def test_list_shows_multiple_checkpoints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, "a.txt"), "x")
    checkpoint_save(ws, "one")
    checkpoint_save(ws, "two")

    out = checkpoint_list(ws)
    assert "one" in out
    assert "two" in out


def test_save_with_no_state_dir_still_saves_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = str(tmp_path / "workspace")
    _write(os.path.join(ws, "a.txt"), "x")

    msg = checkpoint_save(ws, "cp")
    assert "Saved" in msg
    assert "no state dir found" in msg
