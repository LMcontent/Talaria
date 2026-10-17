"""Exposes Anthropic "Agent Skills" (talaria/agent_skills.py) as tools.

Deliberately three tools total, not one per skill: an Agent Skill is
markdown instructions for the model to follow with its OWN existing
tools (run_python for a bundled script's contents, read_document/
write_document for workspace files), not a function call this registers
and dispatches itself. list_agent_skills gives the cheap, always-visible
summary (name + one-line description); use_skill loads one skill's full
instructions only when the model decides it's relevant; read_skill_file
reads a specific bundled file (script, template, reference doc) that
use_skill listed.

Skills are scanned once, at tool-list build time (same as
talaria/skills.py) - there is deliberately no watch/reload; restart the
process to pick up a new or edited skill folder.
"""

import os

from talaria.agent_skills import AgentSkill, load_agent_skills
from talaria.providers.base import ToolSpec
from talaria.tools.workspace import WorkspaceError, resolve_path


def _format_list(skills: dict[str, AgentSkill]) -> str:
    if not skills:
        return "(no agent skills installed)"
    return "\n".join(f"- {s.name}: {s.description}" for s in skills.values())


def _bundled_files(skill: AgentSkill) -> list[str]:
    out = []
    for root, _dirs, files in os.walk(skill.dir):
        for f in files:
            if root == skill.dir and f == "SKILL.md":
                continue
            out.append(os.path.relpath(os.path.join(root, f), skill.dir))
    return sorted(out)


def use_skill(skills: dict[str, AgentSkill], name: str = "") -> str:
    """Return a skill's full instructions plus a listing of its bundled
    files, or an error naming the known skills if 'name' doesn't match."""
    skill = skills.get(str(name).strip())
    if skill is None:
        if not skills:
            return "Error: no agent skills are installed."
        return "Error: unknown skill '{}'. Known: {}".format(name, ", ".join(sorted(skills)))

    header = f"# {skill.title}\n"
    if skill.license:
        header += f"License: {skill.license}\n"
    bundled = _bundled_files(skill)
    if bundled:
        header += (
            "\nBundled files (read with read_skill_file; a .py script's "
            "contents can then be run with run_python):\n"
        )
        header += "\n".join(f"  - {b}" for b in bundled) + "\n"
    return header + "\n" + skill.body


def read_skill_file(skills: dict[str, AgentSkill], name: str = "", path: str = "") -> str:
    """Read one bundled file from inside a specific skill's own
    directory. Path traversal out of that directory is refused, same
    protection talaria/tools/workspace.py gives the workspace itself."""
    skill = skills.get(str(name).strip())
    if skill is None:
        return "Error: unknown skill '{}'.".format(name)
    try:
        full_path = resolve_path(skill.dir, path)
    except WorkspaceError as e:
        return f"Error: {e}"
    if not os.path.isfile(full_path):
        return f"Error: file not found in skill '{name}': {path}"
    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error: could not read {path} ({e})"


def make_agent_skills_tools(agent_skills_dir: str) -> list[ToolSpec]:
    skills = load_agent_skills(agent_skills_dir)
    return [
        ToolSpec(
            name="list_agent_skills",
            description=(
                "List installed Agent Skills (the SKILL.md format from "
                "https://github.com/anthropics/skills) with their one-line "
                "descriptions. Check this first when a task sounds like it "
                "might match a specialized skill, before deciding whether "
                "use_skill is worth calling."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: _format_list(skills),
        ),
        ToolSpec(
            name="use_skill",
            description=(
                "Load one Agent Skill's full instructions (by name, from "
                "list_agent_skills) plus a list of its bundled files. The "
                "instructions are markdown for YOU to follow using your own "
                "tools - this does not execute anything itself. A bundled "
                "script's source comes from read_skill_file; run it with "
                "run_python (pass its contents as the code)."
            ),
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Skill name, from list_agent_skills."}},
                "required": ["name"],
            },
            handler=lambda name="": use_skill(skills, name),
        ),
        ToolSpec(
            name="read_skill_file",
            description=(
                "Read one bundled file (script, template, reference doc) "
                "from inside an installed Agent Skill's own directory, as "
                "listed by use_skill. 'path' is relative to that skill's "
                "directory, not the workspace."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name, from list_agent_skills."},
                    "path": {"type": "string", "description": "File path relative to the skill's own directory."},
                },
                "required": ["name", "path"],
            },
            handler=lambda name="", path="": read_skill_file(skills, name, path),
        ),
    ]
