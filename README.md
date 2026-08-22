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

### Run

```bash
python -m mini_hermes.cli
```

### Tools available to the agent

- `web_search`, `web_fetch` — search the internet and read pages (no API key needed, uses DuckDuckGo HTML)
- `read_document`, `write_document`, `list_files` — read/write `.txt`/`.pdf`/`.docx` files, sandboxed to `WORKSPACE_DIR`
- `run_python` — execute a Python snippet and capture its output (not sandboxed beyond a timeout — only use with a model/provider you trust)
- `delegate_task` — hand a self-contained sub-task to a fresh sub-agent (up to `max_delegate_depth` levels deep) and get back its answer

### Architecture

```
mini_hermes/
  config.py            # env-based settings, provider selection
  agent.py             # the tool-calling loop
  providers/
    base.py            # provider-neutral message/tool types
    claude.py           # Anthropic backend
    openai_compat.py    # OpenAI-compatible router backend
  tools/
    web.py, documents.py, code_exec.py, delegate.py, registry.py
  cli.py                # REPL entry point
```

Conversation history is kept in a provider-neutral shape and converted to
each backend's wire format at call time, so switching `LLM_PROVIDER` doesn't
require any other code changes.
