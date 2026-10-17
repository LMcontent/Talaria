import os

from talaria.tools.errbook import errbook_add, errbook_list, errbook_lookup, make_errbook_tools


def test_add_requires_both_fields(tmp_path):
    assert "Error" in errbook_add(str(tmp_path), error_signature="", solution="x")
    assert "Error" in errbook_add(str(tmp_path), error_signature="x", solution="")


def test_add_then_lookup_roundtrip(tmp_path):
    msg = errbook_add(str(tmp_path), error_signature="ModuleNotFoundError: foo", solution="pip install foo")
    assert "ErrEntry #1 saved" in msg

    result = errbook_lookup(str(tmp_path), query="ModuleNotFoundError foo")
    assert "pip install foo" in result
    assert os.path.isfile(os.path.join(str(tmp_path), ".errbook.json"))


def test_lookup_below_threshold_is_no_match(tmp_path):
    errbook_add(str(tmp_path), error_signature="ModuleNotFoundError: foo", solution="pip install foo")
    assert "NO MATCH" in errbook_lookup(str(tmp_path), query="completely unrelated query text")


def test_same_signature_updates_instead_of_duplicating(tmp_path):
    errbook_add(str(tmp_path), error_signature="timeout error", solution="increase timeout")
    msg = errbook_add(str(tmp_path), error_signature="timeout error", solution="retry with backoff")
    assert "Updated existing entry" in msg
    assert "retry with backoff" in errbook_lookup(str(tmp_path), query="timeout error")


def test_list_empty_and_populated(tmp_path):
    assert errbook_list(str(tmp_path)) == "(errbook is empty)"
    errbook_add(str(tmp_path), error_signature="timeout error", solution="increase timeout")
    assert "timeout error" in errbook_list(str(tmp_path))


def test_make_errbook_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_errbook_tools(str(tmp_path))}
    assert names == {"errbook_add", "errbook_lookup", "errbook_list"}
