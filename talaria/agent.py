import threading
from typing import Callable

from talaria.providers.base import Provider, ToolSpec
from talaria.usage import UsageTracker

DEFAULT_SYSTEM = (
    "You are Talaria, a helpful agent with tools for web search/fetch, "
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
        usage: UsageTracker | None = None,
    ):
        self.provider = provider
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.system = system
        self.max_turns = max_turns
        # Shared across the top-level agent and any delegate_task
        # sub-agents (they're passed the same UsageTracker instance), so a
        # session-wide token count/limit reflects everything spent, not
        # just this one agent's own calls.
        self.usage = usage

    def run(
        self,
        user_input: str,
        history: list[dict] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Run one turn. If `history` is given, it is mutated in place with
        the full turn (including any tool calls) so the caller can keep
        reusing the same list across turns for a multi-turn conversation.
        `on_chunk`, if given, is called with each text delta as it streams
        in (in addition to the provider always printing it to stdout).
        `cancel_event`, if given and set while a reply is streaming, cuts
        generation short and returns whatever text was produced so far —
        used by the web UI's stop button.
        """
        if history is None:
            history = []
        history.append({"role": "user", "content": user_input})

        for _ in range(self.max_turns):
            if self.usage and self.usage.over_limit():
                # Checked before each call, so the call that pushed the
                # total over the limit still completed — this only refuses
                # calls that would come *after* it's already over.
                fallback = f"[stopped: session token limit reached — {self.usage.summary()}]"
                print(fallback, end="", flush=True)
                if on_chunk:
                    on_chunk(fallback)
                history.append({"role": "assistant", "content": fallback, "tool_calls": []})
                return fallback

            response = self.provider.chat(
                history, system=self.system, tools=self.tools, on_chunk=on_chunk,
                cancel_event=cancel_event,
            )
            if self.usage and response.usage:
                self.usage.add(response.usage.get("input_tokens", 0), response.usage.get("output_tokens", 0))
            history.append(
                {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": response.tool_calls,
                }
            )

            if response.cancelled or not response.tool_calls:
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

        # Providers stream their text live via print() as it's generated, but
        # this fallback message is never sent through a provider — print it
        # here too so it's not silently swallowed by a caller that relies on
        # streaming output instead of the return value.
        fallback = "[stopped: reached max_turns without a final answer]"
        print(fallback, end="", flush=True)
        if on_chunk:
            on_chunk(fallback)
        return fallback

    def add_tools(self, new_tools: list[ToolSpec]) -> None:
        """Register additional tools on an already-running agent (e.g. a
        skill approved and loaded mid-session via propose_skill)."""
        for t in new_tools:
            self.tools_by_name[t.name] = t
        self.tools = list(self.tools_by_name.values())

    def _call_tool(self, name: str, tool_input: dict) -> str:
        tool = self.tools_by_name.get(name)
        if tool is None:
            return f"Error: unknown tool {name!r}"
        # Printed unconditionally (not just via on_chunk/streaming) so it's
        # always visible in the terminal — the only way to tell "the model
        # actually called this tool" from "the model just said in text that
        # it would", which matters a lot with local/smaller models that
        # sometimes narrate an action instead of emitting a real tool call.
        print(f"\n[tool] {_format_tool_call(name, tool_input)}", flush=True)
        try:
            return str(tool.handler(**tool_input))
        except Exception as e:
            return f"Error running tool {name}: {e}"


def _format_tool_call(name: str, tool_input: dict) -> str:
    def fmt(value):
        s = repr(value)
        return s if len(s) <= 80 else s[:77] + "..."

    args = ", ".join(f"{k}={fmt(v)}" for k, v in tool_input.items())
    return f"{name}({args})"
