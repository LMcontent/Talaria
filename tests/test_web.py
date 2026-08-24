import json

import pytest

import talaria.web as web
from talaria.config import Config
from talaria.providers.base import ProviderResponse
from tests.conftest import RaisingProvider, ScriptedProvider


def make_config(tmp_path) -> Config:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return Config(
        provider="fake",
        workspace_dir=str(tmp_path / "workspace"),
        memory_file=str(tmp_path / ".history.json"),
        notes_file=str(tmp_path / ".notes.json"),
        claude_api_key=None,
        claude_model="x",
        openai_compat_base_url="http://example.invalid",
        openai_compat_api_key=None,
        openai_compat_model="x",
        openai_compat_dns_pin=False,
        openai_compat_dns_servers=[],
        confirm_code_exec=False,
        max_history_turns=30,
        default_role="assistant",
        skills_dir=str(skills_dir),
        web_host="127.0.0.1",
        web_port=0,
    )


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    """Returns a function that builds a Flask test client backed by a
    ScriptedProvider with the given queued responses, so each test controls
    exactly what the "model" says without any real network/API calls.
    """

    def build(responses):
        config = make_config(tmp_path)
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

    def build(provider):
        config = make_config(tmp_path)
        monkeypatch.setattr(web, "make_provider", lambda cfg: provider)
        app = web.create_app(config)
        return app.test_client(), config

    return build


def test_index_page_loads(app_factory):
    client, _, _ = app_factory([])
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Talaria" in resp.data


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
    assert "remember" in names
    assert "propose_skill" in names
