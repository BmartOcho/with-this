# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.4.x)

- **PR #4 (open):** intake vocabulary alignment, kit expansion, and the
  "reconcile" flow — born from the first real-world test, where intake run
  with `--no-projects` produced names the project database never uses and
  `BUILD NOW (0)` against 542 real parts. Merge → `git pull` → re-test.
- **Real-world test in flight (Ben's Mac, `~/with-this`):** inventory built
  via conversational intake — 56 part types / 542 parts in
  `my_inventory.json`, 55 records in `my_inventory.aliases.jsonl`. Still to
  do: the reconcile session (fix USB cable / breadboard / resistor-kit
  naming) and the first real photo intake.

## Next

- Run reconcile + photo intake in one session; correct misidentifications
  freely (corrections are the highest-value alias records).
- Replace the sample project database with a personal `my_projects.json`.
- Add CI: a GitHub Actions workflow running `python -m unittest` so PRs get
  a real green check (repo currently has no checks).

## Later

- **Standalone batch scanner** — photos in, inventory JSON out, no
  conversation. The inventory schema is already its contract (one entry per
  detection, `quantity: 1`, `source`/`confidence` fields, duplicates merge
  by summing) and `*.aliases.jsonl` supplies the naming vocabulary.
- Ideas parked: richer kit/assortment modeling, shopping-list export for a
  chosen project, alias-frequency-informed normalization.

## State notes (2026-08-07)

- `main` = v0.4.0 (PRs #1–#3 merged: matcher → chat mode → conversational
  intake → photo intake). PR #4 carries v0.4.1.
- 72 stdlib `unittest` tests; the chat tests inject fakes, so the suite
  never needs Claude installed.
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json`, its `.bak`, and `my_inventory.aliases.jsonl`.
