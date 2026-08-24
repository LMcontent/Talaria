from talaria.providers.base import ToolSpec, is_tool_list


def _spec(name="t"):
    return ToolSpec(name=name, description="d", input_schema={}, handler=lambda: "ok")


def test_is_tool_list_accepts_real_toolspecs():
    assert is_tool_list([_spec("a"), _spec("b")]) is True


def test_is_tool_list_rejects_empty_list():
    assert is_tool_list([]) is False


def test_is_tool_list_rejects_non_list():
    assert is_tool_list(_spec()) is False
    assert is_tool_list(None) is False
    assert is_tool_list("TOOLS") is False


def test_is_tool_list_rejects_lookalike_class():
    # Regression test: a skill that defines its own ToolSpec-shaped class
    # instead of importing the real one used to pass a naive
    # hasattr(module, "TOOLS") check and then break later in the provider
    # layer, which expects a genuine ToolSpec with .input_schema etc.
    class FakeToolSpec:
        def __init__(self, name, description, input_schema, handler):
            self.name = name
            self.description = description
            self.input_schema = input_schema
            self.handler = handler

    fake = FakeToolSpec(name="a", description="d", input_schema={}, handler=lambda: "ok")
    assert is_tool_list([fake]) is False


def test_is_tool_list_rejects_mixed_list():
    class FakeToolSpec:
        pass

    assert is_tool_list([_spec("a"), FakeToolSpec()]) is False
