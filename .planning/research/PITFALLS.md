# Pitfalls Research

**Domain:** Machine-wide MCP inventory service (Windows, stdlib Python, OneDrive-adjacent data) with shopping list + affiliate links
**Researched:** 2026-08-25
**Confidence:** HIGH for MCP/stdio/OneDrive mechanics (official docs + reproduced GitHub issues + this repo's own verified concerns); MEDIUM for Amazon Associates AI-context claims (policy text verified, enforcement interpretation is community consensus)

## Critical Pitfalls

### Pitfall 1: Stale machine-wide registration — the server that used to work

**What goes wrong:**
A user-scope MCP registration is a frozen snapshot of *how to launch the server at registration time* (interpreter path, module path, cwd assumptions). Then the venv gets rebuilt, Python gets upgraded (new `Python3XX` directory), the repo moves out of OneDrive, or `pip install -e` is re-run — and every Claude Code session on the machine silently loses the tools. Claude Code reports "MCP server failed to connect" (or nothing at all in a headless HEPH run), and nobody connects it to the package change made weeks earlier.

**Why it happens:**
Registration stores a command string, not a live reference. On Windows there are extra layers: `claude mcp add` has known Windows spawn quirks (bare `npx`/script commands need `cmd /c` wrapping; see anthropics/claude-code#7672), and there have been real bugs where `--scope user` wrote to a location the runtime didn't read or didn't apply cross-project (#54803, #32939). The Claude Code CLI is this project's un-pinned, self-updating dependency (CONCERNS.md "Dependencies at Risk") — registration semantics can shift under you.

**How to avoid:**
- Register an *absolute* interpreter path + `-m partsmatcher` style invocation, not whatever `python` resolves to on PATH at registration time. Prefer a launcher that survives package moves (e.g., a tiny stable shim script in a durable location, or `py -3` if version-pinning isn't needed).
- Ship a **verification command** (`partsmatcher mcp-doctor` or a checklist step): does `claude mcp list` show the server, does `claude mcp get partsmatcher` show the expected command, does a one-shot `claude -p "call get_inventory"` succeed? Ben is a non-coder; PASS/FAIL output is the requirement, not a nice-to-have.
- Fix the stale `SERVER_INFO` version string (already flagged in CONCERNS.md) *before* machine-wide registration — it's the primary "which build is actually registered?" debugging signal.
- Document the exact re-registration command in one place so recovery is copy-paste.

**Warning signs:**
Tools present in one project but not another (scope bug); "works when run manually, fails when Claude launches it" (PATH/cwd divergence — Claude Code launches MCP servers with its own cwd and a stripped environment); HEPH reporting the tool "doesn't exist."

**Phase to address:**
Registration phase — with a repeatable real-client smoke check as its exit criterion, not just `claude mcp list` output.

---

### Pitfall 2: Stdout pollution and Windows encoding breaking the stdio transport

**What goes wrong:**
In stdio transport, stdout *is* the protocol. One stray `print()`, a warning from an imported module, a traceback, or a Unicode symbol encoded as cp1252 mojibake corrupts the JSON-RPC stream; the client drops the connection with an opaque error or a silent disconnect. This project has a specific landmine: `tool_match_projects` renders reports by capturing CLI `_print_human` output via `redirect_stdout` (CONCERNS.md) — any future CLI code path that writes to real stdout outside that capture window (or a partially-applied refactor) poisons the transport. Windows adds the encoding layer: `_run_mcp` reconfigures stdio to UTF-8, but that behavior has never been tested against a live client on Windows, and Python <3.15 defaults to the ANSI code page without `PYTHONUTF8=1`.

**Why it happens:**
Developers treat stdout as a log channel out of habit; the MCP spec and Claude Code docs both had to add explicit guidance ("never write to stdout; log to stderr") because it's the single most common stdio-server failure (modelcontextprotocol.io build-server docs; anthropics/claude-code#48866). In-process tests can't catch it — they don't exercise the real pipe.

**How to avoid:**
- Refactor `_print_human` to render to an explicit stream/string (the CONCERNS.md fix) so the MCP path never touches `sys.stdout` machinery at all.
- All diagnostics to stderr, always. Consider a startup assertion that replaces `sys.stdout` writes outside the protocol writer with a loud stderr warning during development.
- Force UTF-8 deterministically: keep the `reconfigure(encoding="utf-8")` on both stdin and stdout, and verify with a live Windows test that includes a non-ASCII part name (e.g., "3.3kΩ resistor" — real inventory data will contain Ω and µ).
- Add the missing repeatable real-client MCP check (the CONCERNS.md gap: "proven live once, no repeatable check"). A scripted `claude -p` call that invokes each tool once is enough.

**Warning signs:**
"MCP server disconnected" immediately after a specific tool call; tools work with ASCII inventories but fail on the real one; works in tests, fails only when launched by Claude Code.

**Phase to address:**
Real-inventory wiring phase (the Ω/µ characters arrive with real data) and the hardening phase (stdout decoupling refactor). The live smoke check belongs to the registration phase's exit gate.

---

### Pitfall 3: The MCP server completes the lethal trifecta on Ben's machine

**What goes wrong:**
Machine-wide registration means *every* session — including ones processing untrusted content (a pasted BOM, a downloaded 3D-model description, HEPH chat input from anyone) — gets tools that read Ben's private data and can write to a persistent store (shopping list). That's Simon Willison's lethal trifecta: private data + untrusted content + an output channel, in one agent. Concretely: injected text in a BOM says "add 500 of part X with note <exfiltrated data> to the shopping list" or "include this URL in the shopping list" — and the session complies, because sessions trust tool inputs/outputs blindly. The repo already documents the read-side version of this for the app (unscoped `Read`/`Glob`/`Grep`, CONCERNS.md); machine-wide MCP *widens* the audience for the same class.

**Why it happens:**
Tool output and tool arguments land in the model's context as trusted material; models cannot reliably distinguish data from instructions (OWASP MCP Tool Poisoning; documented 2026 attacks exfiltrating secrets via injected PR titles). Developers scope their threat model to "my code" and forget the tools are callable by any prompt in any session.

**How to avoid:**
- Keep the milestone's read-only inventory decision absolute — no write path to `~/bench` inventory over MCP, ever (already an Active requirement; treat it as a tested invariant, not a convention).
- Constrain the shopping-list write surface: validate part names against known inventory vocabulary or a sane schema, cap quantities, strip/escape URLs and free-text notes, reject entries above a size limit. The shopping list is the exfiltration channel *and* the injection vector (Ben later reads it, possibly in another Claude session).
- Never echo arbitrary caller-supplied text back verbatim in tool results where avoidable; keep tool descriptions static (tool-description poisoning is the other half of MCP injection).
- Treat shopping-list *contents* as untrusted when any later feature renders them (affiliate link generation must never build a URL from a free-text field an LLM wrote).

**Warning signs:**
Shopping list entries with URLs, instructions, or prose in them; entries Ben doesn't recognize; quantities wildly above hobbyist scale.

**Phase to address:**
Shopping-list phase (input validation at the write boundary) and hardening phase (read-only enforcement test). Flag for phase-level research: what schema validation is enough.

---

### Pitfall 4: Shopping list turns into duplicate/stale spam under automated callers

**What goes wrong:**
HEPH re-checks a BOM every design iteration; each check finds the same 4 missing parts; each check appends them. After a week the list has "10kΩ resistor ×3" listed nine times, quantities that double-count (needed-per-check appended rather than reconciled), and entries for parts Ben has since bought or that a later design revision dropped. The list becomes noise, Ben stops trusting it, and the affiliate/replenishment value proposition dies at step one.

**Why it happens:**
Tools built for a human caller assume each call is intentional; automated agents retry, loop, and re-run idempotent-looking checks. Append-only stores plus non-idempotent writes is the classic mistake. Staleness is the second-order version: nothing reconciles the list against inventory changes, because the inventory and the list are separate files with no linkage.

**How to avoid:**
- Make `add_to_shopping_list` an **upsert keyed on canonical part identity** (the alias/normalization machinery the matcher already has): repeat calls set/raise the needed quantity, never duplicate rows. Record provenance (which BOM/session, when) and last-updated timestamps instead of new rows.
- Separate "needed quantity" from "already owned" at *read* time: when listing, re-check current inventory and show net shortfall, so bought parts age out automatically rather than requiring cleanup writes.
- Distinguish `check_bom` (pure read, no side effects) from an explicit `add_missing_to_shopping_list` action — never let the feasibility check itself write. HEPH depending on a repeatable check means the check must be side-effect free.
- Give Ben a trivial clear/remove path (CLI or tool) — lists humans can't prune get abandoned.

**Warning signs:**
Same part appearing twice in the list file; quantities growing across identical BOM checks; list entries for parts `get_inventory` says are in stock.

**Phase to address:**
Shopping-list phase — idempotency and read-time reconciliation are design decisions, near-impossible to retrofit onto an append-only file format later.

---

### Pitfall 5: Affiliate links that get the account banned before the first commission

**What goes wrong:**
The Amazon Associates failure modes here are specific and terminal: (a) **cloaking/obscuring** — the Program Policies prohibit hiding or redirecting Special Links in ways that prevent Amazon from determining the click origin; generic URL shorteners and redirect wrappers are out (only Amazon's own `amzn.to` is sanctioned). (b) **Prohibited contexts** — links in email, offline documents, or anything easily read offline are banned; a shopping-list *file on disk* that Ben forwards or that another tool emails is exactly this trap. (c) **The generative-AI clause** — since March 2024 the Operating Agreement prohibits Special Links "in connection with generative AI"; interpretation is unsettled, but links *generated inside AI-agent tool output* sits closer to the prohibited reading than a blog post does. Amazon's own Alexa Associates program shows AI surfacing isn't categorically banned, but this project's shape (links emitted by an MCP tool into an LLM transcript) is untested ground. (d) **The 180-day/3-sale rule** — a new account with no qualifying sales in 180 days is closed; enrolling before there's real purchase traffic burns the application. (e) **Missing required disclosure** — Amazon mandates the Associates disclosure statement wherever links appear, and the FTC requires clear-and-conspicuous material-connection disclosure adjacent to the link ("paid link" suffices; a buried disclosure page does not).

**Why it happens:**
The Operating Agreement is long, enforcement is account-closure-first-questions-later, and developers treat affiliate tags as a URL parameter rather than a regulated relationship. The 24-hour cookie also means link *placement quality* matters more than volume — links nobody clicks within a purchase-intent window earn nothing.

**How to avoid:**
- This milestone's stubbed-tag decision is exactly right: build the plumbing with per-vendor tag config, ship with tags empty/disabled, and **do not enroll** until the loop demonstrably produces clicks (protects the 180-day window).
- Emit **direct, undisguised product URLs** with the tag as a visible query parameter — no redirect layer, no shortener, no link-wrapping "for cleanliness."
- Attach the disclosure *in the same tool output that carries the links* (e.g., a fixed `disclosure` field: "As an Amazon Associate, Ben earns from qualifying purchases" + "paid links"). Don't rely on the consuming session to add it — the session may summarize links without it. Make the disclosure part of the rendered shopping-list format itself.
- Keep affiliate-tagged links out of anything that becomes email or offline docs; scope them to the interactive shopping-list view.
- Before enrolling for real, re-read the current Operating Agreement's generative-AI clause and check whether the new Creators API (PA-API's announced replacement, transition through 2026) has AI-app guidance — this is a decision point, not a build-time detail. Electronics vendors (Digi-Key, Mouser, Adafruit via affiliate networks) have their own ToS; verify each before adding tags.

**Warning signs:**
Any redirect/shortener in the link pipeline; links appearing in exported/emailed artifacts; shopping-list output rendered anywhere without the disclosure string; an Associates account created "to have it ready" with no traffic behind it.

**Phase to address:**
Affiliate-plumbing phase — with an explicit "compliance re-check before tag activation" task deferred to when Ben actually enrolls. Flag: needs fresh ToS research at activation time (policies shift; the PA-API→Creators API transition is live through 2026).

---

### Pitfall 6: OneDrive + concurrent JSON writes corrupting the only copy of real data

**What goes wrong:**
Machine-wide MCP means *multiple* server processes can be alive at once (one per Claude Code session — Claude Code spawns a separate stdio server instance per session/project). If two sessions add to the shopping list simultaneously, last-writer-wins silently drops entries; worse, non-atomic writes plus OneDrive's sync-lock behavior can leave truncated JSON. This is not hypothetical: Claude Code's own `~/.claude.json` suffered a corruption cascade from exactly this combination (non-atomic writes + concurrent processes + OneDrive contention, anthropics/claude-code#29153), and this repo's sync-back is already flagged as non-atomic on OneDrive-adjacent files (CONCERNS.md). `~/bench` is the only copy of rebuilt data after a prior total loss. OneDrive Files-On-Demand adds a read-side trap: a dehydrated (cloud-only) file can fail or stall on open.

**Why it happens:**
`write_text()` in place feels atomic but isn't; OneDrive's sync engine takes momentary exclusive locks and produces sharing violations (`OSError`/WinError 32) at unpredictable times; multiple stdio server instances is an easy fact to miss when you tested with one session.

**How to avoid:**
- Every write: temp file in the same directory → `os.replace()` (atomic on the same NTFS volume). Retry once or twice with short backoff on Windows sharing violations — OneDrive locks are transient.
- Serialize shopping-list writers with a lock file (`msvcrt.locking` or an `O_CREAT|O_EXCL` lockfile with stale-lock timeout — stdlib-only compatible) since multiple MCP processes are the *expected* case, not an edge case.
- Read-modify-write must re-read under the lock, not merge from a stale in-memory copy.
- Keep `~/bench` (already outside OneDrive, in the home directory) as the durable data home — do **not** relocate data into the OneDrive-synced repo folder for convenience. Mark bench files "Always keep on this device" if OneDrive ever touches them.
- Inventory reads over MCP should tolerate a mid-write shopping list (validate JSON, fall back to last-good/backup rather than crashing the tool call).
- Timestamped or generation-rotated backups instead of the single-generation `.bak` (CONCERNS.md).

**Warning signs:**
`PermissionError`/WinError 32 in stderr logs; shopping-list entries vanishing after concurrent sessions; zero-byte or truncated JSON; OneDrive "sync conflict" copies (`file-DESKTOP-XXX.json`) appearing beside data files.

**Phase to address:**
Hardening phase (atomic writes, locking) — but the shopping-list *store design* must assume multi-process from day one, so the locking decision belongs in the shopping-list phase, before the first write path ships.

---

### Pitfall 7: Schema drift between producer (partsmatcher) and consumer (HEPH) with no contract

**What goes wrong:**
HEPH depends on `check_bom`'s output shape, but the shape is defined only by what the code emits today — partly by capturing human-oriented CLI text (CONCERNS.md). A field rename, a wording change in the human report, or a new result category silently changes what HEPH's LLM sees; the LLM "helpfully" reinterprets it, producing plausible-but-wrong feasibility answers instead of a loud failure. Meanwhile the real-inventory wiring changes data richness (76 types/856 parts with real naming quirks vs. sample data), which can shift matcher behavior HEPH implicitly relied on.

**Why it happens:**
LLM consumers mask breakage — unlike a typed API client, a model swallows drifted output and improvises. "Proven once inside HEPH Studio" (2026-08-23) is a point-in-time observation, not a contract. Two codebases on one desktop, evolving with a friend, no shared schema artifact.

**How to avoid:**
- Return **structured JSON** from tools (status enum + missing-parts array + quantities), with any human-readable summary as a separate field — never as the primary payload. This also kills the `redirect_stdout` coupling.
- Write the tool result schemas down (a short TOOLS.md or JSON-schema file) and treat changes as versioned events; bump `SERVER_INFO` version (once un-hardcoded) on schema changes so HEPH-side debugging has a signal.
- The repeatable smoke check should assert result *shape*, not just success — that's the drift detector.
- Test `check_bom` against the real inventory's actual naming (aliases, units, Ω/µ) before declaring HEPH-ready.

**Warning signs:**
HEPH sessions describing feasibility results in ways the tool never said; "it worked last month" reports; tool output containing formatting artifacts (ASCII marks, column padding) from the CLI renderer.

**Phase to address:**
BOM-robustness phase — structured output + documented schema is the core of "robust enough for HEPH to depend on."

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Registering the venv's `python.exe` path directly | Works today | Breaks on venv rebuild/Python upgrade; silent machine-wide outage | Only with a doctor/re-register command shipped alongside |
| Keeping `redirect_stdout` CLI capture in MCP tools | No refactor needed | Any CLI change breaks MCP invisibly; stdout-pollution risk on the protocol channel | Never past this milestone — real-inventory + HEPH dependence raise the stakes |
| Append-only shopping list file | Trivial to implement | Duplicate spam, no reconciliation, unfixable format later | Never — upsert-by-part-key costs little now |
| Skipping file locking because "it's one user" | Less code | Multiple sessions = multiple server processes; lost writes on the writable store | Never for the shopping list; fine for pure-read paths |
| Enrolling in Amazon Associates early "to be ready" | Feels like progress | 180-day/3-sale closure burns the application before traffic exists | Never — stub tags until the loop produces real clicks |
| Hardcoding affiliate tags in code | Fast | Can't rotate/disable per vendor; tags leak into contexts they shouldn't | Never — config file from the start (already the plan) |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code `claude mcp add` (Windows) | Bare command relying on PATH/shell resolution; assuming `--scope user` behaves as documented across versions | Absolute interpreter + module invocation; verify with `claude mcp list` *and* a real tool call in a fresh directory; re-verify after Claude Code self-updates |
| Claude Code stdio transport | Logging to stdout; assuming client cwd/env matches dev shell | stderr-only logging; no cwd assumptions (resolve `~/bench` absolutely); UTF-8 reconfigure both directions |
| HEPH (consumer) | Treating one successful live run as a contract | Documented JSON result schema + repeatable smoke check asserting shape |
| Amazon Associates | Shorteners/redirects; links in email/offline artifacts; missing in-context disclosure; enrolling pre-traffic; ignoring the generative-AI clause | Direct tagged URLs, disclosure embedded in tool output, stub tags until activation, ToS re-check at activation (Creators API transition live through 2026) |
| Electronics vendor affiliates (Digi-Key/Mouser/Adafruit) | Assuming Amazon's rules generalize | Each runs on its own network (e.g., Impact/CJ) with distinct ToS; verify per vendor before tagging |
| OneDrive | In-place writes; assuming files are hydrated; ignoring WinError 32 | Atomic replace + retry-on-sharing-violation; keep data home outside OneDrive (`~/bench` already is — keep it that way) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-reading/parsing full inventory per tool call | None at 856 parts | Nothing needed — explicitly a non-trap at this scale; don't add caching complexity | ~10⁵ parts, i.e., never for this user |
| Shopping-list file growing unbounded from automation | Slow reads, huge diffs | Upsert semantics + reconciliation (Pitfall 4) | Weeks of HEPH iteration loops |
| Lock-file contention across sessions | Rare stalls on write | Short lock hold (read-modify-write only), stale-lock timeout | Only if a server crashes while holding the lock — timeout handles it |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Any inventory write path over MCP | Injected session corrupts the only copy of real data | Hard read-only invariant with a test; writes only via chat/app guardrails (already decided — enforce, don't just intend) |
| Unvalidated free text into shopping list | Injection payloads persisted, then read by future sessions (stored prompt injection) | Schema-validate entries; strip URLs/instructions from notes; length caps |
| Building affiliate URLs from LLM-written text | Attacker-steered links presented to Ben as "buy this" | Generate URLs only from canonical part→product mappings in config, never from tool-call arguments |
| Registering machine-wide without considering who else runs sessions | Every project on the machine (any cloned repo's CLAUDE.md, any pasted content) can invoke tools against private data | Accept for read-only inventory (low sensitivity, per CONCERNS.md); it's the *write* surface that must be constrained |
| Trusting tool output as ground truth downstream | HEPH asserts feasibility from drifted/garbled output | Structured schema + shape-asserting smoke test |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent registration failure | Ben (non-coder) can't tell "no tools" from "Claude being weird" | `mcp-doctor`-style PASS/FAIL check with the fix command printed |
| Duplicate-riddled shopping list | Ben stops trusting/using it | Upsert + net-shortfall view (Pitfall 4) |
| Affiliate links without disclosure | FTC exposure once public; erodes trust even privately | Disclosure string baked into the rendered list format |
| Error messages as protocol errors | Tool call "fails" opaquely in HEPH instead of saying "part name not recognized" | Return structured, in-band errors (valid JSON-RPC result with an error field) — graceful errors are an Active requirement |
| Cryptic Windows file errors surfacing raw | "WinError 32" means nothing to Ben | Retry silently; if persistent, plain-English message ("another program is using the shopping list — try again in a moment") |

## "Looks Done But Isn't" Checklist

- [ ] **Machine-wide registration:** Often missing verification from a *different* project directory and after a Claude Code update — verify with a fresh-dir real tool call, and re-verify post-update
- [ ] **Real-inventory wiring:** Often missing non-ASCII handling (Ω, µ, ±) end-to-end over the real stdio pipe — verify with a live call returning real part names on Windows
- [ ] **Read-only inventory:** Often an intention, not an invariant — verify a test asserts no MCP code path can write to inventory files
- [ ] **Shopping list:** Often missing idempotency under repeated identical BOM checks — verify: run the same check 5×, list has no duplicates and correct quantities
- [ ] **Shopping list:** Often missing multi-process safety — verify two concurrent adds both land (lock + atomic replace)
- [ ] **Affiliate plumbing:** Often missing the disclosure in the output payload itself — verify the rendered list contains it with tags enabled, and that stub mode emits clean untagged URLs
- [ ] **check_bom for HEPH:** Often missing a written result schema and a repeatable check — verify smoke script asserts shape, and TOOLS/schema doc exists
- [ ] **Hardening:** Often missing the crash-mid-write case — verify kill-during-write leaves either old or new file, never truncated JSON

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Stale registration | LOW | `claude mcp remove` + re-add with corrected command (documented copy-paste); doctor command confirms |
| Stdout pollution disconnect | LOW-MEDIUM | Reproduce with live smoke script; grep for non-stderr writes; the `_print_human` decoupling eliminates the class |
| Corrupted shopping list JSON | LOW (if backups exist) / HIGH (if not) | Restore from generation backup; since ~/bench is git, `git checkout` the file — make committing part of the write story or keep rotated backups |
| Corrupted inventory | Must not happen | Read-only enforcement + ~/bench git history is the last line; no MCP write path exists to cause it |
| Amazon Associates account closed (180-day) | MEDIUM | Reapply later with real traffic — allowed, but rejection can't be reinstated on the same application; avoid by not enrolling early |
| Amazon ban for policy violation (cloaking/context) | HIGH | Bans are frequently permanent per community post-mortems; prevention (direct links, disclosure, context limits) is the only real strategy |
| HEPH broken by schema drift | MEDIUM | Version signal in SERVER_INFO + schema doc localizes the diff; smoke test catches it before HEPH does |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Stale registration / Windows spawn quirks | Registration phase | Fresh-directory real tool call passes; doctor command exists and passes |
| Stdout pollution / Windows encoding | Real-inventory + hardening phases | Live smoke on Windows with non-ASCII part names; `_print_human` no longer captured via redirect_stdout |
| Lethal-trifecta exposure | Shopping-list + hardening phases | Read-only invariant test; shopping-list input validation tests incl. injection-shaped inputs |
| Shopping-list dup/stale spam | Shopping-list phase | 5× identical BOM check → no duplicates; bought part disappears from net-shortfall view |
| Affiliate ToS/FTC traps | Affiliate phase (+ activation-time re-check) | Direct URLs only; disclosure in payload; tags stubbed; written activation checklist with ToS re-read |
| OneDrive/concurrent JSON corruption | Hardening phase (design in shopping-list phase) | Kill-mid-write test leaves valid file; concurrent-add test; retry-on-WinError-32 covered |
| Schema drift vs HEPH | BOM-robustness phase | Structured JSON results; schema doc; shape-asserting smoke test |

**Research flags for later phases:** Affiliate activation needs fresh ToS research when Ben enrolls (generative-AI clause interpretation + Creators API transition are both moving through 2026). Electronics-vendor affiliate programs (Digi-Key, Mouser, Adafruit) were not individually verified this pass — each needs its own ToS check before tagging.

## Sources

- Repo-verified: `.planning/codebase/CONCERNS.md` (2026-08-25 audit — non-atomic sync writes, redirect_stdout coupling, stale SERVER_INFO, unscoped reads, un-pinned Claude Code dependency), `.planning/PROJECT.md`
- MCP/stdio: [MCP build-server docs — stdout warning](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server), [claude-code#48866 stdout/stderr guidance gap](https://github.com/anthropics/claude-code/issues/48866), [Postman community — stdout pollution → invalid JSON-RPC](https://community.postman.com/t/mcp-server-stdout-pollution-causing-invalid-json-rpc-messages-in-claude-desktop/89753) — HIGH confidence
- Registration on Windows: [claude-code#7672 silent Windows failures / cmd wrapping](https://github.com/anthropics/claude-code/issues/7672), [claude-code#54803 user-scope write/read mismatch](https://github.com/anthropics/claude-code/issues/54803), [claude-code#32939 user scope not cross-project](https://github.com/anthropics/claude-code/issues/32939), [Claude Code MCP docs](https://code.claude.com/docs/en/mcp-quickstart) — HIGH confidence (official tracker)
- Prompt injection: [Simon Willison — the lethal trifecta (2025-06-16)](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/), [OWASP — MCP Tool Poisoning](https://owasp.org/www-community/attacks/MCP_Tool_Poisoning), [Invariant Labs — tool poisoning notification](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) — HIGH confidence
- Amazon Associates: [Associates Program Policies (cloaking, shorteners, offline/email)](https://affiliate-program.amazon.com/help/operating/policies), [Participation Requirements](https://affiliate-program.amazon.com/help/operating/participation/), [Geniuslink on cloaking compliance](https://geniuslink.com/blog/link-cloaking-amazon/), [ChatAds — Operating Agreement & AI apps, generative-AI clause, Creators API transition (2026)](https://www.getchatads.com/blog/amazon-associates-operating-agreement-ai-apps/) — policy text HIGH, AI-context interpretation MEDIUM (unsettled, community consensus)
- FTC: [FTC Endorsement Guides FAQ ("paid link" adequate; footer/sidebar insufficient)](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking), [16 CFR Part 255](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-255) — HIGH confidence
- OneDrive/JSON: [claude-code#29153 — .claude.json corruption cascade (concurrent writes + OneDrive)](https://github.com/anthropics/claude-code/issues/29153), [claude-code#62140 — Files-On-Demand dehydration corruption](https://github.com/anthropics/claude-code/issues/62140), [MyWorkDrive — OneDrive sync-engine limitations](https://www.myworkdrive.com/blog/onedrive-as-a-file-server-limitations) — HIGH confidence

---
*Pitfalls research for: machine-wide MCP inventory service with shopping list + affiliate links (Windows/OneDrive, stdlib Python)*
*Researched: 2026-08-25*
