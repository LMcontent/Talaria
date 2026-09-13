import os

from talaria.chats import (
    auto_title,
    create_chat,
    delete_chat,
    history_path,
    list_chats,
    rename_chat,
    set_chat_role,
    touch_chat,
)


def test_list_chats_empty_when_none_created(tmp_path):
    assert list_chats(str(tmp_path)) == []


def test_create_chat_returns_and_persists_an_entry(tmp_path):
    chat = create_chat(str(tmp_path), title="First task")
    assert chat["title"] == "First task"
    assert "id" in chat and "created" in chat and "updated" in chat

    chats = list_chats(str(tmp_path))
    assert len(chats) == 1
    assert chats[0]["id"] == chat["id"]


def test_create_chat_defaults_to_new_chat_title(tmp_path):
    chat = create_chat(str(tmp_path))
    assert chat["title"] == "New chat"


def test_create_chat_stores_its_own_role(tmp_path):
    chat = create_chat(str(tmp_path), role="researcher")
    assert chat["role"] == "researcher"
    assert list_chats(str(tmp_path))[0]["role"] == "researcher"


def test_set_chat_role_updates_it_without_bumping_updated(tmp_path):
    chat = create_chat(str(tmp_path), role="assistant")
    before = list_chats(str(tmp_path))[0]["updated"]

    ok = set_chat_role(str(tmp_path), chat["id"], "coder")

    assert ok is True
    entry = list_chats(str(tmp_path))[0]
    assert entry["role"] == "coder"
    assert entry["updated"] == before


def test_set_chat_role_unknown_chat_returns_false(tmp_path):
    assert set_chat_role(str(tmp_path), "nonexistent", "coder") is False


def test_list_chats_sorted_most_recently_updated_first(tmp_path):
    a = create_chat(str(tmp_path), title="A")
    b = create_chat(str(tmp_path), title="B")

    touch_chat(str(tmp_path), a["id"])  # A is now the most recently updated

    chats = list_chats(str(tmp_path))
    assert [c["id"] for c in chats] == [a["id"], b["id"]]


def test_rename_chat(tmp_path):
    chat = create_chat(str(tmp_path), title="Untitled")
    ok = rename_chat(str(tmp_path), chat["id"], "Renamed")
    assert ok is True
    assert list_chats(str(tmp_path))[0]["title"] == "Renamed"


def test_rename_unknown_chat_returns_false(tmp_path):
    assert rename_chat(str(tmp_path), "nonexistent", "x") is False


def test_delete_chat_removes_entry_and_history_file(tmp_path):
    chat = create_chat(str(tmp_path))
    path = history_path(str(tmp_path), chat["id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("[]")

    ok = delete_chat(str(tmp_path), chat["id"])

    assert ok is True
    assert list_chats(str(tmp_path)) == []
    assert not os.path.exists(path)


def test_delete_unknown_chat_returns_false(tmp_path):
    assert delete_chat(str(tmp_path), "nonexistent") is False


def test_history_path_is_scoped_per_chat(tmp_path):
    p1 = history_path(str(tmp_path), "abc")
    p2 = history_path(str(tmp_path), "def")
    assert p1 != p2
    assert p1.endswith("abc.json")


def test_auto_title_collapses_whitespace_and_truncates():
    assert auto_title("hello   world") == "hello world"
    long_msg = "x" * 100
    title = auto_title(long_msg, max_len=10)
    assert len(title) == 10
    assert title.endswith("…")


def test_auto_title_empty_message_falls_back_to_new_chat():
    assert auto_title("   ") == "New chat"
