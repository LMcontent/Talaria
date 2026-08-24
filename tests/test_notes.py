from talaria.notes import add_note, forget_note, format_notes_for_prompt, load_notes


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


def test_format_notes_for_prompt_empty():
    assert format_notes_for_prompt([]) == ""


def test_format_notes_for_prompt_lists_all_with_index():
    notes = [{"text": "a"}, {"text": "b"}]
    text = format_notes_for_prompt(notes)
    assert "[0] a" in text
    assert "[1] b" in text


def test_format_notes_for_prompt_truncates_to_most_recent():
    notes = [{"text": "x" * 2000}, {"text": "y" * 2000}]
    text = format_notes_for_prompt(notes)
    assert len(text) <= 3000 + len("Known facts remembered from previous sessions:\n")
    # Truncation keeps the tail, so the most recently added note survives.
    assert "y" in text
