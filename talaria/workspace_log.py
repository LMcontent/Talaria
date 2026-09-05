"""Small shared helper for the capped, append-only JSON log files written
by unattended background loops (talaria/autonomous.py, talaria/cron_scheduler.py)
under WORKSPACE_DIR, and read back by talaria/web.py's log endpoints.
"""

import json
import os

_MAX_ENTRIES = 200


def append_log(workspace_dir: str, filename: str, entry: dict) -> None:
    path = os.path.join(workspace_dir, filename)
    os.makedirs(workspace_dir, exist_ok=True)
    entries = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []
    entries.append(entry)
    entries = entries[-_MAX_ENTRIES:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
