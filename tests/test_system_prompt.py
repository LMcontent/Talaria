from talaria.notes import add_note
from talaria.roles import ROLES
from talaria.system_prompt import build_system


def test_no_notes_returns_the_bare_role_prompt(tmp_path):
    notes_file = str(tmp_path / ".notes.json")
    assert build_system("assistant", notes_file) == ROLES["assistant"]["system"]


def test_notes_present_appends_a_hint_not_the_notes_themselves(tmp_path):
    notes_file = str(tmp_path / ".notes.json")
    add_note(notes_file, "likes dark mode")

    system = build_system("assistant", notes_file)

    assert system.startswith(ROLES["assistant"]["system"])
    assert "recall" in system
    # The actual note text must NOT be force-injected — that's the whole
    # point: a fresh, unrelated chat shouldn't start out clogged with
    # facts from some other task. The model pulls it in itself via recall
    # if it decides it's relevant.
    assert "likes dark mode" not in system
