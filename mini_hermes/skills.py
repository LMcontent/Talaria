"""Load pluggable tools from a skills directory.

A "skill" is any *.py file in the skills directory that defines a
top-level `TOOLS: list[ToolSpec]`. Drop a file in there to add a new tool
without touching mini_hermes itself — see skills/example_time.py.
"""

import importlib.util
import os

from mini_hermes.providers.base import ToolSpec, is_tool_list


def load_skills(skills_dir: str) -> list[ToolSpec]:
    if not os.path.isdir(skills_dir):
        return []

    tools: list[ToolSpec] = []
    for filename in sorted(os.listdir(skills_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        path = os.path.join(skills_dir, filename)
        module_name = f"mini_hermes_skill_{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[skills] failed to load {filename}: {e}")
            continue

        module_tools = getattr(module, "TOOLS", None)
        if module_tools is None:
            continue
        if not is_tool_list(module_tools):
            print(
                f"[skills] skipped {filename}: TOOLS must be a non-empty list of "
                "mini_hermes.providers.base.ToolSpec instances"
            )
            continue

        tools.extend(module_tools)
        print(f"[skills] loaded {filename}: {', '.join(t.name for t in module_tools)}")

    return tools
