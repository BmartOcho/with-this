# Feature Research

**Domain:** Machine-wide MCP inventory service — BOM feasibility, part suggestions, writable shopping list, affiliate links
**Researched:** 2026-08-25
**Confidence:** MEDIUM-HIGH (MCP tool patterns and affiliate rules verified against multiple credible sources; shopping-list semantics drawn from established app conventions; some MCP-ecosystem specifics are WebSearch-only)

## Context Anchors (what already exists)

The current server (`partsmatcher/mcp.py`) exposes three read-only, prose-returning tools: `get_inventory` (substring filter), `match_projects` (three-bucket report), `check_bom` (OWNED / SHORT / NOT OWNED verdict with `difflib` closest-name hints and a net shopping list). Files re-read per call; tool failures return `isError: true` results, not protocol errors. This research covers what must be added or upgraded for the "machine-wide + shopping list + affiliate" milestone.

## Findings by Question Area

### 1. Tool surface conventions in comparable MCP servers

- **Naming:** verb_noun snake_case is the dominant convention (`create_todo`, `list_todos`, `complete_todo`, `remove_todo`, `clear_todos` in the reference todo servers). PartsMatcher's existing names (`get_inventory`, `check_bom`) already fit. Avoid dots/spaces/brackets in names.
- **Granularity:** several small, single-purpose tools beat one multiplexed tool ("action" parameters hurt tool selection). Keep parameter counts small (AWS guidance: ~8 or fewer). Schema quality drives tool-selection quality more than anything else.
- **Read vs write:** write tools are separate, explicitly named tools with narrow schemas (`add_x`, not `modify_anything`). Some servers model reads as MCP *resources* and writes as tools, but Claude Code's practical surface is tools — keeping reads as tools (as partsmatcher does) is the pragmatic, proven pattern here.
- **Structured vs prose results:** the June 2025 MCP spec added `outputSchema` / `structuredContent` — return typed JSON for the model *alongside* a human-readable text block. For a tool HEPH must depend on programmatically (`check_bom`), structured output is the ecosystem-standard answer; prose-only forces the consuming model to re-parse a report, which is where drift/misreads happen. Prose-only is fine for tools whose consumer is conversation (e.g., `match_projects`).
- **Descriptions are the API:** tool descriptions should state when to call and when NOT to (the existing "never state a match from memory — call this" phrasing is exactly right and should extend to new tools).

### 2. What a good BOM-feasibility response contains

Established electronics-inventory tools (PartKeepr, BOMIST, Part-DB) converge on the same report shape the current `check_bom` already has: in-stock / understocked / not-stocked, per line. What "dependable" adds on top:

- **Exact shortfalls per line:** required, have, buy = required − have (current output has this).
- **A machine-readable overall verdict** plus per-line status enum (`owned` / `short` / `not_owned`) — currently prose-only.
- **Substitution hints clearly labeled as hints:** difflib closest-name output exists; the key property (already honored) is that hints never count toward the verdict. A confidence signal per hint (e.g., difflib ratio, or "close" / "weak") makes them usable without making them dangerous.
- **Echo of what was checked:** design name, line count, inventory file used, timestamp — so a HEPH run is auditable and a stale-file bug is visible.
- **Graceful, specific errors as tool results:** empty BOM, malformed lines, missing file — each with a message the calling model can act on (partially present).
- **Idempotent + repeatable:** same BOM + same inventory = same answer; needs an automated repeatable check (currently validated only by one live run inside HEPH Studio).

### 3. Shopping-list semantics (table stakes vs nice-to-have)

From grocery/todo list conventions (Mealie, CopyMeThat, Listonic, todo-MCP servers):

- **Table stakes:** add with quantity; **merge on duplicate add** (same normalized name → quantities sum, never two lines); list with quantities; remove a line; clear the list; purchased/checked state distinct from deletion; persistent across sessions; atomic writes.
- **Expected merge subtleties:** adding an item that exists *checked-off* should either revive it (uncheck, set new qty) or create a fresh unchecked line — silently merging into a checked line is a known UX failure in shopping apps. Pick one behavior and document it in the tool description.
- **Provenance is the differentiator for this domain:** a line that records *which design/BOM check* wanted it ("2× HC-SR04 — for HEPH design 'ultrasonic-turret', short 2") turns the list from a scratchpad into a replenishment queue.
- **Nice-to-have, not required:** per-line notes, priorities, vendors-per-line editing, multiple named lists, undo history.
- **Deliberately out:** editing inventory when an item is marked purchased (inventory writes over MCP are ruled out — purchased items re-enter inventory via chat/app intake).

### 4. Part-suggestion queries

Real design-session phrasings are role/kind based, not name based: "what sensors do I own," "any motor drivers on hand," "what can I use to detect distance." Substring filter on names (`get_inventory query=`) only works when the part name happens to contain the word ("sensor" matches "ultrasonic sensor HC-SR04" but not "HC-SR04" alone or "photoresistor"). What makes answers useful:

- **Category/role grouping:** parts tagged or bucketed by kind (sensor, driver, MCU, passive, connector) so "what sensors" is answerable. This needs category data — either a small category map maintained in `~/bench`, tags on inventory entries, or a bundled keyword→category table. Without it, suggestion answers are only as good as name substrings.
- **Quantities in the answer:** "own 3× HC-SR04" lets a design pick a count immediately.
- **Honest empties:** "no parts categorized as 'motor driver'; closest names: L298N x2" beats an empty list.
- **Scoped output:** return the matching subset, not the whole 76-type inventory dump, to keep the calling session's context lean (a stated MCP best practice).

### 5. Affiliate UX

- **Where links live:** industry norm is link-at-the-point-of-purchase-decision — i.e., per shopping-list line (each line carries a vendor + tagged URL), rendered wherever the list is displayed. In an MCP context that means the shopping-list read tool returns links in structured output; a rendered page/markdown export is a nice-to-have on top, not the foundation.
- **Disclosure (FTC / Amazon Associates):** disclosure must be clear, conspicuous, and adjacent to the links — same screen, before or beside the first link, not buried. Amazon additionally mandates the exact statement "As an Amazon Associate I earn from qualifying purchases" wherever Associates links appear, and permits short link-level markers like "(paid link)". FTC penalties run to ~$53k/violation; Amazon terminates non-compliant accounts. **Practical consequence:** the tool that emits links must emit the disclosure text with them, so no rendering surface can accidentally strip it.
- **Amazon ToS trap:** Associates links may not be cloaked/redirected in ways that hide the destination, and must not be used in "offline" or non-approved contexts; link output should be plain tagged URLs (`?tag=xxx-20`), and the stub mode (no account yet) should emit untagged vendor search URLs, never fake tags.
- **Anti-features:** auto-purchasing or cart automation (liability, ToS); scraping live prices (fragile, adds HTTP dependencies against the stdlib-only rule); injecting links into *feasibility* output (`check_bom` should stay a verdict — monetization belongs on the shopping list, keeping the trusted tool untainted); hard-coding one vendor (config-per-vendor from day one since electronics parts split across Amazon/DigiKey/Adafruit-style vendors).

## Feature Landscape

### Table Stakes (the tools aren't dependable without these)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Machine-wide registration (user scope) serving real ~/bench data | The whole point of "any session can ask"; sample data = wrong answers | LOW | `claude mcp add --scope user`; path config must survive Claude Code updates; needs a verification step Ben can run |
| `check_bom` structured output (per-line status enum, shortfall numbers, overall verdict) alongside prose | HEPH consumes results programmatically; prose re-parsing is where errors creep in | MEDIUM | Use MCP `structuredContent` + `outputSchema` (spec 2025-06-18 supports it); keep the text block for humans |
| Specific, recoverable tool errors (missing file, bad BOM shape, empty BOM) | A dependency HEPH calls blind must fail legibly | LOW | Pattern already exists (`isError: true` results); extend coverage |
| Repeatable end-to-end check against a real MCP client | "Worked once on 2026-08-23" is not dependable | MEDIUM | Extend the existing real-Claude smoke script; in-process protocol tests for new tools |
| Shopping list: add (with qty), list, remove, clear | Minimum viable writable store; every todo/shopping MCP server has these | LOW | verb_noun snake_case names; narrow schemas |
| Dedup/merge on add (normalized name match → sum quantities) | Duplicate lines are the #1 shopping-list complaint; sessions will add the same part repeatedly | MEDIUM | Reuse `normalize_name`; define checked-item collision behavior explicitly in the tool description |
| Purchased/checked state distinct from delete | Universal list convention; "bought it" ≠ "never wanted it" | LOW | `mark_purchased` tool or status field on lines |
| Atomic writes + durable data home for list (and inventory reads) | OneDrive locking + crash mid-write can truncate JSON; ~/bench is the only copy of real data | MEDIUM | write-temp-then-`os.replace` on same volume; the milestone's hardening slice |
| Inventory strictly read-only over MCP | Standing decision; sessions must not corrupt bench data | LOW | Structural: no inventory-write tool exists, period |
| Affiliate disclosure emitted with links, in the same output | FTC "clear and conspicuous, same screen" + Amazon's mandated statement; stripping it is a compliance violation | LOW | Disclosure string lives in the tool output, not in a rendering layer |

### Differentiators (what makes this valuable to HEPH/Ben)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| One-call "check BOM and queue the gaps": shortfalls flow into the shopping list with provenance (design name, qty short) | Turns feasibility check into a replenishment loop — the commercial thesis in miniature | MEDIUM | Either a flag on `check_bom` (`add_missing_to_list`) or a distinct `add_bom_gaps_to_list` tool; distinct tool is cleaner for consent/least-surprise |
| Part suggestions by category/role ("what sensors do I own") with quantities | Substring search can't answer how designers actually ask; this is HEPH's second stated need | MEDIUM-HIGH | Requires category data: tags in ~/bench inventory or a keyword→category map; start with a curated map over the 76 types, grow via the alias dataset |
| Per-vendor affiliate link plumbing, configurable + stubbed | Links ready the day Ben's accounts exist; zero blocking on enrollment | MEDIUM | Config file beside the list (vendor → tag/URL template); stub mode emits untagged search URLs; no HTTP calls (stdlib rule) |
| Substitution hints with a confidence signal, never counted in verdict | Keeps the honest-matching philosophy while making hints actionable in a design session | LOW | Expose difflib ratio or a coarse close/weak label in structured output |
| Check-echo metadata in `check_bom` (inventory file, timestamp, line count) | Auditability for a non-coder owner: "which data answered this?" | LOW | Cheap; goes in structuredContent |
| Rendered shopping-list export (markdown/HTML page with links + disclosure) | Ben-facing artifact he can actually shop from | LOW-MEDIUM | v1.x; the structured tool output must come first |

### Anti-Features (deliberately NOT building)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Inventory writes over MCP (including auto-decrement on "purchased") | "The list knows what I bought, update stock" | Sessions could corrupt the only copy of real data; violates the milestone's core safety decision | Purchased parts re-enter inventory via chat/app intake, where confirm-before-write and sync-back guardrails exist |
| Fuzzy matching in the BOM verdict | Fewer annoying NOT OWNED misses | Silently wrong verdicts are worse than honest misses; poisons trust in the one tool HEPH depends on | Keep exact-match verdicts + clearly-labeled hints; grow the alias dataset to fix naming properly |
| Live price scraping / vendor APIs | "Show me the cheapest" | Adds HTTP + third-party deps (violates stdlib rule), fragile, rate-limited, ToS risk | Static link templates per vendor; price discovery happens at the vendor page |
| Affiliate links inside `check_bom` output | "Monetize every surface" | Taints the trusted feasibility tool; disclosure burden spreads everywhere; incentive-skewed verdicts is a perception risk | Links live only on the shopping list, the natural point of purchase intent |
| One multiplexed `shopping_list(action=...)` tool | Fewer tools to register | Action-parameter tools measurably hurt model tool selection; schemas get baggy | Small single-purpose tools: `add_to_shopping_list`, `get_shopping_list`, `mark_purchased`, `remove_from_shopping_list`, `clear_shopping_list` |
| Link cloaking/shorteners on affiliate URLs | Prettier links | Amazon Associates prohibits obscuring the destination; breaks auditability | Plain tagged URLs |
| Multiple named lists / sharing / sync | Standard in consumer list apps | Audience is one person + one program on one desktop; pure scope creep | One list beside the inventory in ~/bench |

## Feature Dependencies

```
Machine-wide registration (real data)
    └──requires──> Durable data home + atomic-write hardening

check_bom structured output
    └──enables──> HEPH programmatic dependence
    └──enables──> "queue the gaps" flow (needs machine-readable shortfalls)

Shopping list core (add/list/remove/clear, dedup, purchased state)
    └──requires──> Atomic writes (it's the writable surface)
    └──enables──> BOM-gaps-to-list flow
    └──enables──> Affiliate link plumbing (links attach to list lines)
                      └──requires──> Disclosure-in-output
                      └──enables──> Rendered export page

Part suggestions by category
    └──requires──> Category data on inventory (map or tags in ~/bench)

Repeatable real-client check ──gates──> everything above being called "dependable"
```

### Dependency Notes

- **Affiliate plumbing requires the shopping list, not vice versa:** ship the list first with bare lines; links are additive fields. Stub mode means enrollment never blocks.
- **"Queue the gaps" requires structured check_bom:** the gap data must exist as data, not prose, before another tool can consume it.
- **Category suggestions require category data:** this is the only feature needing a data-model addition to ~/bench; it can land last without blocking anything else.
- **Hardening gates registration with real data:** don't point machine-wide tools at the only copy of real data until writes near it are atomic.

## MVP Definition

### Launch With (v1)

- [ ] User-scope registration serving ~/bench real data, with a Ben-runnable PASS/FAIL verification — the core value statement
- [ ] Atomic writes + durable home for the shopping list — safety precondition
- [ ] `check_bom` with structured output, shortfalls, labeled hints, specific errors — HEPH's dependency
- [ ] Shopping list: add/list/remove/clear + dedup-merge + purchased state — the writable surface
- [ ] BOM gaps → shopping list with provenance — the loop that proves the concept
- [ ] Repeatable real-client smoke check — "dependable" needs proof

### Add After Validation (v1.x)

- [ ] Affiliate link fields + config + stub mode — trigger: shopping list stable; accounts trigger real tags
- [ ] Disclosure-in-output — ships with the first link field, not after
- [ ] Category-based part suggestions — trigger: HEPH design sessions actually asking role-based questions
- [ ] Rendered shopping-list page/export — trigger: Ben wants a shoppable artifact

### Future Consideration (v2+)

- [ ] Public/multi-user distribution — after the local loop proves out (per PROJECT.md)
- [ ] Vendor price/stock integration — only if the stdlib rule is ever revisited
- [ ] Alias-dataset-driven matching improvements — rides the long-game vision-scanner track

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Machine-wide registration on real data | HIGH | LOW | P1 |
| Atomic writes / durable home | HIGH | MEDIUM | P1 |
| Structured check_bom | HIGH | MEDIUM | P1 |
| Shopping list core + dedup + purchased | HIGH | MEDIUM | P1 |
| BOM gaps → list (provenance) | HIGH | MEDIUM | P1 |
| Repeatable real-client check | HIGH | MEDIUM | P1 |
| Affiliate plumbing (stubbed) + disclosure | MEDIUM | MEDIUM | P2 |
| Category part suggestions | MEDIUM | MEDIUM-HIGH | P2 |
| Rendered list export | MEDIUM | LOW | P3 |
| Hint confidence signal | LOW | LOW | P3 |

## Competitor Feature Analysis

| Feature | PartKeepr / Part-DB / BOMIST | Todo-list MCP servers | Our Approach |
|---------|------------------------------|----------------------|--------------|
| BOM vs stock report | in-stock / understocked / must-order per line | n/a | Same triad (OWNED/SHORT/NOT OWNED) — already aligned; add structured output |
| Substitution | manual alternates/equivalents DB | n/a | Hints only, never in verdict; alias dataset is the long-term fix |
| Write surface | full CRUD on inventory | create/update/complete/delete tools | Writes confined to shopping list; inventory read-only |
| Reorder flow | reorder alerts, supplier links | n/a | Shopping list with per-vendor affiliate links |
| Tool granularity | n/a | one small tool per verb | Same: single-purpose snake_case tools |

## Sources

- MCP tool design: [AWS blog — MCP tool design tradeoffs](https://aws.amazon.com/blogs/machine-learning/mcp-tool-design-practical-approaches-and-tradeoffs/), [awslabs/mcp DESIGN_GUIDELINES](https://github.com/awslabs/mcp/blob/main/DESIGN_GUIDELINES.md), [The New Stack — 15 MCP best practices](https://thenewstack.io/15-best-practices-for-building-mcp-servers-in-production/), [Snyk — 5 MCP best practices](https://snyk.io/articles/5-best-practices-for-building-mcp-servers/), [KanseiLink — MCP tool schema guide](https://kansei-link.com/en/insights/mcp-tool-schema-design-guide-2026.html) (structuredContent/outputSchema per MCP spec 2025-06-18)
- Todo/list MCP tool surfaces: [RegiByte/todo-list-mcp](https://github.com/RegiByte/todo-list-mcp), [idsulik/todo-mcp-server](https://github.com/idsulik/todo-mcp-server), [wdm0006/todolist-mcp](https://github.com/wdm0006/todolist-mcp)
- Shopping-list semantics: [Mealie shopping-list survey](https://docs.mealie.io/news/surveys/2024-october/q9/), [CopyMeThat smart merge](https://www.copymethat.com/features/shopping-list/), [Listonic item details](https://listonic.com/add-details-to-your-shopping-list-items-pro)
- Electronics inventory/BOM tools: [PartKeepr BOM tooling](https://github.com/Gasman2014/KC2PK), [Part-DB docs](https://docs.part-db.de/), [BOMIST](https://bomist.com/)
- Affiliate compliance: [Amazon Associates help](https://affiliate-program.amazon.com/help/node/topic/GHQNZAU6669EZS98), [Geniuslink — Amazon disclosure guide](https://geniuslink.com/blog/amazon-affiliate-disclosure-guide/), [Termly — disclosure templates](https://termly.io/resources/articles/amazon-affiliate-disclosure/), [LegalClarity — FTC requirements](https://legalclarity.org/amazon-affiliate-disclaimer-examples-and-ftc-requirements/)
- Existing codebase: `partsmatcher/mcp.py`, `.planning/PROJECT.md`, `.planning/codebase/INTEGRATIONS.md`

---
*Feature research for: machine-wide MCP inventory + shopping list + affiliate service*
*Researched: 2026-08-25*
