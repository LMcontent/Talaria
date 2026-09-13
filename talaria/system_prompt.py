"""Builds the system prompt for a role.

Pulled out from talaria/cli.py (which originally defined this and was
imported by every other entry point) so entry points can depend on this
directly instead of on each other — talaria/cron_scheduler.py needs it
too, and importing it from cli.py would be a circular import (cli.py
would need to import cron_scheduler to start the scheduler).
"""

from talaria.notes import load_notes
from talaria.roles import ROLES

# Deliberately just a nudge, not the notes themselves: dumping every saved
# note into every system prompt regardless of relevance (the old behavior)
# gets worse as separate chats multiply — a fresh, unrelated chat would
# start out clogged with facts from someone else's task. recall's own tool
# description already tells the model the tool exists; this only adds the
# "a fresh conversation might still want it" framing that description
# can't carry on its own — pull specific facts in on demand instead.
_MEMORY_HINT = (
    "\n\nYou have long-term memory (remember/recall/forget) that persists "
    "across separate chats, not just this conversation. Call recall early "
    "in a fresh chat if past context would plausibly help, rather than "
    "assuming a blank slate — but only pull in what's actually relevant."
)


def build_system(role: str, notes_file: str) -> str:
    base = ROLES[role]["system"]
    return base + _MEMORY_HINT if load_notes(notes_file) else base
