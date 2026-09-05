"""A minimal local web chat UI for Talaria, as an alternative to the
CLI. Binds to localhost only by default — do NOT expose this port on an
untrusted network, since run_python/install_package/propose_skill can
execute code with your OS-level permissions.

Confirmation prompts (run_python, install_package, propose_skill) still
appear and are answered in the terminal running this server, not in the
browser — a chat request simply waits until you respond there. This
reuses the exact same Agent/tool code as the CLI; only the transport is
different.
"""

import json
import os
import queue
import subprocess
import sys
import threading

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_file

from talaria.agent import Agent
from talaria.compaction import compact_history
from talaria.config import Config, load_config
from talaria.cron_scheduler import start_cron_scheduler
from talaria.memory import clear_history, load_history, save_history
from talaria.providers import make_provider
from talaria.roles import DEFAULT_ROLE, ROLES
from talaria.system_prompt import build_system
from talaria.tools.cron import load_jobs as load_cron_jobs
from talaria.tools.registry import build_tools
from talaria.tools.skill_authoring import make_propose_skill_tool
from talaria.tools.workspace import WorkspaceError, resolve_path
from talaria.usage import UsageTracker

# Extensions servable via /workspace-file/<path> for inline chat display —
# an allowlist rather than serving anything under WORKSPACE_DIR, so an
# image/video markdown tag can't be (ab)used to read .env-adjacent state
# files (.history.json, .goals.json, ...) that also live there.
_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".mp4", ".webm", ".ogg", ".mov",
}

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _load_logo_data_uri() -> str:
    # Read fresh from disk rather than baking it into this module, so
    # replacing assets/logo.png (as happened more than once already)
    # doesn't also require touching this file. Embedded as a data: URI
    # rather than served from a route, since there's no static-file
    # serving set up for assets/ (unlike WORKSPACE_DIR's dedicated
    # /workspace-file/ route) and this file is small. Empty string
    # (renders nothing) if it's ever missing, rather than a broken-image
    # icon or a hard failure.
    import base64

    try:
        with open(os.path.join(_ASSETS_DIR, "logo.png"), "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except OSError:
        return ""


WEB_MEDIA_HINT = (
    "\n\nThis is the web chat UI, which renders Markdown images and "
    "videos inline. When you create or already have an image/video file "
    "in the workspace worth showing, reference it in your reply with "
    "standard Markdown image syntax, e.g. ![description](chart.png) — "
    "relative paths resolve against the workspace — so it displays "
    "directly in the chat instead of just being a filename."
)

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
  .brand { display: flex; align-items: center; gap: 8px; }
  /* Sized to the cap-height of the "T" next to it (h1 is 24px), not the
     full line box — an icon at font-size would look oversized next to
     text this size. */
  .brand-logo { display: block; height: 17px; width: auto; flex-shrink: 0; }
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
  #reset-btn, #open-workspace-btn {
    width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #ccc;
    background: #fff; cursor: pointer; font-size: 19.5px;
  }
  #open-workspace-btn { margin-top: 8px; }

  .setting-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  #mode-label { font-size: 19.5px; font-weight: 600; }
  #mode-label.danger { color: #a4231d; }
  .switch { position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch-slider {
    position: absolute; inset: 0; background: #ccc; border-radius: 22px;
    cursor: pointer; transition: background 0.15s;
  }
  .switch-slider::before {
    content: ""; position: absolute; width: 16px; height: 16px; left: 3px; top: 3px;
    background: #fff; border-radius: 50%; transition: transform 0.15s;
  }
  .switch input:checked + .switch-slider { background: #a4231d; }
  .switch input:checked + .switch-slider::before { transform: translateX(18px); }
  #mode-desc { margin-top: 6px; font-size: 16.5px; line-height: 1.4; color: #777; }

  .tool-item, .log-item { padding: 6px 0; border-bottom: 1px solid #e5e5e5; font-size: 18px; }
  .tool-item:last-child, .log-item:last-child { border-bottom: none; }
  .tool-item .tname, .log-item .tname { font-weight: 600; font-family: ui-monospace, monospace; }
  .tool-item .tdesc, .log-item .tdesc { color: #777; margin-top: 2px; line-height: 1.35; }
  .log-item .tname { font-family: inherit; font-weight: 400; color: #555; font-size: 0.9em; }

  .sidebar-section-title a {
    float: right; text-decoration: none; color: inherit; font-weight: 400;
    text-transform: none; letter-spacing: normal; cursor: pointer;
  }
  .sidebar-section-title a:hover { color: #2b6cb0; }

  #usage-box { font-size: 16.5px; color: #555; line-height: 1.5; }
  #usage-box .over-limit { color: #a4231d; font-weight: 600; }

  #sidebar-resizer {
    width: 5px; flex-shrink: 0; height: 100vh; cursor: col-resize;
    background: transparent;
  }
  #sidebar-resizer:hover, #sidebar-resizer.dragging { background: #2b6cb0; }

  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; height: 100vh; }
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
  .msg.working {
    align-self: stretch; display: flex; align-items: center; gap: 8px;
    color: #888; font-size: 17px;
  }
  .working-dots { display: inline-flex; gap: 3px; }
  .working-dots span {
    width: 6px; height: 6px; border-radius: 50%; background: #999;
    animation: working-bounce 1.1s infinite ease-in-out;
  }
  .working-dots span:nth-child(2) { animation-delay: 0.15s; }
  .working-dots span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes working-bounce {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
    40% { transform: scale(1); opacity: 1; }
  }
  .working-timer { font-variant-numeric: tabular-nums; }

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
  .msg .table-wrap { overflow-x: auto; max-width: 100%; margin: 6px 0; }
  .msg table { border-collapse: collapse; font-size: 0.9em; }
  .msg th, .msg td { border: 1px solid rgba(0, 0, 0, 0.15); padding: 6px 10px; text-align: left; }
  .msg th { font-weight: 600; background: rgba(0, 0, 0, 0.04); }
  .msg h1, .msg h2, .msg h3 { margin: 0.5em 0 0.25em; line-height: 1.3; }
  .msg h1 { font-size: 1.3em; }
  .msg h2 { font-size: 1.15em; }
  .msg h3 { font-size: 1.05em; }
  .msg img, .msg video {
    max-width: 100%; border-radius: 8px; margin: 6px 0; display: block;
    border: 1px solid rgba(0, 0, 0, 0.08);
  }

  form#composer {
    display: flex; gap: 8px; padding: 12px 20px; border-top: 1px solid #ddd;
    background: #fff; flex-shrink: 0;
  }
  #input {
    flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 17.5px;
    font-family: inherit; resize: none; overflow-y: auto; max-height: 200px; line-height: 1.4;
  }
  #send { padding: 10px 18px; border-radius: 8px; border: none; background: #2b6cb0; color: #fff; font-size: 17.5px; cursor: pointer; }
  #send:disabled { opacity: 0.5; cursor: default; }
  #send.stop { background: #a4231d; }

  @media (prefers-color-scheme: dark) {
    body { background: #17181c; color: #e6e6e6; }
    #sidebar { background: #1b1c20; border-color: #2c2d31; }
    #sidebar .meta { color: #999; }
    .sidebar-section-title { color: #888; }
    #role-select, #reset-btn, #open-workspace-btn { background: #24262c; color: #e6e6e6; border-color: #444; }
    .tool-item, .log-item { border-color: #2c2d31; }
    .tool-item .tdesc, .log-item .tdesc { color: #999; }
    #mode-desc { color: #999; }
    .switch-slider { background: #444; }
    .log-item .tname { color: #999; }
    .sidebar-section-title a:hover { color: #5a9fd4; }
    #usage-box { color: #aaa; }
    form#composer { background: #1f2126; border-color: #333; }
    #input { background: #24262c; color: #e6e6e6; border-color: #444; }
    .msg code { background: rgba(255, 255, 255, 0.12); }
    .msg pre.codeblock { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.1); }
    .msg .tok-k { color: #c678dd; }
    .msg .tok-s { color: #98c379; }
    .msg .tok-c { color: #7f848e; }
    .msg .tok-n { color: #d19a66; }
    .msg th, .msg td { border-color: rgba(255, 255, 255, 0.15); }
    .msg th { background: rgba(255, 255, 255, 0.06); }
    .msg img, .msg video { border-color: rgba(255, 255, 255, 0.12); }
  }
</style>
</head>
<body>
<div id="sidebar">
  <div class="brand">
    <img class="brand-logo" src="{{ logo_src }}" alt="">
    <h1>Talaria</h1>
  </div>
  <div class="meta">provider: {{ provider_name }} &middot; model: {{ model_name }}</div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">Role</div>
    <select id="role-select">
      {% for name, info in roles.items() %}
      <option value="{{ name }}" {% if name == role %}selected{% endif %}>{{ name }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">Settings</div>
    <div class="setting-row">
      <span id="mode-label">Safe mode</span>
      <label class="switch" title="Confirmations for run_python / install_package / propose_skill appear in the TERMINAL running this server, not here — check there if a message seems to hang.">
        <input type="checkbox" id="mode-toggle">
        <span class="switch-slider"></span>
      </label>
    </div>
    <div id="mode-desc" class="tdesc">run_python / install_package ask for confirmation in the terminal.</div>
  </div>
  <div class="sidebar-section">
    <button id="reset-btn" type="button">Reset history</button>
    <button id="open-workspace-btn" type="button" title="Opens the workspace folder on the machine running this server">Open workspace folder</button>
  </div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">Usage</div>
    <div id="usage-box">Loading…</div>
  </div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">
      Autonomous log
      <a id="autonomous-log-refresh" href="#" title="Reload — this updates outside the web UI's own requests">&#8635;</a>
    </div>
    <div id="autonomous-log">Loading…</div>
  </div>
  <div class="sidebar-section">
    <div class="sidebar-section-title">
      Cron jobs
      <a id="cron-refresh" href="#" title="Reload — jobs can be added/changed from chat (cron_add etc.) or by the scheduler firing them">&#8635;</a>
    </div>
    <div id="cron-list">Loading…</div>
  </div>
  <div class="sidebar-section sidebar-tools">
    <div class="sidebar-section-title">Tools</div>
    <div id="tools-list">Loading…</div>
  </div>
</div>
<div id="sidebar-resizer"></div>
<div id="main">
  <div id="messages"><div id="messages-inner"></div></div>
  <form id="composer">
    <textarea id="input" placeholder="Type a message… (Shift+Enter for a new line)" rows="1"></textarea>
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
const openWorkspaceBtn = document.getElementById("open-workspace-btn");
const toolsList = document.getElementById("tools-list");
const usageBox = document.getElementById("usage-box");
const autonomousLog = document.getElementById("autonomous-log");
const autonomousLogRefresh = document.getElementById("autonomous-log-refresh");
const cronList = document.getElementById("cron-list");
const cronRefresh = document.getElementById("cron-refresh");
const sidebar = document.getElementById("sidebar");
const sidebarResizer = document.getElementById("sidebar-resizer");
const modeToggle = document.getElementById("mode-toggle");
const modeLabel = document.getElementById("mode-label");
const modeDesc = document.getElementById("mode-desc");

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

// Turns one GFM-style pipe table (header row + |---|---| separator row +
// zero or more data rows, already split apart by the caller) into a real
// <table>. The separator row may carry alignment markers (:---, :---:,
// ---:), reflected as a text-align style on the matching column.
function renderTable(block) {
  const lines = block.split("\n").filter((l) => l.trim() !== "");
  if (lines.length < 2) return null;

  const splitRow = (line) => {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|")) s = s.slice(0, -1);
    return s.split("|").map((c) => c.trim());
  };

  const header = splitRow(lines[0]);
  const aligns = splitRow(lines[1]).map((c) => {
    const left = c.startsWith(":");
    const right = c.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return "";
  });
  const dataRows = lines.slice(2).map(splitRow);

  const cell = (tag, c, i) =>
    "<" + tag + (aligns[i] ? ' style="text-align:' + aligns[i] + '"' : "") + ">" + c + "</" + tag + ">";

  let html = "<table><thead><tr>";
  html += header.map((c, i) => cell("th", c, i)).join("");
  html += "</tr></thead>";
  if (dataRows.length) {
    html += "<tbody>";
    html += dataRows.map((row) => "<tr>" + row.map((c, i) => cell("td", c, i)).join("") + "</tr>").join("");
    html += "</tbody>";
  }
  html += "</table>";
  return '<div class="table-wrap">' + html + "</div>";
}

const VIDEO_EXTENSIONS = new Set(["mp4", "webm", "ogg", "mov"]);

// A relative path (from the model's own workspace-relative filenames)
// resolves against the /workspace-file/ route below; an http(s)/data URL
// is used as-is. Segments are encoded individually so a path with a
// subdirectory still works ("/" itself must survive unencoded).
function resolveMediaSrc(src) {
  if (/^(https?:|data:)/i.test(src)) return src;
  const clean = src.replace(/^\.?\//, "");
  return "/workspace-file/" + clean.split("/").map(encodeURIComponent).join("/");
}

function renderMedia(alt, src) {
  const url = resolveMediaSrc(src);
  const ext = (src.split(".").pop() || "").toLowerCase();
  if (VIDEO_EXTENSIONS.has(ext)) {
    return '<video controls src="' + url + '">' + alt + "</video>";
  }
  return '<img src="' + url + '" alt="' + alt + '" loading="lazy">';
}

// Small, dependency-free renderer for the subset of Markdown models
// actually use in replies: headings, inline/fenced code, bold, italic,
// tables, images/videos, and "- " bullet lists. Input is HTML-escaped
// first, so nothing the model writes can inject markup — the only tags
// produced come from here.
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
  html = html.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => renderMedia(alt, src));
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(
    /(^|\n)(\|[^\n]*\|[ \t]*\n\|[ \t:|-]+\|[ \t]*\n(?:\|[^\n]*\|[ \t]*(?:\n|$))*)/g,
    (match, pre, block) => {
      const rendered = renderTable(block);
      return rendered ? pre + rendered : match;
    }
  );
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

// Grows the composer textarea to fit what's typed (up to the CSS
// max-height, beyond which it scrolls internally instead), and shrinks it
// back down as text is deleted — so a long pasted message stays fully
// visible instead of scrolling inside a single fixed-height line.
function autoGrowInput() {
  input.style.height = "auto";
  input.style.height = input.scrollHeight + "px";
}
input.addEventListener("input", autoGrowInput);

// Enter sends the message (like a normal chat input); Shift+Enter inserts
// a literal newline instead, since a plain <textarea> would otherwise
// just add a newline on every Enter and never submit.
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

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
let genStartTime = 0;
let genTimerInterval = null;
let workingDiv = null;

function formatElapsed(seconds) {
  if (seconds < 60) return seconds + "s";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m + ":" + String(s).padStart(2, "0");
}

// Shared by an actual send and by noticing on page load that a reply kicked
// off before a reload is still running server-side (see checkOngoingGeneration)
// — both cases show the same "Thinking…" bubble + live timer and lock the
// composer the same way.
function startWorkingIndicator() {
  input.disabled = true;
  generating = true;
  sendBtn.classList.add("stop");
  sendBtn.textContent = "Stop";

  genStartTime = Date.now();
  workingDiv = addMessage("", "working", false, true);
  workingDiv.innerHTML =
    '<span class="working-dots"><span></span><span></span><span></span></span>' +
    '<span class="working-timer">Thinking… 0s</span>';
  genTimerInterval = setInterval(() => {
    const timerEl = workingDiv ? workingDiv.querySelector(".working-timer") : null;
    if (!timerEl) {
      clearInterval(genTimerInterval);
      return;
    }
    const elapsed = Math.floor((Date.now() - genStartTime) / 1000);
    timerEl.textContent = "Thinking… " + formatElapsed(elapsed);
  }, 500);
}

function stopWorkingIndicator() {
  clearInterval(genTimerInterval);
  if (workingDiv) { workingDiv.remove(); workingDiv = null; }
  input.disabled = false;
  generating = false;
  sendBtn.textContent = "Send";
  sendBtn.classList.remove("stop");
}

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
  autoGrowInput();
  stopRequested = false;
  startWorkingIndicator();

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
      if (!replyDiv) {
        if (workingDiv) { workingDiv.remove(); workingDiv = null; }
        replyDiv = addMessage("", "assistant", true, false);
      }
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
    stopWorkingIndicator();
    input.focus();
    loadUsage();
  }
});

async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  // Idempotent (clears first) — also reused once a resumed generation
  // finishes, to pull in the reply that arrived while this page was gone.
  messagesEl.innerHTML = "";
  for (const turn of data.turns) {
    if (turn.role === "user") {
      addMessage(turn.text, "user", false, false);
    } else {
      addMessage(turn.text, "assistant", true, false);
    }
  }
  scrollEl.scrollTop = scrollEl.scrollHeight;
}

// A reply kicked off before a reload (or from another tab) keeps running
// server-side regardless — this notices that on load and shows the same
// working indicator a live send would, instead of the page just looking
// idle while the model is still actually working.
async function checkOngoingGeneration() {
  let res;
  try {
    res = await fetch("/api/generating");
  } catch (err) {
    return;
  }
  const data = await res.json();
  if (!data.generating) return;

  stopRequested = false;
  startWorkingIndicator();

  const poll = setInterval(async () => {
    let r;
    try {
      r = await fetch("/api/generating");
    } catch (err) {
      return;
    }
    const d = await r.json();
    if (!d.generating) {
      clearInterval(poll);
      stopWorkingIndicator();
      await loadHistory();
      loadUsage();
    }
  }, 1000);
}

(async () => {
  await loadHistory();
  await checkOngoingGeneration();
})();

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

// Formats an ISO-8601 UTC timestamp (as written by talaria.autonomous) in
// the browser's own local time/format, falling back to the raw string if
// parsing fails for some reason.
function formatLogTimestamp(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

async function loadAutonomousLog() {
  const res = await fetch("/api/autonomous-log");
  const data = await res.json();
  autonomousLog.innerHTML = "";
  if (!data.entries.length) {
    autonomousLog.textContent = "(no autonomous check-ins yet — see the Autonomous mode section in the README)";
    return;
  }
  // Newest first, capped so an old, huge log doesn't blow up the sidebar.
  for (const e of data.entries.slice(-20).reverse()) {
    const item = document.createElement("div");
    item.className = "log-item";
    const when = document.createElement("div");
    when.className = "tname";
    // goal_focus()'s output is multi-line ("FOCUS: ...\nPriority: ...\n...")
    // — only the first line is worth showing in this compact list.
    const focusLine = (e.focus || "").split("\n")[0];
    when.textContent = formatLogTimestamp(e.ts) + " — " + focusLine;
    const reply = document.createElement("div");
    reply.className = "tdesc";
    reply.textContent = e.reply.length > 400 ? e.reply.slice(0, 400) + "…" : e.reply;
    item.appendChild(when);
    item.appendChild(reply);
    autonomousLog.appendChild(item);
  }
}
loadAutonomousLog();

autonomousLogRefresh.addEventListener("click", (e) => {
  e.preventDefault();
  autonomousLog.textContent = "Loading…";
  loadAutonomousLog();
});

async function loadCronJobs() {
  const res = await fetch("/api/cron");
  const data = await res.json();
  cronList.innerHTML = "";
  if (!data.jobs.length) {
    cronList.textContent = "(no cron jobs — ask the agent to schedule one with cron_add)";
    return;
  }
  for (const j of data.jobs) {
    const item = document.createElement("div");
    item.className = "log-item";
    const when = document.createElement("div");
    when.className = "tname";
    const label = j.name ? j.name + " — " : "";
    when.textContent = "#" + j.id + " " + label + j.schedule + (j.enabled ? "" : " (disabled)");
    const desc = document.createElement("div");
    desc.className = "tdesc";
    desc.textContent = "last run: " + (j.last_run ? formatLogTimestamp(j.last_run) : "never");
    item.appendChild(when);
    item.appendChild(desc);
    cronList.appendChild(item);
  }
}
loadCronJobs();

cronRefresh.addEventListener("click", (e) => {
  e.preventDefault();
  cronList.textContent = "Loading…";
  loadCronJobs();
});

function applyMode(safe) {
  modeToggle.checked = !safe;
  modeLabel.textContent = safe ? "Safe mode" : "Extreme mode";
  modeLabel.classList.toggle("danger", !safe);
  modeDesc.textContent = safe
    ? "run_python / install_package ask for confirmation in the terminal."
    : "run_python / install_package execute immediately — no confirmation prompt.";
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  applyMode(data.safe_mode);
}
loadSettings();

modeToggle.addEventListener("change", async () => {
  const wantSafe = !modeToggle.checked;
  if (!wantSafe) {
    const ok = confirm(
      "Extreme mode runs model-generated code with NO confirmation prompt, " +
      "with your OS-level permissions. Are you sure?"
    );
    if (!ok) {
      modeToggle.checked = true;
      return;
    }
  }
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ safe_mode: wantSafe }),
  });
  const data = await res.json();
  applyMode(data.safe_mode);
});

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

openWorkspaceBtn.addEventListener("click", async () => {
  openWorkspaceBtn.disabled = true;
  try {
    const res = await fetch("/api/open-workspace", { method: "POST" });
    const data = await res.json();
    if (!data.ok) {
      addMessage("Could not open workspace folder: " + data.error, "error");
    }
  } catch (err) {
    addMessage("Network error: " + err, "error");
  } finally {
    openWorkspaceBtn.disabled = false;
  }
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
    state = {
        "role": config.default_role if config.default_role in ROLES else DEFAULT_ROLE,
        "history": compact_history(load_history(config.memory_file), config.max_history_turns),
        "cancel_event": None,
        # Safe mode (default, from .env) asks for a y/N confirmation in the
        # terminal before run_python/install_package execute. Extreme mode
        # skips that prompt entirely. A callable (not the bool itself) is
        # handed to build_tools so flipping this via the sidebar toggle
        # takes effect on the next tool call, with no rebuild/restart.
        "safe_mode": config.confirm_code_exec,
    }
    tools = build_tools(config, provider, usage=usage, confirm_code_exec=lambda: state["safe_mode"])
    agent = Agent(
        provider, tools, system=build_system(state["role"], config.notes_file),
        max_turns=config.max_turns, usage=usage,
    )
    agent.add_tools([make_propose_skill_tool(provider, config.skills_dir, agent, usage=usage)])
    # Runs jobs scheduled via cron_add for as long as this process stays up
    # — see talaria/cron_scheduler.py for why that's an acceptable
    # limitation at this stage.
    start_cron_scheduler(config, provider, usage)
    chat_lock = threading.Lock()

    @app.route("/")
    def index():
        model_name = (
            config.claude_model if config.provider == "claude" else config.openai_compat_model
        )
        return render_template_string(
            INDEX_HTML,
            provider_name=config.provider,
            model_name=model_name,
            role=state["role"],
            roles=ROLES,
            logo_src=_load_logo_data_uri(),
        )

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json(force=True) or {}
        user_input = (data.get("message") or "").strip()
        if not user_input:
            return jsonify({"error": "empty message"}), 400

        agent.system = build_system(state["role"], config.notes_file) + WEB_MEDIA_HINT
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

        agent.system = build_system(state["role"], config.notes_file) + WEB_MEDIA_HINT
        history = state["history"]
        history_len_before = len(history)

        q: queue.Queue = queue.Queue()
        cancel_event = threading.Event()
        state["cancel_event"] = cancel_event

        # Runs to completion (and always saves/rolls back history) regardless
        # of whether anything is still reading `q` afterwards — the browser
        # tab can be closed or reloaded mid-stream, but the model call it
        # kicked off keeps running server-side either way, so finishing it
        # cleanly can't depend on a client still being attached to consume
        # the stream.
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
                state["history"] = compact_history(history, config.max_history_turns)
                save_history(config.memory_file, state["history"])
                state["cancel_event"] = None
                q.put(("done", ""))
            except Exception as e:
                print(f"\n[web] error: {e}")
                del history[history_len_before:]
                state["cancel_event"] = None
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
            return jsonify({"error": first_payload}), 500

        if first_kind == "done":
            return Response("", mimetype="text/plain")

        def generate():
            yield first_payload
            while True:
                kind, payload = q.get()
                if kind == "chunk":
                    yield payload
                elif kind in ("error", "done"):
                    return

        return Response(generate(), mimetype="text/plain")

    @app.route("/api/chat/stop", methods=["POST"])
    def chat_stop():
        cancel_event = state.get("cancel_event")
        if cancel_event is None:
            return jsonify({"ok": False, "error": "nothing is generating"}), 409
        cancel_event.set()
        return jsonify({"ok": True})

    @app.route("/api/generating")
    def generating_endpoint():
        # A reply kicked off from /api/chat/stream keeps running server-side
        # (in its worker thread) even if the page that started it is closed
        # or reloaded — this lets a freshly loaded page notice that and show
        # a working indicator instead of looking like nothing is happening.
        return jsonify({"generating": state.get("cancel_event") is not None})

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

    @app.route("/api/autonomous-log")
    def autonomous_log():
        # Written by talaria.autonomous, a separate process — read fresh
        # from disk on every request rather than cached, since it changes
        # outside this server's own request/response cycle.
        path = os.path.join(config.workspace_dir, ".autonomous_log.json")
        entries = []
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    entries = data
            except Exception:
                entries = []
        return jsonify({"entries": entries})

    @app.route("/api/cron")
    def cron_endpoint():
        # Jobs are also added/edited by the agent itself (cron_add etc.,
        # talaria/tools/cron.py) from any chat turn, not just this
        # process's own scheduler thread — read fresh from disk rather
        # than caching.
        return jsonify({"jobs": load_cron_jobs(config.workspace_dir)})

    @app.route("/workspace-file/<path:relpath>")
    def workspace_file(relpath):
        # Backs inline ![...](...) image/video rendering in the chat — the
        # extension allowlist (not just path-sandboxing) matters here since
        # this is a bare, unauthenticated GET: without it, a crafted
        # markdown tag could read .env-adjacent state files that also live
        # under WORKSPACE_DIR (.history.json, .goals.json, ...).
        if os.path.splitext(relpath)[1].lower() not in _MEDIA_EXTENSIONS:
            abort(403)
        try:
            full_path = resolve_path(config.workspace_dir, relpath)
        except WorkspaceError:
            abort(403)
        if not os.path.isfile(full_path):
            abort(404)
        return send_file(full_path)

    @app.route("/api/open-workspace", methods=["POST"])
    def open_workspace():
        # Opens the folder on the machine running this server, using its
        # native file manager — makes sense for the common case (server and
        # browser on the same machine, WEB_HOST=127.0.0.1) but note this is
        # NOT "open on the device viewing the page" if accessed over a LAN.
        path = os.path.abspath(config.workspace_dir)
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606 - local-only opener, no user input in path
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "path": path})

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

    @app.route("/api/settings", methods=["GET", "POST"])
    def settings_endpoint():
        if request.method == "POST":
            data = request.get_json(force=True) or {}
            if "safe_mode" in data:
                state["safe_mode"] = bool(data["safe_mode"])
        return jsonify({"safe_mode": state["safe_mode"]})

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
        "Confirmations for run_python / install_package / propose_skill appear "
        "HERE in this terminal, not in the browser — check back here if a chat message "
        "seems to hang."
    )
    app.run(host=config.web_host, port=config.web_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
