# Architecture Patterns

**Domain:** Machine-wide MCP inventory service (local-first, stdlib-only Python, single user, Windows primary)
**Researched:** 2026-08-25
**Confidence:** HIGH on Claude Code registration semantics (official docs) and Python atomicity primitives (documented stdlib behavior); MEDIUM on lock-file tuning parameters (community-standard pattern, no single authority)

## Recommended Architecture

The milestone adds one new layer — a **data-home access layer** — between the existing frontends and the user's files, and repoints the MCP frontend at the real bench repo. Nothing about the pure core changes.

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        Entry / Frontends                             │
├────────────┬────────────┬──────────────┬───────────────┬─────────────┤
│ match/     │ chat (TTY) │ app (browser)│ mcp (stdio)   │ init (new)  │
│ shopping   │ chat.py    │ app/*        │ mcp.py        │ init.py     │
│ (CLI)      │            │              │ per-session,  │ one-shot    │
│ cli.py     │            │              │ N at once     │ bootstrap   │
└─────┬──────┴─────┬──────┴──────┬───────┴──────┬────────┴──────┬──────┘
      │            │             │              │               │
      ▼            ▼             ▼              ▼               ▼
┌──────────────────────────────────────────────────────────────────────┐
│          Data-home access layer — partsmatcher/datahome.py (NEW)     │
│  resolve_home()        → args > $PARTSMATCHER_HOME > pointer file    │
│  atomic_write_json()   → tmp-in-same-dir + os.replace + retry        │
│  FileLock              → O_CREAT|O_EXCL lockfile, stale takeover     │
│  ShoppingList store    → lock → read → modify → atomic replace       │
│  read_inventory()/read_projects()/read_affiliates()  (read-only)     │
└───────────────┬──────────────────────────────────────────────────────┘
                │ decoded JSON values only (unchanged contract)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│           Pure matching core — partsmatcher/matcher.py (unchanged)   │
└──────────────────────────────────────────────────────────────────────┘

        On disk:
        ~/.partsmatcher/config.json      ← pointer: {"data_home": "C:/Users/User/bench"}
        ~/bench/                         ← the data home (existing local git repo)
        ~/.claude.json                   ← Claude Code user-scope MCP registration
```

Key property preserved: `matcher.py` stays I/O-free; the new layer owns *all* file access that used to be scattered across `cli.py`, `mcp.py`, and `chat.py` sync helpers. The MCP server stays read-per-call (no caching) — that behavior is already correct for a service whose data can change underneath it.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `datahome.py` (new) | Resolve data home; atomic writes; lock files; shopping-list store; read-only loaders | Reads/writes `~/bench/data/*`; imported by cli, mcp, chat, init |
| `init.py` (new, or `_run_init` in cli.py) | Create/adopt data home, migrate loose files, write pointer, register MCP user-scope, self-verify | Shells out to `claude mcp add`; calls `datahome.py`; writes `~/.partsmatcher/config.json` |
| `affiliates.py` (new, small) | Pure link rendering: (part name, vendor config) → tagged URL list; stub tags until accounts exist | Called by shopping-list renderers in cli.py and mcp.py; config read via `datahome.py` |
| `mcp.py` (extended) | Existing 3 tools + `add_to_shopping_list`, `suggest_parts` (or extended `get_inventory` filters); inventory strictly read-only | `datahome.py` for all file access; `matcher.py`; `affiliates.py` |
| `cli.py` (extended) | New `init` and `shopping` subcommands (lazy imports, per convention) | `datahome.py`, `init.py` |
| `chat.py` sync helpers (hardened) | Same sync-back semantics, writes routed through `atomic_write_json` + timestamped backups | `datahome.py` (write primitives only) |
| `~/bench` (data home) | Single source of truth: inventory, projects, aliases, shopping list, affiliate config; git-versioned | Touched only through `datahome.py` (product paths) and by Ben directly (git, editor) |

### Data Flow

**MCP tool call (read):** Claude Code session → stdio JSON-RPC → `mcp.py` handler → `datahome.resolve_home()` → read `data/inventory.json` fresh → `matcher.py` → text result. Read-only by construction: `mcp.py` simply has no import of any write function except the shopping-list store.

**MCP shopping-list add (the one write):** tool call → `ShoppingList.add(...)` in `datahome.py` → acquire lockfile → read current `shopping_list.json` → merge item (dedupe by `normalize_name`, sum qty, record source/project/timestamp) → write tmp file in same dir → `os.replace` → release lock → return updated list text (with affiliate links rendered by `affiliates.py`).

**CLI shopping commands:** `partsmatcher shopping list|add|remove|clear` → the *same* `ShoppingList` methods. One code path; the CLI adds only argument parsing and human rendering.

**Bootstrap:** `partsmatcher init` → create/adopt `~/bench` → write pointer file → `claude mcp add --scope user partsmatcher -- python -m partsmatcher mcp` → registration lands in `~/.claude.json` → every future Claude Code session on the machine loads the server (user scope loads in all projects — verified against current Claude Code docs).

## The Five Questions, Answered

### 1. Data home layout and access layer

Adopt the bench repo's existing `data/` convention rather than inventing a new one — `~/bench` is live with 76 types / 856 parts and 7 intake commits; the product should meet it where it is.

```text
~/bench/                          # existing local git repo = the data home
  data/
    inventory.json                # read-only over MCP
    projects.json                 # read-only over MCP
    inventory.aliases.jsonl       # append-only, chat/app path only
    shopping_list.json            # THE writable MCP surface (new)
    affiliates.json               # vendor → tag template config (new, stub tags OK)
    .shopping_list.lock           # transient; gitignored
  .backups/                       # timestamped pre-write copies (new; replaces single-gen .bak)
  .claude/ , CLAUDE.md, .git/     # existing bench-repo machinery, untouched
```

**Discovery (how three frontends find it):** precedence is explicit CLI args → `PARTSMATCHER_HOME` env var → pointer file `~/.partsmatcher/config.json` (`{"data_home": ...}`) → bundled samples (current fallback). The pointer file is written once by `init` and lives *outside* the data home so the data home can move without touching registration. Registration then needs **no paths at all**: `claude mcp add --scope user partsmatcher -- python -m partsmatcher mcp` — the server resolves the home at startup. This is deliberately different from the current registration hint in `cli.py:244` (which bakes inventory/projects paths into the registration); baking paths in means re-registering every time the home moves, and `~/.claude.json` entries are not something Ben should hand-edit.

**Access layer:** one new module, `partsmatcher/datahome.py`. Everything that touches the data home goes through it. It exposes read-only loaders (inventory, projects, affiliates), the write primitives (`atomic_write_json`, `FileLock`), and the `ShoppingList` store. `mcp.py`, `cli.py`, and `chat.py`'s sync helpers all import it. This also gives the "inventory is read-only over MCP" requirement a structural enforcement: `mcp.py` never imports a function capable of writing `inventory.json`.

**Why not a config format fancier than JSON:** stdlib-only rule; JSON pointer file with one key is the whole need.

### 2. Where shopping-list write logic lives

In `datahome.py` as a `ShoppingList` class (or module functions): `add`, `remove`, `set_qty`, `clear`, `items`. Both frontends are thin:

- `mcp.py` `add_to_shopping_list` tool → parse args → `ShoppingList.add` → render result text.
- `cli.py` `shopping` subcommand → argparse → same methods → `_print_human`-style rendering.

The merge/dedupe policy (key on `normalize_name`, keep display spelling, sum quantities, track `{added_by: "mcp"|"cli", project, timestamp}` per entry) lives in the store, tested once, shared everywhere. `check_bom` gains an optional "add missing to shopping list" behavior by calling the same store — never by duplicating write logic in the tool handler. Affiliate-link rendering is **not** in the store; it's a pure function in `affiliates.py` applied at render time, so the stored file stays vendor-neutral data and link config can change without rewriting the list.

### 3. Concurrency across simultaneous MCP processes

Reality check on the load: one MCP server process per open Claude Code session — plausibly 3–6 alive at once on Ben's machine — but writes are human-triggered and rare (a few per day at most). The design goal is *no lost or torn data ever*, not throughput.

**Minimal safe design — three pieces, all stdlib:**

1. **Atomic replace for every write** (shopping list, and retrofit chat.py sync): write to `tmpfile` in the *same directory* (same volume — required for atomicity), `f.flush()` + `os.fsync()`, then `os.replace(tmp, target)`. `os.replace` is documented atomic on both POSIX and Windows (NTFS). Consequence: **readers never need locks** — any reader sees either the complete old file or the complete new file, never a truncated one. This alone fixes the CONCERNS-verified torn-write hazard.
   - Windows wrinkle: `os.replace` can raise `PermissionError` if another process (or OneDrive/AV) momentarily holds the destination open. Wrap in a short retry loop (e.g. 5 attempts, 50–100 ms backoff). Note `~/bench` is `C:\Users\User\bench` — *not* inside OneDrive's synced folders, unlike the dev repo — so the OneDrive hazard mostly disappears the moment real data operations happen in the data home. Keep the retry anyway; AV scanners cause the same transient sharing violations. (MEDIUM confidence on frequency, HIGH on the mitigation being standard.)

2. **Exclusive lockfile around read-modify-write.** Last-writer-wins on the whole file is *not* acceptable here: two sessions adding different parts concurrently would silently drop one add — the exact "silent data loss" class this project has already been burned by. But full merge logic (CRDT-ish reconciliation) is over-engineering for single-digit writers. The middle path: serialize writers with a lockfile so read→modify→replace is exclusive, and then no merge is ever needed. Implementation: `os.open(lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` — atomic create-or-fail on POSIX and Windows — write PID + timestamp into it, retry with backoff for ~5 s, delete on release (`try/finally`).

3. **Stale-lock takeover**, because MCP processes are killed without cleanup when a Claude Code session closes mid-write. If the lockfile's mtime is older than a timeout (10–30 s is generous for a sub-millisecond critical section), delete it and retry. Optionally check the recorded PID with `os.kill(pid, 0)`/`OpenProcess` — but mtime age alone is adequate at this scale and simpler on Windows.

Explicitly rejected: `fcntl`/`msvcrt.locking` advisory locks (two platform code paths, `msvcrt` locks byte ranges not files and interacts badly with the replace-the-file pattern); SQLite for the shopping list (real concurrency answer, but breaks the human-readable/git-diffable JSON story of the bench repo and adds schema machinery for a file with tens of entries); append-only JSONL ledger with compaction (genuinely lock-free for adds, but removes/qty-edits need tombstones and a compaction story — more total machinery than one lockfile).

### 4. Registration/bootstrap: `partsmatcher init` sequence

Idempotent, re-runnable, plain-English output with a PASS/FAIL summary (Ben is the operator).

1. **Resolve target home** — `--home PATH` flag, default `~/bench`.
2. **Adopt or create.** If `data/inventory.json` exists (Ben's live repo): adopt — parse-validate all present files via the core parsers, touch nothing that validates. Else: create the layout; **migrate** any loose legacy files found (`~/my_inventory.json`, `~/my_projects.json`, `~/my_inventory.aliases.jsonl` → `data/` names), copying not moving, and report what was found.
3. **Seed missing pieces** — empty `shopping_list.json`, `affiliates.json` with stub vendor entries (`{"amazon": {"tag": null, "url_template": ...}}`), `.backups/`, gitignore entries for `.backups/` and `*.lock`.
4. **Git** — `git init` + initial commit if no `.git`; if repo exists and is dirty, commit the seeded files only (or instruct). Never rewrite history.
5. **Write pointer** — `~/.partsmatcher/config.json` with the resolved absolute path (atomic write, naturally).
6. **Register MCP user-scope** — check `claude` on PATH (`shutil.which`); run `claude mcp add --scope user partsmatcher -- python -m partsmatcher mcp` via subprocess. Handle "already exists" by `claude mcp remove --scope user partsmatcher` then re-add (or `add --force` if supported at build time — verify against the installed CLI, this flag surface changes). If `claude` is missing, print the exact command for later instead of failing the whole init. Note: registration captures the `python` on PATH; document that a Python upgrade may need `init --register-only` re-run.
7. **Self-verify** — spawn the just-registered server command as a subprocess, drive a real `initialize` → `tools/list` → `get_inventory` over its actual stdio, and confirm the response mentions the real inventory path and a plausible part count. Print `PASS: 76 part types served from C:\Users\User\bench` style lines. This doubles as the seed of the missing repeatable MCP real-transport check (CONCERNS: "MCP server against a real client").

Steps 2–5 are pure `datahome.py`/`init.py`; step 6 is the only Claude-Code-coupled step and should be independently invokable (`init --register-only`) for post-upgrade repair.

### 5. Build order

Dependency-driven; each phase leaves the system shippable.

| Order | Phase | Depends on | Why this position |
|-------|-------|-----------|-------------------|
| 1 | **Data-home access layer + atomic writes** (`datahome.py`: resolve, `atomic_write_json`, `FileLock`; retrofit `chat.py` sync + timestamped backups) | — | Everything else imports it; atomic writes are the standing data-safety mandate and retrofitting sync-back early means every later phase inherits safe writes. Pure library work, fully unit-testable (crash-simulation, lock-contention tests). |
| 2 | **init + machine-wide registration** (pointer file, adopt `~/bench`, `claude mcp add --scope user`, self-verify) | 1 | The moment this lands, MCP serves *real* data in every session — the milestone's core value — even before any new tools exist. Also unblocks live HEPH testing of existing tools against real inventory. |
| 3 | **Shopping list** (store in `datahome.py`, `add_to_shopping_list` MCP tool, `shopping` CLI subcommand) | 1 (lock+atomic), 2 (useful only once registered) | First writable surface; must not exist before the concurrency primitives do. |
| 4 | **Affiliate links** (`affiliates.py`, config schema, stubbed tags, rendering in CLI + MCP output) | 3 | Pure rendering over the shopping list; zero coupling to anything earlier; safe to defer or parallelize with 5. |
| 5 | **HEPH-facing polish** (`suggest_parts` capability, `check_bom` error-shape hardening, `SERVER_INFO` version fix, extend the step-7 self-verify into a repeatable real-transport test; decouple MCP output from `cli._print_human` per CONCERNS) | 2 (needs live registration to validate against real sessions) | Iterative by nature — the HEPH integration shape is still evolving with Ben's buddy, so it benefits from landing last, after real sessions have exercised phases 2–3 and produced concrete feedback. |

Phases 4 and 5 are independent of each other and can swap or interleave. The one hard rule: **no writable store before phase 1's primitives exist** — the project's data-loss history makes "temporary" unsafe writes the named anti-pattern.

## Patterns to Follow

### Pattern: tmp-then-`os.replace` atomic write
**What:** Every persistent-file write goes tmp-file-in-same-dir → fsync → `os.replace`, with a small Windows `PermissionError` retry.
**When:** All writes in `datahome.py`; retrofit `_sync_inventory`/`_sync_projects`/`_sync_aliases`.
**Example:**
```python
def atomic_write_text(path: Path, text: str, retries: int = 5) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(retries):
            try:
                os.replace(tmp, path)   # atomic on POSIX and Windows (same volume)
                return
            except PermissionError:     # transient sharing violation (AV, sync client)
                if attempt == retries - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
```

### Pattern: lockfile-serialized read-modify-write
**What:** `O_CREAT|O_EXCL` lockfile with mtime-based stale takeover, held only for the read→modify→replace of one file.
**When:** Every shopping-list mutation, from any frontend.

### Pattern: structural read-only enforcement
**What:** The MCP module imports only read loaders plus the shopping-list store — no code path in the process can write `inventory.json`.
**When:** Keep as an invariant; add a test asserting `mcp.py` has no import of inventory-writing symbols.

### Pattern: registration without paths
**What:** MCP registration command carries no data paths; the server resolves its home via env/pointer at startup.
**When:** `init` step 6; keeps `~/.claude.json` stable across data-home moves.

## Anti-Patterns to Avoid

### Anti-pattern: last-writer-wins on the shopping list
**Why bad:** Concurrent adds from two sessions silently drop one — the project's signature failure class (silent data loss) recurring on the new surface.
**Instead:** Lockfile-serialized RMW (above); it costs ~30 lines and removes the merge problem entirely.

### Anti-pattern: caching inventory in the MCP process
**Why bad:** N long-lived server processes with cached state means stale answers after an intake session updates `~/bench`; the current read-per-call design is already correct and cheap at 10²-part scale.
**Instead:** Keep re-reading per tool call; atomic writes guarantee those reads are never torn.

### Anti-pattern: shopping-list writes bypassing the shared store
**Why bad:** Same duplication disease as the chat/app session-prep drift already logged in CONCERNS — two write paths guarantees eventual divergence in dedupe/locking behavior.
**Instead:** `ShoppingList` in `datahome.py` is the only code that opens the file for writing; CLI and MCP are callers.

### Anti-pattern: baking affiliate tags into stored data
**Why bad:** Tags don't exist yet (accounts pending) and will change; stored URLs go stale and pollute git history.
**Instead:** Store vendor-neutral part entries; render links at display time from `affiliates.json`.

## Scalability Considerations

Not a scaling milestone — single user, single machine, tens of shopping-list entries, hundreds of parts. The axes that matter are **process count** (handled by the lock design; correctness is independent of how many sessions are open) and **data durability** (atomic writes + timestamped backups + git). If this later becomes the multi-user API MVP, the `datahome.py` seam is exactly where a real database swaps in; nothing above or below it changes.

## Sources

- Claude Code MCP docs — scopes, `--scope user` stored in `~/.claude.json`, loads in all projects, `--` arg separator, scope precedence: https://code.claude.com/docs/en/mcp (fetched 2026-08-25) — HIGH
- Python docs, `os.replace`: "If successful, the renaming will be an atomic operation" (POSIX + Windows same-volume) — HIGH
- Python docs, `os.open` `O_CREAT|O_EXCL` atomic create-or-fail (basis of portable lockfiles) — HIGH
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md` (2026-08-25) — verified in-repo facts: non-atomic sync writes, temp-dir workspace hazard, data-loss history, `mcp.py` path handling, `cli.py:244` registration hint — HIGH
- `docs/bench-repo/README.md` + memory note `bench-repo-live.md` — live `~/bench` layout (`data/` subdir, filenames, git-local-only, Windows) — HIGH
- Lockfile stale-takeover tuning (timeout values, PID checks) — community-standard practice, no single authority — MEDIUM

---

*Architecture research for roadmap: 2026-08-25*
