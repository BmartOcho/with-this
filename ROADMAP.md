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

- **App v1 hardening from Ben's first real run:** live-fire the headless
  turn loop against Ben's actual `claude` install (stream-json shapes,
  the allowlist actually covering what sessions do, per-turn latency
  feel). The doc's 1C option (one long-lived stream-json process) is the
  planned upgrade path if per-turn spawn grates — the runner interface
  was shaped so it can slot in behind the server unchanged.
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

## State notes (2026-08-07)

- `main` = v0.7.0 (matcher → chat mode → conversational intake → photo
  intake → vocabulary alignment/reconcile → recover + mid-session matcher
  command → CI → project-database intake → kickoff greeting polish →
  local app).
- 127 stdlib `unittest` tests; the chat and app tests inject fakes, so the suite
  never needs Claude installed. CI: GitHub Actions runs the suite plus a
  sample-data smoke run on every PR and push to main (Python 3.9 + 3.13).
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json` (58 part types / 544 parts, two entries with photo
  provenance), `my_projects.json` (11 projects, all BUILD NOW), their
  `.bak` files, and `my_inventory.aliases.jsonl` (67 records).
