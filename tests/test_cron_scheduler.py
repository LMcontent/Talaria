import json
import os
from datetime import datetime, timezone

from talaria.config import Config
from talaria.cron_scheduler import EXCLUDED_TOOLS, build_cron_tools, _tick
from talaria.providers.base import ProviderResponse
from talaria.tools.cron import cron_add, load_jobs
from talaria.usage import UsageTracker
from tests.conftest import ScriptedProvider


def make_config(tmp_path, **overrides) -> Config:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    fields = dict(
        provider="fake",
        workspace_dir=str(tmp_path / "workspace"),
        memory_file=str(tmp_path / ".history.json"),
        notes_file=str(tmp_path / ".notes.json"),
        claude_api_key=None,
        claude_model="x",
        claude_show_thinking=False,
        claude_effort="",
        openai_compat_base_url="http://example.invalid",
        openai_compat_api_key=None,
        openai_compat_model="x",
        openai_compat_dns_pin=False,
        openai_compat_dns_servers=[],
        openai_compat_timeout_seconds=120.0,
        confirm_code_exec=False,
        max_history_turns=30,
        default_role="assistant",
        skills_dir=str(skills_dir),
        web_host="127.0.0.1",
        web_port=0,
    )
    fields.update(overrides)
    return Config(**fields)


def test_build_cron_tools_excludes_risky_tools(tmp_path):
    config = make_config(tmp_path)
    provider = ScriptedProvider([])

    tools = build_cron_tools(config, provider)

    names = {t.name for t in tools}
    assert names & EXCLUDED_TOOLS == set()
    assert "cron_add" in names
    assert "web_search" in names


def test_tick_fires_a_due_job_and_logs_it(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    cron_add(config.workspace_dir, "* * * * *", "say hi", name="Every minute")

    now = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    provider = ScriptedProvider([ProviderResponse(text="hi there", tool_calls=[])])
    usage = UsageTracker()

    _tick(config, provider, usage, now=now)

    jobs = load_jobs(config.workspace_dir)
    assert jobs[0]["last_run"] == now.isoformat()
    assert jobs[0]["last_fired_minute"] == now.isoformat()

    log_path = os.path.join(config.workspace_dir, ".cron_log.json")
    with open(log_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    assert entries[0]["reply"] == "hi there"
    assert entries[0]["name"] == "Every minute"


def test_tick_does_not_fire_twice_for_the_same_minute(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    cron_add(config.workspace_dir, "* * * * *", "say hi")

    now = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    provider = ScriptedProvider([ProviderResponse(text="hi", tool_calls=[])])
    usage = UsageTracker()

    _tick(config, provider, usage, now=now)
    # Second tick, same minute: must NOT call the provider again (it would
    # raise — ScriptedProvider ran out of scripted responses — if it did).
    _tick(config, provider, usage, now=now)

    log_path = os.path.join(config.workspace_dir, ".cron_log.json")
    with open(log_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1


def test_tick_fires_again_the_next_minute_it_matches(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    cron_add(config.workspace_dir, "* * * * *", "say hi")

    provider = ScriptedProvider(
        [ProviderResponse(text="one", tool_calls=[]), ProviderResponse(text="two", tool_calls=[])]
    )
    usage = UsageTracker()

    _tick(config, provider, usage, now=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))
    _tick(config, provider, usage, now=datetime(2024, 1, 1, 9, 1, tzinfo=timezone.utc))

    log_path = os.path.join(config.workspace_dir, ".cron_log.json")
    with open(log_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert [e["reply"] for e in entries] == ["one", "two"]


def test_tick_skips_disabled_jobs(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    cron_add(config.workspace_dir, "* * * * *", "say hi")
    from talaria.tools.cron import cron_toggle

    cron_toggle(config.workspace_dir, "1", "false")

    provider = ScriptedProvider([])  # must not be called
    usage = UsageTracker()
    _tick(config, provider, usage, now=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))

    assert not os.path.exists(os.path.join(config.workspace_dir, ".cron_log.json"))


def test_tick_skips_jobs_whose_schedule_does_not_match(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    cron_add(config.workspace_dir, "0 3 * * *", "say hi")  # only at 3am

    provider = ScriptedProvider([])  # must not be called
    usage = UsageTracker()
    _tick(config, provider, usage, now=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc))

    assert not os.path.exists(os.path.join(config.workspace_dir, ".cron_log.json"))


def test_tick_is_a_noop_with_no_jobs(tmp_path):
    config = make_config(tmp_path)
    provider = ScriptedProvider([])
    usage = UsageTracker()
    _tick(config, provider, usage)  # must not raise
