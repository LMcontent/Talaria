from talaria.skills import load_skills

VALID_SKILL = '''
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

# Regression test for the original bug: a skill defining its own
# ToolSpec-shaped class instead of importing the real one. It passes a
# naive hasattr(module, "TOOLS") check but must still be rejected, since
# the provider layer later expects a genuine ToolSpec.
CONFLICTING_TOOLSPEC_SKILL = '''
class ToolSpec:
    def __init__(self, name, description, input_schema, handler):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

TOOLS = [ToolSpec(name="fake", description="d", input_schema={}, handler=lambda: "x")]
'''

BROKEN_SKILL = "this is not valid python ("


def test_missing_skills_dir_returns_empty(tmp_path):
    assert load_skills(str(tmp_path / "does-not-exist")) == []


def test_loads_a_valid_skill(tmp_path):
    (tmp_path / "greet.py").write_text(VALID_SKILL)

    tools = load_skills(str(tmp_path))

    assert [t.name for t in tools] == ["greet"]
    assert tools[0].handler() == "hi"


def test_rejects_conflicting_toolspec_class(tmp_path, capsys):
    (tmp_path / "conflict.py").write_text(CONFLICTING_TOOLSPEC_SKILL)

    tools = load_skills(str(tmp_path))

    assert tools == []
    assert "skipped conflict.py" in capsys.readouterr().out


def test_skips_broken_file_without_crashing_other_skills(tmp_path, capsys):
    (tmp_path / "broken.py").write_text(BROKEN_SKILL)
    (tmp_path / "greet.py").write_text(VALID_SKILL)

    tools = load_skills(str(tmp_path))

    assert [t.name for t in tools] == ["greet"]
    assert "failed to load broken.py" in capsys.readouterr().out


def test_ignores_non_python_and_underscore_prefixed_files(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "_private.py").write_text(VALID_SKILL)

    assert load_skills(str(tmp_path)) == []


def test_skill_with_no_tools_attribute_is_silently_ignored(tmp_path):
    (tmp_path / "empty.py").write_text("x = 1\n")

    assert load_skills(str(tmp_path)) == []
