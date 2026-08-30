# -*- coding: utf-8 -*-
"""Persistent key-value store backed by a JSON file in the workspace.

Gives the agent memory that survives across run_python calls AND sessions:
anything saved here can be read later by any tool, skill, or code snippet.
"""
import json
import os

from talaria.providers.base import ToolSpec

_STATE_DIR = os.path.join(".", "state")
_STATE_FILE = os.path.join(_STATE_DIR, "store.json")


def _load_db():
    if not os.path.isfile(_STATE_FILE):
        return {}
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_db(db):
    os.makedirs(_STATE_DIR, exist_ok=True)
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATE_FILE)


def state_set(key: str = "", value: str = "") -> str:
    """Save a value under a key in the persistent store."""
    k = str(key).strip()
    if not k:
        return "Error: empty key"
    db = _load_db()
    db[k] = str(value)
    _save_db(db)
    return "Saved '{}' ({} chars). Total keys: {}".format(k, len(str(value)), len(db))


def state_get(key: str = "") -> str:
    """Read a value by key from the persistent store."""
    db = _load_db()
    k = str(key).strip()
    if k not in db:
        return "Not found: {}".format(k)
    return str(db[k])


def state_list(key: str = "") -> str:
    """List all keys in the persistent store with value sizes."""
    db = _load_db()
    if not db:
        return "(store is empty)"
    return "\n".join("- {}: {} chars".format(k, len(str(v))) for k, v in sorted(db.items()))


def state_delete(key: str = "") -> str:
    """Delete a key from the persistent store."""
    db = _load_db()
    k = str(key).strip()
    if k not in db:
        return "Not found: {}".format(k)
    del db[k]
    _save_db(db)
    return "Deleted '{}'.".format(k)


TOOLS = [
    ToolSpec(
        name="state_set",
        description="Persistently save a string value under a key (survives between python runs and chat sessions).",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Unique key."},
                "value": {"type": "string", "description": "Value to store."},
            },
            "required": ["key", "value"],
        },
        handler=state_set,
    ),
    ToolSpec(
        name="state_get",
        description="Read a value by key from the persistent store.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to read."},
            },
            "required": ["key"],
        },
        handler=state_get,
    ),
    ToolSpec(
        name="state_list",
        description="List all keys stored in the persistent store.",
        input_schema={"type": "object", "properties": {}},
        handler=state_list,
    ),
    ToolSpec(
        name="state_delete",
        description="Delete a key from the persistent store.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to delete."},
            },
            "required": ["key"],
        },
        handler=state_delete,
    ),
]
