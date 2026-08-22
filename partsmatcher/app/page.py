"""The app's single page, embedded as a string so packaging stays trivial.

Vanilla HTML/CSS/JS, no external resources: the page talks to the local
server with `fetch` and reads the turn stream incrementally (the message
endpoint responds as a text/event-stream the page parses by hand).

The page is rendered per session by `render_page`, which substitutes the
session token the server requires on every POST.
"""

TOKEN_PLACEHOLDER = "__PM_TOKEN__"

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PartsMatcher</title>
<style>
  :root {
    --bg: #14161a; --panel: #1d2026; --line: #2c313a; --text: #e6e8eb;
    --dim: #9aa3af; --accent: #4cc38a; --warn: #e5c76b; --bad: #e5766b;
    --user: #24344a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    display: grid; grid-template-columns: minmax(0, 1fr) 340px; height: 100vh;
  }
  main { display: flex; flex-direction: column; min-width: 0; }
  header {
    padding: 10px 16px; border-bottom: 1px solid var(--line);
    display: flex; align-items: center; gap: 12px;
  }
  header h1 { font-size: 16px; margin: 0; }
  header .status { color: var(--dim); font-size: 13px; flex: 1; }
  button {
    background: var(--panel); color: var(--text); border: 1px solid var(--line);
    border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 13px;
  }
  button:hover { border-color: var(--accent); }
  button:disabled { opacity: .45; cursor: default; }
  #log { flex: 1; overflow-y: auto; padding: 16px; }
  .msg {
    max-width: 720px; margin: 0 auto 12px; padding: 10px 14px;
    border-radius: 10px; white-space: pre-wrap; overflow-wrap: break-word;
  }
  .msg.user { background: var(--user); }
  .msg.claude { background: var(--panel); }
  .msg.meta { background: none; color: var(--dim); font-size: 13px; text-align: center; }
  .msg .tool { color: var(--dim); font-size: 13px; font-style: italic; }
  form { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--line); }
  textarea {
    flex: 1; resize: none; background: var(--panel); color: var(--text);
    border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px;
    font: inherit; height: 62px;
  }
  aside {
    border-left: 1px solid var(--line); overflow-y: auto; padding: 14px 16px;
    background: #171a1f;
  }
  aside h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
             color: var(--dim); margin: 18px 0 8px; }
  aside h2:first-child { margin-top: 0; }
  aside ul { list-style: none; margin: 0; padding: 0; font-size: 13.5px; }
  aside li { padding: 2px 0; display: flex; justify-content: space-between; gap: 8px; }
  aside li .qty { color: var(--dim); }
  .grp { margin-bottom: 10px; }
  .grp .name { font-weight: 600; font-size: 13px; }
  .grp.now .name { color: var(--accent); }
  .grp.almost .name { color: var(--warn); }
  .grp.notyet .name { color: var(--bad); }
  .grp li { display: block; }
  .grp li .short { color: var(--dim); }
</style>
</head>
<body>
<main>
  <header>
    <h1>PartsMatcher</h1>
    <div class="status" id="status">connecting…</div>
    <button id="end">End session &amp; sync</button>
  </header>
  <div id="log"></div>
  <form id="form">
    <textarea id="input" placeholder="Describe parts, ask what to build, request wiring help…"
              autofocus></textarea>
    <button type="submit" id="send">Send</button>
  </form>
</main>
<aside>
  <h2>Inventory <span id="invcount"></span></h2>
  <ul id="inventory"></ul>
  <h2>Match report</h2>
  <div id="report"></div>
</aside>
<script>
// Session token, substituted server-side. Sent on every POST so a page
// on another origin can't drive this session.
const PM_TOKEN = '__PM_TOKEN__';
const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const endBtn = document.getElementById('end');
const statusEl = document.getElementById('status');
let busy = false, ended = false;

function bubble(cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text || '';
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function setBusy(value) {
  busy = value;
  sendBtn.disabled = value || ended;
  statusEl.textContent = ended ? 'session ended' : (value ? 'Claude is working…' : 'ready');
}

async function refreshState() {
  const res = await fetch('/api/state');
  const state = await res.json();
  renderState(state);
  return state;
}

function renderState(state) {
  const inv = document.getElementById('inventory');
  inv.innerHTML = '';
  document.getElementById('invcount').textContent =
    '· ' + state.inventory.part_types + ' types / ' + state.inventory.total_parts + ' parts';
  for (const part of state.inventory.parts) {
    const li = document.createElement('li');
    const name = document.createElement('span'); name.textContent = part.name;
    const qty = document.createElement('span'); qty.className = 'qty';
    qty.textContent = '×' + part.quantity;
    li.append(name, qty); inv.appendChild(li);
  }
  const rep = document.getElementById('report');
  rep.innerHTML = '';
  rep.className = '';
  if (!state.report) {
    rep.textContent = state.report_error || 'No project database loaded.';
    rep.className = 'msg meta'; return;
  }
  const groups = [
    ['now', 'BUILD NOW', state.report.build_now, p => ''],
    ['almost', 'ALMOST THERE', state.report.almost, p => ' — short ' + p.total_missing],
    ['notyet', 'NOT YET', state.report.not_yet, p => ' — short ' + p.total_missing],
  ];
  for (const [cls, label, items, suffix] of groups) {
    const div = document.createElement('div'); div.className = 'grp ' + cls;
    const name = document.createElement('div'); name.className = 'name';
    name.textContent = label + ' (' + items.length + ')';
    div.appendChild(name);
    if (items.length) {
      const ul = document.createElement('ul');
      for (const p of items) {
        const li = document.createElement('li');
        li.textContent = p.name;
        const extra = suffix(p);
        if (extra) {
          const s = document.createElement('span'); s.className = 'short';
          s.textContent = extra; li.appendChild(s);
        }
        ul.appendChild(li);
      }
      div.appendChild(ul);
    }
    rep.appendChild(div);
  }
}

async function sendTurn(message, displayAs) {
  if (busy || ended) return;
  setBusy(true);
  if (displayAs !== null) bubble('user', displayAs === undefined ? message : displayAs);
  let claudeDiv = null;
  try {
    const res = await fetch('/api/message', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-PartsMatcher-Token': PM_TOKEN},
      body: JSON.stringify({text: message}),
    });
    if (!res.ok) { bubble('meta', 'error: ' + await res.text()); return; }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let split;
      while ((split = buffer.indexOf('\\n\\n')) >= 0) {
        const chunk = buffer.slice(0, split); buffer = buffer.slice(split + 2);
        if (!chunk.startsWith('data: ')) continue;
        const event = JSON.parse(chunk.slice(6));
        if (event.type === 'text') {
          if (!claudeDiv) claudeDiv = bubble('claude', '');
          claudeDiv.textContent += (claudeDiv.textContent ? '\\n\\n' : '') + event.text;
        } else if (event.type === 'tool') {
          const t = document.createElement('div'); t.className = 'tool';
          t.textContent = '⚙ ' + event.name;
          (claudeDiv || (claudeDiv = bubble('claude', ''))).appendChild(t);
        } else if (event.type === 'error') {
          bubble('meta', 'error: ' + event.message);
        }
        log.scrollTop = log.scrollHeight;
      }
    }
  } catch (err) {
    bubble('meta', 'connection error: ' + err);
  } finally {
    setBusy(false);
    refreshState().catch(() => {});
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  sendTurn(text);
});
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});

endBtn.addEventListener('click', async () => {
  if (busy || ended) return;
  ended = true; setBusy(false);
  endBtn.disabled = true; input.disabled = true;
  const res = await fetch('/api/end', {
    method: 'POST', headers: {'X-PartsMatcher-Token': PM_TOKEN},
  });
  const result = await res.json();
  bubble('meta', 'Session synced:\\n' +
    (result.messages.length ? result.messages.join('\\n') : 'no changes to sync') +
    '\\nThe app has shut down — you can close this tab.');
  statusEl.textContent = 'session ended';
});

(async () => {
  // One fetch only: /api/state hands the kickoff out exactly once, so a
  // second fetch here would find it already consumed (and a page reload
  // correctly gets none — the session resumes without re-firing it).
  const state = await refreshState();
  if (state.kickoff) sendTurn(state.kickoff, null);
  else setBusy(false);
})();
</script>
</body>
</html>
"""


def render_page(token: str) -> str:
    """The page with this session's token substituted in."""
    return PAGE_TEMPLATE.replace(TOKEN_PLACEHOLDER, token)
