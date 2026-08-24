from talaria.compaction import compact_history


def _turn(user_text, assistant_text="ok"):
    return [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text, "tool_calls": []},
    ]


def test_no_trim_when_under_limit():
    history = _turn("a") + _turn("b")
    assert compact_history(history, max_turns=5) is history


def test_max_turns_zero_or_negative_disables_trimming():
    history = _turn("a") + _turn("b") + _turn("c")
    assert compact_history(history, max_turns=0) is history
    assert compact_history(history, max_turns=-1) is history


def test_trims_to_last_n_whole_turns():
    history = _turn("a") + _turn("b") + _turn("c") + _turn("d")
    trimmed = compact_history(history, max_turns=2)
    assert trimmed == _turn("c") + _turn("d")


def test_never_splits_a_turn_with_tool_calls_and_results():
    # A turn with a tool round trip has more than 2 entries; trimming must
    # keep the whole turn together (an assistant's tool_calls and their
    # tool results can never be separated without breaking both providers'
    # wire formats).
    turn_with_tool = [
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "", "tool_calls": ["fake_call"]},
        {"role": "tool", "tool_call_id": "1", "name": "x", "content": "result"},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]
    history = _turn("a") + turn_with_tool + _turn("c")
    trimmed = compact_history(history, max_turns=2)
    assert trimmed == turn_with_tool + _turn("c")
    assert trimmed[0]["role"] == "user"
