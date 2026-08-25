# Codebase Concerns

**Analysis Date:** 2026-08-25

## Tech Debt

**Per-turn Claude process spawn with full-transcript resume:**
- Issue: The app runs one `claude -p --resume <session-id>` child process per chat turn; `--resume` rehydrates the entire transcript every turn, so latency and token cost grow with conversation length. The planned upgrade path (one long-lived stream-json process, "option 1C" in `docs/APP_ARCHITECTURE.md`) is unbuilt, and the instrumentation to decide is dead: `self.turns` is incremented in `partsmatcher/app/runner.py` (`run_turn`) and never read anywhere.
- Files: `partsmatcher/app/runner.py`, `docs/APP_ARCHITECTURE.md`, `docs/MOBILE.md` (unratified proposal to freeze 1B)
- Impact: Long sessions get progressively slower and more expensive; no measurement exists to know when it hurts.
- Fix approach: Either surface per-turn timing (the `turns` counter plus wall-clock) to make the 1C decision data-driven, or ratify the docs/MOBILE.md proposal and delete the dead counter.

**Duplicated session-prep between `chat` and `app`:**
- Issue: `chat.run_chat` (`partsmatcher/chat.py:1001`) and `app.run_app` (`partsmatcher/app/__init__.py:104`) each repeat the same ~40-line sequence: resolve workspace, guard CLAUDE.md, stage photos, build the match command, build context, prepare workspace, write session record, pick default prompt. Input loading is shared (`_gather_session_inputs` in `partsmatcher/cli.py`), but workspace preparation is not.
- Files: `partsmatcher/chat.py`, `partsmatcher/app/__init__.py`, `partsmatcher/cli.py`
- Impact: A change to workspace setup (e.g. a new data file, a session-record field) must be made twice; the two paths can silently drift. The `package_root` computation already differs (`parent.parent` vs `parent.parent.parent`) — correct for each file's depth, but exactly the kind of subtlety duplication breeds.
- Fix approach: Extract a shared `prepare_session(...)` helper (in `chat.py` or a new module) returning the workspace + kickoff prompt; both entry points call it.

**`chat.py` is a grab-bag module (1,130 lines):**
- Issue: `partsmatcher/chat.py` holds context-markdown generation, workspace lifecycle, photo staging, three sync functions, session records, recovery, workspace listing/cleaning, and the interactive launcher.
- Files: `partsmatcher/chat.py`
- Impact: Hard to navigate; the sync/recover machinery (used by `app`, `recover`, and `chat` alike) is entangled with chat-specific prompt text.
- Fix approach: Split along the existing seams: `context.py` (CLAUDE.md builder), `workspace.py` (prepare/stage/session record), `syncback.py` (sync + recover + inspect). Pure refactor; the test suite (`tests/test_chat.py`, 1,158 lines) already covers the behavior.

**MCP server version string is stale:**
- Issue: `SERVER_INFO = {"name": "partsmatcher", "version": "0.1.0"}` in `partsmatcher/mcp.py:55` is hardcoded while the package is at `0.7.1` (`partsmatcher/__init__.py:18`, `pyproject.toml`).
- Files: `partsmatcher/mcp.py`
- Impact: MCP clients report a misleading server version; a future "which version is registered machine-wide?" debugging session gets a wrong answer.
- Fix approach: `from . import __version__` and use it in `SERVER_INFO`.

**MCP tool renders reports by capturing CLI stdout:**
- Issue: `tool_match_projects` (`partsmatcher/mcp.py:259`) imports `_print_human` from `cli.py` and captures it via `contextlib.redirect_stdout(StringIO())`. `_print_human` reads `sys.stdout` for mark selection, so the coupling includes a load-bearing side effect (StringIO has no `.encoding`, forcing ASCII marks).
- Files: `partsmatcher/mcp.py`, `partsmatcher/cli.py` (`_print_human`, `_pick_marks`)
- Impact: Any CLI-output refactor (e.g. writing to an explicit stream, adding color detection) can silently change or break MCP tool output; `redirect_stdout` is also not thread-safe if the MCP server ever grows concurrency.
- Fix approach: Refactor `_print_human` to render to a passed stream (or return a string) with explicit `ascii_marks`/`color` flags; both CLI and MCP call it directly.

## Known Bugs

*(No live known bugs. Two recently fixed ones are worth remembering because of what they reveal — see Fragile Areas and Test Coverage Gaps.)*

- **Fixed 2026-08-25:** the workspace `Edit(...)` permission rule was emitted as a Windows `C:\` path, which Claude Code accepts but never matches — every headless write on Windows was silently permission-denied. Fixed by POSIX-normalizing to `/c/...` in `_workspace_edit_rule` (`partsmatcher/app/__init__.py:61`). No automated test can catch a regression in the *semantics* side of this (see Fragile Areas).
- **Fixed 2026-08-25:** DOS short-path (8.3) assertion failures in tests, exposed the moment `windows-latest` was added to CI (`.github/workflows/tests.yml`, commit 61c3323) — evidence that Ubuntu-only CI was masking Windows-specific path behavior for the primary user's platform.

## Security Considerations

**The whole write-scoping model rests on undocumented Claude Code internals:**
- Risk: Headless permission enforcement depends on unpublished, observed-not-specified Claude Code behavior: (a) only `Edit(path)`/`Read(path)` rules are consulted for file tools — a `Write(...)` path rule is accepted but ignored; (b) rules match against POSIX-normalized paths (`/c/users/...` on Windows); (c) `//` anchors absolute paths. All three are documented only in this repo's own comments (`_workspace_edit_rule` docstring, `GATES.md` G1–G3). A Claude Code update can invalidate any of them, and the failure mode is silent: a denied write in headless mode has no prompt to recover from, and the fake-driven test suite stays green.
- Files: `partsmatcher/app/__init__.py` (`_workspace_edit_rule`, `write_permission_settings`, `BASE_ALLOWED_TOOLS`), `GATES.md`
- Current mitigation: `GATES.md` G11 mandates a live-run check; `scripts/real_claude_smoke.py` exercises the loop against real Claude, manually, pre-release. Last live permission validation was macOS (2026-08-22); the Windows-rule fix landed 2026-08-25.
- Recommendations: Run `scripts/real_claude_smoke.py` on Windows (the primary user's platform) after the POSIX-normalization fix and record it in GATES.md; add a rule-shape assertion for Windows drive paths to `tests/test_app.py` if not present; re-run the smoke script after every Claude Code upgrade, not just before releases.

**Read tools are unscoped (documented, deliberate, still open):**
- Risk: `BASE_ALLOWED_TOOLS = ["Read", "Glob", "Grep"]` are pre-allowed with no path scope. A prompt-injected headless turn (e.g. hostile text smuggled into a photo or a pasted BOM) can read and exfiltrate-into-the-transcript any file the user can read — `~/.ssh/`, browser profiles, anything.
- Files: `partsmatcher/app/__init__.py:58`, `GATES.md` ("Not gated here — deliberate follow-up")
- Current mitigation: Writes are pinned to the workspace, so injection cannot *modify* files outside it; the app is loopback-only and single-user. GATES.md names this openly.
- Recommendations: When scoping reads, follow the GATES.md instruction: pair it with a live run (G11-style), because a denied read is the same silent-failure class as a denied write.

**The `Bash(...)` allow rule's open tail — verified NOT exploitable via chaining (2026-08-25):**
- Risk (refuted): `write_permission_settings` emits `Bash({match_command}*)` (`partsmatcher/app/__init__.py:94`), and an earlier draft of this document claimed the trailing `*` allowed chaining `; <arbitrary command>` off the allowed prefix. Checked against the official permissions documentation ("Compound commands"): Claude Code splits commands on `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines and requires a rule to match **each subcommand independently**, so a chained command is never auto-allowed by the prefix rule. This is documented, deliberate injection protection.
- Files: `partsmatcher/app/__init__.py`
- Residual risk: The `*` still allows extra *arguments* to the matcher invocation itself (e.g. flags); `cli.py`'s argparse accepts only the two positionals and a small flag set, so the surface is trivial.
- Recommendations: No action needed. If tightened anyway, re-verify with a live run that the matcher re-run still fires unprompted.

**DNS-rebinding can bypass the session token (verified by code inspection 2026-08-25):**
- Risk: The token/Origin scheme (`partsmatcher/app/server.py`) stops ordinary cross-origin pages, but not DNS rebinding: `GET /` and `GET /api/state` require no token, and `_authorized` compares `Origin` to the request's own `Host` header rather than to a localhost allowlist. A domain rebound to `127.0.0.1` is same-origin with itself — the attacker page can fetch `/` (which embeds `PM_TOKEN`), read the token, and POST with a matching Origin/Host pair, gaining full session control including `/api/end` (which overwrites the user's real inventory via sync).
- Files: `partsmatcher/app/server.py` (`_authorized`, `do_GET`), `partsmatcher/app/page.py` (token embedded in the page)
- Current mitigation: The server binds `127.0.0.1` and uses an OS-assigned random port per run, so the attacker must also discover the port; sessions are short-lived. Low likelihood for a hobbyist tool, but the sync's write-to-real-files makes the impact nontrivial.
- Recommendations: Validate the `Host` header against `127.0.0.1`/`localhost` (reject anything else with 403) — one small check closes the class.

**`/api/state` serves the full inventory without the token:**
- Risk: Any local process (or the rebinding attacker above) can read the user's complete parts inventory and workspace path from an unauthenticated GET.
- Files: `partsmatcher/app/server.py` (`do_GET` → `state_payload`)
- Current mitigation: Loopback-only; the data is a hobbyist parts list, low sensitivity.
- Recommendations: If the Host check lands, this is largely covered; requiring the token on `/api/state` (the page already has it) would finish it.

## Performance Bottlenecks

**Full-transcript rehydration per turn:**
- Problem: Each app turn re-loads the whole conversation via `--resume` (see Tech Debt above). Not yet measured.
- Files: `partsmatcher/app/runner.py`
- Cause: One child process per turn, by design (architecture option 1B).
- Improvement path: Measure first; option 1C (long-lived process) is the designed escape hatch.

**Otherwise not a concern:** the matcher is O(projects × parts) over in-memory dicts (`partsmatcher/matcher.py`), inventories are hundreds of parts, and `/api/state` re-reads two small JSON files per poll. Nothing here approaches a limit at personal-inventory scale.

## Fragile Areas

**`partsmatcher/app/runner.py` — the stream-json contract:**
- Files: `partsmatcher/app/runner.py`
- Why fragile: `_events_from_record` pattern-matches an undocumented, versioned output format (`type: assistant`/`result`, `subtype: success`, `is_error`, content-block shapes) and `build_command` hardcodes CLI flags (`-p`, `--output-format stream-json`, `--verbose`, `--resume`). Every test drives it with fabricated records; a real Claude Code update that renames a field or changes flag requirements breaks the app while the suite stays green. Unknown records are silently skipped (`json.JSONDecodeError` → `continue`), so a format change degrades to an empty-looking turn rather than a loud error.
- Safe modification: Change the event vocabulary only alongside a `scripts/real_claude_smoke.py` run; keep the "unknown record → skip" behavior but consider logging skipped record types to stderr so drift is visible.
- Test coverage: Fakes only; the real binary is exercised solely by the manual smoke script.

**`runner.run_turn` stderr handling can deadlock (verified by code inspection 2026-08-25):**
- Files: `partsmatcher/app/runner.py:99-133`
- Why fragile: The child is spawned with `stderr=subprocess.PIPE`, but the turn loop reads only stdout; stderr is read *after* `process.wait()`, and only on nonzero exit. If a `claude` process writes more than the OS pipe buffer (~64 KB) to stderr, it blocks on the full pipe, never exits, `wait()` never returns, and the turn (holding `turn_busy`) hangs the whole app.
- Safe modification: Drain stderr on a background thread (or use a temp file / `stderr=subprocess.STDOUT` filtered by JSON-parse failure), then `wait()`.
- Test coverage: No test exercises a chatty-stderr child.

**Sync-back writes are non-atomic, on OneDrive-adjacent files (verified by code inspection 2026-08-25):**
- Files: `partsmatcher/chat.py` (`_sync_inventory:449-459`, `_sync_projects:531-539`, `_sync_aliases:571-580`)
- Why fragile: The store update is `backup.write_text(...)` then `inventory_store.write_text(updated)` — a crash, power loss, or an OneDrive sync-lock `OSError` between or during the two can leave a truncated store file. The repo itself lives inside a OneDrive-synced folder on the owner's machine, and the user's data files plausibly do too; OneDrive's file locking and sync races are a real hazard for a tool whose exit path rewrites JSON files in place. The `.bak` is also single-generation: a second sync (even a bad one) overwrites the only backup.
- Safe modification: Write to a temp file in the same directory and `os.replace()` over the store (atomic on the same volume); catch `OSError` per file (already done) but retry once on Windows sharing violations; consider timestamped backups.
- Test coverage: Happy path and validation-failure paths are tested; mid-write crash / locked-file behavior is not.

**Recoverable workspaces live in the system temp directory:**
- Files: `partsmatcher/chat.py` (`_resolve_workspace_dir`, `find_recoverable_workspaces`, `SESSION_FILENAME`)
- Why fragile: An unclean session's only copy of unsynced edits (and, for sample sessions, the *only* copy period) sits in `tempfile.gettempdir()`, which the OS or disk-cleanup tools may purge at any time. The project has already lost user data once for a related reason — ROADMAP.md records that `my_inventory.json` (59 types/547 parts), `my_projects.json`, and the 69-record alias dataset all vanished from the owner's machine, noticed 2026-08-22 — see Missing Critical Features.
- Safe modification: Prefer a stable app-data directory (`~/.partsmatcher/sessions/`) over the temp dir for workspaces, or at minimum for session records.
- Test coverage: recover/list/clean are well tested against injected temp roots; temp-dir eviction is inherently untestable but the exposure is architectural.

**`AppState.take_kickoff` is unsynchronized (verified by code inspection 2026-08-25):**
- Files: `partsmatcher/app/server.py:75-80`
- Why fragile: `ThreadingHTTPServer` handles requests concurrently; two simultaneous `GET /api/state` calls can race `kickoff_sent` check-then-set and both receive the kickoff, double-firing the opening turn (the exact symptom the 2026-08-08 double-fetch bug produced by other means). The page's single-fetch discipline makes it unlikely, not impossible.
- Safe modification: Guard with a lock or use the existing `_sync_lock` pattern.
- Test coverage: Single-threaded tests only.

**The generated CLAUDE.md protocol is prose, enforced by nothing:**
- Files: `partsmatcher/chat.py` (`build_context_markdown`, ~230 lines of behavioral instructions)
- Why fragile: Inventory schema preservation, append-only `aliases.jsonl`, confirm-before-write, exact-name vocabulary — all are instructions to a model, not code. The sync layer validates schema on the way out (good), but alias append-only-ness and vocabulary discipline rely on model compliance; `_new_alias_records` assumes seeded lines are never rewritten (`lines[alias_seed_count:]`) — a model that reorders or edits earlier lines would corrupt what gets synced without any warning beyond the malformed-record counter.
- Safe modification: When editing the prose, keep the machine-checked invariants (schema shape, seed-count slicing) in mind; consider hashing the seeded alias prefix at session start and warning at sync if it changed.
- Test coverage: Sync-side validation is tested; model-compliance obviously cannot be.

## Scaling Limits

**Not a near-term concern.** Single user, loopback server, one turn at a time (`turn_busy` lock), inventories of ~10² parts, projects of ~10¹. The only growth axis that bites is conversation length (see Performance). The sidebar re-reads and re-matches on every `/api/state` poll — linear and trivially cheap at this scale.

## Dependencies at Risk

**Claude Code CLI (the load-bearing, un-pinned dependency):**
- Risk: The entire chat/app experience shells out to whatever `claude` binary is on PATH — flags, stream-json schema, permission-rule semantics, session-store behavior (`--resume`) are all unversioned from this repo's perspective, and Claude Code updates itself. This is simultaneously the project's core design choice (no API key, user's own login) and its biggest external risk.
- Impact: Any of: broken turns, silently-denied writes, lost session resume, changed permission matching. The test suite cannot detect any of it (fakes throughout).
- Migration plan: None needed — but institutionalize `scripts/real_claude_smoke.py` (run on Windows *and* macOS, after Claude Code updates as well as before releases; see `docs/RELEASING.md`), and keep the observed-behavior notes in `GATES.md`/`_workspace_edit_rule` current, since they are the only documentation of the contract anywhere.

**Python stdlib only otherwise** — zero third-party runtime dependencies is a project rule and holds; no dependency-rot exposure.

## Missing Critical Features

**No durable home for user data (`init-repo`):**
- Problem: The user's real inventory, project database, and alias dataset live as loose untracked files in a home directory plus temp-dir workspace copies. This already caused a total loss: ROADMAP.md ("State notes 2026-08-16", loss noticed 2026-08-22) records `my_inventory.json`, `my_projects.json`, and the 69-record alias dataset gone with no recoverable copy anywhere. The rebuilt inventory now lives in a local-only git repo (`~/bench`, hand-built per `docs/bench-repo/`), but that's a manual arrangement, not a product feature.
- Blocks: Safe accumulation of the naming-alias dataset (the stated long-game asset for the vision scanner); confidence that a session can't be the last copy of anything. `partsmatcher init-repo` is the ROADMAP's named answer and does not exist yet.

**No automated check of the page's JavaScript:**
- Problem: `partsmatcher/app/page.py` is a 260-line HTML/JS string; tests assert substrings of it (token present, both POSTs carry the header) but never execute it. The SSE hand-parser, the state renderer, the kickoff single-fetch discipline, and the end-session flow run for the first time in a real browser.
- Blocks: Refactoring the page with confidence; catching a JS syntax error before a user does. (A JS bug cannot fail any test — confirmed by the 2026-08-24/25 safety-net review.)

## Test Coverage Gaps

**The real-Claude boundary (the big one):**
- What's not tested: Everything past the fake seam — real `claude` flag acceptance, real stream-json parsing, real permission-rule matching (especially the just-fixed Windows POSIX-normalization behavior), real `--resume` continuity. 168+ tests, all green, prove nothing about any of it.
- Files: `partsmatcher/app/runner.py`, `partsmatcher/app/__init__.py` (permission rules), `tests/test_app.py`, `tests/test_chat.py`
- Risk: A Claude Code update breaks the app with a fully green CI; a permission regression on Windows denies every write silently.
- Priority: High. `scripts/real_claude_smoke.py` exists but is manual and, as far as the repo records, has not been run on Windows since the rule fix.

**Page JavaScript execution:**
- What's not tested: All client-side behavior (see Missing Critical Features).
- Files: `partsmatcher/app/page.py`, `tests/test_app.py` (`PageContractTests` — string assertions only)
- Risk: Rendering/streaming/end-session bugs ship invisibly.
- Priority: Medium. A minimal option: run the page's `<script>` under Node with a fetch stub, or at least a JS syntax check (`node --check` on the extracted script) in CI.

**Concurrency and failure-mode paths:**
- What's not tested: Concurrent `/api/state` kickoff race; child process with oversized stderr (deadlock path); mid-write crash / locked-store `OSError` during sync-back; OneDrive-style sharing violations on Windows.
- Files: `partsmatcher/app/server.py`, `partsmatcher/app/runner.py`, `partsmatcher/chat.py`
- Risk: Rare hangs and partial-write data corruption on the primary user's actual platform.
- Priority: Medium (low likelihood, high annoyance; the sync-back corruption path touches real user data).

**MCP server against a real client:**
- What's not tested: `partsmatcher mcp` over a real stdio transport with a real Claude Code client (handshake quirks, encoding on Windows consoles — `cli.py:_run_mcp` reconfigures stdio to UTF-8, untested live in CI).
- Files: `partsmatcher/mcp.py`, `tests/test_mcp.py` (in-process fakes)
- Risk: Registration works but tool calls fail in the field.
- Priority: Low-Medium; it was proven live once (2026-08-23, inside HEPH Studio) but has no repeatable check.

---

*Concerns audit: 2026-08-25*
