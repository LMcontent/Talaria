import threading

from talaria.agent import Agent
from talaria.providers.base import ProviderResponse, ToolCall, ToolSpec
from talaria.usage import UsageTracker
from tests.conftest import ScriptedProvider


def _echo_tool():
    return ToolSpec(
        name="echo",
        description="echoes its input",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=lambda x: f"echo:{x}",
    )


def test_simple_reply_no_tools():
    provider = ScriptedProvider([ProviderResponse(text="hi there", tool_calls=[])])
    agent = Agent(provider, tools=[], system="sys")

    reply = agent.run("hello")

    assert reply == "hi there"
    assert provider.calls[0]["system"] == "sys"


def test_history_is_mutated_in_place_across_the_turn():
    provider = ScriptedProvider([ProviderResponse(text="hi", tool_calls=[])])
    agent = Agent(provider, tools=[], system="sys")
    history: list[dict] = []

    agent.run("hello", history=history)

    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "tool_calls": []},
    ]


def test_tool_call_round_trip():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="", tool_calls=[ToolCall(id="1", name="echo", input={"x": "hi"})]
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[_echo_tool()], system="sys")
    history: list[dict] = []

    reply = agent.run("go", history=history)

    assert reply == "done"
    assert history[2] == {
        "role": "tool",
        "tool_call_id": "1",
        "name": "echo",
        "content": "echo:hi",
    }
    # The second chat() call must have seen the tool result already appended.
    assert provider.calls[1]["history"][2]["content"] == "echo:hi"


def test_unknown_tool_reports_error_without_crashing():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="", tool_calls=[ToolCall(id="1", name="nope", input={})]
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[], system="sys")
    history: list[dict] = []

    agent.run("go", history=history)

    assert "unknown tool" in history[2]["content"]


def test_tool_handler_exception_is_caught():
    def boom(**_):
        raise ValueError("kaboom")

    tool = ToolSpec(name="boom", description="d", input_schema={}, handler=boom)
    provider = ScriptedProvider(
        [
            ProviderResponse(text="", tool_calls=[ToolCall(id="1", name="boom", input={})]),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[tool], system="sys")
    history: list[dict] = []

    agent.run("go", history=history)

    assert "kaboom" in history[2]["content"]


def test_max_turns_exhausted_returns_fallback():
    # Every scripted response keeps calling the same tool, so the loop
    # never gets a final text-only answer and must stop after max_turns.
    responses = [
        ProviderResponse(text="", tool_calls=[ToolCall(id=str(i), name="echo", input={"x": "x"})])
        for i in range(5)
    ]
    provider = ScriptedProvider(responses)
    agent = Agent(provider, tools=[_echo_tool()], system="sys", max_turns=5)

    chunks = []
    reply = agent.run("go", on_chunk=chunks.append)

    assert reply == "[stopped: reached max_turns without a final answer]"
    assert chunks[-1] == reply


def test_cancelled_response_stops_the_loop_without_running_tools():
    # A cancelled response is treated as final even if it happened to carry
    # tool_calls (real providers never return any when cancelled, but the
    # loop shouldn't rely on that) — no tool should get executed after a
    # cancellation, and the partial text is returned as-is.
    called = []

    def handler(**_):
        called.append(True)
        return "should not run"

    tool = ToolSpec(name="x", description="d", input_schema={}, handler=handler)
    provider = ScriptedProvider(
        [ProviderResponse(text="partial...", tool_calls=[], cancelled=True)]
    )
    agent = Agent(provider, tools=[tool], system="sys")

    reply = agent.run("go")

    assert reply == "partial..."
    assert called == []


def test_cancel_event_is_forwarded_to_the_provider():
    provider = ScriptedProvider([ProviderResponse(text="hi", tool_calls=[])])
    agent = Agent(provider, tools=[], system="sys")
    cancel_event = threading.Event()

    agent.run("hello", cancel_event=cancel_event)

    assert provider.calls[0]["cancel_event"] is cancel_event


def test_usage_is_accumulated_from_provider_responses():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="", tool_calls=[ToolCall(id="1", name="echo", input={"x": "hi"})],
                usage={"input_tokens": 100, "output_tokens": 10},
            ),
            ProviderResponse(text="done", tool_calls=[], usage={"input_tokens": 120, "output_tokens": 5}),
        ]
    )
    usage = UsageTracker()
    agent = Agent(provider, tools=[_echo_tool()], system="sys", usage=usage)

    agent.run("go")

    assert usage.input_tokens == 220
    assert usage.output_tokens == 15
    assert usage.calls == 2


def test_response_without_usage_data_is_not_counted():
    provider = ScriptedProvider([ProviderResponse(text="hi", tool_calls=[])])
    usage = UsageTracker()
    agent = Agent(provider, tools=[], system="sys", usage=usage)

    agent.run("go")

    assert usage.total_tokens == 0
    assert usage.calls == 0


def test_over_limit_refuses_the_next_call_without_contacting_the_provider():
    provider = ScriptedProvider([])  # must never be called
    usage = UsageTracker(max_tokens=100)
    usage.add(input_tokens=90, output_tokens=20)  # already over 100 from an earlier turn
    agent = Agent(provider, tools=[], system="sys", usage=usage)
    history: list[dict] = []

    reply = agent.run("another message", history=history)

    assert "token limit" in reply
    assert provider.calls == []
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] == reply


def test_add_tools_registers_new_tool_for_next_call():
    provider = ScriptedProvider(
        [
            ProviderResponse(text="", tool_calls=[ToolCall(id="1", name="echo", input={"x": "y"})]),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[], system="sys")
    assert "echo" not in agent.tools_by_name

    agent.add_tools([_echo_tool()])

    assert "echo" in agent.tools_by_name
    history: list[dict] = []
    agent.run("go", history=history)
    assert history[2]["content"] == "echo:y"
