import threading
import time

from talaria import notes as notes_mod
from talaria.notes import add_note, forget_note, load_notes


def test_load_notes_missing_file_returns_empty(tmp_path):
    assert load_notes(str(tmp_path / "nope.json")) == []


def test_add_note_then_recall(tmp_path):
    path = str(tmp_path / ".notes.json")
    msg = add_note(path, "likes dark mode")
    assert "0" in msg

    notes = load_notes(path)
    assert len(notes) == 1
    assert notes[0]["text"] == "likes dark mode"
    assert "created_at" in notes[0]


def test_forget_note_valid_index(tmp_path):
    path = str(tmp_path / ".notes.json")
    add_note(path, "first")
    add_note(path, "second")

    msg = forget_note(path, 0)
    assert "first" in msg

    remaining = load_notes(path)
    assert len(remaining) == 1
    assert remaining[0]["text"] == "second"


def test_forget_note_invalid_index_leaves_notes_untouched(tmp_path):
    path = str(tmp_path / ".notes.json")
    add_note(path, "first")

    msg = forget_note(path, 5)
    assert "Error" in msg
    assert len(load_notes(path)) == 1

    msg_negative = forget_note(path, -1)
    assert "Error" in msg_negative


def test_concurrent_remembers_do_not_lose_an_update(tmp_path, monkeypatch):
    # Regression test for the exact race STATE_LOCK exists to prevent: two
    # `remember` calls firing in the same turn (now that talaria/agent.py
    # can run tool calls in parallel) must not both load the same starting
    # list and clobber each other's save. Widen the load-to-save window
    # with an artificial sleep so the race would actually manifest if the
    # lock were missing.
    path = str(tmp_path / ".notes.json")
    original_load = notes_mod.load_notes

    def slow_load(p):
        data = original_load(p)
        time.sleep(0.05)
        return data

    monkeypatch.setattr(notes_mod, "load_notes", slow_load)

    threads = [threading.Thread(target=add_note, args=(path, f"fact {i}")) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(original_load(path)) == 5
