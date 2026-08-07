# PartsMatcher app — architecture proposal (pre-code)

Decision doc for the full local app (ROADMAP "Next", Ben 2026-08-07). Two
decisions to settle before any app code, each with options and a
recommendation. Nothing here is built yet.

The constant across every option: the app reuses the existing workspace
mechanics unchanged. `chat.py` already separates the three phases the app
needs — `prepare_workspace` + `build_context_markdown` (generated CLAUDE.md,
data files, session record), the launch itself, and `_sync_inventory` /
`_sync_projects` / `_sync_aliases` + `recover_session`. Only the middle
phase (how Claude is driven) changes; sync-back, alias logging, and
`recover` keep working because Claude still edits the same workspace files.

## Decision 1 — how the app drives the local Claude Code

### Option 1A: interactive terminal handoff (status quo)

The app prepares the workspace, then opens a real terminal running `claude`
(e.g. spawns the user's terminal app pointed at the workspace).

- **For:** zero new machinery; the full Claude Code UI (permission prompts,
  slash commands, image drops) for free; already tested.
- **Against:** it is not an embedded chat — it's a launcher button. The app
  can't render Claude's replies in its own UI, can't interleave app views
  (match report, photo review) with the conversation, and can't know when a
  turn ends. This fails Ben's framing: "chat embedded in the app."

### Option 1B: headless CLI, one `claude -p` process per turn

For each user message the app runs
`claude -p "<message>" --output-format stream-json` in the workspace,
using `--resume <session-id>` after the first turn so Claude Code's own
session store carries the conversation. The app streams the JSON events to
the browser as they arrive.

- **For:** stdlib `subprocess` only; same binary, same subscription login,
  no API key — the existing `find_claude` + `CLAUDE_NOT_FOUND_HINT` story
  holds. Each turn is a bounded process: a crash loses one turn, not the
  session, and `recover` semantics stay simple. Claude Code's session
  persistence (`--resume`) gives us conversation history for free and even
  survives app restarts.
- **Against:** per-turn process startup (~1–3 s before first token).
  Permission prompts can't be answered interactively in `-p` mode, so the
  workspace needs a settings file pre-allowing the tools the session uses
  (Read/Write/Edit in the workspace, the matcher command) — an explicit,
  auditable allowlist we generate next to CLAUDE.md.

### Option 1C: headless CLI, one long-lived process per session

Launch `claude --input-format stream-json --output-format stream-json -p`
once per session and speak newline-delimited JSON over stdin/stdout for
every turn.

- **For:** still stdlib-only; no per-turn spawn latency; a natural place
  for streaming and interrupt support.
- **Against:** the app now owns a long-lived child (liveness, restart,
  backpressure, protocol drift across CLI versions). A dead process
  mid-session is a new failure mode `recover` doesn't currently model.
  More moving parts for a v1 than the latency win justifies.

### Option 1D: Claude Agent SDK (Python)

`pip install claude-agent-sdk`; programmatic streaming, hooks, permission
callbacks.

- **For:** the richest control surface (per-tool-call permission callbacks,
  typed events).
- **Against:** first real third-party dependency, and it still spawns the
  same CLI underneath — for this app it's an abstraction layer over what
  1B/1C do directly. Version coupling between SDK and CLI becomes our
  problem. Worth revisiting if 1B's control surface proves too coarse.

**Recommendation: 1B** — per-turn `claude -p --resume` with `stream-json`
output. Simplest thing that makes the chat genuinely embedded, keeps the
zero-dependency rule intact even at the app boundary, and keeps failure
containment (one turn) aligned with the existing recover model. 1C is the
documented upgrade path if per-turn latency grates; the app's internal
"send a turn, stream events back" interface should be written so 1C can
slot in behind it without UI changes.

## Decision 2 — the app's own stack

### Option 2A: stdlib server + one static page (zero-dep everywhere)

`http.server.ThreadingHTTPServer` serving a single vanilla-HTML/JS/CSS
page from the package; JSON POST endpoints for actions (send message,
start/end session, run matcher); Server-Sent Events for streaming Claude's
reply tokens and status into the page. `python -m partsmatcher app` starts
the server on localhost and opens the browser (`webbrowser.open`).

- **For:** the zero-dependency rule holds for the whole product, not just
  the engine — install stays "clone and run", CI stays trivial, and the
  existing fake-injection test style extends to the server (inject fake
  launch, drive endpoints with `http.client`). SSE works fine over
  `http.server` with a threading server; no websockets needed for a
  localhost single-user app.
- **Against:** we hand-roll routing, SSE framing, and a no-framework
  frontend. For one user on localhost with maybe six endpoints, that's a
  few hundred lines, not a liability.

### Option 2B: relax the rule at the UI boundary (FastAPI + uvicorn, or Flask)

- **For:** websockets, routing, and static serving handled; nicer
  developer ergonomics if the app grows many views.
- **Against:** first dependencies in the project, a second install story
  (venv/pip), heavier CI, and none of it buys anything a localhost SSE app
  actually needs today. The batch-scanner review screen is still just
  forms and images.

### Option 2C: desktop shell (pywebview / Textual TUI / Electron)

Rejected for v1: packaging weight (Electron) or a dependency that only
wraps a browser we can open anyway (pywebview). A TUI contradicts the
point of leaving the terminal. The 2A page runs in the browser Ben already
has; a shell can wrap the same server later if a dock icon ever matters.

**Recommendation: 2A** — the zero-dependency rule stays project-wide.
App code lives in `partsmatcher/app/` (server, static assets, a
`ClaudeTurnRunner` wrapping 1B), importing the engine and `chat.py`
helpers; the engine gains no dependency on the app.

## Sketch of v1 if both recommendations are accepted

- `python -m partsmatcher app [inventory] [projects]` → prepares the
  workspace exactly as `run_chat` does (CLAUDE.md, data files, session
  record, allowlist settings), starts the localhost server, opens the page.
- Page: chat pane (SSE-streamed replies), sidebar with live inventory and
  the deterministic match report (re-rendered from the workspace files
  after each turn, since Claude edits them), and an explicit **End
  session** button that runs the existing sync-back and shows its messages.
- Server shutdown without End session leaves the session record in place —
  `recover` works unchanged, and the app can offer recovery on next start.
- Batch scanner later: its photo-review screen becomes another route on
  the same server, feeding the same confirmation → sync → alias pipeline.

## Open questions for Ben

1. Sign off on 1B and 2A (or pick otherwise)?
2. Turn-level permission allowlist: comfortable with the workspace
   pre-allowing file edits + the matcher command in headless mode (no
   per-action prompt, mirroring what sessions already do today)?
3. Should ending the app auto-sync (current chat behavior on exit), or is
   the explicit End-session button the only sync trigger?
