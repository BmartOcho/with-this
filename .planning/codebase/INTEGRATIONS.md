# External Integrations

**Analysis Date:** 2026-08-25

## APIs & External Services

**AI / Claude Code CLI (the central integration):**
- Local Claude Code CLI (`claude` binary) - Powers `partsmatcher chat` and `partsmatcher app`. PartsMatcher deliberately does NOT call the Anthropic HTTP API and needs no API key; it drives the user's already-installed, already-logged-in `claude` binary as a child process, so the user's existing subscription auth applies.
  - SDK/Client: None — `shutil.which("claude")` + `subprocess` only
  - Auth: None held by this tool (Claude Code's own login is used)
  - Integration points:
    - `partsmatcher/chat.py` - interactive mode: builds a temp workspace (`partsmatcher-chat-*`) containing a generated `CLAUDE.md` (inventory + deterministic match report + assistant instructions), `inventory.json`, `aliases.jsonl`, optional `projects.json` and `photos/`; launches `claude` with the workspace as cwd via `subprocess.call`; on exit, validates and syncs edited files back to the user's stores (with `.bak` backups). `find_claude()` locates the binary; missing binary prints an install hint (`CLAUDE_NOT_FOUND_HINT`) and exits 2. `recover` re-runs the sync from the `.partsmatcher-session.json` sidecar after a crash.
    - `partsmatcher/app/runner.py` - headless mode: one `claude -p <message> --output-format stream-json --verbose` process per chat turn, `--resume <session-id>` to continue the conversation through Claude Code's own session store; parses stream-json into events (`session`/`text`/`tool`/`done`/`error`) forwarded to the browser page.
  - Failure mode: chat/app modes refuse to start without `claude` on PATH; the deterministic matcher (`partsmatcher match`) never requires it.

**No other external APIs.** No HTTP clients, SDKs, or third-party service calls anywhere in the package.

## Served Interfaces (this package as a provider)

**MCP stdio server (`partsmatcher mcp`):**
- `partsmatcher/mcp.py` - Model Context Protocol server, protocol version `2025-06-18`, for any MCP client on the machine (typically Claude Code sessions).
  - Transport: MCP stdio — one JSON-RPC 2.0 message per line on stdin/stdout, UTF-8; diagnostics to stderr. Hand-rolled, no MCP SDK.
  - Tools exposed (the only sanctioned way for a model to get a match verdict):
    - `get_inventory` - list owned parts, optional substring filter
    - `match_projects` - the deterministic BUILD NOW / ALMOST THERE / NOT YET report
    - `check_bom` - OWNED / SHORT / NOT OWNED verdict for a BOM (accepts HEPH `out/bom.json` format via `bom_path` or inline `bom_json`), with `difflib` closest-name hints for NOT OWNED lines
  - Data files (`inventory.json`, `projects.json`) are re-read from disk on every tool call, so mid-session edits are seen.
  - Registration: `claude mcp add --scope user partsmatcher -- python -m partsmatcher mcp <inventory.json> <projects.json>`
  - Tool failures return `isError: true` results (not protocol errors) so the model can recover.

**Localhost HTTP server (`partsmatcher app`):**
- `partsmatcher/app/server.py` - stdlib `ThreadingHTTPServer` on localhost, browser opened via `webbrowser.open` (`partsmatcher/app/__init__.py`)
  - `GET /` - embedded single-file page (`partsmatcher/app/page.py`)
  - `GET /api/state` - inventory + match report, recomputed from workspace files on disk
  - `POST /api/message` - one chat turn, streamed back as `text/event-stream` (SSE)
  - `POST /api/end` - end-of-session sync, then server shutdown
  - Security: per-session `secrets.token_urlsafe(32)` token embedded in the page; every state-changing request must echo it in the `X-PartsMatcher-Token` header (compared with `hmac`); no CORS preflight is ever answered, blocking cross-origin drive-by requests. Token is regenerated per run, never written to disk.

**HEPH interop:**
- `check_bom` consumes the BOM format emitted by HEPH's ship step (`{"lines": [{"key", "description", "qty", ...}]}`); `bom_as_project()` in `partsmatcher/mcp.py` prefers whichever spelling (machine `key` vs human `description`) the inventory recognizes. Exact-name matching is deliberate. Design context in `docs/BUILDER.md`.

## Data Storage

**Databases:**
- None. All persistence is plain JSON files owned by the user:
  - `inventory.json` - `{"parts": [{"name": str, "quantity": int >= 0}]}` (extra fields like `source`/`confidence` tolerated)
  - `projects.json` - `{"projects": [{"name", "description", "parts": [...]}]}`
  - `aliases.jsonl` - append-only naming-alias dataset (raw phrasing → canonical name), grown by chat sessions for a future vision module
  - Bundled samples: `partsmatcher/samples/inventory.json`, `partsmatcher/samples/projects.json`
  - The user's real data lives outside this repo (a separate local "bench" repo)

**File Storage:**
- Local filesystem only. Chat sessions use temp workspaces (`tempfile`, prefix `partsmatcher-chat-`) with a `.partsmatcher-session.json` sidecar enabling `partsmatcher recover` after crashes; syncs write `.bak` backups next to the user's files.

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None in this tool. Claude access rides on the user's existing Claude Code login/subscription. The localhost app uses the per-session token described above; the MCP server trusts its stdio parent.

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- Plain prints to stdout/stderr; MCP server diagnostics go to stderr (ignored by the stdio transport)

## CI/CD & Deployment

**Hosting:**
- PyPI (`partsmatcher`, https://pypi.org/p/partsmatcher) with TestPyPI staging; GitHub repo `BmartOcho/with-this`

**CI Pipeline:**
- GitHub Actions:
  - `.github/workflows/tests.yml` - `python -m unittest` + CLI smoke test on {ubuntu, windows} × {3.9, 3.13}, on push to main and PRs
  - `.github/workflows/release.yml` - on `v*` tags: verifies tag == `pyproject.toml` version, re-runs tests, builds sdist/wheel, `twine check`, verifies the sdist's own test suite runs, publishes to TestPyPI then PyPI via Trusted Publishing (OIDC, `id-token: write` — no API tokens or repo secrets). The `pypi` environment is intended to require a manual reviewer click. The workflow filename `release.yml` is part of the PyPI trust registration — do not rename.

## Environment Configuration

**Required env vars:**
- None. `PYTHONPATH` is set by chat.py only in the match command it hands to Claude for source-tree runs (`partsmatcher/chat.py` `run_chat`).

**Secrets location:**
- No secrets exist in this project. Publishing uses OIDC Trusted Publishing; Claude auth belongs to the Claude Code CLI.

## Webhooks & Callbacks

**Incoming:**
- None (localhost app endpoints only, listed above)

**Outgoing:**
- None

---

*Integration audit: 2026-08-25*
