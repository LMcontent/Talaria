"""Shared lock around the small JSON-backed persistent-state tools —
long-term memory (talaria/notes.py), the goal tree (talaria/tools/goals.py),
cron jobs (talaria/tools/cron.py), and checkpoints (talaria/tools/checkpoint.py).

Each does its own read-modify-write (load the file, change it, save it
back) with no locking of its own — fine as long as only one tool call
touches persistent state at a time, which was true when talaria/agent.py
ran every tool call strictly one after another. Now that it can run
several calls concurrently (see its ThreadPoolExecutor use), two calls
racing the *same* read-modify-write (e.g. two `remember` calls in one
turn) could silently lose one of them: both load the same starting list,
each appends its own item, and whichever save() runs last wins, discarding
the other's write. Holding this lock around each such critical section
serializes just those brief in-memory-then-flush operations — cheap
compared to what's actually worth parallelizing (network calls,
subprocesses, delegate_task sub-agents) — without blocking any of that.

Deliberately one shared lock rather than one per module: these are all
fast, and simplicity here matters more than a small amount of extra
serialization between unrelated files.
"""

import threading

STATE_LOCK = threading.Lock()
