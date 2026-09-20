import requests

import talaria.tools.web as web_mod
from talaria.tools.web import make_web_tools, web_fetch, web_search
from talaria.user_agent import USER_AGENT


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeJSONResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_web_fetch_presents_as_a_real_browser_not_as_talaria(monkeypatch):
    # Regression test: the old UA literally said "compatible; Talaria/0.1",
    # which announces this as a bot to any site that looks — some blocked
    # it outright regardless of anything else about the request.
    captured = {}

    def fake_get(*args, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse("<html><body>hello</body></html>")

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    result = web_fetch("https://example.com")

    assert result == "hello"
    assert captured["headers"]["User-Agent"] == USER_AGENT
    assert "Talaria" not in captured["headers"]["User-Agent"]
    assert "Accept-Language" in captured["headers"]


def test_web_search_uses_the_same_realistic_headers(monkeypatch):
    captured = {}

    def fake_get(*args, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse("<html><body></body></html>")

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    web_search("test query")

    assert captured["headers"]["User-Agent"] == USER_AGENT
    assert "Talaria" not in captured["headers"]["User-Agent"]


def test_web_fetch_and_browser_open_share_the_same_user_agent():
    # The whole point of factoring USER_AGENT out to its own module: both
    # entry points present as the same ordinary browser, not two different
    # Talaria-specific fingerprints that could each give it away and would
    # need updating separately.
    import talaria.tools.browser as browser_mod

    assert web_mod.USER_AGENT == browser_mod.USER_AGENT


def test_web_search_uses_google_when_both_credentials_are_configured(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeJSONResponse({
            "items": [
                {"title": "Провод ПКСВ 2х0,5 — купить", "link": "https://example.com/wire", "snippet": "Цена: 45 руб/м"},
            ]
        })

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    result = web_search("провод ПКСВ 2х0,5 цена", google_api_key="test-key", google_cx="test-cx")

    assert captured["url"] == web_mod._GOOGLE_CSE_URL
    assert captured["params"]["key"] == "test-key"
    assert captured["params"]["cx"] == "test-cx"
    assert captured["params"]["q"] == "провод ПКСВ 2х0,5 цена"
    assert "example.com/wire" in result
    assert "Цена: 45 руб/м" in result


def test_web_search_falls_back_to_duckduckgo_without_full_google_credentials(monkeypatch):
    captured = {"google_called": False, "ddg_called": False}

    def fake_get(url, *args, **kwargs):
        if url == web_mod._GOOGLE_CSE_URL:
            captured["google_called"] = True
            return _FakeJSONResponse({"items": []})
        captured["ddg_called"] = True
        return _FakeResponse("<html><body></body></html>")

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    # Only one of the two credentials set — must not attempt Google with a
    # missing cx (the API would just reject it), fall back cleanly instead.
    web_search("test query", google_api_key="test-key", google_cx=None)

    assert captured["google_called"] is False
    assert captured["ddg_called"] is True


def test_web_search_google_reports_a_clear_error_on_request_failure(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    result = web_search("test query", google_api_key="test-key", google_cx="test-cx")

    assert "Error" in result
    assert "Google search failed" in result


def test_web_search_google_with_no_results(monkeypatch):
    monkeypatch.setattr(web_mod.requests, "get", lambda *a, **k: _FakeJSONResponse({}))

    result = web_search("test query", google_api_key="test-key", google_cx="test-cx")

    assert result == "No results found."


def test_make_web_tools_names_and_search_handler_passes_through_credentials(monkeypatch):
    tools = make_web_tools(google_search_api_key="test-key", google_search_cx="test-cx")
    assert {t.name for t in tools} == {"web_search", "web_fetch"}

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        return _FakeJSONResponse({"items": []})

    monkeypatch.setattr(web_mod.requests, "get", fake_get)

    search_tool = next(t for t in tools if t.name == "web_search")
    search_tool.handler(query="anything")

    assert captured["url"] == web_mod._GOOGLE_CSE_URL
