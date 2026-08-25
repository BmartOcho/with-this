<!-- refreshed: 2026-08-25 -->
# Architecture

**Analysis Date:** 2026-08-25

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          Entry / Frontends                          │
├──────────────┬──────────────┬───────────────────┬───────────────────┤
│  match (CLI) │  chat (TTY)  │   app (browser)   │   mcp (stdio)     │
│  `cli.py`    │  `chat.py`   │ `app/__init__.py` │   `mcp.py`        │
│              │              │ `app/server.py`   │                   │
│              │              │ `app/runner.py`   │                   │
│              │              │ `app/page.py`     │                   │
└──────┬───────┴──────┬───────┴─────────┬─────────┴─────────┬─────────┘
       │              │                 │                   │
       ▼              ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Pure matching core — `partsmatcher/matcher.py`         │
│   parse_inventory / parse_projects / evaluate / match               │
│   (no I/O; decoded JSON in, MatchReport out)                        │
└─────────────────────────────────────────────────────────────────────┘
       │                              │
       ▼                              ▼
┌──────────────────────┐   ┌────────────────────────────────────────┐
│  User's JSON files   │   │  Session workspace (temp dir)          │
│  inventory.json      │   │  CLAUDE.md, inventory.json,            │
│  projects.json       │◄──│  projects.json, aliases.jsonl,         │
│  *.aliases.jsonl     │   │  photos/, .partsmatcher-session.json   │
│  (`samples/` bundled)│   │  (sync-back with .bak backups)         │
└──────────────────────┘   └────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Matching core | Parse inventory/projects, multiset-coverage matching, three-bucket report | `partsmatcher/matcher.py` |
| Public API | Re-exports the core symbols + `__version__` | `partsmatcher/__init__.py` |
| CLI | Argument parsing, file I/O, human/JSON rendering, subcommand dispatch | `partsmatcher/cli.py` |
| Module entry | `python -m partsmatcher` → `cli.main` | `partsmatcher/__main__.py` |
| Chat session | Workspace prep, CLAUDE.md context generation, interactive `claude` launch, sync-back, `recover` machinery | `partsmatcher/chat.py` |
| App orchestrator | Reuses chat workspace machinery, adds permission settings, wires runner + server | `partsmatcher/app/__init__.py` |
| HTTP server | `ThreadingHTTPServer`, page + JSON endpoints, per-session token auth, SSE streaming | `partsmatcher/app/server.py` |
| Turn runner | One headless `claude -p --resume` subprocess per turn, stream-json → event vocabulary | `partsmatcher/app/runner.py` |
| Embedded page | Single-file HTML/CSS/JS page as a Python string, token substituted per session | `partsmatcher/app/page.py` |
| MCP server | JSON-RPC 2.0 over stdio: `get_inventory`, `match_projects`, `check_bom` tools; HEPH BOM adapter | `partsmatcher/mcp.py` |
| Sample data | Bundled default inventory/projects so the tool runs out of the box | `partsmatcher/samples/*.json` |

## Pattern Overview

**Overall:** Pure functional core with multiple thin frontends (hexagonal / ports-and-adapters in miniature), stdlib-only.

**Key Characteristics:**
- Zero third-party dependencies anywhere — `http.server`, `subprocess`, `argparse`, `json`, `dataclasses` only. This is a project-wide rule (stated in `partsmatcher/mcp.py` docstring).
- The core (`matcher.py`) does no I/O: parsers take already-decoded JSON values; frontends own file reading and rendering.
- Claude integration is always the user's locally installed, already-logged-in `claude` binary via subprocess — never the Anthropic API, no API keys anywhere.
- Dependency injection for testability: `which`, `popen`, `launch`, `serve`, stdio streams are all injectable parameters so tests never need Claude installed.

## Layers

**Core (matcher):**
- Purpose: deterministic parsing + matching logic
- Location: `partsmatcher/matcher.py`
- Contains: dataclasses (`Inventory`, `Project`, `MissingPart`, `ProjectMatch`, `MatchReport`), parse functions, `evaluate`, `match`, `normalize_name`
- Depends on: stdlib only
- Used by: every frontend (`cli.py`, `chat.py`, `mcp.py`, `app/server.py`, `app/__init__.py`)

**CLI (dispatch + rendering):**
- Purpose: subcommand parsing, file loading, human/JSON output
- Location: `partsmatcher/cli.py`
- Contains: `build_parser`, `main`, `_run_match`/`_run_chat`/`_run_app`/`_run_mcp`/`_run_recover`, `_gather_session_inputs` (shared session loader for chat + app), `_print_human` renderer
- Depends on: `matcher.py` always; `chat`, `app`, `mcp` imported lazily inside `_run_*` so `match` never pays for them
- Used by: `__main__.py`, console script `partsmatcher` (`pyproject.toml [project.scripts]`)

**Session layer (chat):**
- Purpose: prepare a temp workspace with generated `CLAUDE.md` context + copies of data files, launch Claude, sync edits back with `.bak` backups, recover crashed sessions
- Location: `partsmatcher/chat.py`
- Contains: `run_chat`, `build_context_markdown`, `prepare_workspace`, `_sync_inventory`/`_sync_projects`/`_sync_aliases`, `recover_session`, `list_workspaces`, `clean_workspaces`, `WorkspaceStatus`
- Depends on: `matcher.py`
- Used by: `cli.py` (lazily), `app/__init__.py` (imports the private sync/workspace helpers directly)

**App layer (browser frontend):**
- Purpose: same session mechanics as chat but served on localhost with headless per-turn Claude
- Location: `partsmatcher/app/` (`__init__.py` orchestrates, `server.py` serves, `runner.py` drives Claude, `page.py` is the UI)
- Depends on: `chat.py` (workspace/sync helpers), `matcher.py`
- Used by: `cli.py` `app` subcommand

**MCP layer:**
- Purpose: expose the matcher as MCP tools so any Claude Code session on the machine consults real inventory
- Location: `partsmatcher/mcp.py`
- Depends on: `matcher.py`; borrows `cli._print_human` (deferred import) for `match_projects` output
- Used by: `cli.py` `mcp` subcommand

## Data Flow

### `match` (deterministic report)

1. `cli.main` prepends implicit `match` subcommand if none given (`partsmatcher/cli.py:606`)
2. `_run_match` resolves paths (falling back to `partsmatcher/samples/`), loads JSON (`cli.py:429-434`)
3. `parse_inventory` / `parse_projects` validate schema, raising `PartsMatcherError` (`matcher.py:120`, `matcher.py:143`)
4. `match()` evaluates every project independently against the full inventory (multiset coverage; projects never consume parts from each other) and buckets into build_now / almost / not_yet (`matcher.py:277`)
5. Output: `_print_human` (ANSI-aware, encoding-aware marks) or `_report_to_dict` → JSON (`cli.py:374`, `cli.py:349`)

### `chat` (interactive session)

1. `_gather_session_inputs` loads inventory/projects/photos, resolves persistent stores (`cli.py:450`) — bundled samples never get written back
2. `run_chat` finds `claude`, builds workspace: generated `CLAUDE.md` (guarded so a foreign CLAUDE.md is never overwritten), `inventory.json`, `projects.json`, `aliases.jsonl`, staged `photos/`, session record `.partsmatcher-session.json` (`chat.py:1001-1070`)
3. Interactive `claude` inherits the terminal, edits workspace files (`chat.py:1102-1108`)
4. On exit, `_sync_inventory`/`_sync_projects`/`_sync_aliases` validate workspace edits and write them back to the user's files with `.bak` backups (`chat.py:1110-1127`)
5. Unclean exit → `partsmatcher recover` replays the same sync from the session record (`chat.py:884`)

### `app` (browser session)

1. Same workspace prep as chat, plus `write_permission_settings` writes `.claude/settings.local.json` pinning writes to the workspace (`app/__init__.py:87`)
2. `make_server` binds a `ThreadingHTTPServer` on 127.0.0.1 with a per-run `secrets.token_urlsafe` token (`app/server.py:254`)
3. Browser page → `POST /api/message` → `ClaudeTurnRunner.run_turn` spawns `claude -p <msg> --output-format stream-json [--resume <id>]`, parses stream-json into `{session|text|tool|done|error}` events streamed back as `text/event-stream` (`app/runner.py:99`, `app/server.py:209`)
4. `GET /api/state` re-reads `inventory.json`/`projects.json` from the workspace on every call and recomputes the match report — no in-memory state tracking (`app/server.py:82`)
5. `POST /api/end` or Ctrl-C runs the run-once sync (same chat helpers) and shuts down (`app/server.py:204`, `app/__init__.py:225-237`)

### `mcp` (tool server)

1. `MCPServer.serve` reads one JSON-RPC message per line on stdin (`mcp.py:354`)
2. `handle_message` is pure request-in/response-out; `initialize`, `ping`, `tools/list`, `tools/call` (`mcp.py:288`)
3. Inventory/projects re-read from disk on every tool call, so mid-session edits are seen (`mcp.py:237`)
4. `check_bom` adapts HEPH `bom.json` (`{"lines": [{"key", "description", "qty"}]}`) onto the project contract, preferring whichever spelling the inventory recognizes (`mcp.py:119`); misses get `difflib` closest-name hints, deliberately no fuzzy matching
5. Tool failures return `isError: true` results, not protocol errors, so the model can recover (`mcp.py:328-334`)

**State Management:**
- No databases, no global state. All persistent state is the user's JSON files; all session state lives in the temp workspace and is synced back on exit. The app server re-derives sidebar state from disk per request.

## Key Abstractions

**`Inventory` / `Project` (parsed inputs):**
- Purpose: normalized-name-keyed quantities with original display spellings kept separately
- Examples: `partsmatcher/matcher.py:72`, `matcher.py:135`
- Pattern: `normalize_name` (trim, collapse spaces, casefold) is the single canonical comparison; quantity-0 inventory entries are retained for vocabulary but excluded from `on_hand()`/counts

**`MatchReport` / `ProjectMatch` / `MissingPart`:**
- Purpose: the three-bucket verdict with per-part deficits; `to_dict()` for JSON output
- Examples: `matcher.py:255`, `matcher.py:201`, `matcher.py:190`

**Session workspace:**
- Purpose: an isolated temp dir (`partsmatcher-chat-*` prefix) Claude may freely edit; the sync-back is the only path to the user's real files
- Examples: `chat.py:355` (`_resolve_workspace_dir`), `chat.py:376` (`prepare_workspace`), `chat.py:588` (`_write_session_record`)
- Pattern: session record + original-text snapshots make sync idempotent and recoverable

**Event vocabulary (app turns):**
- Purpose: decouple Claude Code's stream-json format from the page
- Examples: `app/runner.py:9-13` — `{"type": "session"|"text"|"tool"|"done"|"error"}`

**BOM adapter:**
- Purpose: map an external BOM format (HEPH) onto the matcher's project contract without changing the core
- Examples: `mcp.py:119` (`bom_as_project`), `mcp.py:157` (`check_bom_text`)

## Entry Points

**Console script / module:**
- Location: `partsmatcher/cli.py:596` (`main`), `partsmatcher/__main__.py`
- Triggers: `partsmatcher ...` (via `pyproject.toml [project.scripts]`) or `python -m partsmatcher`
- Responsibilities: `--` splitting (pass-through args for `chat`), backwards-compat implicit `match`, subcommand dispatch to `match`/`chat`/`app`/`recover`/`mcp`

**Library import:**
- Location: `partsmatcher/__init__.py`
- Triggers: `from partsmatcher import match, parse_inventory, ...`
- Responsibilities: stable public API over the core only (no chat/app/mcp symbols exported)

**Pre-release smoke test:**
- Location: `scripts/real_claude_smoke.py`
- Triggers: manual, before a release
- Responsibilities: end-to-end app loop against the real `claude` binary over real HTTP (the automated suite fakes the binary)

## Architectural Constraints

- **Zero dependencies:** Stdlib only, everywhere — including the web app and MCP server. Do not add third-party packages.
- **Python floor:** `requires-python = ">=3.9"` (`pyproject.toml`); type annotations in strings (`"list[str]"`) and `from __future__ import annotations` keep 3.9 compatibility.
- **Threading:** The app uses `ThreadingHTTPServer`; concurrency is guarded by locks in `AppState` (`turn_busy`, `_sync_lock` in `app/server.py:69-73`) and `ClaudeTurnRunner.lock` (`app/runner.py:57`). One Claude turn at a time. `shutdown()` must be called from a non-handler thread (`app/server.py:135-138`).
- **Lazy imports:** `cli.py` imports `chat`, `app`, `mcp` only inside the subcommands that need them; `mcp.py` defers its `cli` import. Preserve this — `match` must stay light.
- **Windows-aware:** Path rules for headless permissions must be POSIX-normalized with lowercase drive letters (`app/__init__.py:61-84` `_workspace_edit_rule`); stdout/stdin reconfigured to UTF-8 for MCP (`cli.py:566-568`); encoding-aware output marks (`cli.py:335`).
- **Sample data is read-only:** Bundled samples (`partsmatcher/samples/`) are never sync targets — `inventory_store`/`projects_store` stay `None` for samples (`cli.py:504-513`).
- **App writes are pinned:** Headless Claude turns can only edit the session workspace, enforced by the generated `.claude/settings.local.json` `Edit(//...)` rule.

## Anti-Patterns

### I/O inside the core

**What happens:** Adding file reading, printing, or path handling to `partsmatcher/matcher.py`.
**Why it's wrong:** The core's whole design is decoded-JSON-in / report-out so every frontend (CLI, app, MCP, tests, future scanners) can reuse it.
**Do this instead:** Load and decode in the frontend (`cli.py:_load_json`, `mcp.py:_load_inventory`, `app/server.py:state_payload`) and pass plain values to `parse_inventory`/`parse_projects`/`match`.

### Bypassing the sync machinery

**What happens:** Writing directly to the user's inventory/projects files from a session feature.
**Why it's wrong:** Sync-back validates edits, writes `.bak` backups, is idempotent, and is recoverable after a crash via the session record — a direct write loses all of that.
**Do this instead:** Let Claude edit the workspace copies; route persistence through `_sync_inventory`/`_sync_projects`/`_sync_aliases` in `partsmatcher/chat.py`, and record enough in `.partsmatcher-session.json` for `recover`.

### Fuzzy name matching

**What happens:** Making `check_bom`/`match` guess at near-miss part names.
**Why it's wrong:** Deliberately avoided (`mcp.py` docstring): the naming-alias problem is shown honestly (NOT OWNED + closest-name hints) rather than papered over. Aliases are handled explicitly via `aliases.jsonl` records.
**Do this instead:** Keep matching exact on `normalize_name`; surface `difflib.get_close_matches` hints as suggestions, not matches.

## Error Handling

**Strategy:** One domain exception, `PartsMatcherError(ValueError)` (`matcher.py:23`), for "decoded fine as JSON but doesn't fit the schema". Frontends catch it at the boundary.

**Patterns:**
- CLI: catch `PartsMatcherError`, print `partsmatcher: error: {exc}` to stderr, return exit code 2 (`cli.py:435-437` and every `_run_*`)
- Parse errors carry location context: `"project #3 ('LED Cube'), part #2: ..."` built via `where=` strings
- MCP: tool failures become `isError: true` results the model can read; only protocol-level failures use JSON-RPC error objects; one bad message never kills the serve loop (`mcp.py:328`, `mcp.py:370`)
- App `/api/state`: parse failures while Claude is mid-edit degrade gracefully — the payload carries `inventory_error`/`report_error` and the page keeps its last good sidebar (`app/server.py:103-108`)
- Runner: subprocess launch failure and nonzero exits become `{"type": "error"}` events, never exceptions across the stream (`app/runner.py:104-131`)

## Cross-Cutting Concerns

**Logging:** None — output is `print()` to stdout (reports) and stderr (notes, errors, MCP diagnostics). The app handler silences `http.server` request logging (`app/server.py:148`).
**Validation:** All input validation lives in the core parsers (`_entry_list`, `_parse_part` in `matcher.py`); frontends never pre-validate schema.
**Authentication:** No API keys anywhere. Claude access is the user's logged-in `claude` binary. The app server authenticates POSTs with a per-session random token header (`X-PartsMatcher-Token`) plus an Origin check, using `hmac.compare_digest` (`app/server.py:167-175`).

---

*Architecture analysis: 2026-08-25*
