"""propose_skill: lets the agent author a brand-new tool for itself, but
only through a mandatory gate — the code is shown to the user, reviewed by
a dedicated security-review model call, and only saved/loaded after
explicit y/N approval. This is the one and only way a skill gets added at
runtime; the agent is instructed not to write skill files directly with
write_document.
"""

import importlib.util
import os

from mini_hermes.providers.base import Provider, ToolSpec, is_tool_list
from mini_hermes.security_review import review_code


def make_propose_skill_tool(provider: Provider, skills_dir: str, agent) -> ToolSpec:
    def propose_skill(filename: str, code: str, description: str) -> str:
        if filename != os.path.basename(filename) or not filename.endswith(".py"):
            return "Error: filename must be a plain 'name.py' with no path separators."

        print(f"\n--- The agent wants to add a new skill: {filename} ---")
        print(f"Purpose: {description}")
        print(code)
        print("--- end of proposed skill code ---")

        print("\n[security review] ", end="", flush=True)
        try:
            verdict = review_code(provider, code, description)
        except Exception as e:
            verdict = f"VERDICT: RISKY\n(the security review call itself failed: {e} — treating as risky to be safe)"
            print(verdict)
        print()

        # Fail closed: anything other than a clean "VERDICT: SAFE" — including
        # a malformed/missing verdict from a model that didn't follow the
        # review prompt — is treated as risky and needs the harder gate below.
        is_risky = not verdict.strip().upper().startswith("VERDICT: SAFE")

        if is_risky:
            answer = input(
                "\nThe security review flagged this RISKY (or the review "
                "itself failed) — see above. This code would run with your "
                "OS-level permissions every time the agent calls it, with NO "
                "further confirmation after today. To proceed anyway, type "
                "exactly: yes, I understand the risk\n> "
            ).strip().lower()
            approved = answer == "yes, i understand the risk"
        else:
            answer = input(
                "\nThis code will run with your OS-level permissions every time "
                "the agent calls this tool, with NO further confirmation after "
                "today. Save and load this skill? [y/N]: "
            ).strip().lower()
            approved = answer in ("y", "yes", "д", "да")

        if not approved:
            return (
                "The user declined to add this skill. Do not propose the "
                "same or equivalent code again without addressing the "
                "concern that likely caused the decline."
            )

        os.makedirs(skills_dir, exist_ok=True)
        path = os.path.join(skills_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            spec = importlib.util.spec_from_file_location(
                f"mini_hermes_skill_{filename[:-3]}", path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            os.remove(path)
            return f"Error: the saved file failed to import ({e}); removed it. Fix the code and try again."

        new_tools = getattr(module, "TOOLS", None)
        if not is_tool_list(new_tools):
            os.remove(path)
            return (
                "Error: TOOLS must be a non-empty list of "
                "mini_hermes.providers.base.ToolSpec instances — import "
                "ToolSpec from mini_hermes.providers.base, don't define your "
                "own class with that name. Removed the file; fix and try again."
            )

        agent.add_tools(new_tools)
        return (
            f"Skill saved to {path} and loaded (security review said: {verdict[:200]}). "
            f"Tool(s) now available: {', '.join(t.name for t in new_tools)}."
        )

    return ToolSpec(
        name="propose_skill",
        description=(
            "Propose a brand-new tool ('skill') for yourself, as Python "
            "source defining a top-level TOOLS list of ToolSpec objects "
            "(same pattern as the built-in tools). The code MUST start with "
            "'from mini_hermes.providers.base import ToolSpec' — do not "
            "define your own ToolSpec-like class, it will be rejected. The "
            "code is shown to the user, security-reviewed, and only saved/"
            "loaded if the user explicitly approves. This is the ONLY way "
            "to add a new tool — never write skill files directly with "
            "write_document."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Plain filename, e.g. 'weather.py' — no path separators.",
                },
                "code": {"type": "string", "description": "Full Python source implementing the skill."},
                "description": {
                    "type": "string",
                    "description": "One-sentence summary of what this skill does, shown to the user before they approve.",
                },
            },
            "required": ["filename", "code", "description"],
        },
        handler=propose_skill,
    )
