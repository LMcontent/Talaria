from datetime import datetime, timezone

from talaria.tools.cron import (
    cron_add,
    cron_list,
    cron_matches,
    cron_remove,
    cron_toggle,
    load_jobs,
    make_cron_tools,
    validate_cron_expression,
)


def test_validate_cron_expression_accepts_common_forms():
    assert validate_cron_expression("* * * * *") is None
    assert validate_cron_expression("0 9 * * 1-5") is None
    assert validate_cron_expression("*/15 * * * *") is None
    assert validate_cron_expression("0,30 8-18 * * *") is None


def test_validate_cron_expression_rejects_bad_forms():
    assert "5 space-separated fields" in validate_cron_expression("* * * *")
    assert "minute" in validate_cron_expression("60 * * * *")
    assert "hour" in validate_cron_expression("0 24 * * *")
    assert "day-of-week" in validate_cron_expression("0 0 * * 7")


def test_cron_matches_exact_minute_and_hour():
    dt = datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc)  # Monday
    assert cron_matches("30 9 * * *", dt)
    assert not cron_matches("31 9 * * *", dt)
    assert not cron_matches("30 10 * * *", dt)


def test_cron_matches_step_and_wildcards():
    assert cron_matches("*/15 * * * *", datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc))
    assert not cron_matches("*/15 * * * *", datetime(2024, 1, 1, 9, 31, tzinfo=timezone.utc))


def test_cron_matches_weekday_restriction():
    monday = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    saturday = datetime(2024, 1, 6, 9, 0, tzinfo=timezone.utc)
    assert cron_matches("0 9 * * 1-5", monday)
    assert not cron_matches("0 9 * * 1-5", saturday)


def test_cron_matches_dom_and_dow_both_restricted_is_or():
    # Standard cron quirk: if both day-of-month and day-of-week are
    # restricted, a match on either is enough.
    # 2024-01-01 is a Monday (dow=1) and day-of-month 1.
    dt = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    assert cron_matches("0 9 1 * 3", dt)  # day-of-month matches, dow (Wed) doesn't
    assert cron_matches("0 9 15 * 1", dt)  # dow (Mon) matches, day-of-month doesn't
    assert not cron_matches("0 9 15 * 3", dt)  # neither matches


def test_cron_add_rejects_invalid_schedule(tmp_path):
    result = cron_add(str(tmp_path), "not a cron expr", "do something")
    assert "Error" in result


def test_cron_add_rejects_empty_prompt(tmp_path):
    result = cron_add(str(tmp_path), "* * * * *", "   ")
    assert "Error" in result


def test_cron_add_list_remove_roundtrip(tmp_path):
    ws = str(tmp_path)
    msg = cron_add(ws, "0 9 * * *", "Check the news", name="Morning check")
    assert "Added cron job #1" in msg
    assert "Morning check" in msg

    listing = cron_list(ws)
    assert "#1" in listing
    assert "Morning check" in listing
    assert "enabled" in listing

    jobs = load_jobs(ws)
    assert len(jobs) == 1
    assert jobs[0]["schedule"] == "0 9 * * *"
    assert jobs[0]["prompt"] == "Check the news"

    removed = cron_remove(ws, "1")
    assert "Removed cron job #1" in removed
    assert cron_list(ws) == "(no cron jobs — use cron_add to schedule one)"


def test_cron_remove_unknown_id(tmp_path):
    assert "Error" in cron_remove(str(tmp_path), "99")


def test_cron_toggle_disables_and_enables(tmp_path):
    ws = str(tmp_path)
    cron_add(ws, "* * * * *", "ping")

    cron_toggle(ws, "1", "false")
    assert load_jobs(ws)[0]["enabled"] is False
    assert "disabled" in cron_list(ws)

    cron_toggle(ws, "1", "true")
    assert load_jobs(ws)[0]["enabled"] is True


def test_make_cron_tools_names(tmp_path):
    names = {t.name for t in make_cron_tools(str(tmp_path))}
    assert names == {"cron_add", "cron_list", "cron_remove", "cron_toggle"}
