from talaria.notes import add_note, forget_note, load_notes
from talaria.providers.base import ToolSpec


def make_memory_tools(notes_file: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="remember",
            description=(
                "Save a fact or preference to long-term memory, persisted "
                "across sessions (not just this conversation). Use for "
                "things worth knowing next time, e.g. user preferences, "
                "project details, decisions made."
            ),
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The fact to remember."}},
                "required": ["text"],
            },
            handler=lambda text: add_note(notes_file, text),
        ),
        ToolSpec(
            name="recall",
            description="List everything currently saved in long-term memory, with its index.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: (
                "\n".join(f"[{i}] {n['text']}" for i, n in enumerate(load_notes(notes_file)))
                or "(no saved notes)"
            ),
        ),
        ToolSpec(
            name="forget",
            description="Delete a note from long-term memory by its index (see recall).",
            input_schema={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Note index, from recall."}
                },
                "required": ["index"],
            },
            handler=lambda index: forget_note(notes_file, index),
        ),
    ]
