# Codebase Structure

**Analysis Date:** 2026-08-25

## Directory Layout

```
with-this/
├── partsmatcher/            # The package — everything ships from here
│   ├── __init__.py          # Public API: re-exports matcher core + __version__
│   ├── __main__.py          # `python -m partsmatcher` → cli.main
│   ├── matcher.py           # Pure matching core (no I/O), 305 lines
│   ├── cli.py               # argparse CLI: match/chat/app/recover/mcp subcommands
│   ├── chat.py              # Chat session: workspace prep, sync-back, recover (1130 lines)
│   ├── mcp.py               # MCP stdio server: get_inventory/match_projects/check_bom
│   ├── app/                 # Localhost web app
│   │   ├── __init__.py      # run_app orchestrator + permission settings
│   │   ├── server.py        # ThreadingHTTPServer, AppState, JSON/SSE endpoints
│   │   ├── runner.py        # ClaudeTurnRunner: headless `claude -p` per turn
│   │   └── page.py          # Single-page UI embedded as a Python string
│   └── samples/             # Bundled default data (packaged via package-data)
│       ├── inventory.json
│       └── projects.json
├── tests/                   # unittest suite, one file per module
│   ├── __init__.py
│   ├── test_matcher.py
│   ├── test_cli.py
│   ├── test_chat.py
│   ├── test_app.py
│   └── test_mcp.py
├── scripts/
│   └── real_claude_smoke.py # Manual pre-release E2E against the real claude binary
├── docs/
│   ├── APP_ARCHITECTURE.md  # App design doc
│   ├── BUILDER.md           # Commercial fork decision doc
│   ├── MOBILE.md            # Mobile notes
│   ├── RELEASING.md         # Release process
│   └── bench-repo/          # Skill/settings for the user's real inventory repo
│       ├── README.md
│       ├── SKILL.md
│       └── settings.json
├── .github/workflows/       # CI: tests.yml, release.yml
├── pyproject.toml           # Packaging (setuptools), console script, package-data
├── MANIFEST.in              # sdist includes
├── README.md                # User-facing docs
├── ROADMAP.md               # Doubles as the changelog (pyproject Changelog URL)
├── GATES.md                 # Project gates/decision log
├── CONTRIBUTING.md
└── LICENSE                  # Apache-2.0
```

(`partsmatcher.egg-info/` is build output; `.planning/` is GSD planning state — neither is source.)

## Directory Purposes

**`partsmatcher/`:**
- Purpose: the entire installable package — flat, one module per frontend
- Contains: core + four frontends + bundled samples
- Key files: `matcher.py` (core), `cli.py` (dispatch), `chat.py` (session machinery shared by chat and app)

**`partsmatcher/app/`:**
- Purpose: the only subpackage; the browser frontend split by role
- Contains: orchestrator (`__init__.py`), HTTP server (`server.py`), Claude subprocess driver (`runner.py`), embedded HTML page (`page.py`)
- Key files: `server.py` defines the endpoint contract (`GET /`, `GET /api/state`, `POST /api/message`, `POST /api/end`)

**`partsmatcher/samples/`:**
- Purpose: default inventory/projects so `python -m partsmatcher` works with zero setup
- Contains: `inventory.json`, `projects.json`; declared in `pyproject.toml [tool.setuptools.package-data]`
- Never written back to by session sync

**`tests/`:**
- Purpose: automated suite (stdlib `unittest`), mirrors the package one-to-one
- Contains: `test_<module>.py` per source module; all Claude interaction is faked via injectable `which`/`popen`/`launch`

**`scripts/`:**
- Purpose: manual tooling outside the package
- Key files: `real_claude_smoke.py` — run by hand before releases; the only thing that exercises the real `claude` binary and the page's JS path

**`docs/`:**
- Purpose: design/process docs, not user docs (README is user-facing)
- Key files: `docs/APP_ARCHITECTURE.md`, `docs/RELEASING.md`, `docs/BUILDER.md`

## Key File Locations

**Entry Points:**
- `partsmatcher/cli.py` (`main`): console script `partsmatcher` per `pyproject.toml [project.scripts]`
- `partsmatcher/__main__.py`: `python -m partsmatcher`
- `partsmatcher/__init__.py`: library import surface (core only)

**Configuration:**
- `pyproject.toml`: packaging, version (also in `partsmatcher/__init__.py:__version__` — keep both in sync), console script, package-data
- `MANIFEST.in`: sdist contents
- `.github/workflows/tests.yml`, `.github/workflows/release.yml`: CI

**Core Logic:**
- `partsmatcher/matcher.py`: parsing, normalization, matching, report dataclasses
- `partsmatcher/chat.py`: workspace lifecycle + sync-back + recover (shared by `chat` and `app`)

**Testing:**
- `tests/test_*.py`: one per module; run with `python -m unittest discover` (or `python -m unittest tests.test_matcher` etc.)

## Naming Conventions

**Files:**
- One lowercase module per frontend/concern: `matcher.py`, `cli.py`, `chat.py`, `mcp.py`
- Tests mirror modules exactly: `tests/test_<module>.py`
- Workspace artifacts have fixed names defined as constants in `chat.py`: `CLAUDE.md`, `inventory.json`, `projects.json`, `aliases.jsonl`, `photos/`, `.partsmatcher-session.json`; temp workspaces are `partsmatcher-chat-*`
- User alias sidecar: `<inventory-stem>.aliases.jsonl` next to the inventory file (`cli.py:509`)

**Directories:**
- Only subpackage is `app/`; new multi-file frontends should follow that pattern (subpackage with a `run_*` orchestrator in `__init__.py`)

**Code:**
- snake_case functions, PascalCase dataclasses, UPPER_SNAKE module constants
- Private helpers prefixed `_` (note: `app/__init__.py` deliberately imports `chat.py`'s `_`-prefixed sync helpers — an accepted internal seam)
- 3.9-compatible annotations: string form for subscripted builtins (`"list[str]"`, `"Optional[Path]"`) plus `from __future__ import annotations`

## Where to Add New Code

**New matching capability (core):**
- Primary code: `partsmatcher/matcher.py` — keep it pure (no I/O); export through `partsmatcher/__init__.py` `__all__`
- Tests: `tests/test_matcher.py`

**New CLI subcommand:**
- Add a subparser in `build_parser` and a `_run_<name>` in `partsmatcher/cli.py`; register the name in `KNOWN_COMMANDS` (`cli.py:39`) or the implicit-`match` fallback will swallow it; heavy imports go lazily inside `_run_<name>`
- Tests: `tests/test_cli.py`

**New MCP tool:**
- Add a schema entry to `TOOLS` and a `tool_<name>` method + `_call_tool` dispatch entry in `partsmatcher/mcp.py`; re-read files per call
- Tests: `tests/test_mcp.py` (drives `handle_message` directly, no stdio needed)

**New app endpoint / page feature:**
- Endpoint: `partsmatcher/app/server.py` (`do_GET`/`do_POST`); state-changing routes must check `_authorized()`
- UI: `partsmatcher/app/page.py` `PAGE_TEMPLATE` string
- Tests: `tests/test_app.py`; update `scripts/real_claude_smoke.py` if the Claude-facing loop changes

**Session/workspace behavior:**
- `partsmatcher/chat.py` — both `chat` and `app` reuse it; anything synced back must also be recorded in `_write_session_record` so `recover` still works
- Tests: `tests/test_chat.py`

**Utilities:**
- No shared utils module; helpers live in the module that owns them. Cross-module reuse goes through `matcher.py` (core) or `chat.py` (session machinery).

## Special Directories

**`partsmatcher.egg-info/`:**
- Purpose: setuptools build metadata
- Generated: Yes
- Committed: Yes (currently in the repo; regenerated by builds)

**`.planning/`:**
- Purpose: GSD planning documents (this analysis)
- Generated: Yes (by tooling)
- Committed: Per project workflow

**`docs/bench-repo/`:**
- Purpose: files intended for the user's separate real-inventory repo (`~/bench`) — a Claude Code skill (`SKILL.md`) and settings; not imported by the package
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-08-25*
