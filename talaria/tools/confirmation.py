"""Shared confirmation-gate type for any tool whose handler needs a live
y/N gate — either a fixed bool (CLI/autonomous — set once at startup from
.env) or a zero-arg callable resolved fresh on every call (the web UI's
Safe/Extreme/Mega Extreme mode toggle — reading a bool wouldn't see a
change made after the tool was built, since Python closures capture the
value, not a live reference).

Used by talaria/tools/code_exec.py (run_python/install_package) and
talaria/tools/skill_authoring.py (propose_skill).
"""

from typing import Callable, Union

Confirmation = Union[bool, Callable[[], bool]]


def wants_confirmation(require_confirmation: Confirmation) -> bool:
    return require_confirmation() if callable(require_confirmation) else require_confirmation
