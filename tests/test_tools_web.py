import talaria.tools.web as web_mod
from talaria.tools.web import web_fetch, web_search
from talaria.user_agent import USER_AGENT


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


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
