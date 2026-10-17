from talaria.tools.idea_lab import lab_exp, lab_hyp, lab_next, lab_show, make_idea_lab_tools


def test_hyp_requires_idea(tmp_path):
    assert "Error" in lab_hyp(str(tmp_path), idea="  ")


def test_hyp_then_show(tmp_path):
    msg = lab_hyp(str(tmp_path), idea="try X", expected="faster results")
    assert "Hypothesis H1 registered" in msg
    assert "H1 [ ]: try X" in lab_show(str(tmp_path))


def test_exp_rejects_bad_hyp_id_and_verdict(tmp_path):
    lab_hyp(str(tmp_path), idea="try X")
    assert "Error" in lab_exp(str(tmp_path), hyp_id="abc", verdict="keep")
    assert "Error" in lab_exp(str(tmp_path), hyp_id="1", verdict="maybe")
    assert "Error" in lab_exp(str(tmp_path), hyp_id="99", verdict="keep")


def test_exp_logs_and_updates_status(tmp_path):
    lab_hyp(str(tmp_path), idea="try X")
    msg = lab_exp(str(tmp_path), hyp_id="1", what="ran it", result="worked", verdict="keep")
    assert "Experiment E1 logged for H1 -> KEEP" in msg
    assert "[OK]" in lab_show(str(tmp_path))


def test_next_on_empty_lab(tmp_path):
    assert "Лаборатория пуста" in lab_next(str(tmp_path))


def test_next_suggests_oldest_todo(tmp_path):
    lab_hyp(str(tmp_path), idea="try X")
    lab_hyp(str(tmp_path), idea="try Y")
    assert "H1" in lab_next(str(tmp_path))


def test_make_idea_lab_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_idea_lab_tools(str(tmp_path))}
    assert names == {"lab_hyp", "lab_exp", "lab_show", "lab_next"}
