"""Builds the system prompt for a role, plus that role's persistent notes.

Pulled out from talaria/cli.py (which originally defined this and was
imported by every other entry point) so entry points can depend on this
directly instead of on each other — talaria/cron_scheduler.py needs it
too, and importing it from cli.py would be a circular import (cli.py
would need to import cron_scheduler to start the scheduler).
"""

from talaria.notes import format_notes_for_prompt, load_notes
from talaria.roles import ROLES


def build_system(role: str, notes_file: str) -> str:
    base = ROLES[role]["system"]
    notes_block = format_notes_for_prompt(load_notes(notes_file))
    return f"{base}\n\n{notes_block}" if notes_block else base
