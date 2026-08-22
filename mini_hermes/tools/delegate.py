from mini_hermes.providers.base import Provider, ToolSpec

SUBAGENT_SYSTEM = (
    "You are a focused sub-agent spawned by mini-hermes to complete one "
    "specific task. Use your tools as needed, then give a clear, complete "
    "final answer — there is no one else to hand off to."
)


def make_delegate_tool(
    provider: Provider, build_subagent_tools, depth: int, max_depth: int
) -> ToolSpec | None:
    """Tool letting the agent hand a self-contained task to a fresh sub-agent.

    `build_subagent_tools` is a zero-arg callable returning the tool list the
    sub-agent gets (built at call time, one delegation level deeper, so the
    sub-agent can itself delegate up to `max_depth`).
    """
    if depth >= max_depth:
        return None

    def delegate_task(goal: str, context: str = "") -> str:
        from mini_hermes.agent import Agent

        sub_agent = Agent(provider, build_subagent_tools(), system=SUBAGENT_SYSTEM)
        prompt = goal if not context else f"Context:\n{context}\n\nTask:\n{goal}"
        return sub_agent.run(prompt)

    return ToolSpec(
        name="delegate_task",
        description=(
            "Delegate a self-contained sub-task to a fresh sub-agent with its "
            "own tools and context window, and get back its final answer. "
            "Useful for splitting a big job into independent pieces."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The task for the sub-agent to complete."},
                "context": {
                    "type": "string",
                    "description": "Optional background info the sub-agent needs.",
                },
            },
            "required": ["goal"],
        },
        handler=delegate_task,
    )
