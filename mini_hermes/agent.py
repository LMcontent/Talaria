from mini_hermes.providers.base import Provider, ToolSpec

DEFAULT_SYSTEM = (
    "You are mini-hermes, a helpful agent with tools for web search/fetch, "
    "reading and writing documents, running Python code, and delegating "
    "sub-tasks to other agents. Use tools when they help answer the "
    "request; otherwise answer directly. Be concise."
)


class Agent:
    def __init__(
        self,
        provider: Provider,
        tools: list[ToolSpec],
        system: str = DEFAULT_SYSTEM,
        max_turns: int = 15,
    ):
        self.provider = provider
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.system = system
        self.max_turns = max_turns

    def run(self, user_input: str, history: list[dict] | None = None) -> str:
        """Run one turn. If `history` is given, it is mutated in place with
        the full turn (including any tool calls) so the caller can keep
        reusing the same list across turns for a multi-turn conversation.
        """
        if history is None:
            history = []
        history.append({"role": "user", "content": user_input})

        for _ in range(self.max_turns):
            response = self.provider.chat(history, system=self.system, tools=self.tools)
            history.append(
                {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": response.tool_calls,
                }
            )

            if not response.tool_calls:
                return response.text

            for call in response.tool_calls:
                result = self._call_tool(call.name, call.input)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": result,
                    }
                )

        return "[stopped: reached max_turns without a final answer]"

    def _call_tool(self, name: str, tool_input: dict) -> str:
        tool = self.tools_by_name.get(name)
        if tool is None:
            return f"Error: unknown tool {name!r}"
        try:
            return str(tool.handler(**tool_input))
        except Exception as e:
            return f"Error running tool {name}: {e}"
