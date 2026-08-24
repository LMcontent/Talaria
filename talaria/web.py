"""A minimal local web chat UI for Talaria, as an alternative to the
CLI. Binds to localhost only by default — do NOT expose this port on an
untrusted network, since run_python/propose_skill can execute code with
your OS-level permissions.

Confirmation prompts (run_python, propose_skill) still appear and are
answered in the terminal running this server, not in the browser — a chat
request simply waits until you respond there. This reuses the exact same
Agent/tool code as the CLI; only the transport is different.
"""

import queue
import sys
import threading

from flask import Flask, Response, jsonify, render_template_string, request

from talaria.agent import Agent
from talaria.cli import build_system
from talaria.compaction import compact_history
from talaria.config import Config, load_config
from talaria.memory import clear_history, load_history, save_history
from talaria.providers import make_provider
from talaria.roles import DEFAULT_ROLE, ROLES
from talaria.tools.registry import build_tools
from talaria.tools.skill_authoring import make_propose_skill_tool

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Talaria</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    margin: 0; display: flex; flex-direction: column; height: 100vh;
    background: #f5f5f7; color: #1a1a1a;
  }
  header {
    padding: 10px 16px; border-bottom: 1px solid #ddd; background: #fff;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; }
  header .meta { font-size: 12px; color: #666; }
  header select, header button {
    font-size: 13px; padding: 4px 8px; border-radius: 6px; border: 1px solid #ccc;
    background: #fff; cursor: pointer;
  }
  #warning {
    font-size: 12px; color: #8a5a00; background: #fff6e0; padding: 6px 16px;
    border-bottom: 1px solid #eedca0;
  }
  #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 75%; padding: 8px 12px; border-radius: 10px; white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { align-self: flex-end; background: #2b6cb0; color: #fff; }
  .msg.assistant { align-self: flex-start; background: #fff; border: 1px solid #ddd; }
  .msg.error { align-self: flex-start; background: #ffe4e4; border: 1px solid #f5b5b5; color: #8a1f1f; }
  .msg.pending { align-self: flex-start; color: #888; font-style: italic; }
  .msg code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: rgba(0, 0, 0, 0.07); padding: 1px 5px; border-radius: 4px; font-size: 0.9em;
  }
  .msg ul { margin: 4px 0; padding-left: 20px; }
  .msg li { margin: 2px 0; }
  form#composer {
    display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #ddd; background: #fff;
  }
  #input { flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 14px; }
  #send { padding: 10px 18px; border-radius: 8px; border: none; background: #2b6cb0; color: #fff; font-size: 14px; cursor: pointer; }
  #send:disabled { opacity: 0.5; cursor: default; }
  @media (prefers-color-scheme: dark) {
    body { background: #17181c; color: #e6e6e6; }
    header, form#composer { background: #1f2126; border-color: #333; }
    .msg.assistant { background: #24262c; border-color: #333; }
    #input { background: #24262c; color: #e6e6e6; border-color: #444; }
    header select, header button { background: #24262c; color: #e6e6e6; border-color: #444; }
    .msg code { background: rgba(255, 255, 255, 0.12); }
  }
</style>
</head>
<body>
<header>
  <h1>Talaria</h1>
  <span class="meta">provider: {{ provider_name }}</span>
  <select id="role-select">
    {% for name, info in roles.items() %}
    <option value="{{ name }}" {% if name == role %}selected{% endif %}>{{ name }} — {{ info.description }}</option>
    {% endfor %}
  </select>
  <button id="tools-btn" type="button">Tools</button>
  <button id="reset-btn" type="button">Reset history</button>
</header>
<div id="warning">
  Confirmations for run_python / propose_skill appear in the TERMINAL running this server, not here — check there if a message seems to hang.
</div>
<div id="messages"></div>
<form id="composer">
  <input id="input" type="text" placeholder="Type a message…" autocomplete="off">
  <button id="send" type="submit">Send</button>
</form>
<script>
const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const roleSelect = document.getElementById("role-select");
const toolsBtn = document.getElementById("tools-btn");
const resetBtn = document.getElementById("reset-btn");

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Small, dependency-free renderer for the subset of Markdown models
// actually use in replies: inline code, bold, italic, and "- " bullet
// lists. Input is HTML-escaped first, so nothing the model writes can
// inject markup — the only tags produced come from this function itself.
function renderMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/(^|\n)((?:- .*(?:\n|$))+)/g, (_, pre, block) => {
    const items = block.replace(/\n$/, "").split("\n")
      .map((l) => "<li>" + l.replace(/^- /, "") + "</li>").join("");
    return pre + "<ul>" + items + "</ul>";
  });
  html = html.replace(/\n/g, "<br>");
  return html;
}

function addMessage(text, cls, renderMd) {
  const div = document.createElement("div");
  div.className = "msg " + cls;
  if (renderMd) {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, "user");
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;

  let replyDiv = null;
  let fullText = "";

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      addMessage("Error: " + (data.error || res.statusText), "error");
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunkText = decoder.decode(value, { stream: true });
      if (!chunkText) continue;
      if (!replyDiv) replyDiv = addMessage("", "assistant");
      fullText += chunkText;
      replyDiv.innerHTML = renderMarkdown(fullText);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    if (!replyDiv) {
      addMessage("(no response)", "pending");
    }
  } catch (err) {
    addMessage("Network error: " + err, "error");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
});

async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  for (const turn of data.turns) {
    if (turn.role === "user") {
      addMessage(turn.text, "user");
    } else {
      addMessage(turn.text, "assistant", true);
    }
  }
}
loadHistory();


roleSelect.addEventListener("change", async () => {
  await fetch("/api/role", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: roleSelect.value }),
  });
  addMessage("(role switched to " + roleSelect.value + ")", "pending");
});

resetBtn.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  messagesEl.innerHTML = "";
  addMessage("(history cleared)", "pending");
});

toolsBtn.addEventListener("click", async () => {
  const res = await fetch("/api/tools");
  const data = await res.json();
  const lines = data.tools.map((t) => "- " + t.name + ": " + t.description);
  addMessage("Available tools:\n" + lines.join("\n"), "pending");
});
</script>
</body>
</html>
"""


def create_app(config: Config) -> Flask:
    app = Flask(__name__)

    provider = make_provider(config)
    tools = build_tools(config, provider)
    state = {
        "role": config.default_role if config.default_role in ROLES else DEFAULT_ROLE,
        "history": compact_history(load_history(config.memory_file), config.max_history_turns),
    }
    agent = Agent(
        provider, tools, system=build_system(state["role"], config.notes_file), max_turns=config.max_turns
    )
    agent.add_tools([make_propose_skill_tool(provider, config.skills_dir, agent)])
    chat_lock = threading.Lock()

    @app.route("/")
    def index():
        return render_template_string(
            INDEX_HTML, provider_name=config.provider, role=state["role"], roles=ROLES
        )

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json(force=True) or {}
        user_input = (data.get("message") or "").strip()
        if not user_input:
            return jsonify({"error": "empty message"}), 400

        agent.system = build_system(state["role"], config.notes_file)
        history = state["history"]
        history_len_before = len(history)

        print(f"\n[web] you> {user_input}")
        print("[web] talaria> ", end="", flush=True)
        try:
            with chat_lock:
                reply = agent.run(user_input, history=history)
        except Exception as e:
            del history[history_len_before:]
            print(f"\n[web] error: {e}")
            return jsonify({"error": str(e)}), 500
        print()

        state["history"] = compact_history(history, config.max_history_turns)
        save_history(config.memory_file, state["history"])
        return jsonify({"reply": reply})

    @app.route("/api/chat/stream", methods=["POST"])
    def chat_stream():
        data = request.get_json(force=True) or {}
        user_input = (data.get("message") or "").strip()
        if not user_input:
            return jsonify({"error": "empty message"}), 400

        agent.system = build_system(state["role"], config.notes_file)
        history = state["history"]
        history_len_before = len(history)

        q: queue.Queue = queue.Queue()

        def worker():
            print(f"\n[web] you> {user_input}")
            print("[web] talaria> ", end="", flush=True)
            try:
                with chat_lock:
                    agent.run(user_input, history=history, on_chunk=lambda t: q.put(("chunk", t)))
                print()
                q.put(("done", ""))
            except Exception as e:
                print(f"\n[web] error: {e}")
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        # Block for the first event before deciding how to respond: if the
        # very first thing that happens is an error (by far the most common
        # case — bad key, connection refused, etc., all fail before any text
        # streams), we can still return a clean JSON 4xx/5xx instead of
        # starting a 200 stream. Only once text has actually started do we
        # commit to a streaming response.
        first_kind, first_payload = q.get()

        if first_kind == "error":
            del history[history_len_before:]
            return jsonify({"error": first_payload}), 500

        def finalize():
            state["history"] = compact_history(history, config.max_history_turns)
            save_history(config.memory_file, state["history"])

        if first_kind == "done":
            finalize()
            return Response("", mimetype="text/plain")

        def generate():
            yield first_payload
            while True:
                kind, payload = q.get()
                if kind == "chunk":
                    yield payload
                elif kind == "error":
                    del history[history_len_before:]
                    return
                elif kind == "done":
                    finalize()
                    return

        return Response(generate(), mimetype="text/plain")

    @app.route("/api/history")
    def history_endpoint():
        turns = []
        for entry in state["history"]:
            if entry["role"] == "user":
                turns.append({"role": "user", "text": entry["content"]})
            elif entry["role"] == "assistant" and entry.get("content"):
                turns.append({"role": "assistant", "text": entry["content"]})
        return jsonify({"turns": turns})

    @app.route("/api/reset", methods=["POST"])
    def reset():
        state["history"] = []
        clear_history(config.memory_file)
        return jsonify({"ok": True})

    @app.route("/api/role", methods=["GET", "POST"])
    def role_endpoint():
        if request.method == "POST":
            data = request.get_json(force=True) or {}
            name = data.get("role")
            if name not in ROLES:
                return jsonify({"error": f"unknown role {name!r}"}), 400
            state["role"] = name
        return jsonify(
            {"current": state["role"], "roles": {k: v["description"] for k, v in ROLES.items()}}
        )

    @app.route("/api/tools")
    def tools_endpoint():
        return jsonify({"tools": [{"name": t.name, "description": t.description} for t in agent.tools]})

    return app


def main() -> None:
    config = load_config()

    try:
        app = create_app(config)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Talaria web UI ready at http://{config.web_host}:{config.web_port}  (Ctrl+C to stop)")
    print(
        "Confirmations for run_python / propose_skill appear HERE in this "
        "terminal, not in the browser — check back here if a chat message "
        "seems to hang."
    )
    app.run(host=config.web_host, port=config.web_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
