# Roadmap — Machine-Wide MCP Service Milestone

**Created:** 2026-08-25
**Granularity:** standard
**Coverage:** 23/23 v1 requirements mapped

## Overview

Turns the proven-once MCP server into the machine-wide inventory service for every Claude Code session on Ben's desktop, backed by his real ~/bench data, with a shopping list as the one writable surface and stubbed affiliate links on top. Ordering follows the hard dependency chain: atomic-write/locking primitives before anything writable or machine-wide; registration lands the core value; the shopping list before anything that renders it.

## Phases

- [ ] **Phase 1: Data Home & Atomic-Write Hardening** - One shared access layer owns all file I/O with atomic writes and locking
- [ ] **Phase 2: Machine-Wide Registration & Real Data** - One init command registers the server user-scope and serves ~/bench in every session
- [ ] **Phase 3: Shopping List** - The one writable surface: idempotent add/list/remove/purchase plus BOM-gaps-to-list
- [ ] **Phase 4: BOM Robustness & HEPH Contract** - Structured, self-describing, error-safe check_bom that HEPH can depend on
- [ ] **Phase 5: Part Categories & Suggestions** - Curated category map over the inventory and "what do I own by kind" answers
- [ ] **Phase 6: Affiliate Links & Shoppable Export** - Config-driven vendor links with disclosure, rendered to a shoppable artifact

## Phase Details

### Phase 1: Data Home & Atomic-Write Hardening
**Goal**: Ben's data can no longer be corrupted or lost by a crash, an OneDrive lock, or two processes writing at once — every frontend goes through one hardened access layer
**Depends on**: Nothing (first phase)
**Requirements**: HOME-01, HOME-02, HOME-04
**Success Criteria** (what must be TRUE):
  1. A kill-mid-write crash test passes: no scenario leaves a truncated or corrupt JSON file — the old file survives intact until the new one fully replaces it (PASS/FAIL runnable)
  2. A lock-contention test passes: two processes writing the same store simultaneously never lose an entry — writes are serialized, never last-writer-wins (PASS/FAIL runnable)
  3. An audit check confirms no frontend (CLI, chat/app sync, MCP) touches user-data JSON files directly — all reads and writes go through the data-home layer
  4. Every write to user data leaves a timestamped backup Ben can restore from, replacing the single-generation .bak
**Plans**: TBD

### Phase 2: Machine-Wide Registration & Real Data
**Goal**: Every Claude Code session on the machine can ask about Ben's real inventory with zero per-project setup — the milestone's core value, live
**Depends on**: Phase 1
**Requirements**: HOME-03, MCP-01, MCP-02, MCP-03, MCP-04
**Success Criteria** (what must be TRUE):
  1. Ben runs one init command that adopts ~/bench (or creates a fresh data home), validates it, records its location, and registers the MCP server user-scope — ending with a printed PASS
  2. A brand-new Claude Code session opened in any folder on the desktop can call `get_inventory` and see the real ~/bench data (76 types / 856 parts) with no setup
  3. Ben can run a plain-English PASS/FAIL verification any time that exercises the registered server over real stdio end to end, including real non-ASCII part names (Ω, µ)
  4. The verification's tool listing confirms no MCP tool capable of modifying inventory exists — read-only is structural, not a convention
**Plans**: TBD

### Phase 3: Shopping List
**Goal**: Sessions can capture what's missing into a persistent, idempotent shopping list beside the inventory — the system's first and only writable surface
**Depends on**: Phase 1, Phase 2
**Requirements**: LIST-01, LIST-02, LIST-03, LIST-04, LIST-05
**Success Criteria** (what must be TRUE):
  1. A session can add a part with quantity to the shopping list; the entry persists beside the inventory and survives restart
  2. Adding the same part five times in a row yields one merged line with summed quantity — never duplicates; the checked-off-line case behaves as documented in the tool description (PASS/FAIL idempotency test)
  3. A session can read the list, remove a line, clear the list, and mark a line purchased — purchased is visibly distinct from deleted, and purchased parts never enter inventory automatically
  4. One call queues a BOM check's gaps onto the list with provenance: each queued line shows which design wanted it and how short the inventory was
**Plans**: TBD

### Phase 4: BOM Robustness & HEPH Contract
**Goal**: HEPH can depend on `check_bom` — structured results it consumes as data, self-describing enough that stale answers are visible, and errors that never lie
**Depends on**: Phase 2 (can run alongside Phase 3)
**Requirements**: BOM-01, BOM-02, BOM-03, BOM-04
**Success Criteria** (what must be TRUE):
  1. `check_bom` returns structured output (per-line status enum, exact shortfall numbers, overall verdict) alongside the prose report, and the repeatable smoke test asserts the output *shape* — PASS/FAIL Ben can run
  2. Every result echoes what was checked: design name, line count, inventory source, and timestamp — a stale-data answer is visible on its face
  3. Substitution hints carry a labeled confidence signal and never change the verdict
  4. A malformed or empty BOM produces a specific, actionable tool error — never a crash and never a silent wrong verdict (error-case checks in the smoke test)
**Plans**: TBD

### Phase 5: Part Categories & Suggestions
**Goal**: A session designing something can ask what Ben owns by kind ("what sensors do I have") and get an honest, quantified answer
**Depends on**: Phase 2 (can run alongside Phases 3-4)
**Requirements**: CAT-01, CAT-02
**Success Criteria** (what must be TRUE):
  1. Inventory parts carry category/role data via a curated map living in the data home that covers the current 76 types and grows with intake
  2. Asking "what sensors do I own" over MCP returns a category-scoped answer with quantities from the real inventory
  3. Asking for a category with no matches returns an honest empty answer with closest-name suggestions — never a guess presented as a match
**Plans**: TBD

### Phase 6: Affiliate Links & Shoppable Export
**Goal**: The shopping list becomes shoppable — per-vendor buy links with mandatory disclosure, rendered at display time over vendor-neutral stored data, exportable as an artifact Ben can use
**Depends on**: Phase 3
**Requirements**: AFF-01, AFF-02, AFF-03, EXP-01
**Success Criteria** (what must be TRUE):
  1. Shopping-list output carries per-vendor buy links driven by a config file (vendor → URL template + optional tag); with no affiliate tag configured, links are plain untagged vendor search URLs — never fake tags
  2. Everywhere links appear, the required disclosure text (FTC + Amazon's mandated statement once enrolled) appears in the same output — a check confirms no link-emitting path omits it
  3. Inspecting the stored shopping-list file shows no baked-in URLs or vendor tags — links are rendered at display time only
  4. Ben can render the shopping list to a shoppable markdown/HTML artifact with links and disclosure included, and open it
**Plans**: TBD
**UI hint**: yes

## Requirement Coverage

| Requirement | Phase |
|-------------|-------|
| HOME-01 | Phase 1 |
| HOME-02 | Phase 1 |
| HOME-03 | Phase 2 |
| HOME-04 | Phase 1 |
| MCP-01 | Phase 2 |
| MCP-02 | Phase 2 |
| MCP-03 | Phase 2 |
| MCP-04 | Phase 2 |
| BOM-01 | Phase 4 |
| BOM-02 | Phase 4 |
| BOM-03 | Phase 4 |
| BOM-04 | Phase 4 |
| LIST-01 | Phase 3 |
| LIST-02 | Phase 3 |
| LIST-03 | Phase 3 |
| LIST-04 | Phase 3 |
| LIST-05 | Phase 3 |
| CAT-01 | Phase 5 |
| CAT-02 | Phase 5 |
| AFF-01 | Phase 6 |
| AFF-02 | Phase 6 |
| AFF-03 | Phase 6 |
| EXP-01 | Phase 6 |

**Mapped: 23/23 ✓ — no orphans, no duplicates**

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Home & Atomic-Write Hardening | 0/? | Not started | - |
| 2. Machine-Wide Registration & Real Data | 0/? | Not started | - |
| 3. Shopping List | 0/? | Not started | - |
| 4. BOM Robustness & HEPH Contract | 0/? | Not started | - |
| 5. Part Categories & Suggestions | 0/? | Not started | - |
| 6. Affiliate Links & Shoppable Export | 0/? | Not started | - |

## Notes

- Phases 4 and 5 depend only on Phase 2 and can interleave with Phase 3 (parallelization is enabled in config); Phase 6 needs Phase 3's store to exist.
- Research flags for phase planning: Phase 3 needs a concrete schema decision on shopping-list free-text validation (injection boundary); Phase 6's Amazon Associates generative-AI clause needs a fresh compliance re-check at actual enrollment time, not build time. Phases 1, 2, and 4 are standard patterns — skip deep research.
- Every phase's exit criteria correspond to the pitfall-mapped verification gates from research (crash test, non-ASCII live smoke, 5x idempotency, disclosure-in-payload).

---
*Consumed by /gsd-plan-phase. Phase details above are the source of truth for phase goals and scope.*
