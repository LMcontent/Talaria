from mini_hermes.config import Config
from mini_hermes.providers.base import Provider, ToolSpec
from mini_hermes.skills import load_skills
from mini_hermes.tools.browser import BROWSER_TOOLS
from mini_hermes.tools.code_exec import make_code_tool
from mini_hermes.tools.delegate import make_delegate_tool
from mini_hermes.tools.documents import make_document_tools
from mini_hermes.tools.memory_tools import make_memory_tools
from mini_hermes.tools.web import WEB_TOOLS


def build_tools(config: Config, provider: Provider, depth: int = 0) -> list[ToolSpec]:
    tools = [
        *WEB_TOOLS,
        *BROWSER_TOOLS,
        *make_document_tools(config.workspace_dir),
        make_code_tool(config.workspace_dir, config.confirm_code_exec),
        *make_memory_tools(config.notes_file),
        *load_skills(config.skills_dir),
    ]

    delegate_tool = make_delegate_tool(
        provider,
        build_subagent_tools=lambda: build_tools(config, provider, depth=depth + 1),
        depth=depth,
        max_depth=config.max_delegate_depth,
    )
    if delegate_tool is not None:
        tools.append(delegate_tool)

    return tools
