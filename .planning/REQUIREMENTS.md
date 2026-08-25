# Requirements — Machine-Wide MCP Service Milestone

**Defined:** 2026-08-25 · from PROJECT.md + `.planning/research/` (scoped interactively with Ben)

## v1 Requirements

### Data Home & Hardening (HOME)

- [ ] **HOME-01**: All frontends (CLI, chat/app sync, MCP) read and write user data through one shared data-home access layer — no frontend touches the JSON files directly
- [ ] **HOME-02**: Every write to user data is atomic (temp file + `os.replace`, same volume) with retry on Windows sharing violations — a crash or OneDrive lock can never leave a truncated file
- [ ] **HOME-03**: User can run one init command that adopts the existing `~/bench` repo (or creates a fresh data home), validates it, and records its location so no tool needs paths passed by hand
- [ ] **HOME-04**: Concurrent writers (multiple MCP server processes, one per open Claude Code session) are serialized so simultaneous shopping-list writes never lose an entry

### Machine-Wide MCP Service (MCP)

- [ ] **MCP-01**: User can register the MCP server machine-wide (user scope) in one step, so every Claude Code session on the desktop gets the tools with zero per-project setup
- [ ] **MCP-02**: MCP tools answer from Ben's real inventory (~/bench), not sample data
- [ ] **MCP-03**: Inventory is structurally read-only over MCP — no tool capable of modifying inventory exists
- [ ] **MCP-04**: User can run a plain-English PASS/FAIL verification that exercises the registered server over real stdio, end to end — the repeatable "is it dependable" check

### BOM Feasibility for HEPH (BOM)

- [ ] **BOM-01**: `check_bom` returns structured output (per-line status enum, exact shortfall numbers, overall verdict) alongside the human-readable report, so HEPH consumes data instead of re-parsing prose
- [ ] **BOM-02**: Substitution hints are clearly labeled with a confidence signal and never count toward the verdict
- [ ] **BOM-03**: Every `check_bom` result echoes what was checked (design name, line count, inventory source, timestamp) so a stale-data answer is visible
- [ ] **BOM-04**: Malformed or empty BOMs produce specific, actionable tool errors — never a crash or a silent wrong verdict

### Shopping List (LIST)

- [ ] **LIST-01**: A session can add a part (with quantity) to a persistent shopping list stored beside the inventory
- [ ] **LIST-02**: Adding a part already on the list merges by normalized name (quantities sum) — never duplicate lines; behavior when the existing line is checked-off is defined and documented in the tool description
- [ ] **LIST-03**: A session can read the list, remove a line, and clear the list
- [ ] **LIST-04**: A line can be marked purchased — distinct from deletion; purchased parts re-enter inventory only via chat/app intake (never automatically)
- [ ] **LIST-05**: A session can queue a BOM check's gaps onto the shopping list in one call, with provenance (which design wanted it, how short)

### Part Categories & Suggestions (CAT)

- [ ] **CAT-01**: Inventory parts carry category/role data (sensor, driver, MCU, passive, connector, …) — a curated map over the current 76 types that lives in the data home and grows with intake
- [ ] **CAT-02**: A session can ask what's on hand by category ("what sensors do I own") and get a scoped answer with quantities, and an honest empty (with closest names) when nothing matches

### Affiliate Plumbing (AFF)

- [ ] **AFF-01**: Shopping-list lines carry per-vendor buy links from a config file (vendor → URL template + optional tag); with no affiliate tag configured, links are plain untagged vendor search URLs — never fake tags
- [ ] **AFF-02**: Wherever links are emitted, the required disclosure text (FTC + Amazon's mandated statement once enrolled) is emitted in the same output, so no rendering surface can strip it
- [ ] **AFF-03**: Stored shopping-list data stays vendor-neutral — links are rendered at display time, never baked into the store

### Shoppable Export (EXP)

- [ ] **EXP-01**: User can render the shopping list to a shoppable artifact (markdown/HTML) with links and disclosure included

## v2 Requirements (deferred)

- [ ] Real affiliate tags live — when Ben's Amazon Associates account exists and the loop has real traffic (per pitfalls research: don't enroll early)
- [ ] Public/multi-user distribution of the MCP + affiliate flow — after the local loop proves out
- [ ] Alias-dataset-driven matching improvements — rides the vision-scanner long game

## Out of Scope

- **Inventory writes over MCP** (including auto-decrement on purchase) — sessions must never be able to corrupt the only copy of real data; intake stays in chat/app mode with its guardrails
- **Fuzzy matching in the BOM verdict** — silently wrong verdicts poison the one tool HEPH must trust; hints stay hints
- **Live price scraping / vendor APIs** — violates the stdlib-only rule; fragile; ToS risk
- **Affiliate links inside `check_bom` output** — monetization stays on the shopping list; the feasibility verdict stays untainted
- **Link cloaking/shorteners** — prohibited by Amazon Associates; breaks auditability
- **Multiple named lists / sharing** — one person + one program on one desktop; scope creep
- **App-server-only fixes** (DNS-rebinding Host check, kickoff race, stderr drain) — verified real, tracked in `.planning/codebase/CONCERNS.md`, not on this milestone's path

## Traceability

(Filled by roadmap — every v1 REQ-ID maps to exactly one phase.)

---
*Scoped with Ben 2026-08-25: all P1 core in; affiliate stubbed in v1; categories in v1 as inventory organization; rendered export in v1.*
