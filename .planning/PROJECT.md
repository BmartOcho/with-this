# PartsMatcher — Machine-Wide MCP Service

## What This Is

PartsMatcher tells Ben what he can build from the electronics parts he actually owns. This milestone turns its proof-of-concept MCP server into the machine-wide inventory service for every Claude Code session on Ben's Windows desktop — most importantly HEPH, his buddy's chat-to-3D-print generator, which needs to check the electronics BOM of a generated design against Ben's real bench inventory.

## Core Value

Any Claude Code session on this machine — HEPH first — can ask "can Ben build this right now, and what's missing?" against his real inventory, without any per-project setup.

## Requirements

### Validated

<!-- Inferred from the existing codebase (see .planning/codebase/) and repo history. -->

- ✓ Deterministic matcher: BUILD NOW / ALMOST THERE / NOT YET against an inventory — existing (`partsmatcher match`)
- ✓ Conversational intake and project chat via the user's local Claude Code (no API key) — existing (`partsmatcher chat`)
- ✓ Local browser app with live sidebar, headless per-turn Claude, sync-back with backups — existing (`partsmatcher app`, live-fire validated 2026-08-08)
- ✓ Session recovery for unclean exits — existing (`partsmatcher recover`)
- ✓ MCP stdio server with `get_inventory`, `match_projects`, `check_bom` — existing (`partsmatcher mcp`, proven once inside HEPH Studio 2026-08-23)
- ✓ End-to-end real-Claude smoke test + Windows CI — existing (2026-08-25)

### Active

- [ ] MCP server registered machine-wide (user scope) so every Claude Code session gets the tools with zero per-project setup
- [ ] MCP serves Ben's real inventory (~/bench, 76 types / 856 parts) — not sample data
- [ ] Inventory is read-only over MCP; sessions cannot corrupt bench data
- [ ] Shopping list: a writable store beside the inventory that MCP tools can add missing parts to
- [ ] BOM feasibility tool robust enough for HEPH to depend on (clear results, graceful errors, repeatable check)
- [ ] Part-suggestion capability: a session can ask what's on hand by kind/role while designing
- [ ] Affiliate-link plumbing: shopping-list output can carry per-vendor affiliate-tagged links (Amazon + electronics vendors), configurable and stubbed until Ben's affiliate accounts exist
- [ ] Hardening of what this path touches: durable data home for inventory/shopping list, atomic writes (no truncated JSON on crash or OneDrive lock)

### Out of Scope

- Public/multi-user distribution of the MCP + affiliate flow — audience is Ben + HEPH this milestone; public comes after it proves out locally
- Affiliate account setup itself — external task for Ben (Amazon Associates + electronics vendors); code ships with configurable/stubbed tags
- Inventory writes over MCP — intake stays in chat/app mode where confirm-before-write and sync-back guardrails exist
- App-server-only fixes (DNS-rebinding Host check, kickoff race, stderr drain) — verified real but not on this milestone's path; tracked in `.planning/codebase/CONCERNS.md`
- The standalone vision scanner — long-game; this milestone only keeps feeding the alias dataset it will need
- Long-lived Claude process for app turns (architecture option 1C) — unrelated to MCP path

## Context

- **Codebase:** stdlib-only Python (>=3.9), zero third-party runtime dependencies (project rule). Mapped 2026-08-25 in `.planning/codebase/` (STACK, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS — CONCERNS findings individually verified).
- **Real data:** Ben's rebuilt inventory lives in a local-only git repo at `~/bench` (manual arrangement after a total data loss noticed 2026-08-22 — `my_inventory.json`, `my_projects.json`, and the 69-record alias dataset vanished). The repo ROADMAP names `init-repo` (a durable, product-supported data home) as the unbuilt answer; this milestone's hardening requirement is its MCP-scoped slice.
- **HEPH:** buddy's chat-to-3D-print generator on the same Windows desktop. Integration shape still evolving with him — BOM feasibility and part suggestions are the known needs. The existing `check_bom` tool ran successfully inside HEPH Studio once (2026-08-23) but has no repeatable check.
- **Commercial direction:** inventory MVP via API plus the affiliate/replenishment angle; Ben is a non-coder owner, so plain-English reporting, PASS/FAIL-style verification, and safety nets matter more than usual.
- **Testing culture:** 198 unittest tests, DI-over-mocking, Windows + Ubuntu CI, manual real-Claude smoke script (`scripts/real_claude_smoke.py`) for what fakes can't cover. The MCP server currently has in-process tests only — no repeatable check against a real client.

## Constraints

- **Tech stack**: Python stdlib only, no third-party runtime dependencies — standing project rule, keeps install friction zero
- **Compatibility**: Python >=3.9; must work on Windows (Ben's platform, now in CI) and POSIX
- **Dependencies**: Claude Code CLI is the load-bearing external — MCP registration, stdio transport, and permission semantics are its territory; changes arrive unversioned
- **Data safety**: ~/bench is the only copy of rebuilt real data; nothing on the MCP path may write inventory, and every file write must be atomic
- **Environment**: repo lives in a OneDrive-synced folder; file locking/sync races are a real hazard for in-place JSON writes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Audience is Ben + HEPH first, public later | Prove the loop end-to-end on one desktop before designing for strangers | — Pending |
| Inventory read-only over MCP; shopping list is the writable surface | Sessions can't corrupt the only copy of real data; the useful write (what to buy) gets its own store | — Pending |
| Shopping list lives beside the inventory (~/bench) | Same home, same versioning/backup story as the data it derives from | — Pending |
| Affiliate: Amazon + electronics vendors, stubbed until accounts exist | Ben has no affiliate accounts yet; link plumbing shouldn't block on enrollment | — Pending |
| Harden only what the MCP path touches this milestone | Fix durable-home + atomic writes now; app-only fixes stay tracked, not blocking | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-25 after initialization*
