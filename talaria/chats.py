"""Multiple independent conversations ("chats"), each with its own
history file — the web UI's answer to "a task ends, I want to start a
fresh one without dragging its whole history along", the way ChatGPT/
Claude.ai/most agent UIs handle it.

Deliberately narrow: this module only owns the chat list (create/list/
rename/delete) and where each chat's history file lives. Everything else
— tools, skills, goals, checkpoints, cron jobs, long-term memory — stays
process-wide, shared by every chat, since those are capabilities and
durable knowledge, not something scoped to one conversation. Splitting
memory the same way chats are split would silently wall off exactly the
"remembered across sessions" facts recall exists to surface.

CLI/autonomous/cron are unaffected — this is web-UI-only for now, backed
by its own chats/ subdirectory rather than the single MEMORY_FILE those
still use directly.
"""

import json
import os
import uuid
from datetime import datetime, timezone

_INDEX_FILENAME = "index.json"


def _chats_dir(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, "chats")


def _index_path(workspace_dir: str) -> str:
    return os.path.join(_chats_dir(workspace_dir), _INDEX_FILENAME)


def history_path(workspace_dir: str, chat_id: str) -> str:
    return os.path.join(_chats_dir(workspace_dir), f"{chat_id}.json")


def _load_index(workspace_dir: str) -> list[dict]:
    path = _index_path(workspace_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_index(workspace_dir: str, chats: list[dict]) -> None:
    path = _index_path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_chats(workspace_dir: str) -> list[dict]:
    """Most recently updated first."""
    return sorted(_load_index(workspace_dir), key=lambda c: c["updated"], reverse=True)


def create_chat(workspace_dir: str, title: str = "New chat", role: str = "assistant") -> dict:
    chats = _load_index(workspace_dir)
    entry = {
        "id": uuid.uuid4().hex[:12], "title": title, "role": role,
        "created": _now(), "updated": _now(),
    }
    chats.append(entry)
    _save_index(workspace_dir, chats)
    return entry


def set_chat_role(workspace_dir: str, chat_id: str, role: str) -> bool:
    """Each chat remembers its own role (assistant/researcher/coder/...)
    independently — switching chats switches which one is active, the way
    switching chats already switches history. Doesn't bump `updated`: a
    role change isn't conversation activity, so it shouldn't reorder the
    chat list on its own."""
    chats = _load_index(workspace_dir)
    for c in chats:
        if c["id"] == chat_id:
            c["role"] = role
            _save_index(workspace_dir, chats)
            return True
    return False


def rename_chat(workspace_dir: str, chat_id: str, title: str) -> bool:
    chats = _load_index(workspace_dir)
    for c in chats:
        if c["id"] == chat_id:
            c["title"] = title
            c["updated"] = _now()
            _save_index(workspace_dir, chats)
            return True
    return False


def touch_chat(workspace_dir: str, chat_id: str) -> None:
    """Bumps updated so the chat list can sort by most-recently-active."""
    chats = _load_index(workspace_dir)
    for c in chats:
        if c["id"] == chat_id:
            c["updated"] = _now()
            _save_index(workspace_dir, chats)
            return


def delete_chat(workspace_dir: str, chat_id: str) -> bool:
    chats = _load_index(workspace_dir)
    remaining = [c for c in chats if c["id"] != chat_id]
    if len(remaining) == len(chats):
        return False
    _save_index(workspace_dir, remaining)
    path = history_path(workspace_dir, chat_id)
    if os.path.isfile(path):
        os.remove(path)
    return True


def auto_title(first_message: str, max_len: int = 48) -> str:
    """A ChatGPT-style title guess from the first user message — used
    only while a chat is still untitled (its default "New chat" name)."""
    title = " ".join(first_message.split())
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    return title or "New chat"
