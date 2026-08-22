# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.7.x)

- **Local app v1 (v0.7.0):** `partsmatcher app` — the chat session as a
  browser page. Ben ratified both architecture recommendations
  (docs/APP_ARCHITECTURE.md, merged 2026-08-07): headless per-turn
  `claude -p --resume` with stream-json (1B), and a zero-dependency
  stdlib `http.server` + embedded page + streamed turns (2A) — the
  zero-dependency rule holds project-wide. Sync fires on the page's
  End-session button and on clean Ctrl-C; headless permissions come from
  a generated workspace allowlist (`.claude/settings.local.json`);
  `recover` covers unclean exits unchanged. The `chat` and `app`
  commands share one input-loading path in the CLI.
- **Live-fire validated on Ben's Mac (2026-08-08), same day it merged:**
  a real session did plain-language intake (NeoPixel strip ×1 added, 10k
  resistor merged 20 → 22), Claude re-ran the matcher itself through the
  generated allowlist (the biggest headless unknown — the `Bash` pattern
  held), the sidebar refreshed live to 59 types / 547 parts, sync landed
  in the real files (aliases 67 → 69), and a post-sync `recover` was
  correctly idempotent ("already in sync", nothing re-appended).
- **Authoring test: run and passed (2026-08-07).** One session built
  `my_projects.json` from nothing: 8 sample projects adapted with honest
  substitutions (UNO + Type-B throughout; DHT11-for-BME280 with serial
  logging replacing the missing microSD), 2 honestly skipped with
  reasons, 3 new projects drafted from the inventory. Exit sync created
  the file (`0 → 11 projects; new file`), logged 3 substitution alias
  records, and the on-disk run produced the first honest
  `BUILD NOW (11)`. The mid-session matcher command was exercised live,
  and the session hand-computed what the matcher deliberately doesn't:
  concurrent-build capacity (ceiling of 2 — boards, cables, and
  breadboards run out before components).
- **v0.6.1 polishes what the test surfaced:** a default kickoff greeting
  (a plain session used to open as a blank terminal — now it introduces
  what it knows unless the user passes `--prompt`), a pointer to the
  bundled sample database in personal-DB session context (the user had
  to hand-paste the path to adapt samples), and narrow-terminal output
  guidance (wide tables wrapped into fragments mid-session).

## Next

- **App v1 hardening, remainder — mostly closed (2026-08-08):** the
  hardening pass found and fixed a real kickoff bug: the page's startup
  double-fetched `/api/state`, and the first fetch consumed the one-shot
  kickoff before the second looked for it — so the default greeting
  never actually fired in the app (a page-contract test now pins the
  single-fetch pattern). Tab-reload continuity rides the same mechanism
  and is covered server-side (kickoff handed out exactly once;
  `--resume` state lives in the server process, untouched by reload).
  The double-send 409 guard and kill-then-`recover` with UNsynced
  changes through an app-created workspace both have tests now. The
  sidebar renderer was hardened (empty groups no longer emit an empty
  `<ul>`, empty suffix spans skipped, stale `msg meta` class reset) —
  code audit found no path that emits an empty bullet, so Ben should
  still eyeball "ALMOST THERE (0)" on the next real run.
- **Workspace accumulation closed (v0.7.1, 2026-08-16):** `recover
  --list` shows every leftover workspace, its age, and what each still
  owes ("inventory edits not yet written to …", "1 naming-alias
  record(s) not yet appended to …"), and `recover --clean` deletes the
  disposable ones. Disposable is decided by the same already-in-sync
  tests `recover` itself runs, factored out into `inspect_workspace` so
  the two can't drift — a workspace reported synced is one `recover`
  would find nothing to do for. Anything still holding changes is kept
  and reported, including sample sessions where the workspace is the
  only copy and corrupt session records; `--force` overrides. Verified
  end to end: list → clean (removes 1 of 2) → recover the kept one →
  clean again removes it.
- **Still open:** Ben's per-turn latency verdict — the doc's 1C option
  (one long-lived stream-json process) is the planned upgrade path if
  spawning grates. That's the last open item on app v1.
  **A proposal to close it by declining to choose is on the table**
  (docs/MOBILE.md, 2026-08-21, unratified): void on the mobile path
  (Anthropic's client owns the session loop, so there is no spawn to
  optimize), 1B frozen on the desktop path. Unmeasured either way —
  `self.turns` is incremented at `runner.py:107` and never read, and
  `--resume` rehydrates the whole transcript per turn, so cost grows with
  conversation length.
- **Mobile-first proposal (docs/MOBILE.md, 2026-08-21, unratified):**
  Claude Code cannot run on a phone (native-binary-only since ~v2.1.113),
  and a third-party app that signs into a Claude subscription is
  prohibited — but what PartsMatcher already does is explicitly permitted,
  and Anthropic's Remote Control already is the phone-drives-my-Mac
  feature. Proposal: PartsMatcher stops being the harness and becomes a
  git repo with a `.claude/skills/` protocol the Claude app reads.
  Hand-build kit in docs/bench-repo/.
- **Photo test passed (Ben, 2026-08-22):** a cloud session accepts a
  camera-roll photo attached from the phone, so the laptop-off path is
  real. Follow-up verification also found the write-back wrinkle — a cloud
  session defaults to an auto-generated `claude/*` branch with no PR, and
  merging isn't something the Claude mobile app does, so SKILL.md now
  instructs a direct push to `main` (permitted by auto mode; the
  ref-advancing push itself is still untested). And skill `allowed-tools:`
  frontmatter, not `settings.json`, is what reliably pre-authorizes the
  matcher — repo `permissions.allow` is gated on workspace trust, which a
  freshly cloned cloud repo may not have. Next: the bench-repo evening.
- **Standalone batch scanner** — unchanged in scope (photos in,
  inventory JSON out, no conversation; the inventory schema is its
  contract and `*.aliases.jsonl` supplies the naming vocabulary, 67
  records). Its detection-review screen becomes an app view once the
  app exists.

## Later

- Ideas parked: richer kit/assortment modeling, substitution modeling
  (a UNO standing in for a Nano, passive buzzer for piezo),
  concurrent-build planning (which combination of projects can run at
  once — sessions currently hand-compute it), shopping-list export for a
  chosen project, alias-frequency-informed normalization,
  specificity-preserving renames (reconcile currently trades detail for
  match-ability: "Breadboard (830 tie-points)" → "Breadboard").

## State notes (2026-08-16)

- `main` = v0.7.1 (matcher → chat mode → conversational intake → photo
  intake → vocabulary alignment/reconcile → recover + mid-session matcher
  command → CI → project-database intake → kickoff greeting polish →
  local app → workspace list/clean).
- 168 stdlib `unittest` tests; the chat and app tests inject fakes, so the suite
  never needs Claude installed. CI: GitHub Actions runs the suite plus a
  sample-data smoke run on every PR and push to main (Python 3.9 + 3.13).
- **User-side data was lost (noticed 2026-08-22).** This section previously
  recorded `my_inventory.json` at 59 part types / 547 parts,
  `my_projects.json` at 11 projects, and `my_inventory.aliases.jsonl` at 69
  alias records, all living on Ben's machine outside the repo. A search of
  that machine found none of them — no `my_*` files, no `*.aliases.jsonl`,
  and no leftover chat workspaces holding a copy. They are gone, and the
  69-record alias dataset went with them.
  The lesson, recorded because it drives a roadmap item: user data that
  lives only in a temp-directory workspace and one untracked file in a home
  directory has no backup story at all. `partsmatcher init-repo` — putting
  the inventory in a git repo of its own — is now the answer to that, not
  just a convenience for the mobile path.
