# demo

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

### Memory

Conversation history is saved to `WORKSPACE_DIR/.history.json` after every
turn and reloaded automatically the next time you start the CLI — you don't
lose context by closing the terminal. `/reset` clears it (in memory and on
disk). Override the file location with `MEMORY_FILE` in `.env`.

Old turns are trimmed automatically once the conversation exceeds
`MAX_HISTORY_TURNS` (default 30) so requests don't keep growing forever —
tune it in `.env` if you need a longer or shorter window.

### Streaming and code execution

Responses are streamed to the terminal as they're generated (for both
providers), instead of waiting for the full answer.

`run_python` asks for a `y/N` confirmation in the terminal before actually
running any code the model generated — the code runs with your OS-level
permissions, so review it before approving. Set `CONFIRM_CODE_EXEC=false`
in `.env` to skip the prompt (only if you fully trust the model/provider).

### Tools available to the agent

- `web_search`, `web_fetch` — search the internet and read pages via plain HTTP (no API key needed, uses DuckDuckGo HTML). Fast, but can't run JavaScript.
- `browser_fetch` — open a URL in a real headless Chromium (via Playwright) that executes JavaScript, for sites where `web_fetch` returns empty/garbled content. Slower, and **not a guaranteed bypass** for sites with strong anti-bot protection (e.g. Ozon) — they can still block or serve a challenge page to a headless browser.
- `read_document`, `write_document`, `list_files` — read/write `.txt`/`.pdf`/`.docx` files, sandboxed to `WORKSPACE_DIR`
- `run_python` — execute a Python snippet and capture its output (not sandboxed beyond a timeout — only use with a model/provider you trust; asks for confirmation first, see above)
- `delegate_task` — hand a self-contained sub-task to a fresh sub-agent (up to `max_delegate_depth` levels deep) and get back its answer

### Architecture

```
mini_hermes/
  config.py            # env-based settings, provider selection
  memory.py             # persist/reload conversation history to disk
  compaction.py          # trim old turns once history grows too large
  agent.py             # the tool-calling loop
  providers/
    base.py            # provider-neutral message/tool types
    claude.py           # Anthropic backend (streams responses)
    openai_compat.py    # OpenAI-compatible router backend (streams responses)
    dns_pin.py           # optional DNS pinning for blocked regions
  tools/
    web.py, browser.py, documents.py, code_exec.py, delegate.py, registry.py
  cli.py                # REPL entry point
```

Conversation history is kept in a provider-neutral shape and converted to
each backend's wire format at call time, so switching `LLM_PROVIDER` doesn't
require any other code changes.
