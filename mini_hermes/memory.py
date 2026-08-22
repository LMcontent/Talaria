"""Persist conversation history to disk between CLI runs."""

import json
import os

from mini_hermes.providers.base import ToolCall


def save_history(path: str, history: list[dict]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    serializable = []
    for entry in history:
        e = dict(entry)
        if "tool_calls" in e:
            e["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "input": tc.input} for tc in e["tool_calls"]
            ]
        serializable.append(e)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def load_history(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    history = []
    for entry in raw:
        e = dict(entry)
        if "tool_calls" in e:
            e["tool_calls"] = [
                ToolCall(id=tc["id"], name=tc["name"], input=tc["input"]) for tc in e["tool_calls"]
            ]
        history.append(e)
    return history


def clear_history(path: str) -> None:
    if os.path.isfile(path):
        os.remove(path)
