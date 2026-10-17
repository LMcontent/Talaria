import os

from talaria.tools.agent_skills import make_agent_skills_tools


def _write_skill(base, name, frontmatter, body="Do the thing.\n", files=None):
    skill_dir = os.path.join(base, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\n" + frontmatter + "\n---\n" + body)
    for rel_path, content in (files or {}).items():
        full = os.path.join(skill_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    return skill_dir


def _tools(tmp_path):
    return {t.name: t for t in make_agent_skills_tools(str(tmp_path))}


def test_list_when_empty(tmp_path):
    tools = _tools(tmp_path)
    assert tools["list_agent_skills"].handler() == "(no agent skills installed)"


def test_list_shows_name_and_description(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    tools = _tools(tmp_path)
    assert tools["list_agent_skills"].handler() == "- greeter: Says hello."


def test_use_skill_returns_body_and_title(tmp_path):
    _write_skill(tmp_path, "greeter", "name: Greeter Pro\ndescription: Says hello.", body="Say hi nicely.\n")
    tools = _tools(tmp_path)

    result = tools["use_skill"].handler(name="greeter")

    assert "# Greeter Pro" in result
    assert "Say hi nicely." in result


def test_use_skill_lists_bundled_files(tmp_path):
    _write_skill(
        tmp_path, "greeter", "name: greeter\ndescription: Says hello.",
        files={"scripts/greet.py": "print('hi')\n", "reference.md": "notes\n"},
    )
    tools = _tools(tmp_path)

    result = tools["use_skill"].handler(name="greeter")

    assert "scripts/greet.py" in result
    assert "reference.md" in result
    assert "read_skill_file" in result


def test_use_skill_omits_bundled_section_when_there_are_none(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    tools = _tools(tmp_path)
    assert "Bundled files" not in tools["use_skill"].handler(name="greeter")


def test_use_skill_unknown_name_lists_known_skills(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    tools = _tools(tmp_path)

    result = tools["use_skill"].handler(name="nope")

    assert "Error" in result
    assert "greeter" in result


def test_use_skill_unknown_name_when_none_installed(tmp_path):
    tools = _tools(tmp_path)
    assert "Error: no agent skills are installed" in tools["use_skill"].handler(name="nope")


def test_read_skill_file_roundtrip(tmp_path):
    _write_skill(
        tmp_path, "greeter", "name: greeter\ndescription: Says hello.",
        files={"scripts/greet.py": "print('hi')\n"},
    )
    tools = _tools(tmp_path)

    result = tools["read_skill_file"].handler(name="greeter", path="scripts/greet.py")

    assert result == "print('hi')\n"


def test_read_skill_file_missing_file(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    tools = _tools(tmp_path)

    result = tools["read_skill_file"].handler(name="greeter", path="nope.py")

    assert "Error" in result
    assert "not found" in result


def test_read_skill_file_unknown_skill(tmp_path):
    tools = _tools(tmp_path)
    assert "Error" in tools["read_skill_file"].handler(name="nope", path="x.py")


def test_read_skill_file_refuses_path_traversal(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    tools = _tools(tmp_path)

    result = tools["read_skill_file"].handler(name="greeter", path="../secret.txt")

    assert "Error" in result
    assert "escapes" in result


def test_make_agent_skills_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_agent_skills_tools(str(tmp_path))}
    assert names == {"list_agent_skills", "use_skill", "read_skill_file"}
