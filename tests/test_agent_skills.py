import os

from talaria.agent_skills import load_agent_skills


def _write_skill(base, name, frontmatter, body="Do the thing.\n"):
    skill_dir = os.path.join(base, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\n" + frontmatter + "\n---\n" + body)
    return skill_dir


def test_missing_dir_returns_empty(tmp_path):
    assert load_agent_skills(str(tmp_path / "nope")) == {}


def test_loads_a_well_formed_skill(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.\nlicense: MIT")

    skills = load_agent_skills(str(tmp_path))

    assert set(skills) == {"greeter"}
    s = skills["greeter"]
    assert s.name == "greeter"
    assert s.title == "greeter"
    assert s.description == "Says hello."
    assert s.license == "MIT"
    assert s.body == "Do the thing."
    assert s.dir == os.path.realpath(os.path.join(str(tmp_path), "greeter"))


def test_license_is_optional(tmp_path):
    _write_skill(tmp_path, "greeter", "name: greeter\ndescription: Says hello.")
    s = load_agent_skills(str(tmp_path))["greeter"]
    assert s.license is None


def test_title_falls_back_to_directory_name_when_name_field_missing(tmp_path):
    _write_skill(tmp_path, "greeter", "description: Says hello.")
    s = load_agent_skills(str(tmp_path))["greeter"]
    assert s.title == "greeter"


def test_skips_folder_missing_skill_md(tmp_path):
    os.makedirs(tmp_path / "not-a-skill")
    assert load_agent_skills(str(tmp_path)) == {}


def test_skips_skill_missing_description(tmp_path, capsys):
    _write_skill(tmp_path, "broken", "name: broken")
    skills = load_agent_skills(str(tmp_path))
    assert skills == {}
    assert "missing 'description'" in capsys.readouterr().out


def test_skips_skill_with_no_frontmatter_block(tmp_path, capsys):
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Just some text, no frontmatter.\n")

    skills = load_agent_skills(str(tmp_path))

    assert skills == {}
    assert "invalid or missing SKILL.md frontmatter" in capsys.readouterr().out


def test_skips_skill_with_malformed_yaml(tmp_path, capsys):
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: [unterminated\n---\nbody\n")

    skills = load_agent_skills(str(tmp_path))

    assert skills == {}
    assert "invalid or missing SKILL.md frontmatter" in capsys.readouterr().out


def test_loads_multiple_skills_independently_of_one_broken_one(tmp_path, capsys):
    _write_skill(tmp_path, "good", "name: good\ndescription: Works fine.")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "SKILL.md").write_text("no frontmatter here\n")

    skills = load_agent_skills(str(tmp_path))

    assert set(skills) == {"good"}
    assert "skipped broken" in capsys.readouterr().out
