# Stack Research

**Domain:** Machine-wide stdio MCP inventory service for Claude Code (Windows) + shopping-list/affiliate plumbing, stdlib-only Python
**Researched:** 2026-08-25
**Confidence:** HIGH (registration, protocol, atomic writes — verified against current official docs) / MEDIUM-HIGH (affiliate landscape — verified with dated sources, some vendor negatives are absence-of-evidence)

The existing stack (Python >=3.9 stdlib-only, hand-rolled JSON-RPC MCP server at protocol `2025-06-18`) is the right foundation and needs no replacement. This document covers only what this milestone ADDS. **The zero-third-party-dependency rule holds for every recommendation below — nothing here requires an exception.**

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `claude mcp add --scope user` | Claude Code CLI (current, unversioned) | Machine-wide registration | User scope loads the server in **all projects** on the machine, private to Ben — exactly the "zero per-project setup" requirement. Verified current: user-scope entries live at the top level of `~/.claude.json` (`%USERPROFILE%\.claude.json` on Windows, i.e. `C:\Users\User\.claude.json`), or inside `CLAUDE_CONFIG_DIR` if set |
| MCP protocol `2025-06-18` | spec revision 2025-06-18 | Wire protocol target | Claude Code's default (v1) runtime connects stdio servers on the legacy handshake; the 2026-07-28 revision is only negotiated with stdio servers if the user opts in via `MCP_PROTOCOL_NEGOTIATION=auto`. The existing server already speaks 2025-06-18 and has connected successfully. Stay put; add tolerant version negotiation (below) |
| Plain tagged deep links (no vendor API) | n/a | Affiliate links | Amazon PA-API was deprecated May 15, 2026 and its replacement (Creators API) requires ~10 qualified sales/30 days to keep access — a non-starter for a stubbed, pre-enrollment design. Plain `?tag=` URLs require no API, no credentials, no dependencies |
| `tempfile` + `os.fsync` + `os.replace` with retry | stdlib | Atomic JSON writes | `os.replace` is atomic on Windows (MoveFileEx with REPLACE_EXISTING) since Python 3.3. OneDrive/AV can briefly hold the destination open, surfacing `PermissionError` (winerror 5/32); the established pattern is exponential-backoff retry around the replace call only |

### Supporting Pieces (all stdlib)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `os.path.expanduser("~/bench")` | Locate data home | Resolving inventory/shopping-list paths; `~/bench` is outside OneDrive (`C:\Users\User\bench`), which is itself a hardening win — keep it that way |
| `json` | Shopping-list store + vendor config | Same format family as inventory; human-inspectable, git-friendly in the bench repo |
| `urllib.parse.quote_plus` / `urlencode` | Build affiliate URLs | Encoding part names into vendor search-link templates |
| `time.sleep` + `os` error codes | Replace-retry backoff | Only in the atomic-write helper; no-op path on POSIX (POSIX rename doesn't hit sharing violations) |
| `string.Formatter` / `str.format` | Vendor URL templates | `{query}` / `{tag}` substitution in per-vendor link templates from config |

## 1. Machine-Wide Registration (verified against code.claude.com/docs/en/mcp, fetched 2026-08-25)

**The exact command:**

```bash
claude mcp add --scope user --transport stdio partsmatcher -- python -m partsmatcher mcp "%USERPROFILE%\bench\my_inventory.json" "%USERPROFILE%\bench\my_projects.json"
```

Mechanics that matter (all verified current):

- **`--` separator:** everything after `--` is the server command, passed untouched. Claude Code options (`--scope`, `--transport`, `--env`) go before it.
- **Storage:** user scope writes a top-level `mcpServers` entry in `%USERPROFILE%\.claude.json` (shape: `{"type": "stdio", "command": ..., "args": [...], "env": {}}`). Local scope (the default) writes under the *current project's* path in the same file — wrong for this milestone; always pass `--scope user`.
- **Precedence:** local > project > user, matched by server name. A project that defines its own `partsmatcher` server shadows the user-scope one entirely (entries are not merged). Fine for HEPH — it should carry no project-scope entry and inherit the user-scope server.
- **Windows quirk:** the `cmd /c` wrapper is only needed for `.cmd` shims like `npx`. A native `python.exe` needs no wrapper. **Recommend registering with the absolute interpreter path** (e.g. `C:\Python313\python.exe`, or whatever `where python` resolves to) rather than bare `python`, so the server doesn't break when PATH differs between Claude Code launch contexts.
- **Duplicate add fails:** `claude mcp add` with an existing name at the same scope errors with `MCP server partsmatcher already exists in user config`. Re-registration is `claude mcp remove --scope user partsmatcher` then `add` (or edit `~/.claude.json` directly).
- **Verification:** `claude mcp list` shows health per server; `claude mcp get partsmatcher` shows the stored entry. Use these in the milestone's repeatable check.
- **Working directory is NOT the project:** don't rely on cwd. Claude Code sets `CLAUDE_PROJECT_DIR` in the spawned server's environment (project root) — useful later if a tool wants project-relative behavior, but inventory paths must stay absolute CLI args.

**Versioning/upgrade story:** the config stores a *command*, not a version. Registering `python -m partsmatcher` against a `pip install`ed (or `pip install -e` editable) package means `pip install -U partsmatcher` upgrades the server for every future session with **zero re-registration** — each Claude Code session spawns a fresh process. This is the recommended story: register once, upgrade via pip/git pull. The only events requiring re-registration are: interpreter path changes, data-file path changes, or CLI-arg signature changes (avoid the last by keeping `partsmatcher mcp`'s positional args stable, or moving path config into an env var/config file read at startup).

## 2. Protocol Target for the Hand-Rolled Server

Target **`2025-06-18`**, tools-only. Rationale: Claude Code's stdio path uses the legacy (v1 runtime) handshake by default; the 2026-07-28 revision is opt-in for stdio and adds nothing this server needs. `2025-11-25` additions (icons, tasks, OIDC) are likewise irrelevant to a local tools-only server.

Spec-verified conventions to implement (from modelcontextprotocol.io 2025-06-18 lifecycle spec):

- **Version negotiation:** if the client's `initialize` requests a version the server doesn't know (e.g. a future Claude Code sends `2026-07-28`), the server MUST respond with the latest version it *does* support (`2025-06-18`) — **not** an error. The client then accepts or disconnects. Make sure the handler echoes the client's version only when it matches, otherwise returns `"2025-06-18"` unconditionally.
- **Capabilities:** declare `{"capabilities": {"tools": {}}, "serverInfo": {"name": "partsmatcher", "version": <package version>}}`. Do not declare `listChanged` (the tool list is static), `resources`, or `prompts`. Optionally return `instructions` — a short string describing when to call `check_bom` vs `get_inventory`; Claude Code surfaces it to the model and it's free capability.
- **Lifecycle:** accept and ignore `notifications/initialized` and unknown notifications (never reply to a message without an `id`); respond to `ping` with an empty result; exit cleanly on stdin EOF (client closes stdin first, then escalates SIGTERM/SIGKILL).
- **Error conventions:** JSON-RPC errors (`-32700` parse, `-32601` method not found, `-32602` invalid params, `-32603` internal) for *protocol* failures only. Tool-level failures (bad BOM path, malformed JSON, missing inventory) return a normal result with `isError: true` and a human-readable `content` text — the existing server already does this; keep it, it's what lets the model recover and retry.
- **Output budget:** Claude Code warns at 10,000 tokens of tool output and truncates at 25,000 by default (`MAX_MCP_OUTPUT_TOKENS`). `get_inventory` over 76 types / 856 parts is nowhere near this, but keep tool output compact (no pretty-printed JSON blobs) as a rule.
- **Permissions naming:** tools surface as `mcp__partsmatcher__get_inventory` etc. — this is the string HEPH's settings will allowlist; document it.

## 3. Affiliate Link Formats (verified with dated sources, 2026-08-25)

The landscape finding that shapes the design: **of the four named electronics vendors, none has an affiliate program.** Amazon is the only Tier-1 target; everything else is a config-driven stub.

| Vendor | Program? | Link format | Notes |
|--------|----------|-------------|-------|
| Amazon Associates | **Yes** | `https://www.amazon.com/s?k={query}&tag={associates-id}` (search link) or `https://www.amazon.com/dp/{ASIN}?tag={associates-id}` (product link) | The `tag` query parameter (Associates/Store ID, e.g. `benbench-20`) is the entire attribution mechanism for plain links — no API required. PartsMatcher has part *names*, not ASINs, so **search links are the practical format**. Rules: links must not be cloaked/shortened to hide the Amazon destination; 3 qualifying sales in first 180 days or the account closes |
| Amazon PA-API / Creators API | Avoid | n/a | PA-API deprecated 2026-05-15, no new signups; successor Creators API requires ~10 qualified sales per 30 days to retain access. Do not build against it |
| Adafruit | **No — explicitly never** (official blog policy) | Plain link: `https://www.adafruit.com/search?q={query}` | Include as an *untagged* convenience vendor; the config schema treats "no tag" as "plain link" |
| SparkFun | **No** (not on CJ/ShareASale/Rakuten/Pepperjam; community forum asks went nowhere) | Plain link: `https://www.sparkfun.com/search/results?term={query}` | Same untagged treatment |
| Mouser | **No** (B2B distributor, no affiliate/referral program found) | Plain link: `https://www.mouser.com/c/?q={query}` | Same |
| Digi-Key | **No** (B2B distributor, no affiliate/referral program found) | Plain link: `https://www.digikey.com/en/products/result?keywords={query}` | Same |
| Jameco | Yes (5%, 120-day cookie, via network) | Network-generated links | The one hobby-electronics vendor with a real program; optional Tier-2 if Ben wants a second enrollment. LOW confidence on current terms — verify at enrollment time |

**Design implication (prescriptive):** implement affiliate plumbing as a per-vendor config file (JSON, beside the shopping list in `~/bench`, e.g. `vendors.json`):

```json
{
  "vendors": [
    {"id": "amazon",   "label": "Amazon",   "url_template": "https://www.amazon.com/s?k={query}&tag={tag}", "tag": null},
    {"id": "adafruit", "label": "Adafruit", "url_template": "https://www.adafruit.com/search?q={query}",    "tag": null}
  ]
}
```

Rule: if a template contains `{tag}` and `tag` is null/empty, emit the URL with the tag parameter stripped (a valid untagged link) — that is the "stubbed until Ben's accounts exist" behavior, and enrollment later is a one-line config edit, no code change. URL-encode `{query}` with `urllib.parse.quote_plus`. Do not hardcode vendor URLs in Python; the template file is the extension point for future vendors/networks (which mostly issue opaque network links that fit the same template model).

## 4. Atomic File Writes on Windows (OneDrive-aware)

The pattern, entirely stdlib (`tempfile`, `os`, `time`):

1. Create the temp file **in the same directory as the target** (`tempfile.mkstemp(dir=os.path.dirname(target), prefix=".{name}.", suffix=".tmp")`) — same volume is required for `os.replace` atomicity.
2. Write UTF-8 JSON, then `f.flush()` and `os.fsync(f.fileno())` before closing — otherwise a crash can atomically install an empty/truncated file.
3. `os.replace(tmp, target)` — atomic on both POSIX and Windows (Python >=3.3).
4. **Retry the replace on Windows sharing violations:** OneDrive's sync engine, search indexer, and AV briefly open files without `FILE_SHARE_DELETE`, making `os.replace` raise `PermissionError` (WinError 5 "Access is denied" / 32 "sharing violation"). Field-proven mitigation (e.g. CoolProp PR #2905): wrap only the `os.replace` call in ~8 attempts of exponential backoff starting at ~0.05s (worst case a few seconds). On POSIX this path never triggers — no platform branching needed beyond catching `PermissionError`/`OSError`.
5. On final failure, delete the temp file and raise — never fall back to an in-place write.

Two placement rules that reduce the hazard to near zero:

- **Shopping list and vendor config live in `~/bench`** (already decided) — `C:\Users\User\bench` is *outside* OneDrive, so the retry loop is a safety net, not a load-bearing mechanism. Do not move the data home into a OneDrive-synced path.
- `.bak` sibling backups (the existing chat-sync convention) apply to the shopping list too: write `shopping_list.json.bak` via the same atomic helper before replacing the real file.

The inventory files need no write path at all this milestone (read-only over MCP is a stated requirement) — the atomic helper serves the shopping list, vendor config, and any future bench-repo writes.

## Installation

```bash
# No packages to install — stdlib only. "Installation" is registration:

# 1. Install/upgrade the package (from PyPI or the repo)
pip install -U partsmatcher        # or: pip install -e <repo> for the dev machine

# 2. Register machine-wide (once; survives package upgrades)
claude mcp add --scope user --transport stdio partsmatcher -- ^
  C:\Path\To\python.exe -m partsmatcher mcp ^
  "%USERPROFILE%\bench\my_inventory.json" "%USERPROFILE%\bench\my_projects.json"

# 3. Verify
claude mcp list          # partsmatcher should show healthy
claude mcp get partsmatcher
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Hand-rolled 2025-06-18 stdio server (existing) | Official `mcp` Python SDK / FastMCP | Only if the zero-dep rule were dropped. The SDK would add pydantic + anyio + httpx to a project whose entire value proposition includes zero install friction. Nothing this milestone needs (tools, isError, version echo) is hard by hand |
| User scope (`~/.claude.json`) | Project scope (`.mcp.json` committed to HEPH) | If HEPH were distributed to other machines and needed to declare the dependency explicitly. For one shared desktop, user scope is strictly better (no approval prompt, no per-repo file, works in every future project automatically) |
| `python -m partsmatcher` via pip-installed package | Registering a repo-path script | Repo-path registration couples every Claude session to a OneDrive-synced working tree; `pip install` (even editable) decouples it and gives the clean `pip install -U` upgrade story |
| Amazon search links (`/s?k=...&tag=`) | ASIN product links via Creators API | Only after Ben has an active Associates account *and* sustained sales volume (10/30 days). Revisit post-enrollment; the vendor-template design accommodates it without rework |
| Stubbed per-vendor URL templates | Affiliate-network SDKs (Impact, CJ, etc.) | Never for this codebase — all are HTTP-API/JS-snippet based and unnecessary; networks issue plain trackable URLs that fit the template model |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| FastMCP / `mcp` PyPI SDK | Violates the zero-third-party-dependency rule (pulls pydantic, anyio, httpx); existing hand-rolled server already works against real Claude Code | Existing `partsmatcher/mcp.py`, extended |
| Amazon PA-API / Creators API (now) | PA-API deprecated 2026-05-15; Creators API demands 10 qualified sales/30 days — Ben has no account yet. Also drags in request signing/OAuth | Plain `?tag=` search links from templates |
| SiteStripe image embeds | Discontinued Dec 2023; dead images | Text links only; images aren't needed for a shopping list |
| Adafruit/SparkFun/Mouser/Digi-Key "affiliate" work | No programs exist (Adafruit's policy is explicit and permanent) | Untagged search links via the same template config |
| Bare `python` in the registration command | PATH varies across Claude Code launch contexts (Terminal vs VS Code vs Desktop app); silent server-start failures | Absolute interpreter path in `~/.claude.json` |
| In-place `open(target, "w")` JSON writes | Crash or OneDrive lock mid-write truncates the only copy of real data | tmp-in-same-dir + fsync + `os.replace` + backoff retry |
| Storing shopping list under the OneDrive repo | Sync engine sharing violations, conflict copies, and the data outlives the repo | `~/bench` (outside OneDrive), beside the inventory |
| `notifications/*` replies or JSON-RPC errors for tool failures | Replying to notifications violates JSON-RPC; protocol errors for tool failures prevent model recovery | Ignore notifications; `isError: true` results for tool failures |

## Stack Patterns by Variant

**If Claude Code later negotiates a newer protocol with stdio servers by default:**
- The version-echo rule (respond with `2025-06-18` when the requested version is unknown) already handles it — the spec makes the *client* decide whether to proceed or disconnect. No preemptive multi-version support needed.

**If Ben's Amazon Associates account gets approved:**
- Set `"tag": "<his-id>-20"` in `vendors.json`. No code change, no re-registration.

**If HEPH moves to another machine:**
- Re-run the two-step install/register there; consider shipping a `partsmatcher register` convenience subcommand that shells out to `claude mcp add --scope user` with the resolved interpreter and data paths (it can also detect the duplicate-name error and offer remove+re-add).

## Version Compatibility

| Component | Compatible With | Notes |
|-----------|-----------------|-------|
| Python >=3.9 stdlib | Everything above | `os.replace`, `tempfile.mkstemp`, `urllib.parse` all pre-3.9; no new floor |
| MCP `2025-06-18` server | Claude Code v1 runtime (default for stdio) | Verified: stdio servers stay on the legacy handshake unless `MCP_PROTOCOL_NEGOTIATION=auto` |
| `claude mcp add` CLI syntax | Claude Code current (2026-08) | CLI is unversioned upstream; the stored JSON shape (`type`/`command`/`args`/`env`) is the stabler contract — the repeatable check should assert on `claude mcp list`/`get` output, not on internal file layout |

## Sources

- https://code.claude.com/docs/en/mcp — fetched 2026-08-25: scopes table (local/project/user → `~/.claude.json` / `.mcp.json`), precedence, `--` separator semantics, duplicate-add error, `CLAUDE_PROJECT_DIR`, v1/v2 runtimes and stdio legacy-handshake default, `MAX_MCP_OUTPUT_TOKENS` 25k cap / 10k warning, `MCP_TIMEOUT`. **HIGH confidence**
- https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle — fetched 2026-08-25: initialize/initialized flow, version-negotiation MUSTs, capabilities table, stdio shutdown, error example. **HIGH confidence**
- https://modelcontextprotocol.io/specification/2025-11-25/changelog + MCP anniversary blog — revision timeline (2024-11-05 → 2025-03-26 → 2025-06-18 → 2025-11-25). **HIGH confidence**
- https://webservices.amazon.com/paapi5/documentation/ (deprecation notice) + https://www.keywordrush.com/blog/amazon-creator-api-what-changed-and-how-to-switch/ — PA-API deprecated 2026-05-15, Creators API successor, 10-sales/30-day access rule. **HIGH confidence** on deprecation (official), MEDIUM on the exact sales-threshold interpretation
- https://www.wptasty.com/amazon-images-on-your-blog + Associates program-requirement guides — SiteStripe image links discontinued Dec 2023; 3 qualifying sales/180 days; no link cloaking. **MEDIUM confidence** (multiple credible secondary sources agree)
- https://blog.adafruit.com/2009/09/14/adafruit-has-never-and-will-never-do-any-affiliate-programs-period/ — Adafruit's explicit permanent no-affiliate policy. **HIGH confidence**
- https://community.sparkfun.com/t/affiliate-program/12890 + affiliate-network absence checks — SparkFun/Mouser/Digi-Key have no programs. **MEDIUM confidence** (absence of evidence across networks; re-verify at enrollment time)
- https://getlasso.co/niche/electronics/ — Jameco 5% / 120-day cookie. **LOW confidence** (single aggregator; verify before enrolling)
- https://github.com/CoolProp/CoolProp/pull/2905 — field-proven `os.replace` retry-with-backoff on Windows PermissionError (8 attempts, 0.05s base). **MEDIUM confidence** pattern, corroborated by python-atomicwrites issue #25 and general `os.replace` guidance

---
*Stack research for: PartsMatcher machine-wide MCP milestone (registration, protocol, affiliate links, atomic writes)*
*Researched: 2026-08-25*
