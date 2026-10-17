from talaria.tools.feedback_loop import feedback_rate, feedback_report, make_feedback_tools


def test_rate_validates_score(tmp_path):
    assert "Error" in feedback_rate(str(tmp_path), score="abc")
    assert "Error" in feedback_rate(str(tmp_path), score="6")


def test_rate_defaults_task_type_to_general(tmp_path):
    msg = feedback_rate(str(tmp_path), score="4")
    assert "Saved rating 4: general" in msg


def test_report_empty(tmp_path):
    assert feedback_report(str(tmp_path)) == "(no ratings yet)"


def test_report_flags_weakest_area(tmp_path):
    feedback_rate(str(tmp_path), score="2", task_type="research")
    feedback_rate(str(tmp_path), score="5", task_type="code")

    report = feedback_report(str(tmp_path))
    assert "ATTENTION: weakest area 'research'" in report


def test_report_filters_by_task_type(tmp_path):
    feedback_rate(str(tmp_path), score="2", task_type="research")
    feedback_rate(str(tmp_path), score="5", task_type="code")

    report = feedback_report(str(tmp_path), task_type="code")
    assert "research" not in report
    assert "code" in report


def test_make_feedback_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_feedback_tools(str(tmp_path))}
    assert names == {"feedback_rate", "feedback_report"}
