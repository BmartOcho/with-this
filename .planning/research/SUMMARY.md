# Project Research Summary

**Project:** PartsMatcher — machine-wide MCP inventory service (registration, shopping list, affiliate links)
**Domain:** Local-first developer tool / personal inventory service, single user (Ben), Windows desktop, stdlib-only Python, consumed by Claude Code sessions and a sibling project (HEPH)
**Researched:** 2026-08-25
**Confidence:** HIGH

## Executive Summary

This milestone takes an existing, working, hand-rolled stdio MCP server (Python stdlib-only, protocol `2025-06-18`) and turns it from "proven once against sample data" into a dependable, machine-wide service backed by Ben's real 76-type/856-part inventory in `~/bench`, plus a new writable shopping list with stubbed affiliate links. Experts in this space (comparable todo/inventory MCP servers, BOM-feasibility tools like PartKeepr/Part-DB/BOMIST) converge on the same shape this project is already close to: small single-purpose snake_case tools, structured JSON output alongside prose, read/write separation, and idempotent writable stores. The right move is not a rewrite — it's adding one new layer (`datahome.py`) that owns all file access (atomic writes, locking, path resolution) and sits between the existing frontends (CLI, chat, app, MCP) and the unchanged pure matching core.

The recommended approach: register the server once, machine-wide, via `claude mcp add --scope user` with an absolute interpreter path and no baked-in data paths (the server resolves its home from a pointer file at startup, so data can move without re-registration); build a single `ShoppingList` store with lockfile-serialized read-modify-write and atomic `os.replace`-based writes as the one writable surface; keep inventory strictly read-only over MCP as a structural invariant, not a convention; and build affiliate links as a per-vendor config template that emits untagged plain links today and tagged links the moment Ben's Amazon Associates account exists — no code change required at enrollment. The zero-third-party-dependency rule holds throughout; everything above is achievable with `tempfile`, `os`, `json`, and `urllib.parse`.

The key risks cluster around three things that look done but aren't: (1) machine-wide registration is a frozen launch-command snapshot that silently breaks when Python/venv paths change — needs a doctor/verification command, not just `claude mcp list`; (2) concurrent MCP processes (one per open Claude Code session) writing to the same shopping list is the project's known failure class (silent data loss / OneDrive sharing violations) recurring on a new surface — atomic writes plus a lockfile are non-negotiable before the first write path ships; and (3) Amazon Associates and FTC compliance are unforgiving and largely irreversible (180-day account closure, permanent bans for cloaking) — the stubbed-tag, no-early-enrollment design sidesteps this until real usage exists. A fourth, subtler risk is schema drift with HEPH: since HEPH is an LLM consumer of `check_bom`, undocumented, unstructured output changes will be silently "reinterpreted" rather than loudly broken — structured `outputSchema`/`structuredContent` output and a repeatable shape-asserting smoke test are the fix.

## Key Findings

### Recommended Stack

The existing stack (Python >=3.9 stdlib-only, hand-rolled JSON-RPC server at protocol `2025-06-18`) needs no replacement — this milestone only adds machine-wide registration mechanics, a plain-URL affiliate-link scheme, and a stdlib atomic-write pattern. Confidence is HIGH on registration/protocol/atomicity (verified against current official docs) and MEDIUM-HIGH on the affiliate landscape (dated sources; several vendor "no program" findings are absence-of-evidence).

**Core technologies:**
- `claude mcp add --scope user --transport stdio` — machine-wide registration in `~/.claude.json`, loads in every project on the machine, no per-project setup
- MCP protocol `2025-06-18` (unchanged) — Claude Code's stdio default stays on this handshake; add tolerant version-echo negotiation rather than chasing newer revisions
- Plain tagged deep links (`?tag=` query param), no vendor API — Amazon PA-API is deprecated (2026-05-15); its Creators API successor requires sustained sales volume the project doesn't have yet; plain links need no credentials or dependencies
- `tempfile` + `os.fsync` + `os.replace` with retry — atomic JSON writes; `os.replace` is atomic on Windows since Python 3.3, wrapped in short exponential backoff to absorb transient OneDrive/AV sharing violations

### Expected Features

Confidence MEDIUM-HIGH: MCP tool-design and affiliate-compliance findings are well-sourced; shopping-list semantics are drawn from established consumer-app conventions rather than MCP-specific precedent.

**Must have (table stakes):**
- Machine-wide registration serving real `~/bench` data, with a Ben-runnable PASS/FAIL verification
- `check_bom` structured output (per-line status enum, shortfall numbers, overall verdict) alongside prose, plus specific/recoverable tool errors
- Shopping list: add (with qty)/list/remove/clear, with dedup-merge on normalized name and purchased/checked state distinct from delete
- Atomic writes + durable data home (`~/bench`, outside OneDrive) for the shopping list
- Inventory strictly read-only over MCP (structural, not conventional)
- Repeatable end-to-end check against a real MCP client

**Should have (differentiators):**
- One-call "check BOM and queue the gaps" — shortfalls flow into the shopping list with provenance (design name, qty short) — the commercial thesis in miniature
- Part suggestions by category/role ("what sensors do I own") rather than name-substring only
- Per-vendor affiliate link plumbing, stubbed, config-driven, zero-blocking on account enrollment
- Affiliate disclosure emitted in the same tool output that carries links (FTC/Amazon requirement, not optional polish)

**Defer (v2+):**
- Rendered shopping-list markdown/HTML export (ships after structured tool output is stable)
- Live price scraping or vendor APIs (violates stdlib-only rule, adds fragility)
- Multiple named lists, sharing, undo history — scope creep for a one-person, one-machine tool
- Public/multi-user distribution (out of scope for this milestone per PROJECT.md)

### Architecture Approach

Add one new access layer, `partsmatcher/datahome.py`, that owns all file I/O (path resolution via explicit args > env var > pointer file; atomic writes; a lockfile; the `ShoppingList` store; read-only loaders) and is imported by every existing frontend (`cli.py`, `mcp.py`, `chat.py` sync helpers, plus a new `init.py`). The pure matching core (`matcher.py`) stays completely unchanged and I/O-free. The MCP server continues to re-read files per call (no caching — correct at this data scale) but gains a structural guarantee: it imports no function capable of writing `inventory.json`, only the shopping-list store.

**Major components:**
1. `datahome.py` (new) — resolves the data home, performs all atomic writes/locking, hosts the `ShoppingList` store and read-only loaders; the single choke point through which every write happens
2. `init.py` (new) — one-shot, idempotent bootstrap: adopt/create `~/bench`, migrate legacy loose files, write the pointer file, run `claude mcp add --scope user`, self-verify with a real `initialize`->`tools/list`->tool-call round trip
3. `affiliates.py` (new, small, pure) — renders (part name, vendor config) into a tagged or untagged URL at display time; vendor tags never get baked into stored shopping-list data
4. `mcp.py` (extended) — existing three read-only tools plus `add_to_shopping_list` and a category-aware suggestion capability; imports only read loaders and the shopping-list store

### Critical Pitfalls

1. **Stale machine-wide registration** — a frozen launch-command snapshot silently breaks when Python/venv paths change. Avoid: absolute interpreter path, no baked-in data paths, a doctor/verification command Ben can run, documented one-line re-registration.
2. **Concurrent-write data loss / OneDrive corruption** — multiple MCP processes (one per open session) writing the shopping list is this project's signature failure class recurring on a new surface. Avoid: atomic `os.replace` writes for every write path, plus a lockfile-serialized read-modify-write around the shopping-list store from day one — never last-writer-wins.
3. **Stdout pollution breaking the stdio transport** — one stray `print()` or the existing `redirect_stdout` capture pattern in `tool_match_projects` corrupts the JSON-RPC stream. Avoid: refactor `_print_human` to render to a string/stream (never touch real stdout in the MCP path), stderr-only diagnostics, verified UTF-8 handling for real inventory data (Ohm, mu characters).
4. **Shopping list becomes duplicate/stale spam under automated (HEPH) callers** — non-idempotent appends produce nine copies of the same missing resistor after a week of design iteration. Avoid: upsert keyed on canonical part identity, reconcile against current inventory at read time (not write time), keep `check_bom` itself side-effect-free.
5. **Amazon Associates / FTC compliance traps that are irreversible** — cloaked links, offline/email contexts, missing disclosure, or enrolling before real traffic exists can permanently burn the account. Avoid: stub tags until the loop demonstrably produces clicks, plain undisguised URLs only, disclosure baked into the tool output itself, re-check ToS at activation time (not build time).

## Implications for Roadmap

Based on combined research, the dependency chain is unambiguous: nothing writable or machine-wide can safely exist before atomic-write/locking primitives do, and nothing HEPH-facing can be called "dependable" without a repeatable real-client check. Suggested phase structure:

### Phase 1: Data-Home Access Layer & Atomic-Write Hardening
**Rationale:** Everything else imports this layer; it's the standing data-safety mandate given the project's prior data-loss history, and retrofitting `chat.py` sync-back writes here means every later phase inherits safety for free. Pure library work, fully unit-testable via crash-simulation and lock-contention tests — no MCP/Claude Code coupling needed yet.
**Delivers:** `partsmatcher/datahome.py` with `resolve_home()`, `atomic_write_json()` (tmp-in-same-dir + fsync + `os.replace` + Windows retry-on-PermissionError), `FileLock` (O_CREAT|O_EXCL with stale-mtime takeover), and timestamped `.backups/` replacing the single-generation `.bak`.
**Addresses:** the "atomic writes + durable data home" table-stakes feature from FEATURES.md
**Avoids:** Pitfall 6 (OneDrive/concurrent JSON corruption) — designed in before any writable surface exists, not retrofitted

### Phase 2: Machine-Wide Registration & Real-Data Wiring (`init`)
**Rationale:** The moment this lands, MCP serves real `~/bench` data in every Claude Code session on the machine — the milestone's core value statement — even before any new tools exist. It also unblocks live HEPH testing of the three existing tools against real inventory data (non-ASCII part names, real naming quirks).
**Delivers:** `partsmatcher init` (adopt/create `~/bench`, migrate legacy files, write pointer file, `claude mcp add --scope user` with an absolute interpreter path and no baked paths, self-verifying `initialize`->`tools/list`->`get_inventory` real-transport check with PASS/FAIL output).
**Uses:** stack elements from STACK.md (`claude mcp add --scope user`, protocol `2025-06-18` version-echo negotiation, absolute-interpreter registration)
**Implements:** the `init.py` component and pointer-file discovery pattern from ARCHITECTURE.md
**Avoids:** Pitfall 1 (stale registration) and Pitfall 2 (stdout pollution/Windows encoding) — this phase is where the `_print_human`/`redirect_stdout` decoupling and forced UTF-8 stdio reconfiguration must land, verified with real non-ASCII part names (Ohm, mu) over the live pipe

### Phase 3: Shopping List (the one writable surface)
**Rationale:** First writable surface in the whole system; must not exist before Phase 1's lock/atomic primitives do, and is only useful once Phase 2's real registration is live. Design decisions here (idempotency, dedup keying) are near-impossible to retrofit onto an append-only file format later, so they must be right from the first write.
**Delivers:** `ShoppingList` store in `datahome.py` (upsert keyed on normalized part name, provenance/timestamp per entry, purchased/checked state distinct from delete), `add_to_shopping_list` / `get_shopping_list` / `mark_purchased` / `remove_from_shopping_list` / `clear_shopping_list` MCP tools (small single-purpose tools, not one multiplexed action tool), matching `shopping` CLI subcommand, and a `check_bom`-gaps-to-list flow with provenance.
**Addresses:** shopping-list table stakes and the "BOM gaps -> shopping list" differentiator from FEATURES.md
**Avoids:** Pitfall 4 (duplicate/stale spam under automated callers) and Pitfall 3 (lethal-trifecta exposure — input validation, size caps, and never building URLs from LLM-written free text)

### Phase 4: BOM Robustness & HEPH Contract
**Rationale:** Independent of the affiliate work and can interleave or swap order with Phase 5; benefits from landing after Phases 2-3 have produced real usage feedback, since the HEPH integration shape is still evolving alongside a collaborator's project.
**Delivers:** `check_bom` structured output (`outputSchema`/`structuredContent` per MCP spec 2025-06-18: status enum, shortfall numbers, labeled substitution-confidence hints, check-echo metadata) alongside the existing prose; a documented result schema (TOOLS.md or JSON schema); an extended repeatable smoke test that asserts output *shape*, not just success; `SERVER_INFO` version fix so schema-change signals are visible.
**Addresses:** the "structured check_bom" and "repeatable real-client check" table stakes from FEATURES.md
**Avoids:** Pitfall 7 (schema drift silently mis-consumed by an LLM caller)

### Phase 5: Affiliate Link Plumbing
**Rationale:** Pure rendering over an already-stable shopping list; zero coupling to anything earlier, safe to defer or run in parallel with Phase 4.
**Delivers:** `affiliates.py` (pure link-rendering function), `affiliates.json` config schema (per-vendor URL template + nullable tag, untagged-link fallback when tag is empty), disclosure string embedded in the same tool output that carries links, category/role-based part suggestions (`suggest_parts`) if category data has been curated.
**Addresses:** affiliate-plumbing and category-suggestion differentiators from FEATURES.md
**Avoids:** Pitfall 5 (Amazon/FTC compliance traps) — stub tags, no early enrollment, direct undisguised URLs only, disclosure baked into payload

### Phase Ordering Rationale

- Atomic writes and locking (Phase 1) are a hard prerequisite for any writable store — the project's own history of silent data loss makes this the one inviolable ordering rule from ARCHITECTURE.md and PITFALLS.md alike.
- Registration (Phase 2) is sequenced before the shopping list because it delivers the milestone's core value (real data, every session) on its own and de-risks the harder write-path work by exercising the existing read-only tools against real inventory first.
- BOM robustness (Phase 4) and affiliate links (Phase 5) both depend only on the shopping list (Phase 3) existing, not on each other — they can be reordered or parallelized based on whether HEPH feedback or affiliate readiness becomes more urgent during planning.
- Every phase boundary in this structure corresponds to a pitfall-mapped "verification gate" in PITFALLS.md (fresh-directory real tool call, non-ASCII live smoke test, 5x-repeat idempotency test, kill-mid-write crash test, disclosure-present-in-payload test) — these should become the phase exit criteria, not just implementation tasks.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (Affiliate Link Plumbing):** the Amazon Associates generative-AI clause and the PA-API->Creators API transition are both actively moving through 2026; STACK.md and PITFALLS.md both flag this as needing a fresh compliance re-check specifically at the moment Ben enrolls, not at build time. Electronics-vendor programs (Digi-Key, Mouser, Adafruit) were checked only for program existence (mostly none), not detailed ToS — verify each individually if any of them later start affiliate programs.
- **Phase 3 (Shopping List):** the exact schema-validation boundary for shopping-list free text (how much to constrain notes/URLs to prevent the lethal-trifecta injection path) is flagged in PITFALLS.md as needing its own design pass, not a default assumption.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Data-Home/Atomic Writes):** stdlib `os.replace`/`tempfile`/lockfile patterns are HIGH confidence, field-proven (CoolProp PR #2905), fully documented — no additional research needed.
- **Phase 2 (Registration):** `claude mcp add --scope user` mechanics are verified directly against current official Claude Code docs — HIGH confidence, standard pattern.
- **Phase 4 (BOM Robustness):** MCP `outputSchema`/`structuredContent` is a documented 2025-06-18 spec feature with clear precedent in comparable tool-design guides — standard pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Registration, protocol, and atomic-write mechanics verified against current official docs (code.claude.com, modelcontextprotocol.io, Python docs); affiliate landscape MEDIUM-HIGH (dated sources, some vendor "no program" findings are absence-of-evidence) |
| Features | MEDIUM-HIGH | MCP tool-design conventions and affiliate compliance well-sourced across multiple credible references; shopping-list semantics inferred from general consumer-app conventions (Mealie, Listonic) rather than MCP-specific precedent |
| Architecture | HIGH | Claude Code registration semantics and Python atomicity primitives are documented/official; lockfile stale-takeover timeout values are community-standard practice with no single authority (MEDIUM on that one sub-point) |
| Pitfalls | HIGH | MCP/stdio/OneDrive mechanics corroborated by official docs plus reproduced GitHub issues plus this repo's own verified CONCERNS.md; Amazon Associates AI-context enforcement interpretation is MEDIUM (policy text is clear, but how it applies to AI-agent-emitted links is unsettled/community consensus) |

**Overall confidence:** HIGH

### Gaps to Address

- Amazon Associates' generative-AI clause interpretation for links emitted inside an LLM tool-call transcript is unsettled — treat as a mandatory re-check at the moment of actual enrollment (Phase 5), not a build-time decision to finalize now.
- Shopping-list free-text/note validation boundaries (how strict to be against injected instructions/URLs) need a concrete schema decision during Phase 3 planning — research identified the risk clearly but did not prescribe an exact schema.
- Electronics-vendor affiliate programs beyond Amazon and Jameco were checked for existence only (mostly absent); if any come online later, their ToS needs individual verification before tagging.
- Windows UTF-8 stdio reconfiguration (`reconfigure(encoding="utf-8")`) has never been tested against a live Claude Code client on Windows with real non-ASCII inventory data (Ohm, mu) — flagged as a required live verification in Phase 2, not yet empirically confirmed.

## Sources

### Primary (HIGH confidence)
- https://code.claude.com/docs/en/mcp — scopes, precedence, `--` separator, duplicate-add behavior, `CLAUDE_PROJECT_DIR`, output token caps
- https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle — initialize/version-negotiation, capabilities, error conventions
- https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server — stdout/stderr stdio guidance
- Python stdlib docs — `os.replace` atomicity, `os.open(O_CREAT|O_EXCL)` lockfile primitive
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md` — verified in-repo facts (non-atomic sync writes, redirect_stdout coupling, stale SERVER_INFO, data-loss history)
- GitHub anthropics/claude-code issues #7672, #54803, #32939, #29153, #48866, #62140 — reproduced Windows/registration/stdio/OneDrive failure modes
- Amazon Associates Program Policies, Participation Requirements, FTC Endorsement Guides / 16 CFR Part 255 — affiliate/disclosure compliance rules

### Secondary (MEDIUM confidence)
- AWS MCP tool-design blog, awslabs/mcp DESIGN_GUIDELINES, The New Stack/Snyk MCP best-practice writeups — tool granularity and schema conventions
- Mealie/CopyMeThat/Listonic shopping-list convention surveys — dedup/merge/purchased-state UX norms
- ChatAds blog on Amazon Operating Agreement generative-AI clause and Creators API transition — unsettled interpretation, community consensus
- CoolProp PR #2905, python-atomicwrites issue #25 — field-proven Windows `os.replace` retry pattern

### Tertiary (LOW confidence)
- getlasso.co Jameco affiliate terms (5%/120-day cookie) — single aggregator source, verify before enrolling
- SparkFun/Mouser/Digi-Key "no affiliate program" findings — absence-of-evidence across networks, re-verify at enrollment time

---
*Research completed: 2026-08-25*
*Ready for roadmap: yes*
