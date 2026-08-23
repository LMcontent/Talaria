# Talaria

## mini-hermes

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
   `D:\anaconda\mini_hermes` — adjust the path to wherever you want it):
   ```
   git clone https://github.com/LMcontent/demo.git D:\anaconda\mini_hermes
   cd /d D:\anaconda\mini_hermes
   ```
4. Create a dedicated environment (keeps this separate from your base
   `(base)` conda environment):
   ```
   conda create -n mini-hermes python=3.11 -y
   conda activate mini-hermes
   ```
   You should see `(mini-hermes)` at the start of the prompt from now on.
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
   python -m mini_hermes.cli
   ```

**Every time you come back to a new Anaconda Prompt window**, you need to
reactivate the environment and go back to the project folder first, or
Python won't see the installed packages:

```
conda activate mini-hermes
cd /d D:\anaconda\mini_hermes
python -m mini_hermes.cli
```

To pull future updates:

```
cd /d D:\anaconda\mini_hermes
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

One-time browser setup (needed for the `browser_fetch` tool):

```bash
playwright install chromium
```

### Run

```bash
python -m mini_hermes.cli
```

### Web UI

A local browser chat, as an alternative to the terminal:

```bash
python -m mini_hermes.web
```

Then open http://127.0.0.1:5000 (or whatever `WEB_HOST`/`WEB_PORT` you set).
It's the same `Agent` and tools as the CLI — just a different front end —
including memory, roles (switchable from a dropdown in the header), and
`propose_skill`.

**Important:** confirmation prompts for `run_python` and `propose_skill`
still appear in the **terminal window running the server**, not in the
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

### Streaming and code execution

Responses are streamed to the terminal as they're generated (for both
providers), instead of waiting for the full answer.

`run_python` asks for a `y/N` confirmation in the terminal before actually
running any code the model generated — the code runs with your OS-level
permissions, so review it before approving. Set `CONFIRM_CODE_EXEC=false`
in `.env` to skip the prompt (only if you fully trust the model/provider).

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

Add more in `mini_hermes/roles.py`.

### Skills

Drop a `*.py` file into `SKILLS_DIR` (default `./skills`) defining a
top-level `TOOLS: list[ToolSpec]` and it's loaded automatically on startup
— no changes to mini_hermes itself needed. See `skills/example_time.py`
for the pattern. `/tools` in the CLI lists everything currently loaded,
built-in and skill-provided alike. A skill file that fails to import is
skipped with a `[skills] failed to load ...` message — it doesn't take
down the others.

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
- `run_python` — execute a Python snippet and capture its output (not sandboxed beyond a timeout — only use with a model/provider you trust; asks for confirmation first, see above)
- `remember`, `recall`, `forget` — long-term memory across sessions, see above
- `delegate_task` — hand a self-contained sub-task to a fresh sub-agent (up to `max_delegate_depth` levels deep) and get back its answer
- `propose_skill` — top-level agent only; author and (with your approval) load a new tool at runtime, see above

### Architecture

```
mini_hermes/
  config.py            # env-based settings, provider selection
  memory.py             # persist/reload conversation history to disk
  compaction.py          # trim old turns once history grows too large
  notes.py                # long-term memory (remember/recall/forget)
  roles.py               # built-in system-prompt presets, switchable with /role
  skills.py               # loads pluggable tools from SKILLS_DIR
  security_review.py      # model-based review call used by propose_skill
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
```

Conversation history is kept in a provider-neutral shape and converted to
each backend's wire format at call time, so switching `LLM_PROVIDER` doesn't
require any other code changes.
