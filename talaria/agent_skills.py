"""Loads Anthropic "Agent Skills" (SKILL.md + optional bundled files) —
see https://github.com/anthropics/skills for the format this follows.

This is a different paradigm from talaria/skills.py's own plugins: an
Agent Skill is NOT a registered function call. It's a folder with a
SKILL.md (YAML frontmatter: required `name` + `description`, optional
`license`, then markdown instructions) that the model is meant to read
and follow using tools it already has (run_python, read_document, ...).
talaria/tools/agent_skills.py exposes that as three tools
(list_agent_skills/use_skill/read_skill_file) rather than one ToolSpec
per skill, since the whole point of the format is progressive disclosure:
only a one-line description needs to sit in the tool list/system prompt
up front, and the full instructions load on demand.
"""

import os
from dataclasses import dataclass

import yaml

_SKILL_FILE = "SKILL.md"


@dataclass
class AgentSkill:
    name: str  # directory name - the stable identifier used to look it up
    title: str  # frontmatter 'name', for display (may differ from the directory)
    description: str
    license: str | None
    dir: str  # absolute, realpath'd path to the skill's own directory
    body: str  # markdown instructions, frontmatter stripped


def _parse_skill_md(path: str) -> tuple[dict, str] | None:
    """Split a SKILL.md file into (frontmatter dict, body markdown).
    Returns None if it has no valid '---'-delimited frontmatter block, or
    the block isn't a YAML mapping."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None

    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        front = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(front, dict):
        return None
    return front, parts[2].strip()


def load_agent_skills(agent_skills_dir: str) -> dict[str, AgentSkill]:
    """Scan agent_skills_dir for <name>/SKILL.md folders (one level deep,
    like talaria/skills.py's own flat scan). A folder that fails to parse
    (missing frontmatter, missing 'description') is skipped with a
    printed warning rather than failing the whole load - one broken skill
    must never take the others down with it."""
    skills: dict[str, AgentSkill] = {}
    if not os.path.isdir(agent_skills_dir):
        return skills

    for entry in sorted(os.listdir(agent_skills_dir)):
        skill_dir = os.path.join(agent_skills_dir, entry)
        skill_md = os.path.join(skill_dir, _SKILL_FILE)
        if not os.path.isfile(skill_md):
            continue

        parsed = _parse_skill_md(skill_md)
        if parsed is None:
            print(f"[agent_skills] skipped {entry}: invalid or missing SKILL.md frontmatter")
            continue
        front, body = parsed

        description = str(front.get("description") or "").strip()
        if not description:
            print(f"[agent_skills] skipped {entry}: SKILL.md frontmatter missing 'description'")
            continue

        license_ = front.get("license")
        skills[entry] = AgentSkill(
            name=entry,
            title=str(front.get("name") or entry).strip() or entry,
            description=description,
            license=str(license_).strip() if license_ else None,
            dir=os.path.realpath(skill_dir),
            body=body,
        )
        print(f"[agent_skills] loaded {entry}: {description[:60]}")

    return skills
