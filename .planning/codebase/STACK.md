# Technology Stack

**Analysis Date:** 2026-08-25

## Languages

**Primary:**
- Python >=3.9 (stdlib only, zero runtime dependencies) - Entire package: `partsmatcher/` (matcher, CLI, chat, MCP server, app server)

**Secondary:**
- HTML/CSS/JavaScript (vanilla, embedded as a Python string) - The browser app page, `partsmatcher/app/page.py` (single-file page with inline `<script>`, no build step, no frameworks)
- YAML - GitHub Actions workflows in `.github/workflows/`

## Runtime

**Environment:**
- CPython 3.9–3.13 (CI matrix tests 3.9 and 3.13 on Ubuntu and Windows; primary user runs Windows). `from __future__ import annotations` used throughout for 3.9 compatibility.
- No virtualenv or install required to run from source: `python -m partsmatcher` works from the repo root.

**Package Manager:**
- pip / setuptools (build-time only; there are zero runtime dependencies to manage)
- Lockfile: Not applicable (no dependencies)

## Frameworks

**Core:**
- None. Deliberate project-wide rule: stdlib only (stated in `partsmatcher/mcp.py` docstring: "No third-party dependencies, in keeping with the project-wide rule").
- Key stdlib modules in load-bearing roles:
  - `argparse` - CLI with subcommands, `partsmatcher/cli.py`
  - `http.server.ThreadingHTTPServer` - localhost app server, `partsmatcher/app/server.py`
  - `subprocess` - launching the local `claude` binary, `partsmatcher/chat.py` and `partsmatcher/app/runner.py`
  - `json` - all data files and JSON-RPC/MCP wire format
  - `tempfile` - chat session workspaces (`partsmatcher-chat-*` dirs)
  - `hmac`, `secrets` - per-session token auth for the app server
  - `difflib` - closest-name hints in BOM checking, `partsmatcher/mcp.py`
  - `webbrowser` - opening the app page, `partsmatcher/app/__init__.py`

**Testing:**
- `unittest` (stdlib) - Full suite in `tests/` (test_matcher, test_cli, test_chat, test_app, test_mcp). Run: `python -m unittest`. External processes (Claude) are injectable (`which`, `launch`, `popen` parameters) so tests never need Claude installed.
- `scripts/real_claude_smoke.py` - manual smoke test against a real installed Claude Code CLI

**Build/Dev:**
- setuptools >=77 (`pyproject.toml` `[build-system]`), `setuptools.build_meta` backend
- pypa/build + twine - used in CI release job only
- No linter/formatter configuration detected (no ruff/black/flake8 config files)

## Key Dependencies

**Critical:**
- None (zero runtime dependencies — this is a core design constraint, keep it that way)

**Infrastructure:**
- Build-time only: `setuptools>=77`; CI installs `build` and `twine` transiently

## Configuration

**Environment:**
- No environment variables required; no `.env` files exist
- All configuration is CLI flags on `partsmatcher` subcommands (`match`, `chat`, `app`, `mcp`, `recover`) — file paths for `inventory.json` / `projects.json`, `--workdir`, `--almost` threshold, etc.
- Bundled sample data as defaults: `partsmatcher/samples/inventory.json`, `partsmatcher/samples/projects.json` (shipped via `[tool.setuptools.package-data]`)

**Build:**
- `pyproject.toml` - package metadata, entry point `partsmatcher = "partsmatcher.cli:main"`, version 0.7.1
- `MANIFEST.in` - sdist contents; deliberately ships `tests/` including `tests/__init__.py` so the sdist's suite is discoverable
- `.github/workflows/tests.yml` - CI test matrix
- `.github/workflows/release.yml` - PyPI publish pipeline (filename is part of the PyPI Trusted Publishing trust relationship — do not rename)

## Platform Requirements

**Development:**
- Python 3.9+ only; nothing to install. Optional for chat/app modes: Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) on PATH, already logged in.
- OS independent; CI covers Ubuntu and Windows

**Production:**
- Distributed on PyPI as `partsmatcher` (sdist + wheel), TestPyPI staging first
- Runs anywhere Python 3.9+ runs; deterministic matcher is fully offline
- `partsmatcher.egg-info/` present in repo from a local editable/build (generated artifact)

---

*Stack analysis: 2026-08-25*
