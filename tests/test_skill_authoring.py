from talaria.providers.base import ProviderResponse
from talaria.tools.skill_authoring import make_propose_skill_tool
from tests.conftest import RaisingProvider, ScriptedProvider

VALID_CODE = '''
from talaria.providers.base import ToolSpec

TOOLS = [
    ToolSpec(
        name="greet",
        description="says hi",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "hi",
    )
]
'''

BROKEN_CODE = "this is not valid python ("

CONFLICTING_TOOLSPEC_CODE = '''
class ToolSpec:
    def __init__(self, name, description, input_schema, handler):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

TOOLS = [ToolSpec(name="fake", description="d", input_schema={}, handler=lambda: "x")]
'''


class FakeAgent:
    def __init__(self):
        self.added: list = []

    def add_tools(self, tools):
        self.added.extend(tools)


def _propose(provider, tmp_path, monkeypatch, answer, filename="greet.py", code=VALID_CODE):
    agent = FakeAgent()
    tool = make_propose_skill_tool(provider, str(tmp_path), agent)
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    result = tool.handler(filename=filename, code=code, description="greets the user")
    return result, agent


def test_require_confirmation_false_auto_approves_a_safe_verdict(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: SAFE\nlooks fine.", tool_calls=[])])
    agent = FakeAgent()
    tool = make_propose_skill_tool(provider, str(tmp_path), agent, require_confirmation=False)

    def boom(prompt=""):
        raise AssertionError("input() must not be called when require_confirmation is False")

    monkeypatch.setattr("builtins.input", boom)

    result = tool.handler(filename="greet.py", code=VALID_CODE, description="greets the user")

    assert "Skill saved" in result
    assert [t.name for t in agent.added] == ["greet"]


def test_require_confirmation_false_auto_approves_a_risky_verdict_too(tmp_path, monkeypatch):
    # Mega Extreme mode is deliberately this permissive — it skips the
    # harder RISKY gate as well, not just the plain SAFE one.
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: RISKY\ndeletes files.", tool_calls=[])])
    agent = FakeAgent()
    tool = make_propose_skill_tool(provider, str(tmp_path), agent, require_confirmation=False)

    def boom(prompt=""):
        raise AssertionError("input() must not be called when require_confirmation is False")

    monkeypatch.setattr("builtins.input", boom)

    result = tool.handler(filename="greet.py", code=VALID_CODE, description="greets the user")

    assert "Skill saved" in result
    assert [t.name for t in agent.added] == ["greet"]


def test_require_confirmation_accepts_a_live_callable(tmp_path, monkeypatch):
    # Same live-callable pattern as code_exec.py's Confirmation — a plain
    # bool captured at tool-build time wouldn't see a later mode switch.
    flag = {"require": True}
    provider = ScriptedProvider(
        [
            ProviderResponse(text="VERDICT: SAFE\nfine.", tool_calls=[]),
            ProviderResponse(text="VERDICT: SAFE\nfine.", tool_calls=[]),
        ]
    )
    agent = FakeAgent()
    tool = make_propose_skill_tool(
        provider, str(tmp_path), agent, require_confirmation=lambda: flag["require"]
    )

    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    declined = tool.handler(filename="greet.py", code=VALID_CODE, description="d")
    assert "declined" in declined

    flag["require"] = False
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("must not prompt"))
    )
    approved = tool.handler(filename="greet.py", code=VALID_CODE, description="d")
    assert "Skill saved" in approved


def test_rejects_filename_with_path_separator(tmp_path, monkeypatch):
    provider = ScriptedProvider([])  # must not even be called

    def boom(prompt=""):
        raise AssertionError("input() should not be called for an invalid filename")

    monkeypatch.setattr("builtins.input", boom)
    agent = FakeAgent()
    tool = make_propose_skill_tool(provider, str(tmp_path), agent)

    result = tool.handler(filename="../evil.py", code=VALID_CODE, description="d")

    assert "no path separators" in result
    assert not agent.added
    assert list(tmp_path.iterdir()) == []


def test_safe_verdict_plain_yes_approves(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: SAFE\nlooks fine.", tool_calls=[])])

    result, agent = _propose(provider, tmp_path, monkeypatch, answer="y")

    assert "Skill saved" in result
    assert (tmp_path / "greet.py").is_file()
    assert [t.name for t in agent.added] == ["greet"]


def test_safe_verdict_decline_does_not_save(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: SAFE\nlooks fine.", tool_calls=[])])

    result, agent = _propose(provider, tmp_path, monkeypatch, answer="n")

    assert "declined" in result
    assert not agent.added
    assert not (tmp_path / "greet.py").exists()


def test_risky_verdict_requires_exact_phrase_not_plain_yes(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: RISKY\ndeletes files.", tool_calls=[])])

    # A reflexive "y" (which would approve a SAFE verdict) must NOT be
    # enough once the review is risky — this is the fail-closed gate.
    result, agent = _propose(provider, tmp_path, monkeypatch, answer="y")

    assert "declined" in result
    assert not agent.added
    assert not (tmp_path / "greet.py").exists()


def test_risky_verdict_exact_phrase_approves(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: RISKY\ndeletes files.", tool_calls=[])])

    result, agent = _propose(
        provider, tmp_path, monkeypatch, answer="yes, I understand the risk"
    )

    assert "Skill saved" in result
    assert [t.name for t in agent.added] == ["greet"]


def test_malformed_verdict_is_treated_as_risky(tmp_path, monkeypatch):
    # A weaker model that ignores the review prompt's exact-format
    # instruction must still fail closed rather than silently passing.
    provider = ScriptedProvider([ProviderResponse(text="I think this looks okay.", tool_calls=[])])

    result, agent = _propose(provider, tmp_path, monkeypatch, answer="y")

    assert "declined" in result
    assert not agent.added


def test_review_call_failure_fails_closed(tmp_path, monkeypatch):
    provider = RaisingProvider(RuntimeError("network down"))

    result_plain_y, agent1 = _propose(provider, tmp_path, monkeypatch, answer="y")
    assert "declined" in result_plain_y
    assert not agent1.added

    result_exact, agent2 = _propose(
        provider, tmp_path, monkeypatch, answer="yes, I understand the risk"
    )
    assert "Skill saved" in result_exact
    assert [t.name for t in agent2.added] == ["greet"]


def test_broken_code_is_removed_after_failed_import(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: SAFE\nfine.", tool_calls=[])])

    result, agent = _propose(
        provider, tmp_path, monkeypatch, answer="y", filename="broken.py", code=BROKEN_CODE
    )

    assert "failed to import" in result
    assert not agent.added
    assert not (tmp_path / "broken.py").exists()


def test_conflicting_toolspec_class_is_rejected_and_removed(tmp_path, monkeypatch):
    provider = ScriptedProvider([ProviderResponse(text="VERDICT: SAFE\nfine.", tool_calls=[])])

    result, agent = _propose(
        provider,
        tmp_path,
        monkeypatch,
        answer="y",
        filename="conflict.py",
        code=CONFLICTING_TOOLSPEC_CODE,
    )

    assert "TOOLS must be a non-empty list" in result
    assert not agent.added
    assert not (tmp_path / "conflict.py").exists()
