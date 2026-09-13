"""Shared confirmation-gate type for any tool whose handler needs a live
y/N gate — either a fixed bool (CLI/autonomous — set once at startup from
.env) or a zero-arg callable resolved fresh on every call (the web UI's
Safe/Extreme/Mega Extreme mode toggle — reading a bool wouldn't see a
change made after the tool was built, since Python closures capture the
value, not a live reference).

Used by talaria/tools/code_exec.py (run_python/install_package) and
talaria/tools/skill_authoring.py (propose_skill).
"""

import threading
from typing import Callable, Union

Confirmation = Union[bool, Callable[[], bool]]


def wants_confirmation(require_confirmation: Confirmation) -> bool:
    return require_confirmation() if callable(require_confirmation) else require_confirmation


# Held around each "print the prompt, then input()" sequence in
# run_python/install_package/propose_skill. Now that talaria/agent.py can
# run several tool calls concurrently (see its ThreadPoolExecutor use),
# two confirmation prompts firing at once would interleave their printed
# text and race for the same stdin read — genuinely confusing/ambiguous
# about which answer applies to which prompt, not just cosmetic. This
# makes concurrent confirmations queue up one at a time instead: whichever
# thread gets here first fully finishes its prompt+answer before the next
# one's prompt even prints.
CONFIRMATION_LOCK = threading.Lock()
