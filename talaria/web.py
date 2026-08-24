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
from talaria.usage import UsageTracker

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Talaria</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    display: flex; background: #f5f5f7; color: #1a1a1a;
  }
  #sidebar {
    width: 300px; flex-shrink: 0; height: 100vh; overflow-y: auto;
    border-right: 1px solid #ddd; background: #fafafa; padding: 16px;
  }
  #sidebar h1 { font-size: 24px; margin: 0 0 2px; }
  #sidebar .meta { font-size: 18px; color: #666; margin-bottom: 18px; }
  .sidebar-section { margin-bottom: 18px; }
  .sidebar-section-title {
    font-size: 16.5px; text-transform: uppercase; letter-spacing: 0.04em;
    color: #888; margin-bottom: 6px;
  }
  #role-select {
    width: 100%; padding: 6px 8px; border-radius: 6px; border: 1px solid #ccc;
    background: #fff; font-size: 19.5px;
  }
  #reset-btn {
    width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #ccc;
    background: #fff; cursor: pointer; font-size: 19.5px;
  }
  .tool-item { padding: 6px 0; border-bottom: 1px solid #e5e5e5; font-size: 18px; }
  .tool-item:last-child { border-bottom: none; }
  .tool-item .tname { font-weight: 600; font-family: ui-monospace, monospace; }
  .tool-item .tdesc { color: #777; margin-top: 2px; line-height: 1.35; }

  #usage-box { font-size: 16.5px; color: #555; line-height: 1.5; }
  #usage-box .over-limit { color: #a4231d; font-weight: 600; }

  #sidebar-resizer {
    width: 5px; flex-shrink: 0; height: 100vh; cursor: col-resize;
    background: transparent;
  }
  #sidebar-resizer:hover, #sidebar-resizer.dragging { background: #2b6cb0; }

  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; height: 100vh; }
  #warning {
    font-size: 15px; color: #8a5a00; background: #fff6e0; padding: 6px 16px;
    border-bottom: 1px solid #eedca0; flex-shrink: 0;
  }
  #messages { flex: 1; overflow-y: auto; min-height: 0; }
  #messages-inner {
    max-width: 760px; margin: 0 auto; padding: 24px 20px 12px;
    display: flex; flex-direction: column; gap: 18px;
  }

  .msg { white-space: pre-wrap; word-wrap: break-word; line-height: 1.55; font-size: 20px; }
  .msg.user {
    align-self: flex-end; max-width: 75%; background: #2b6cb0; color: #fff;
    padding: 8px 12px; border-radius: 10px;
  }
  .msg.assistant { align-self: stretch; }
  .msg.error { align-self: stretch; color: #a4231d; }
  .msg.pending { align-self: stretch; color: #888; font-style: italic; }

  .msg code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: rgba(0, 0, 0, 0.07); padding: 1px 5px; border-radius: 4px; font-size: 0.9em;
  }
  .msg pre.codeblock {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: rgba(0, 0, 0, 0.07); border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px; padding: 12px 14px; margin: 4px 0;
    white-space: pre; overflow-x: auto; font-size: 0.85em; line-height: 1.5;
  }
  .msg pre.codeblock code { background: none; padding: 0; border-radius: 0; font-size: 1em; }
  .msg .tok-k { color: #a626a4; font-weight: 600; }
  .msg .tok-s { color: #50a14f; }
  .msg .tok-c { color: #a0a1a7; font-style: italic; }
  .msg .tok-n { color: #986801; }
  .msg ul { margin: 4px 0; padding-left: 20px; }
  .msg li { margin: 2px 0; }
  .msg h1, .msg h2, .msg h3 { margin: 0.5em 0 0.25em; line-height: 1.3; }
  .msg h1 { font-size: 1.3em; }
  .msg h2 { font-size: 1.15em; }
  .msg h3 { font-size: 1.05em; }

  form#composer {
    display: flex; gap: 8px; padding: 12px 20px; border-top: 1px solid #ddd;
    background: #fff; flex-shrink: 0;
  }
  #input { flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 17.5px; }
  #send { padding: 10px 18px; border-radius: 8px; border: none; background: #2b6cb0; color: #fff; font-size: 17.5px; cursor: pointer; }
  #send:disabled { opacity: 0.5; cursor: default; }
  #send.stop { background: #a4231d; }

  @media (prefers-color-scheme: dark) {
    body { background: #17181c; color: #e6e6e6; }
    #sidebar { background: #1b1c20; border-color: #2c2d31; }
    #sidebar .meta { color: #999; }
    .sidebar-section-title { color: #888; }
    #role-select, #reset-btn { background: #24262c; color: #e6e6e6; border-color: #444; }
    .tool-item { border-color: #2c2d31; }
    .tool-item .tdesc { color: #999; }
    #usage-box { color: #aaa; }
    form#composer { background: #1f2126; border-color: #333; }
    #input { background: #24262c; color: #e6e6e6; border-color: #444; }
    .msg code { background: rgba(255, 255, 255, 0.12); }
    .msg pre.codeblock { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.1); }
    .msg .tok-k { color: #c678dd; }
    .msg .tok-s { color: #98c379; }
    .msg .tok-c { color: #7f848e; }
    .msg .tok-n { color: #d19a66; }
  }
</style>
</head>
<body>
<div id="sidebar">
  <h1>Talaria</h1>
  <div class="meta">provider: {{ provider_name }}</div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">Role</div>
    <select id="role-select">
      {% for name, info in roles.items() %}
      <option value="{{ name }}" {% if name == role %}selected{% endif %}>{{ name }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="sidebar-section">
    <button id="reset-btn" type="button">Reset history</button>
  </div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">Usage</div>
    <div id="usage-box">Loading…</div>
  </div>
  <div class="sidebar-section sidebar-tools">
    <div class="sidebar-section-title">Tools</div>
    <div id="tools-list">Loading…</div>
  </div>
</div>
<div id="sidebar-resizer"></div>
<div id="main">
  <div id="warning">
    Confirmations for run_python / propose_skill appear in the TERMINAL running this server, not here — check there if a message seems to hang.
  </div>
  <div id="messages"><div id="messages-inner"></div></div>
  <form id="composer">
    <input id="input" type="text" placeholder="Type a message…" autocomplete="off">
    <button id="send" type="submit">Send</button>
  </form>
</div>
<script>
const messagesEl = document.getElementById("messages-inner");
const scrollEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const roleSelect = document.getElementById("role-select");
const resetBtn = document.getElementById("reset-btn");
const toolsList = document.getElementById("tools-list");
const usageBox = document.getElementById("usage-box");
const sidebar = document.getElementById("sidebar");
const sidebarResizer = document.getElementById("sidebar-resizer");

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Best-effort token coloring for Python fenced code blocks. Runs on text
// that is already HTML-escaped, in one pass so a keyword inside a string
// or comment can't get colored twice. Any other/unknown language is left
// as plain (but still monospaced/boxed) text rather than mis-highlighted.
function highlightCode(code, lang) {
  const l = (lang || "").toLowerCase();
  if (l && l !== "python" && l !== "py") return code;
  const pattern =
    /(#[^\n]*)|("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')|\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b|\b(\d+\.?\d*)\b/g;
  return code.replace(pattern, (m, comment, str, kw, num) => {
    if (comment) return '<span class="tok-c">' + comment + "</span>";
    if (str) return '<span class="tok-s">' + str + "</span>";
    if (kw) return '<span class="tok-k">' + kw + "</span>";
    if (num) return '<span class="tok-n">' + num + "</span>";
    return m;
  });
}

// Small, dependency-free renderer for the subset of Markdown models
// actually use in replies: headings, inline/fenced code, bold, italic, and
// "- " bullet lists. Input is HTML-escaped first, so nothing the model
// writes can inject markup — the only tags produced come from here.
function renderMarkdown(text) {
  let html = escapeHtml(text);

  // Fenced ```lang ... ``` blocks are pulled out into placeholders before
  // any other transform runs, so bold/italic/heading regexes below can't
  // reach into code and mangle it. Restored as real <pre><code> at the end.
  const codeBlocks = [];
  html = html.replace(/```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    code = code.replace(/\n$/, "");
    const idx = codeBlocks.length;
    codeBlocks.push("<pre class=\"codeblock\"><code>" + highlightCode(code, lang) + "</code></pre>");
    return " CB" + idx + " ";
  });

  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/(^|\n)### (.*)/g, (_, pre, t) => pre + "<h3>" + t + "</h3>");
  html = html.replace(/(^|\n)## (.*)/g, (_, pre, t) => pre + "<h2>" + t + "</h2>");
  html = html.replace(/(^|\n)# (.*)/g, (_, pre, t) => pre + "<h1>" + t + "</h1>");
  html = html.replace(/(^|\n)((?:- .*(?:\n|$))+)/g, (_, pre, block) => {
    const items = block.replace(/\n$/, "").split("\n")
      .map((l) => "<li>" + l.replace(/^- /, "") + "</li>").join("");
    return pre + "<ul>" + items + "</ul>";
  });
  html = html.replace(/\n/g, "<br>");
  html = html.replace(/ CB(\d+) /g, (_, i) => codeBlocks[Number(i)]);
  return html;
}

// Drag the strip between the sidebar and the chat to resize it — the wider
// sidebar text (see CSS) needs more room to stay readable, so this is a
// user preference rather than a fixed width. Persisted per-browser.
(function initSidebarResize() {
  try {
    const saved = localStorage.getItem("talaria-sidebar-width");
    if (saved) sidebar.style.width = saved + "px";
  } catch (e) {}

  let dragging = false;
  sidebarResizer.addEventListener("mousedown", (e) => {
    dragging = true;
    sidebarResizer.classList.add("dragging");
    document.body.style.userSelect = "none";
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const w = Math.min(560, Math.max(220, e.clientX));
    sidebar.style.width = w + "px";
  });
  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    sidebarResizer.classList.remove("dragging");
    document.body.style.userSelect = "";
    try {
      localStorage.setItem("talaria-sidebar-width", parseInt(sidebar.style.width, 10));
    } catch (e) {}
  });
})();

function isNearBottom() {
  return scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 80;
}

function addMessage(text, cls, renderMd, forceScroll) {
  const div = document.createElement("div");
  div.className = "msg " + cls;
  if (renderMd) {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }
  messagesEl.appendChild(div);
  if (forceScroll !== false) {
    scrollEl.scrollTop = scrollEl.scrollHeight;
  }
  return div;
}

let generating = false;
let stopRequested = false;

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  // While a reply is generating, the Send button turns into Stop — a
  // submit at that point (click or Enter) means "cancel", not "send".
  if (generating) {
    stopRequested = true;
    sendBtn.disabled = true;
    try {
      await fetch("/api/chat/stop", { method: "POST" });
    } finally {
      sendBtn.disabled = false;
    }
    return;
  }

  const text = input.value.trim();
  if (!text) return;
  addMessage(text, "user");
  input.value = "";
  input.disabled = true;
  generating = true;
  stopRequested = false;
  sendBtn.textContent = "Stop";
  sendBtn.classList.add("stop");

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
      // Only follow the stream to the bottom if the user was already
      // there — lets them scroll up and read older messages while a
      // reply is still being generated, instead of getting yanked back
      // down on every chunk.
      const wasNearBottom = isNearBottom();
      if (!replyDiv) replyDiv = addMessage("", "assistant", true, false);
      fullText += chunkText;
      replyDiv.innerHTML = renderMarkdown(fullText);
      if (wasNearBottom) {
        scrollEl.scrollTop = scrollEl.scrollHeight;
      }
    }
    if (!replyDiv) {
      addMessage("(no response)", "pending");
    } else if (stopRequested) {
      addMessage("(generation stopped)", "pending");
    }
  } catch (err) {
    addMessage("Network error: " + err, "error");
  } finally {
    input.disabled = false;
    generating = false;
    sendBtn.textContent = "Send";
    sendBtn.classList.remove("stop");
    input.focus();
    loadUsage();
  }
});

async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  for (const turn of data.turns) {
    if (turn.role === "user") {
      addMessage(turn.text, "user", false, false);
    } else {
      addMessage(turn.text, "assistant", true, false);
    }
  }
  scrollEl.scrollTop = scrollEl.scrollHeight;
}
loadHistory();

async function loadUsage() {
  const res = await fetch("/api/usage");
  const u = await res.json();
  let text = u.total_tokens.toLocaleString() + " tokens (" +
    u.input_tokens.toLocaleString() + " in / " + u.output_tokens.toLocaleString() +
    " out), " + u.calls + " call" + (u.calls === 1 ? "" : "s");
  if (u.estimated_cost !== null) {
    text += " · ≈ $" + u.estimated_cost.toFixed(4);
  }
  if (u.max_tokens) {
    text += " · limit " + u.max_tokens.toLocaleString();
  }
  usageBox.textContent = text;
  usageBox.classList.toggle("over-limit", u.over_limit);
}
loadUsage();

async function loadTools() {
  const res = await fetch("/api/tools");
  const data = await res.json();
  toolsList.innerHTML = "";
  for (const t of data.tools) {
    const item = document.createElement("div");
    item.className = "tool-item";
    const name = document.createElement("div");
    name.className = "tname";
    name.textContent = t.name;
    const desc = document.createElement("div");
    desc.className = "tdesc";
    desc.textContent = t.description;
    item.appendChild(name);
    item.appendChild(desc);
    toolsList.appendChild(item);
  }
}
loadTools();

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
</script>
</body>
</html>
"""


def create_app(config: Config) -> Flask:
    app = Flask(__name__)

    provider = make_provider(config)
    usage = UsageTracker(
        max_tokens=config.max_session_tokens,
        input_price_per_m=config.token_price_input_per_m,
        output_price_per_m=config.token_price_output_per_m,
    )
    tools = build_tools(config, provider, usage=usage)
    state = {
        "role": config.default_role if config.default_role in ROLES else DEFAULT_ROLE,
        "history": compact_history(load_history(config.memory_file), config.max_history_turns),
        "cancel_event": None,
    }
    agent = Agent(
        provider, tools, system=build_system(state["role"], config.notes_file),
        max_turns=config.max_turns, usage=usage,
    )
    agent.add_tools([make_propose_skill_tool(provider, config.skills_dir, agent, usage=usage)])
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
        cancel_event = threading.Event()
        state["cancel_event"] = cancel_event

        def worker():
            print(f"\n[web] you> {user_input}")
            print("[web] talaria> ", end="", flush=True)
            try:
                with chat_lock:
                    agent.run(
                        user_input,
                        history=history,
                        on_chunk=lambda t: q.put(("chunk", t)),
                        cancel_event=cancel_event,
                    )
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
            state["cancel_event"] = None
            return jsonify({"error": first_payload}), 500

        def finalize():
            state["history"] = compact_history(history, config.max_history_turns)
            save_history(config.memory_file, state["history"])
            state["cancel_event"] = None

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
                    state["cancel_event"] = None
                    return
                elif kind == "done":
                    finalize()
                    return

        return Response(generate(), mimetype="text/plain")

    @app.route("/api/chat/stop", methods=["POST"])
    def chat_stop():
        cancel_event = state.get("cancel_event")
        if cancel_event is None:
            return jsonify({"ok": False, "error": "nothing is generating"}), 409
        cancel_event.set()
        return jsonify({"ok": True})

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

    @app.route("/api/usage")
    def usage_endpoint():
        return jsonify(usage.as_dict())

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
