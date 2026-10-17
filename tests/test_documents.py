import os

from talaria.tools.documents import edit_document, list_files, make_document_tools, read_document, write_document


def test_write_then_read_roundtrip(tmp_path):
    write_document(str(tmp_path), "notes.txt", "hello world")
    assert read_document(str(tmp_path), "notes.txt") == "hello world"


def test_read_missing_file(tmp_path):
    assert "Error" in read_document(str(tmp_path), "nope.txt")
    assert "not found" in read_document(str(tmp_path), "nope.txt")


def test_write_creates_parent_directories(tmp_path):
    write_document(str(tmp_path), "sub/dir/notes.txt", "hi")
    assert os.path.isfile(os.path.join(str(tmp_path), "sub", "dir", "notes.txt"))


def test_path_traversal_is_refused(tmp_path):
    (tmp_path / "secret.txt").write_text("top secret")
    assert "Error" in read_document(str(tmp_path), "../secret.txt")


def test_list_files_empty_and_populated(tmp_path):
    assert list_files(str(tmp_path)) == "(empty)"
    write_document(str(tmp_path), "a.txt", "x")
    assert "a.txt" in list_files(str(tmp_path))


def test_edit_document_requires_existing_file(tmp_path):
    result = edit_document(str(tmp_path), "nope.txt", old_text="x", new_text="y")
    assert "Error" in result
    assert "not found" in result


def test_edit_document_requires_old_text(tmp_path):
    write_document(str(tmp_path), "a.txt", "content")
    assert "Error" in edit_document(str(tmp_path), "a.txt", old_text="", new_text="y")


def test_edit_document_replaces_unique_match(tmp_path):
    write_document(str(tmp_path), "a.txt", "hello world")
    msg = edit_document(str(tmp_path), "a.txt", old_text="world", new_text="there")
    assert "Replaced 1 occurrence" in msg
    assert read_document(str(tmp_path), "a.txt") == "hello there"


def test_edit_document_no_match(tmp_path):
    write_document(str(tmp_path), "a.txt", "hello world")
    result = edit_document(str(tmp_path), "a.txt", old_text="nope", new_text="x")
    assert "Error" in result
    assert "not found" in result


def test_edit_document_refuses_ambiguous_match_without_replace_all(tmp_path):
    write_document(str(tmp_path), "a.txt", "foo bar foo")
    result = edit_document(str(tmp_path), "a.txt", old_text="foo", new_text="baz")
    assert "Error" in result
    assert "occurs 2 times" in result
    assert read_document(str(tmp_path), "a.txt") == "foo bar foo"


def test_edit_document_replace_all(tmp_path):
    write_document(str(tmp_path), "a.txt", "foo bar foo")
    msg = edit_document(str(tmp_path), "a.txt", old_text="foo", new_text="baz", replace_all="true")
    assert "Replaced 2 occurrences" in msg
    assert read_document(str(tmp_path), "a.txt") == "baz bar baz"


def test_edit_document_can_delete_text(tmp_path):
    write_document(str(tmp_path), "a.txt", "hello world")
    edit_document(str(tmp_path), "a.txt", old_text=" world", new_text="")
    assert read_document(str(tmp_path), "a.txt") == "hello"


def test_edit_document_refuses_path_traversal(tmp_path):
    (tmp_path / "secret.txt").write_text("top secret")
    result = edit_document(str(tmp_path), "../secret.txt", old_text="top", new_text="x")
    assert "Error" in result


def test_make_document_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_document_tools(str(tmp_path))}
    assert names == {"read_document", "write_document", "edit_document", "list_files"}
