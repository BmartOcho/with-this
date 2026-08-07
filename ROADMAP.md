# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.6.x)

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

- **Full local app (decision — Ben, 2026-08-07):** the UI direction is a
  full local application, not a read-only report export. Ben's framing:
  the app is "how the chat with Claude feature can actually work" as a
  product surface — chat embedded in the app instead of a bare terminal,
  with the existing workspace mechanics underneath (generated CLAUDE.md
  context, sync-back, alias logging, session records / `recover`).
  Questions for the session that builds it, to settle with Ben BEFORE
  code: (1) how the app drives the local Claude Code — terminal handoff
  as today, or headless/programmatic (`claude -p`, Agent SDK) — and
  (2) whether the zero-dependency rule stays engine-only (stdlib
  `http.server` + static page) or relaxes at the UI boundary. Seams
  already in place: the importable matcher, `chat.py`'s workspace prep
  and session records, and schemas that have held stable across three
  feature waves.
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

- `main` = v0.6.1 (matcher → chat mode → conversational intake → photo
  intake → vocabulary alignment/reconcile → recover + mid-session matcher
  command → CI → project-database intake → kickoff greeting polish).
- 108 stdlib `unittest` tests; the chat tests inject fakes, so the suite
  never needs Claude installed. CI: GitHub Actions runs the suite plus a
  sample-data smoke run on every PR and push to main (Python 3.9 + 3.13).
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json` (58 part types / 544 parts, two entries with photo
  provenance), `my_projects.json` (11 projects, all BUILD NOW), their
  `.bak` files, and `my_inventory.aliases.jsonl` (67 records).
