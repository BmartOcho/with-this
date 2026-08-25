# PartsMatcher

Know what you can build from the electronics parts you actually own. Stdlib-only Python (>=3.9), zero third-party runtime dependencies — this is a standing project rule, not a suggestion.

Owner: Ben (non-coder). Report in plain English; prefer PASS/FAIL-style checks he can run and read; never leave a claim unverified.

## Current milestone

Machine-Wide MCP Service — make `partsmatcher mcp` the inventory service every Claude Code session on this desktop uses (HEPH, the chat-to-3D-print generator, first). Inventory is read-only over MCP; the shopping list is the only writable surface. See `.planning/PROJECT.md` and `.planning/ROADMAP.md` (6 phases, 23 requirements).

## GSD workflow

This project is managed with GSD. `.planning/` is the source of truth:

- `PROJECT.md` — what and why; `REQUIREMENTS.md` — scoped v1 with REQ-IDs; `ROADMAP.md` — phases; `STATE.md` — current position
- `codebase/` — mapped architecture/conventions/concerns (CONCERNS.md findings are individually verified)
- `research/` — domain research backing the roadmap

Work phases via `/gsd-plan-phase N` → `/gsd-execute-phase N`. Config (`.planning/config.json`): YOLO mode, standard granularity, parallel plans, research + plan-check + verifier all on. Model policy: session model for tough tasks (research/planning), Sonnet for grunt work. Commit planning docs.

## Hard rules

- Never write to `~/bench` inventory data except through the data-home layer (Phase 1+); every user-data write must be atomic
- No inventory-write capability may exist on the MCP surface
- `check_bom` output stays free of affiliate links; links live on the shopping list with disclosure in the same output
- Repo root `ROADMAP.md` is the product's own historical roadmap doc — the GSD roadmap is `.planning/ROADMAP.md`; don't confuse them

## Testing

`python -m unittest` (198+ tests, Windows + Ubuntu CI). Before releases: `python scripts/real_claude_smoke.py` — the manual end-to-end check against the real `claude` binary (the suite fakes it). See `docs/RELEASING.md`.
