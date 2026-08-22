"""Keep conversation history from growing without bound.

Every turn resends the full history to the model, so an unbounded
conversation gets slower and more expensive (and can exceed a smaller
model's context window) over time. This trims by whole turns only — never
mid-turn — so an assistant's tool_calls and their tool results are never
separated (which would break both providers' wire formats).
"""


def compact_history(history: list[dict], max_turns: int) -> list[dict]:
    if max_turns <= 0:
        return history

    turn_start_indices = [i for i, entry in enumerate(history) if entry["role"] == "user"]
    if len(turn_start_indices) <= max_turns:
        return history

    cutoff = turn_start_indices[-max_turns]
    return history[cutoff:]
