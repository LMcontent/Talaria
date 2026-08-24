from talaria.providers.base import ProviderResponse
from talaria.tools.delegate import make_delegate_tool
from talaria.usage import UsageTracker
from tests.conftest import ScriptedProvider


def test_delegate_task_shares_usage_tracker_with_subagent():
    provider = ScriptedProvider(
        [
            ProviderResponse(
                text="sub-agent answer",
                tool_calls=[],
                usage={"input_tokens": 50, "output_tokens": 20},
            )
        ]
    )
    usage = UsageTracker()
    tool = make_delegate_tool(
        provider, build_subagent_tools=lambda: [], depth=0, max_depth=2, usage=usage
    )

    result = tool.handler(goal="do something")

    assert result == "sub-agent answer"
    # The sub-agent's own token spend lands on the SAME tracker as the
    # top-level agent's, so a session-wide limit/estimate reflects it too.
    assert usage.input_tokens == 50
    assert usage.output_tokens == 20


def test_delegate_task_unavailable_at_max_depth():
    provider = ScriptedProvider([])
    tool = make_delegate_tool(provider, build_subagent_tools=lambda: [], depth=2, max_depth=2)
    assert tool is None


def test_delegate_task_without_a_usage_tracker_still_works():
    provider = ScriptedProvider([ProviderResponse(text="ok", tool_calls=[])])
    tool = make_delegate_tool(provider, build_subagent_tools=lambda: [], depth=0, max_depth=2)

    assert tool.handler(goal="do something") == "ok"
