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


def test_on_event_fires_tool_call_then_tool_result_in_order():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="", tool_calls=[ToolCall(id="1", name="echo", input={"x": "hi"})]
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[_echo_tool()], system="sys")
    events: list[tuple] = []

    agent.run("go", on_event=lambda etype, data: events.append((etype, data)))

    assert events == [
        ("tool_call", {"id": "1", "name": "echo", "input": {"x": "hi"}}),
        ("tool_result", {"id": "1", "name": "echo", "result": "echo:hi"}),
    ]


def test_on_event_fires_tool_result_with_error_message_on_a_failing_tool():
    boom = ToolSpec(
        name="boom", description="d", input_schema={"type": "object", "properties": {}},
        handler=lambda: (_ for _ in ()).throw(RuntimeError("kaboom")),
    )
    provider = ScriptedProvider(
        [
            ProviderResponse(text="", tool_calls=[ToolCall(id="1", name="boom", input={})]),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[boom], system="sys")
    events: list[tuple] = []

    agent.run("go", on_event=lambda etype, data: events.append((etype, data)))

    assert events[0] == ("tool_call", {"id": "1", "name": "boom", "input": {}})
    assert events[1][0] == "tool_result"
    assert events[1][1]["id"] == "1"
    assert "kaboom" in events[1][1]["result"]


def test_multiple_tool_calls_in_one_turn_run_concurrently():
    # Two tools that each sleep 0.2s: run one at a time that's >= 0.4s,
    # run concurrently it's close to 0.2s — the actual point of
    # parallelizing a turn's tool calls instead of running them in a loop.
    import time

    def make_slow_tool(name, delay):
        return ToolSpec(
            name=name, description="d", input_schema={"type": "object", "properties": {}},
            handler=lambda: (time.sleep(delay), f"{name} done")[1],
        )

    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="",
                tool_calls=[
                    ToolCall(id="1", name="slow_a", input={}),
                    ToolCall(id="2", name="slow_b", input={}),
                ],
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(
        provider, tools=[make_slow_tool("slow_a", 0.2), make_slow_tool("slow_b", 0.2)], system="sys"
    )

    start = time.monotonic()
    agent.run("go")
    elapsed = time.monotonic() - start

    assert elapsed < 0.35, f"took {elapsed:.2f}s — tool calls do not appear to run concurrently"


def test_parallel_tool_results_are_matched_by_id_not_completion_order():
    # slow_a finishes *after* fast_b despite being requested first — the
    # result each gets in history must still be its own, matched by id,
    # not whichever happened to land in the queue first.
    import time

    def make_tool(name, delay, text):
        return ToolSpec(
            name=name, description="d", input_schema={"type": "object", "properties": {}},
            handler=lambda: (time.sleep(delay), text)[1],
        )

    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="",
                tool_calls=[
                    ToolCall(id="1", name="slow_a", input={}),
                    ToolCall(id="2", name="fast_b", input={}),
                ],
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(
        provider,
        tools=[make_tool("slow_a", 0.2, "result A"), make_tool("fast_b", 0.0, "result B")],
        system="sys",
    )
    history: list[dict] = []

    agent.run("go", history=history)

    tool_entries = [e for e in history if e["role"] == "tool"]
    assert tool_entries[0]["tool_call_id"] == "1"
    assert tool_entries[0]["content"] == "result A"
    assert tool_entries[1]["tool_call_id"] == "2"
    assert tool_entries[1]["content"] == "result B"


def test_all_tool_calls_are_announced_before_any_result_arrives():
    # The web UI shows every pending call immediately (see
    # _run_tool_calls's docstring) — both tool_call events must fire
    # before either tool_result does, even though the tools themselves
    # run concurrently and could finish in either order.
    import time

    def make_tool(name, delay):
        return ToolSpec(
            name=name, description="d", input_schema={"type": "object", "properties": {}},
            handler=lambda: (time.sleep(delay), "ok")[1],
        )

    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="",
                tool_calls=[
                    ToolCall(id="1", name="a", input={}),
                    ToolCall(id="2", name="b", input={}),
                ],
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[make_tool("a", 0.1), make_tool("b", 0.1)], system="sys")
    events: list[tuple] = []

    agent.run("go", on_event=lambda etype, data: events.append((etype, data)))

    event_types = [e[0] for e in events]
    assert event_types == ["tool_call", "tool_call", "tool_result", "tool_result"]


def test_on_event_is_passed_through_to_the_provider():
    provider = ScriptedProvider([ProviderResponse(text="hi", tool_calls=[])])
    agent = Agent(provider, tools=[], system="sys")

    agent.run("go", on_event=lambda etype, data: None)

    # ScriptedProvider doesn't itself fire on_event, but chat() must accept
    # the kwarg without raising — real providers rely on it being threaded
    # through, not silently dropped.
    assert len(provider.calls) == 1


def test_tool_call_is_logged_to_the_terminal(capsys):
    # The only way to tell "the model actually called this tool" from "the
    # model just described doing so in text" — matters most with
    # local/smaller models that sometimes narrate instead of calling.
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="", tool_calls=[ToolCall(id="1", name="echo", input={"x": "hi"})]
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[_echo_tool()], system="sys")

    agent.run("go")

    out = capsys.readouterr().out
    assert "[tool] echo(x='hi')" in out


def test_long_tool_call_arguments_are_truncated_in_the_log(capsys):
    tool = ToolSpec(
        name="write_document",
        description="d",
        input_schema={"type": "object", "properties": {}},
        handler=lambda **kw: "written",
    )
    long_content = "x" * 500
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="",
                tool_calls=[
                    ToolCall(id="1", name="write_document", input={"content": long_content})
                ],
            ),
            ProviderResponse(text="done", tool_calls=[]),
        ]
    )
    agent = Agent(provider, tools=[tool], system="sys")

    agent.run("go")

    out = capsys.readouterr().out
    assert "..." in out
    assert long_content not in out


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
