import json
import os

import pytest

from talaria.autonomous import EXCLUDED_TOOLS, build_autonomous_tools, main, tick
from talaria.config import Config
from talaria.providers.base import ProviderResponse
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


def test_build_autonomous_tools_excludes_risky_tools(tmp_path):
    config = make_config(tmp_path)
    provider = ScriptedProvider([])

    tools = build_autonomous_tools(config, provider)

    names = {t.name for t in tools}
    assert names & EXCLUDED_TOOLS == set()
    # Sanity: the filter didn't accidentally strip everything.
    assert "web_search" in names
    assert "goal_add" in names
    assert "remember" in names


def test_tick_returns_none_and_skips_provider_when_no_active_goal(tmp_path, capsys):
    config = make_config(tmp_path)
    provider = ScriptedProvider([])  # must not be called
    usage = UsageTracker()

    result = tick(config, provider, usage)

    assert result is None
    assert "no active goals" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(config.workspace_dir, ".autonomous_log.json"))


def test_tick_works_the_focused_goal_and_logs_it(tmp_path, capsys):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    from talaria.tools.goals import goal_add

    goal_add(config.workspace_dir, title="Research a niche", priority="high")

    provider = ScriptedProvider([ProviderResponse(text="did some research", tool_calls=[])])
    usage = UsageTracker()

    result = tick(config, provider, usage)

    assert result == "did some research"
    out = capsys.readouterr().out
    assert "[autonomous] check-in" in out
    assert "Research a niche" in out

    log_path = os.path.join(config.workspace_dir, ".autonomous_log.json")
    with open(log_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    assert entries[0]["reply"] == "did some research"
    assert "Research a niche" in entries[0]["focus"]

    # The prompt the "model" actually received says which tools are absent
    # and why, so the model doesn't just repeatedly try and fail to call them.
    sent_prompt = provider.calls[0]["history"][0]["content"]
    assert "run_python" in sent_prompt
    assert "unattended" in sent_prompt


def test_tick_appends_to_existing_log(tmp_path):
    config = make_config(tmp_path)
    os.makedirs(config.workspace_dir, exist_ok=True)
    from talaria.tools.goals import goal_add

    goal_add(config.workspace_dir, title="A")
    tick(config, ScriptedProvider([ProviderResponse(text="one", tool_calls=[])]), UsageTracker())
    tick(config, ScriptedProvider([ProviderResponse(text="two", tool_calls=[])]), UsageTracker())

    log_path = os.path.join(config.workspace_dir, ".autonomous_log.json")
    with open(log_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert [e["reply"] for e in entries] == ["one", "two"]


def test_main_exits_immediately_when_autonomous_mode_is_disabled(tmp_path, monkeypatch, capsys):
    import talaria.autonomous as autonomous_module

    config = make_config(tmp_path, autonomous_mode=False)
    monkeypatch.setattr(autonomous_module, "load_config", lambda: config)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert "AUTONOMOUS_MODE is not enabled" in capsys.readouterr().out
