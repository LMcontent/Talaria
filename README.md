# Talaria

<img src="assets/logo.png" alt="Talaria logo" width="120">

A small agent for the internet, documents, code and sub-agents, with a
swappable LLM backend: **Claude API** or any **OpenAI-compatible router**
(OrcaRouter, OpenRouter, etc. — e.g. a free model like `qwen/qwen3.8-27b-free`).

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: set LLM_PROVIDER=claude or openai_compat, and the matching API key
```

### Installation on Windows via Anaconda

If you don't already have Python/git set up, this is the easiest path on
Windows.

1. Open **Anaconda Prompt** (Start menu → search "Anaconda Prompt").
2. Install git, if you don't have it yet:
   ```
   conda install -c conda-forge git -y
   ```
3. Clone the repo into a folder of your choice (example below uses
   `D:\anaconda\talaria` — adjust the path to wherever you want it):
   ```
   git clone https://github.com/LMcontent/Talaria.git D:\anaconda\talaria
   cd /d D:\anaconda\talaria
   ```
4. Create a dedicated environment (keeps this separate from your base
   `(base)` conda environment):
   ```
   conda create -n talaria python=3.11 -y
   conda activate talaria
   ```
   You should see `(talaria)` at the start of the prompt from now on.
5. Install dependencies and the one-time browser download:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
6. Create your config file and fill it in:
   ```
   copy .env.example .env
   notepad .env
   ```
   At minimum set `LLM_PROVIDER` and the matching API key (`ANTHROPIC_API_KEY`
   for `claude`, or `OPENAI_COMPAT_API_KEY` + `OPENAI_COMPAT_MODEL` for
   `openai_compat` — see the comments in `.env.example` for where to get a
   key). Save and close Notepad.
7. Run it:
   ```
   python -m talaria.cli
   ```

**Every time you come back to a new Anaconda Prompt window**, you need to
reactivate the environment and go back to the project folder first, or
Python won't see the installed packages:

```
conda activate talaria
cd /d D:\anaconda\talaria
python -m talaria.cli
```

To pull future updates:

```
cd /d D:\anaconda\talaria
git pull origin main
pip install -r requirements.txt
```

For `openai_compat`, set `OPENAI_COMPAT_BASE_URL` / `OPENAI_COMPAT_API_KEY` /
`OPENAI_COMPAT_MODEL` from your router's console (e.g.
https://www.orcarouter.ai/console/catalog?q=free — check their docs for the
exact base URL and model slug, since routers vary).

If your network can't reach `OPENAI_COMPAT_BASE_URL`'s host directly (e.g.
it's blocked in your region), set `OPENAI_COMPAT_DNS_PIN=true` and
`OPENAI_COMPAT_DNS_SERVERS` to an alternate DNS resolver (a "smart
DNS"/unblocking service) that returns a reachable IP for it. This only
changes which IP gets dialed for that one host — TLS/SNI still use the real
hostname, so certificate validation is unaffected.

**If requests start failing (401/403/connection errors) mid-session but
work again after fully restarting the terminal:** this was a real issue —
some antivirus/network filters silently kill one specific reused HTTP
connection partway through a session, and every request after that keeps
failing on that same broken connection until the whole process (and its
connection pool) restarts. Both providers now open a fresh connection for
every single request instead of reusing one, which should avoid this. If
you still hit it, it's your local network/antivirus actively interfering,
not something to fix in `.env`.

One-time browser setup (needed for the `browser_fetch` tool):

```bash
playwright install chromium
```

### Run

```bash
python -m talaria.cli
```

### Web UI

A local browser chat, as an alternative to the terminal:

```bash
python -m talaria.web
```

Then open http://127.0.0.1:5000 (or whatever `WEB_HOST`/`WEB_PORT` you set).
It's the same `Agent` and tools as the CLI — just a different front end.
Layout is a sidebar (role switcher, reset button, a live token-usage box,
and the full tool list with descriptions, always visible) plus a centered
chat column, similar to Claude Code's UI, rather than a chat that
stretches the full browser width.

"Open workspace folder" opens `WORKSPACE_DIR` in the file manager — the
simplest way to hand the agent a file is to just drop it in there directly
(it reads whatever's in that folder), rather than needing an in-chat
upload button. Note this opens the folder **on the machine running the
server** — if you're browsing from a different device on your network
than the one Talaria is running on, this opens a window there, not on
your device.
Drag the thin strip on the sidebar's right edge to resize it — your chosen
width is remembered in the browser for next time. Reopening the page
reloads the saved conversation into the chat window (not just into the
model's context) so what you see matches what it actually remembers.

Assistant replies render basic Markdown (`# `/`## `/`### ` headings,
`**bold**`, `` `code` ``, `- ` bullet lists, GFM-style `| a | b |` tables,
and fenced ` ```python ` code blocks) instead of showing the raw
punctuation — a small dependency-free renderer built into the page
itself, no CDN involved. Tables render as real bordered `<table>`s
(header row, optional column alignment from `:---`/`:---:`/`---:` in the
separator row), scrolling horizontally on their own if they're wider than
the chat column rather than squeezing it. Fenced code blocks render in a
bordered, horizontally-scrollable block with basic syntax highlighting
for Python (keywords/strings/comments/numbers); any other language still
gets the bordered block, just without coloring. Only your own messages
get the blue bubble; assistant replies flow as plain text, unboxed. While
a reply is streaming, the page only auto-scrolls if you were already at
the bottom — scroll up to read earlier messages and it won't yank you
back down mid-generation. Chat text is sized a bit larger than the
sidebar's default for comfortable reading; the sidebar itself runs
noticeably larger still, since it's mostly short labels.

**Images and video render inline** — standard Markdown image syntax,
`![description](filename.png)`, shows the actual picture (or a `<video
controls>` player, by extension: mp4/webm/ogg/mov) in the chat instead of
just the raw text. Relative paths resolve against `WORKSPACE_DIR` — drop
a file in there (or have the agent produce one via `run_python`/
`write_document`) and reference it by filename; an `http(s)://` or
`data:` URL is used as-is. This is the point of "Open workspace folder"
above and inline images together: put a picture in, ask the agent to
look at/describe/iterate on it, see its output rendered right there, no
separate viewer needed. The system prompt tells the model about this
syntax specifically for the web UI (the CLI has no way to render an
image, so it isn't told to bother).

The file is served by a dedicated `/workspace-file/<path>` route, not a
general static-file handler — restricted to an image/video extension
allowlist and sandboxed to `WORKSPACE_DIR` (same path-escape check as
`read_document`/`write_document`), so a crafted `![...]()` tag can't be
used to read arbitrary files, including the `.json` state files
(history, goals, notes, ...) that also live under `WORKSPACE_DIR`.

The message box grows as you type (up to a max height, then scrolls) so a
long or pasted message stays fully visible instead of scrolling inside a
single fixed-height line. Enter sends the message; Shift+Enter inserts a
newline instead.

The Send button turns into a **Stop** button while a reply is generating —
click it (or press Enter again) to cut generation short mid-answer. This
actually cancels the in-flight request to the model, not just the display:
the partial reply is what gets saved to history, and a "(generation
stopped)" note is shown so it's clear it wasn't a complete answer.

**Important:** confirmation prompts for `run_python`, `install_package`,
and `propose_skill` still appear in the **terminal window running the server**, not in the
browser — a chat message will just sit there "thinking…" until you answer
in that terminal. This keeps the same safety guarantees as the CLI without
a much bigger rewrite (no code ever runs without a confirmation you
actually see, it just isn't in the browser tab).

`WEB_HOST` defaults to `127.0.0.1` (localhost only) — leave it that way
unless you specifically intend to expose this on your network. Anyone who
can reach this port can chat with the agent, including its `run_python`
tool (which still asks for approval in your terminal, but is still not
something you want strangers triggering).

### Memory

Conversation history is saved to `WORKSPACE_DIR/.history.json` after every
turn and reloaded automatically the next time you start the CLI — you don't
lose context by closing the terminal. `/reset` clears it (in memory and on
disk). Override the file location with `MEMORY_FILE` in `.env`.

Old turns are trimmed automatically once the conversation exceeds
`MAX_HISTORY_TURNS` (default 30) so requests don't keep growing forever —
tune it in `.env` if you need a longer or shorter window.

**Long-term memory** is separate from conversation history: the `remember`
tool saves a fact/preference to `WORKSPACE_DIR/.notes.json`, which is
injected into the system prompt on *every* future session — this is what
actually lets the agent "know" things across restarts, not just within one
open terminal. `recall` lists saved notes with their index, `forget
<index>` removes one. Override the file with `NOTES_FILE` in `.env`.

### Goals

For long-running or open-ended work, `goal_add` builds a persistent tree
of goals and sub-goals (each with a priority and a status) in
`WORKSPACE_DIR/.goals.json` — so the objective survives across sessions
instead of needing to be restated every time. `goal_list` shows the tree;
`goal_update` changes a goal's status/priority or appends a progress note
(goals aren't deleted on failure — set status to `dropped` and the record
stays, the same "don't lose the history of what was tried" idea as
`errbook`/`idea_lab`).

The actually useful part is `goal_focus`: rather than the vague top-level
objective ("earn money"), it picks the single highest-priority *active*
goal that has no active sub-goals of its own — drilling past umbrella
goals into whatever concrete child is actually actionable next — and
shows the ancestor chain plus recent notes for context. Call it at the
start of a task with no explicit instruction instead of asking what to do.

This is a goal tracker, not a scheduler — nothing acts on it between
sessions on its own; a session still has to be opened (CLI or web) and
`goal_focus` called for anything to happen — unless you turn on
Autonomous mode below.

### Autonomous mode

**Off by default.** Set `AUTONOMOUS_MODE=true` in `.env` and run
`python -m talaria.autonomous` (its own process, separate from the CLI/web
UI) to have Talaria wake up on its own every `AUTONOMOUS_INTERVAL_MINUTES`
(default 60), call `goal_focus` to see what's actionable, and work on it
— this is what actually closes the gap the Goals section above leaves
open: a goal tree nobody ever checks between sessions doesn't do
anything by itself. Stop the process (or set `AUTONOMOUS_MODE=false`) to
turn it back off.

**Unattended runs never get `run_python`, `install_package`,
`propose_skill`, `delegate_task`, or `run_procedure`.** The first three
execute code or change what's available with your OS-level permissions
and normally ask for a `y/N` confirmation in the terminal, which has no
one to answer it when nothing is watching; the last two are excluded for
a different reason — both build their internal sub-agent/loop from this
agent's own full tool list, so without excluding them by name they'd
silently regain `run_python` and the rest right back through that inner
loop. An autonomous check-in can still read/write workspace files and use
the goal tree, notes, checkpoints, and any skill you already approved
through `propose_skill` in an earlier, attended session (those went
through a security review when you approved them — this doesn't
re-review them).

Each check-in is logged to `WORKSPACE_DIR/.autonomous_log.json`
(timestamp, the goal it focused on, its reply) as well as printed to the
terminal running the process, so you can review what happened while you
were away. Each check-in is a fresh, short-lived agent — it does not
share the CLI/web UI's conversation history, so autonomous work never
pollutes an interactive chat; the goal tree, notes and skill state are
what carry context from one check-in to the next instead.

The web UI's sidebar has an "Autonomous log" section showing the most
recent check-ins (newest first) — it's read fresh from
`.autonomous_log.json` on load, with a refresh (&#8635;) link next to the
title since the log changes from the separate `talaria.autonomous`
process, outside the web UI's own request/response cycle.

### Checkpoints

Before a risky or experimental task, ask the agent to `checkpoint_save`
under a name — it snapshots conversation history, notes, workspace files,
and every skill's own persisted state (errbook, feedback, caches, etc.) as
they stand right then. If the experiment goes badly, `checkpoint_restore`
brings all of that back to exactly that point, discarding everything
written since — so a bad run's wrong answers, mis-learned "lessons" in a
skill's state, or junk files never make it into the memory you keep using
afterwards. `checkpoint_list` shows saved checkpoints, `checkpoint_discard`
deletes one you no longer need.

Restoring only rewrites files on disk — it can't reach into the current
process's already-loaded conversation, so run `/reset` (or start a new
session) right after a restore to make the rollback actually take effect
in what the agent remembers.

### Streaming and code execution

Responses are streamed to the terminal as they're generated (for both
providers), instead of waiting for the full answer.

`run_python` asks for a `y/N` confirmation in the terminal before actually
running any code the model generated — the code runs with your OS-level
permissions, so review it before approving. Set `CONFIRM_CODE_EXEC=false`
in `.env` to skip the prompt (only if you fully trust the model/provider).

### Reasoning depth and turn limits

Genuinely multi-step or creative tasks (several tool calls, install a
package, run it, fix the error, try again...) need more room than a quick
question does. `MAX_TURNS` (default 25) is how many model-call rounds a
single turn gets before the agent gives up with `[stopped: reached
max_turns]`; `MAX_DELEGATE_DEPTH` (default 3) is how many levels deep
`delegate_task` sub-agents can delegate further. Raise either in `.env`
for longer/deeper tool-chains — pair with `MAX_SESSION_TOKENS` (see
Usage above) if you're on a metered key and want a backstop against a
runaway loop.

With `LLM_PROVIDER=claude`, `CLAUDE_EFFORT` (`low`/`medium`/`high`
(default)/`xhigh`/`max`) controls how hard the model thinks before
answering — higher can improve quality on hard/creative problems, at more
tokens and latency. `CLAUDE_SHOW_THINKING=true` prints the model's
reasoning to the terminal (wrapped in `[thinking] ... [/thinking]`
markers) as it streams, before the actual answer — off by default since
it's a lot of extra text, and it only works on models that support a
visible thinking summary (`claude-opus-5`, the default, does; an
older/different `CLAUDE_MODEL` may reject the request — only turn this on
if you know your model supports it).

### Local models (LM Studio, Ollama, ...)

`OPENAI_COMPAT_BASE_URL` doesn't have to be a cloud router — anything that
speaks the OpenAI-compatible chat-completions API works, including a local
server on your own machine or LAN. For LM Studio: enable the Local Server
tab, point `OPENAI_COMPAT_BASE_URL` at it (`http://127.0.0.1:1234/v1` on
the same machine, or `http://<its LAN IP>:1234/v1` from another machine —
turn on "Serve on Local Network" in LM Studio for that), set
`OPENAI_COMPAT_MODEL` to the exact id from `http://<host>:1234/v1/models`,
and `OPENAI_COMPAT_API_KEY` to any non-empty placeholder (local servers
don't check it). Ollama works the same way against its own
OpenAI-compatible endpoint.

Local inference on consumer hardware is a different performance profile
than a cloud API: it reprocesses the *entire* prompt (full conversation
history plus Talaria's tool list) from scratch on every single request,
with no server-side caching across turns — for a long conversation that
alone can take well over a minute on a single consumer GPU, before any
generation even starts. If you see `timed out` errors, raise
`OPENAI_COMPAT_TIMEOUT_SECONDS` (default 120; try 600 for a local model).
It also helps to lower `MAX_HISTORY_TURNS` and `MAX_TURNS` so there's
simply less prompt to reprocess each time. Not every local model handles
tool calling reliably either — if the agent never actually calls
`web_search`/`run_python`/etc. and just describes doing so in text, that's
usually the model, not Talaria; models built for agentic/tool use (e.g.
Qwen2.5+/3.x-Instruct, Llama 3.1+-Instruct, `gpt-oss`) tend to do better
here than general-purpose chat models. Every tool call that actually runs
prints `[tool] name(args)` to the terminal, so you can tell this apart from
the model just narrating an action in its reply text — if the reply
mentions writing a file but no matching `[tool] write_document(...)` line
appeared, the model never really called it.

### Sandbox environment (run_python / install_package)

`run_python` executes in a dedicated virtual environment at
`WORKSPACE_DIR/.sandbox`, created automatically the first time it (or
`install_package`) is used — separate from the environment Talaria itself
runs in. Only the Python standard library is available there until the
agent calls `install_package` (e.g. `pandas` or `requests==2.32.0`, any
valid pip requirement) to add something, which asks for the same `y/N`
approval as `run_python` before it runs. This means the model can pull in
whatever library a task actually needs without you pre-installing it, and
a bad or unwanted install is contained to a throwaway environment — delete
`WORKSPACE_DIR/.sandbox` to reset it to empty, no reinstall of Talaria
needed.

**This isolates installed packages, not the OS.** The sandbox keeps pip
installs from corrupting or fighting with Talaria's own dependencies, but
code run inside it still has the same OS-level user permissions and full
filesystem/network access as Talaria itself — it is not a security
boundary against a malicious model, which is exactly why both `run_python`
and `install_package` still ask for your approval every time
(`CONFIRM_CODE_EXEC=false` skips both prompts, same flag). For a stronger
boundary you'd want a container (e.g. Docker), which Talaria doesn't set
up for you.

Check what's installed anytime with `/venv` in the CLI.

### Usage / session token limit

Talaria counts tokens (input + output) across the whole session, including
anything spent by `delegate_task` sub-agents and `propose_skill`'s
security-review calls — check it anytime with `/usage` in the CLI, or the
always-visible "Usage" section in the web UI's sidebar.

Set `MAX_SESSION_TOKENS` in `.env` (default `0` = no limit) to have Talaria
refuse further model calls with a clear message once that many tokens have
been used, instead of silently continuing to spend — useful so a free or
metered key doesn't run up an unexpectedly large bill on a long session
with a lot of delegation. It's checked before each individual model call,
so the call that pushes the total over the limit still completes; only
calls *after* that are refused.

If you know the $/token price for your specific model (Talaria can't look
this up automatically — it varies by provider/router/model, and routers
like OrcaRouter/OpenRouter serve a large, changing catalog), set
`TOKEN_PRICE_INPUT_PER_M`/`TOKEN_PRICE_OUTPUT_PER_M` ($ per 1,000,000
tokens) in `.env` to also see an estimated cost alongside the token count.
Left at `0` (default), only the raw token count is shown — no guessed cost.

### Roles

`/role` lists the built-in roles and shows which is active; `/role <name>`
switches (changes only the system prompt going forward — history is kept).
Set a different starting role with `DEFAULT_ROLE` in `.env`.

| Role | Focus |
|---|---|
| `assistant` (default) | General-purpose |
| `researcher` | Thorough web research, cites sources |
| `coder` | Writes/runs code to verify itself, terse |
| `analyst` | Works from real data (documents/code), states assumptions |

Add more in `talaria/roles.py`.

### Skills

Drop a `*.py` file into `SKILLS_DIR` (default `./skills`) defining a
top-level `TOOLS: list[ToolSpec]` and it's loaded automatically on startup
— no changes to Talaria itself needed. See `skills/example_time.py`
for the pattern; `skills/roman_numerals.py` and `skills/wolfram_alpha.py`
are two more small examples (the latter needs a free `WOLFRAM_APPID` in
`.env` — see `.env.example` — and returns a clear error instead of
failing silently if it's not set). `/tools` in the CLI lists everything
currently loaded, built-in and skill-provided alike. A skill file that
fails to import is skipped with a `[skills] failed to load ...` message
— it doesn't take down the others.

Skills that persist their own state (`state_store`, `errbook`, `idea_lab`,
`feedback_loop`, `meaning_cache`, `simple_scheduler`, `shift_log`) do it
through `talaria/json_store.py`, which saves under `WORKSPACE_DIR/state/`
— use `load_json`/`save_json` from there in a new skill that needs its
own persistent file, rather than hand-rolling `open()`/`json.load()`
again. (Older versions of these skills used a `./state` folder relative
to wherever the process happened to be launched from, which could
silently point at the wrong place — e.g. `talaria.autonomous` started
from a different working directory than the CLI/web UI. All of them now
resolve the same `WORKSPACE_DIR` `Config.workspace_dir` does, regardless
of process cwd.)

### Self-authored skills

The agent can propose a brand-new tool for itself via `propose_skill`
(Python source defining a `TOOLS` list, same pattern as a regular skill
file) — but only through a mandatory gate: the code is printed to the
terminal and sent through a **separate security-review model call** that
looks for destructive/exfiltrating/obfuscated behavior and prints a
verdict. If the verdict is a clean `VERDICT: SAFE`, a plain `y/N` confirms
it. Anything else — `VERDICT: RISKY`, a malformed/missing verdict (e.g. a
weaker model that didn't follow the review prompt), or the review call
itself failing (network error, etc.) — fails closed: instead of `y/N` you
must type out the full phrase `yes, I understand the risk` to proceed, so
a risky skill can't slip through on a reflexive `y`. Only after that is it
saved + loaded live (no restart needed). A decline, invalid filename (no
path separators allowed), or code that fails to import all fail safely
without touching the skills directory. This tool is only ever given to
the top-level agent — a `delegate_task` sub-agent can't call it, so new
tools can't be added without you seeing it happen.

### Tools available to the agent

- `web_search`, `web_fetch` — search the internet and read pages via plain HTTP (no API key needed, uses DuckDuckGo HTML). Fast, but can't run JavaScript.
- `browser_fetch` — open a URL in a real headless Chromium (via Playwright) that executes JavaScript, for sites where `web_fetch` returns empty/garbled content. Slower, and **not a guaranteed bypass** for sites with strong anti-bot protection (e.g. Ozon) — they can still block or serve a challenge page to a headless browser.
- `read_document`, `write_document`, `list_files` — read/write `.txt`/`.pdf`/`.docx` files, sandboxed to `WORKSPACE_DIR`
- `run_python` — execute a Python snippet in the dedicated sandbox venv and capture its output (isolates installed packages, not the OS — only use with a model/provider you trust; asks for confirmation first, see above)
- `install_package` — pip-install something into that sandbox venv so run_python can use it; same confirmation gate
- `remember`, `recall`, `forget` — long-term memory across sessions, see above
- `delegate_task` — hand a self-contained sub-task to a fresh sub-agent (up to `max_delegate_depth` levels deep) and get back its answer
- `run_procedure` — run a bounded, repetitive tool-calling procedure as a compact state machine instead of a growing conversation, see below
- `propose_skill` — top-level agent only; author and (with your approval) load a new tool at runtime, see above

### Long, repetitive procedures

`delegate_task` and the normal agent loop both accumulate a conversation
— every observation, action, and reasoning step gets appended to history
and resent in full on every turn. Fine for a normal task, but for
genuinely repetitive procedural work ("fix every failing test", "process
each row of this file") that history keeps almost nothing worth keeping:
cumulative tokens grow roughly with the square of the step count, and old
observations linger in context long after they stopped mattering.

`run_procedure` runs an inner loop, hidden from the outer conversation
just like `delegate_task`'s sub-agent, but built around an explicit
JSON **state** instead of a transcript — based on ["SKILL.state: Scalable
Long-Horizon Agent Skills"](https://arxiv.org/html/2608.26263v2) (Badhe et
al., 2026). Each step the model sees only the procedure's instructions,
the *current* state, and the latest observation — never prior steps — and
returns a JSON state patch plus the next tool call (or `finish` with a
summary). The patch is merged into state (a key set to `null` deletes it)
and the reasoning that produced it is discarded immediately, so prompt
size stays roughly flat across the whole procedure instead of growing
with every step, at the cost of the model only ever seeing what it chose
to write into state — nothing is recoverable from "history" because there
isn't any.

This is a poor fit for open-ended or one-off work, and the agent is told
as much in the tool description — reach for it only when a task is
genuinely long and repetitive with a state that's actually capturable in
a handful of fields. Malformed responses (a real risk on weaker/local
models — the paper reports most small-model failures are exactly this,
not reasoning errors) get one retry with the parse error fed back as the
next observation, up to 3 consecutive failures before giving up.
Excluded from Autonomous mode's tool list for the same reason as
`delegate_task`: its internal loop is built from this agent's own full
tool list, so it would otherwise silently regain `run_python` and the
other unattended-excluded tools through it.

### Development / making it your own

Two ways to get your own copy, depending on the goal.

**Just want your own copy to hack on, no link back to this repo:**

```bash
git clone https://github.com/LMcontent/Talaria.git
cd Talaria
```

Edit, commit, and — if you want it backed up somewhere — create a new
empty repo under your own GitHub account and point `origin` at it instead:

```bash
git remote set-url origin https://github.com/<your-account>/<new-name>.git
git push -u origin main
```

From that point it's a fully independent project.

**Want to keep the option of pulling in future updates from this repo (or
sending changes back)?** Fork it on GitHub instead:

1. Click **Fork** on https://github.com/LMcontent/Talaria — creates
   `github.com/<your-account>/Talaria`.
2. Clone your fork (not the original):
   ```bash
   git clone https://github.com/<your-account>/Talaria.git
   cd Talaria
   ```
3. Add the original as a second remote, so you can pull its updates later:
   ```bash
   git remote add upstream https://github.com/LMcontent/Talaria.git
   ```
4. Develop and push to your fork as normal (`git push origin main`) — no
   write access to the original needed, it's entirely your own space.
5. To pull in updates from the original later:
   ```bash
   git fetch upstream
   git merge upstream/main
   ```

Either way, from there it's the same setup as above: `pip install -r
requirements.txt`, copy `.env.example` to `.env` and fill it in,
`playwright install chromium`, then `python -m talaria.cli` or `python -m
talaria.web`.

### Tests

```bash
pytest
```

No API key or network access needed — every test runs against a scripted
fake `Provider` (`tests/conftest.py`) that returns pre-queued replies
instead of calling a real model, so the suite is fast and deterministic.
Covers the agent's tool-calling loop, history compaction, memory/notes
persistence, skill loading (including a regression test for a skill that
shadows `ToolSpec` with a conflicting class), the `propose_skill`
security-review gate — SAFE/RISKY verdicts, a failed review call, a
malformed verdict, a bad filename, code that fails to import — session
token/cost tracking and the `MAX_SESSION_TOKENS` cap (including that a
`delegate_task` sub-agent's spend lands on the same session total), the
web UI's HTTP endpoints including its streaming and stop routes (the
latter via a fake provider that pauses mid-stream so a test can trigger a
real cancellation from a second thread, not a mocked one), and the
`run_python`/`install_package` sandbox — a real venv is actually created
and code actually executed in it (venv creation itself needs no network,
just Python's bundled ensurepip, so this stays offline too), confirming
it can't see Talaria's own installed packages. `ClaudeProvider` itself is
also covered against a fake stream object (text/thinking event handling,
`CLAUDE_SHOW_THINKING`/`CLAUDE_EFFORT` request params, cancellation, usage
extraction), and `OpenAICompatProvider`'s message conversion and
`OPENAI_COMPAT_TIMEOUT_SECONDS` wiring are covered directly — no API key
needed for either, since neither opens a real connection. Run the suite
after changing `talaria/` before pushing, same
idea as `py_compile`/`pyflakes` but for behavior instead of syntax.

### Architecture

```
talaria/
  config.py            # env-based settings, provider selection
  memory.py             # persist/reload conversation history to disk
  compaction.py          # trim old turns once history grows too large
  notes.py                # long-term memory (remember/recall/forget)
  roles.py               # built-in system-prompt presets, switchable with /role
  skills.py               # loads pluggable tools from SKILLS_DIR
  security_review.py      # model-based review call used by propose_skill
  usage.py                # session-wide token/cost tracking, optional MAX_SESSION_TOKENS cap
  sandbox.py               # the dedicated venv run_python/install_package use
  agent.py             # the tool-calling loop
  providers/
    base.py            # provider-neutral message/tool types
    claude.py           # Anthropic backend (streams responses)
    openai_compat.py    # OpenAI-compatible router backend (streams responses)
    dns_pin.py           # optional DNS pinning for blocked regions
  tools/
    web.py, browser.py, documents.py, code_exec.py, memory_tools.py,
    delegate.py, skill_authoring.py, registry.py
  cli.py                # REPL entry point
  web.py                 # local browser chat UI (Flask), same Agent/tools as the CLI
skills/
  example_time.py        # example pluggable skill — see Skills above
  roman_numerals.py       # another small example skill
  wolfram_alpha.py        # example skill needing WOLFRAM_APPID in .env
tests/
  conftest.py             # ScriptedProvider/RaisingProvider fakes shared by the suite
  test_*.py                # see Tests above
```

Conversation history is kept in a provider-neutral shape and converted to
each backend's wire format at call time, so switching `LLM_PROVIDER` doesn't
require any other code changes.
