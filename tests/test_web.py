import json
import os
import threading

import pytest

import talaria.web as web
from talaria.config import Config
from talaria.providers.base import ProviderResponse
from tests.conftest import InterruptibleProvider, RaisingProvider, ScriptedProvider


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


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    """Returns a function that builds a Flask test client backed by a
    ScriptedProvider with the given queued responses, so each test controls
    exactly what the "model" says without any real network/API calls.
    """

    def build(responses, **config_overrides):
        config = make_config(tmp_path, **config_overrides)
        provider = ScriptedProvider(responses)
        monkeypatch.setattr(web, "make_provider", lambda cfg: provider)
        app = web.create_app(config)
        return app.test_client(), config, provider

    return build


@pytest.fixture
def app_factory_with_provider(tmp_path, monkeypatch):
    """Like app_factory, but takes a ready-made provider instance directly
    — for tests that need a provider that raises rather than one driven by
    ScriptedProvider's script.
    """

    def build(provider, **config_overrides):
        config = make_config(tmp_path, **config_overrides)
        monkeypatch.setattr(web, "make_provider", lambda cfg: provider)
        app = web.create_app(config)
        return app.test_client(), config

    return build


def test_index_page_loads(app_factory):
    client, _, _ = app_factory([])
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Talaria" in resp.data


def test_index_page_shows_provider_and_model(app_factory):
    client, _, _ = app_factory([], provider="openai_compat", openai_compat_model="gpt-5.6-luna")
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert "openai_compat" in body
    assert "gpt-5.6-luna" in body


def test_index_page_shows_claude_model_when_that_provider_is_active(app_factory):
    client, _, _ = app_factory([], provider="claude", claude_model="claude-opus-5")
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert "claude-opus-5" in body


def test_chat_rejects_empty_message(app_factory):
    client, _, _ = app_factory([])
    resp = client.post("/api/chat", json={"message": "  "})
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_chat_returns_reply_and_persists_history(app_factory):
    client, config, _ = app_factory([ProviderResponse(text="hi there", tool_calls=[])])

    resp = client.post("/api/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.get_json()["reply"] == "hi there"

    with open(config.memory_file, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved[0] == {"role": "user", "content": "hello"}
    assert saved[1]["content"] == "hi there"


def test_chat_error_does_not_leave_a_partial_turn(app_factory_with_provider):
    client, config = app_factory_with_provider(RaisingProvider(RuntimeError("boom")))

    resp = client.post("/api/chat", json={"message": "hello"})

    assert resp.status_code == 500
    assert "boom" in resp.get_json()["error"]
    assert client.get("/api/history").get_json()["turns"] == []


def test_chat_stream_error_returns_clean_json_before_any_streaming(app_factory_with_provider):
    client, config = app_factory_with_provider(RaisingProvider(RuntimeError("boom")))

    resp = client.post("/api/chat/stream", json={"message": "hello"})

    assert resp.status_code == 500
    assert "boom" in resp.get_json()["error"]
    assert client.get("/api/history").get_json()["turns"] == []


def test_chat_stream_streams_full_reply(app_factory):
    client, config, _ = app_factory([ProviderResponse(text="streamed answer", tool_calls=[])])

    resp = client.post("/api/chat/stream", json={"message": "hello"})

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert body == "streamed answer"


def test_chat_stream_rejects_empty_message(app_factory):
    client, _, _ = app_factory([])
    resp = client.post("/api/chat/stream", json={"message": ""})
    assert resp.status_code == 400


def test_history_endpoint_lists_seeded_turns(app_factory):
    client, _, _ = app_factory([ProviderResponse(text="hi", tool_calls=[])])
    client.post("/api/chat", json={"message": "hello"})

    resp = client.get("/api/history")

    turns = resp.get_json()["turns"]
    assert turns == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi"},
    ]


def test_reset_clears_history(app_factory):
    client, config, _ = app_factory([ProviderResponse(text="hi", tool_calls=[])])
    client.post("/api/chat", json={"message": "hello"})

    resp = client.post("/api/reset")

    assert resp.get_json() == {"ok": True}
    assert client.get("/api/history").get_json()["turns"] == []


def test_role_get_and_post(app_factory):
    client, _, _ = app_factory([])

    current = client.get("/api/role").get_json()
    assert current["current"] == "assistant"
    assert "researcher" in current["roles"]

    switched = client.post("/api/role", json={"role": "researcher"})
    assert switched.get_json()["current"] == "researcher"


def test_role_post_rejects_unknown_role(app_factory):
    client, _, _ = app_factory([])
    resp = client.post("/api/role", json={"role": "not-a-role"})
    assert resp.status_code == 400


def test_tools_endpoint_lists_builtin_tools(app_factory):
    client, _, _ = app_factory([])
    names = [t["name"] for t in client.get("/api/tools").get_json()["tools"]]
    assert "web_search" in names
    assert "run_python" in names
    assert "install_package" in names
    assert "remember" in names
    assert "propose_skill" in names


def test_stop_returns_409_when_nothing_is_generating(app_factory):
    client, _, _ = app_factory([])
    resp = client.post("/api/chat/stop")
    assert resp.status_code == 409


def test_stop_cancels_generation_mid_stream(app_factory_with_provider):
    provider = InterruptibleProvider(["one ", "two ", "three "])
    client, config = app_factory_with_provider(provider)

    result: dict = {}

    def do_request():
        resp = client.post("/api/chat/stream", json={"message": "go"})
        result["status"] = resp.status_code
        result["body"] = resp.get_data(as_text=True)

    t = threading.Thread(target=do_request)
    t.start()

    assert provider.first_chunk_sent.wait(timeout=5), "provider never emitted its first chunk"
    stop_resp = client.post("/api/chat/stop")
    assert stop_resp.status_code == 200
    provider.may_continue.set()

    t.join(timeout=5)
    assert not t.is_alive(), "request thread never finished"

    # Only the chunk that streamed out before the stop request took effect
    # made it into the response body — generation was actually cut short,
    # not just hidden client-side.
    assert result["status"] == 200
    assert result["body"] == "one "

    turns = client.get("/api/history").get_json()["turns"]
    assert turns[-1] == {"role": "assistant", "text": "one "}

    # Nothing is generating anymore, so a second stop is a no-op.
    assert client.post("/api/chat/stop").status_code == 409


def test_usage_endpoint_starts_at_zero(app_factory):
    client, _, _ = app_factory([])
    data = client.get("/api/usage").get_json()
    assert data["total_tokens"] == 0
    assert data["calls"] == 0
    assert data["estimated_cost"] is None
    assert data["over_limit"] is False


def test_usage_endpoint_reflects_chat_turns(app_factory):
    client, _, _ = app_factory(
        [ProviderResponse(text="hi", tool_calls=[], usage={"input_tokens": 30, "output_tokens": 10})]
    )
    client.post("/api/chat", json={"message": "hello"})

    data = client.get("/api/usage").get_json()
    assert data["input_tokens"] == 30
    assert data["output_tokens"] == 10
    assert data["total_tokens"] == 40
    assert data["calls"] == 1


def test_usage_endpoint_reports_estimated_cost_when_prices_configured(app_factory):
    client, _, _ = app_factory(
        [ProviderResponse(text="hi", tool_calls=[], usage={"input_tokens": 1_000_000, "output_tokens": 0})],
        token_price_input_per_m=2.0,
    )
    client.post("/api/chat", json={"message": "hello"})

    assert client.get("/api/usage").get_json()["estimated_cost"] == 2.0


def test_open_workspace_creates_dir_and_launches_opener(app_factory, monkeypatch):
    client, config, _ = app_factory([])
    calls = []
    monkeypatch.setattr(web.subprocess, "Popen", lambda args: calls.append(args))

    resp = client.post("/api/open-workspace")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["path"] == os.path.abspath(config.workspace_dir)
    assert os.path.isdir(config.workspace_dir)
    assert len(calls) == 1


def test_open_workspace_returns_500_when_opener_fails(app_factory, monkeypatch):
    client, _, _ = app_factory([])

    def boom(args):
        raise OSError("no file manager available")

    monkeypatch.setattr(web.subprocess, "Popen", boom)

    resp = client.post("/api/open-workspace")

    assert resp.status_code == 500
    data = resp.get_json()
    assert data["ok"] is False
    assert "no file manager" in data["error"]


def test_session_token_limit_blocks_further_chats_without_calling_the_provider(app_factory):
    client, _, provider = app_factory(
        [ProviderResponse(text="hi", tool_calls=[], usage={"input_tokens": 80, "output_tokens": 30})],
        max_session_tokens=100,
    )

    first = client.post("/api/chat", json={"message": "hello"})
    assert first.get_json()["reply"] == "hi"
    assert client.get("/api/usage").get_json()["over_limit"] is True

    second = client.post("/api/chat", json={"message": "again"})
    assert "token limit" in second.get_json()["reply"]
    # The first, already-scripted response was consumed by the first
    # request — a second provider.chat() call here would raise inside
    # ScriptedProvider, so reaching a 200 with the limit message at all
    # confirms the provider was never contacted a second time.
    assert len(provider.calls) == 1
