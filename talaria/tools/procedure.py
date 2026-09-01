"""SKILL.state-style execution for long, homogeneous tool-calling procedures.

Ordinary Agent.run() accumulates every observation/action/reasoning into
history and resends all of it on every turn — fine for a normal chat, but
for repetitive procedural work (many similar tool calls toward one
concrete goal: "fix every failing test", "process each row") that's
cumulative token growth roughly quadratic in step count, and old,
irrelevant observations linger in context long after they stopped
mattering.

Based on "SKILL.state: Scalable Long-Horizon Agent Skills" (Badhe et al.,
2026): instead of a growing conversation, the model receives only the
procedure's instructions, the CURRENT structured state, and the latest
observation — never prior steps. Each step it returns a JSON state patch
plus the next action; reasoning is discarded immediately after the patch
is applied, so prompt size stays flat instead of growing with each step.
Not a replacement for the normal conversational agent loop — the paper's
own limitations apply here too: this only helps when the task's state can
actually be captured in a compact schema decided step by step, not for
open-ended chat or tasks where the point IS the history (auditing,
explaining what happened).

Exposed as one tool, run_procedure, following the same "runs its own
internal loop, hidden from the outer conversation" pattern as
delegate_task (talaria/tools/delegate.py) — the outer Agent/history never
sees the internal step-by-step churn, only the final result string.
"""

import json
import re

from talaria.providers.base import Provider, ToolSpec
from talaria.usage import UsageTracker

_SYSTEM_TEMPLATE = (
    "You are executing one bounded procedure step by step. You do NOT see "
    "previous steps — only these instructions, the current execution "
    "state, and the latest observation. Anything you'll need on a later "
    "step must be written into the state now via state_patch; anything "
    "left out is gone after this step.\n\n"
    "INSTRUCTIONS:\n{instructions}\n\n"
    "AVAILABLE TOOLS (call at most one per step, by name):\n"
    "{tool_list}\n\n"
    "Respond with your reasoning, then a single fenced ```json block "
    "containing exactly these keys:\n"
    '{{"state_patch": {{...state updates, or {{}} if none — set a key to '
    'null to delete it}}, "tool": "<one of the tool names above, or '
    '\\"finish\\">", "tool_input": {{...arguments for that tool, or {{}} '
    'for finish}}, "summary": "<only when tool is \\"finish\\": the final '
    'result to report back>"}}'
)

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_MAX_RETRIES_PER_STEP = 3
_MAX_STEPS_CAP = 50


def _extract_step(text: str):
    """Parse the last fenced ```json block into the expected shape, or
    return an error string (not a dict) describing what's wrong with it."""
    matches = _JSON_BLOCK_RE.findall(text)
    if not matches:
        return "no ```json block found in your response"
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError as e:
        return f"```json block is not valid JSON ({e})"
    if not isinstance(data, dict):
        return "the json block must be an object"
    if not isinstance(data.get("state_patch", {}), dict):
        return "'state_patch' must be an object"
    if not isinstance(data.get("tool"), str) or not data["tool"]:
        return "'tool' (non-empty string) is required"
    return data


def _apply_patch(state: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if v is None:
            state.pop(k, None)
        else:
            state[k] = v
    return state


def make_procedure_tool(
    provider: Provider, tools: list[ToolSpec], usage: UsageTracker | None = None
) -> ToolSpec:
    tools_by_name = {t.name: t for t in tools}
    tool_list = "\n".join(f"- {t.name}: {t.description}" for t in tools) or "(none)"

    def run_procedure(instructions: str = "", initial_state: str = "", max_steps: str = "20") -> str:
        instr = str(instructions).strip()
        if not instr:
            return "Error: 'instructions' is required."
        try:
            state = json.loads(initial_state) if str(initial_state).strip() else {}
            if not isinstance(state, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return "Error: initial_state must be a JSON object (or empty)."
        try:
            steps = max(1, min(int(str(max_steps).strip() or 20), _MAX_STEPS_CAP))
        except ValueError:
            return "Error: max_steps must be an integer."

        system = _SYSTEM_TEMPLATE.format(instructions=instr, tool_list=tool_list)
        observation = "(procedure starting — no observation yet)"
        retries = 0

        print(f"\n[procedure] starting ({steps}-step budget)")
        for step in range(1, steps + 1):
            prompt = "STATE:\n```json\n{}\n```\n\nLATEST OBSERVATION:\n{}".format(
                json.dumps(state, ensure_ascii=False), observation
            )
            response = provider.chat([{"role": "user", "content": prompt}], system=system, tools=[])
            if usage and response.usage:
                usage.add(response.usage.get("input_tokens", 0), response.usage.get("output_tokens", 0))

            parsed = _extract_step(response.text)
            if isinstance(parsed, str):
                retries += 1
                print(f"\n[procedure] step {step}: invalid response ({parsed}), retry {retries}/{_MAX_RETRIES_PER_STEP}")
                if retries >= _MAX_RETRIES_PER_STEP:
                    return (
                        f"Error: gave up after {retries} consecutive invalid responses at step {step} "
                        f"({parsed}). Last valid state:\n{json.dumps(state, ensure_ascii=False, indent=2)}"
                    )
                observation = f"Error: your last response was invalid ({parsed}). Follow the required JSON format exactly."
                continue
            retries = 0

            state = _apply_patch(state, parsed["state_patch"])
            tool_name = parsed["tool"]

            if tool_name == "finish":
                summary = str(parsed.get("summary", "")).strip() or "(finished, no summary given)"
                print(f"\n[procedure] finished at step {step}")
                return summary

            tool = tools_by_name.get(tool_name)
            if tool is None:
                observation = f"Error: unknown tool {tool_name!r}. Available: {', '.join(tools_by_name) or '(none)'}"
                print(f"\n[procedure] step {step}: {observation}")
                continue

            tool_input = parsed.get("tool_input") or {}
            print(f"\n[procedure] step {step}: {tool_name}({tool_input})")
            try:
                observation = str(tool.handler(**tool_input))
            except Exception as e:
                observation = f"Error running tool {tool_name}: {e}"

        return (
            f"Stopped after the {steps}-step budget without the model calling finish. "
            f"Final state:\n{json.dumps(state, ensure_ascii=False, indent=2)}\n"
            f"Last observation:\n{observation}"
        )

    return ToolSpec(
        name="run_procedure",
        description=(
            "Run a bounded, repetitive procedure (many similar tool calls "
            "toward one concrete goal, e.g. 'fix every failing test', "
            "'process each row of this file') as a compact state machine "
            "instead of a growing conversation — keeps token cost flat "
            "across many steps instead of growing with each one. Give "
            "explicit instructions describing the goal and what to track in "
            "state; each step only sees the current state and the latest "
            "observation, not prior steps, so anything needed later must be "
            "written into state_patch. Not a fit for open-ended, one-off, "
            "or exploratory tasks — use tools directly for those."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string",
                    "description": "The procedure's goal and what to track in state — be explicit, this is the only context each step gets.",
                },
                "initial_state": {
                    "type": "string",
                    "description": 'Optional starting state as a JSON object string, e.g. \'{"done": []}\'. Default empty.',
                },
                "max_steps": {
                    "type": "string",
                    "description": "Step budget before giving up (default 20, max 50).",
                },
            },
            "required": ["instructions"],
        },
        handler=run_procedure,
    )
