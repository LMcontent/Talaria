"""Exercises the actual agent_skills/ directory shipped in this repo (not
just the synthetic fixtures in test_agent_skills.py / test_tools_agent_skills.py)."""

import os

from talaria.agent_skills import load_agent_skills
from talaria.tools.agent_skills import make_agent_skills_tools

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SKILLS_DIR = os.path.join(REPO_ROOT, "agent_skills")


def test_repo_agent_skills_load_without_errors(capsys):
    skills = load_agent_skills(AGENT_SKILLS_DIR)

    assert "skipped" not in capsys.readouterr().out
    assert "hello-world" in skills
    assert skills["hello-world"].description


def test_hello_world_example_runs_through_the_tools(tmp_path):
    tools = {t.name: t for t in make_agent_skills_tools(AGENT_SKILLS_DIR)}

    listing = tools["list_agent_skills"].handler()
    assert "hello-world" in listing

    instructions = tools["use_skill"].handler(name="hello-world")
    assert "scripts/greet.py" in instructions
    assert "read_skill_file" in instructions

    script = tools["read_skill_file"].handler(name="hello-world", path="scripts/greet.py")
    assert 'style = "casual"' in script
