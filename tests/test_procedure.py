from talaria.providers.base import ProviderResponse, ToolSpec
from talaria.tools.procedure import make_procedure_tool
from talaria.usage import UsageTracker
from tests.conftest import ScriptedProvider


def _echo_tool():
    calls = []
    return calls, ToolSpec(
        name="echo",
        description="echoes its input",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=lambda msg="": calls.append(msg) or f"echo:{msg}",
    )


def _step(state_patch=None, tool="finish", tool_input=None, summary=None):
    body = {"state_patch": state_patch or {}, "tool": tool, "tool_input": tool_input or {}}
    if summary is not None:
        body["summary"] = summary
    import json as _json

    return "Some reasoning.\n```json\n" + _json.dumps(body) + "\n```"


def test_missing_instructions_returns_error():
    tool = make_procedure_tool(ScriptedProvider([]), tools=[])
    assert "Error" in tool.handler(instructions="  ")


def test_invalid_initial_state_returns_error():
    tool = make_procedure_tool(ScriptedProvider([]), tools=[])
    assert "Error" in tool.handler(instructions="do it", initial_state="not json")


def test_invalid_max_steps_returns_error():
    tool = make_procedure_tool(ScriptedProvider([]), tools=[])
    assert "Error" in tool.handler(instructions="do it", max_steps="lots")


def test_finishes_immediately_and_returns_summary():
    provider = ScriptedProvider(
        [ProviderResponse(text=_step(tool="finish", summary="all done"), tool_calls=[])]
    )
    tool = make_procedure_tool(provider, tools=[])

    assert tool.handler(instructions="do the thing") == "all done"


def test_calls_a_tool_then_finishes(capsys):
    calls, echo = _echo_tool()
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text=_step(state_patch={"seen": True}, tool="echo", tool_input={"msg": "hi"}),
                tool_calls=[],
            ),
            ProviderResponse(text=_step(tool="finish", summary="done"), tool_calls=[]),
        ]
    )
    tool = make_procedure_tool(provider, tools=[echo])

    result = tool.handler(instructions="say hi")

    assert result == "done"
    assert calls == ["hi"]
    assert "[procedure] step 1: echo({'msg': 'hi'})" in capsys.readouterr().out


def test_state_patch_carries_into_the_next_prompt():
    calls, echo = _echo_tool()
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text=_step(state_patch={"count": 1}, tool="echo", tool_input={"msg": "a"}),
                tool_calls=[],
            ),
            ProviderResponse(text=_step(tool="finish", summary="done"), tool_calls=[]),
        ]
    )
    tool = make_procedure_tool(provider, tools=[echo])

    tool.handler(instructions="count things")

    second_prompt = provider.calls[1]["history"][0]["content"]
    assert '"count": 1' in second_prompt


def test_state_patch_null_deletes_a_key():
    calls, echo = _echo_tool()
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text=_step(state_patch={"tmp": "x"}, tool="echo", tool_input={"msg": "a"}),
                tool_calls=[],
            ),
            ProviderResponse(
                text=_step(state_patch={"tmp": None}, tool="echo", tool_input={"msg": "b"}),
                tool_calls=[],
            ),
            ProviderResponse(text=_step(tool="finish", summary="done"), tool_calls=[]),
        ]
    )
    tool = make_procedure_tool(provider, tools=[echo])

    tool.handler(instructions="do it")

    third_prompt = provider.calls[2]["history"][0]["content"]
    assert '"tmp"' not in third_prompt


def test_prompt_never_grows_across_many_steps():
    calls, echo = _echo_tool()
    n_steps = 6
    responses = [
        ProviderResponse(
            text=_step(state_patch={"i": i}, tool="echo", tool_input={"msg": str(i)}),
            tool_calls=[],
        )
        for i in range(n_steps)
    ]
    responses.append(ProviderResponse(text=_step(tool="finish", summary="done"), tool_calls=[]))
    provider = ScriptedProvider(responses)
    tool = make_procedure_tool(provider, tools=[echo])

    tool.handler(instructions="loop", max_steps=str(n_steps + 1))

    # Every single call sent exactly one message — never an accumulating
    # transcript — which is the entire point of this runtime.
    assert len(provider.calls) == n_steps + 1
    for call in provider.calls:
        assert len(call["history"]) == 1


def test_unknown_tool_reports_error_as_next_observation():
    provider = ScriptedProvider(
        [
            ProviderResponse(text=_step(tool="not_a_real_tool"), tool_calls=[]),
            ProviderResponse(text=_step(tool="finish", summary="done"), tool_calls=[]),
        ]
    )
    tool = make_procedure_tool(provider, tools=[])

    tool.handler(instructions="do it")

    second_prompt = provider.calls[1]["history"][0]["content"]
    assert "unknown tool" in second_prompt
    assert "not_a_real_tool" in second_prompt


def test_invalid_json_retries_then_succeeds():
    provider = ScriptedProvider(
        [
            ProviderResponse(text="no json block here at all", tool_calls=[]),
            ProviderResponse(text=_step(tool="finish", summary="recovered"), tool_calls=[]),
        ]
    )
    tool = make_procedure_tool(provider, tools=[])

    assert tool.handler(instructions="do it") == "recovered"


def test_gives_up_after_max_consecutive_invalid_responses():
    provider = ScriptedProvider([ProviderResponse(text="garbage", tool_calls=[])] * 3)
    tool = make_procedure_tool(provider, tools=[])

    result = tool.handler(instructions="do it")

    assert "Error" in result
    assert "gave up" in result


def test_stops_at_max_steps_without_finish():
    provider = ScriptedProvider(
        [ProviderResponse(text=_step(tool="wait"), tool_calls=[])] * 3
    )
    tool = make_procedure_tool(provider, tools=[])

    result = tool.handler(instructions="loop forever", max_steps="3")

    assert "Stopped after the 3-step budget" in result


def test_usage_is_accumulated_across_steps():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text=_step(tool="finish", summary="done"),
                tool_calls=[],
                usage={"input_tokens": 50, "output_tokens": 10},
            )
        ]
    )
    usage = UsageTracker()
    tool = make_procedure_tool(provider, tools=[], usage=usage)

    tool.handler(instructions="do it")

    assert usage.input_tokens == 50
    assert usage.output_tokens == 10
