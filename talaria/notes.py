"""Long-term memory: facts the agent explicitly chooses to remember,
persisted across sessions — distinct from conversation history, which is
just the raw back-and-forth. Injected into the system prompt on every turn.
"""

import json
import os
from datetime import datetime, timezone

_MAX_INJECTED_CHARS = 3000


def load_notes(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_notes(path: str, notes: list[dict]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def add_note(path: str, text: str) -> str:
    notes = load_notes(path)
    notes.append({"text": text, "created_at": datetime.now(timezone.utc).isoformat()})
    save_notes(path, notes)
    return f"Remembered (note #{len(notes) - 1})."


def forget_note(path: str, index: int) -> str:
    notes = load_notes(path)
    if index < 0 or index >= len(notes):
        return f"Error: no note #{index}. Use recall to see valid indices."
    removed = notes.pop(index)
    save_notes(path, notes)
    return f"Forgot note #{index}: {removed['text']!r}"


def format_notes_for_prompt(notes: list[dict]) -> str:
    if not notes:
        return ""
    lines = [f"[{i}] {n['text']}" for i, n in enumerate(notes)]
    text = "\n".join(lines)
    if len(text) > _MAX_INJECTED_CHARS:
        text = text[-_MAX_INJECTED_CHARS:]  # keep the most recent notes
    return "Known facts remembered from previous sessions:\n" + text
