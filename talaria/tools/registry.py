from talaria.config import Config
from talaria.providers.base import Provider, ToolSpec
from talaria.skills import load_skills
from talaria.tools.browser import BROWSER_TOOLS
from talaria.tools.checkpoint import make_checkpoint_tools
from talaria.tools.code_exec import make_code_tool, make_install_package_tool
from talaria.tools.delegate import make_delegate_tool
from talaria.tools.documents import make_document_tools
from talaria.tools.goals import make_goal_tools
from talaria.tools.memory_tools import make_memory_tools
from talaria.tools.web import WEB_TOOLS
from talaria.usage import UsageTracker


def build_tools(
    config: Config, provider: Provider, depth: int = 0, usage: UsageTracker | None = None
) -> list[ToolSpec]:
    tools = [
        *WEB_TOOLS,
        *BROWSER_TOOLS,
        *make_document_tools(config.workspace_dir),
        make_code_tool(config.workspace_dir, config.confirm_code_exec),
        make_install_package_tool(config.workspace_dir, config.confirm_code_exec),
        *make_memory_tools(config.notes_file),
        *make_goal_tools(config.workspace_dir),
        *make_checkpoint_tools(config.workspace_dir),
        *load_skills(config.skills_dir),
    ]

    delegate_tool = make_delegate_tool(
        provider,
        build_subagent_tools=lambda: build_tools(config, provider, depth=depth + 1, usage=usage),
        depth=depth,
        max_depth=config.max_delegate_depth,
        usage=usage,
    )
    if delegate_tool is not None:
        tools.append(delegate_tool)

    return tools
