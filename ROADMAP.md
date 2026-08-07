# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.4.x)

- **Real-world photo test (in flight, Ben's Mac, `~/with-this`):** one
  session doing reconcile + the first photo intake —
  `python -m partsmatcher chat my_inventory.json --photo <bench-photo>`,
  opening with "Reconcile my inventory with the project database, then
  identify the photo." Collect what the photo pass identified vs. got
  wrong, the corrections (highest-value alias records), the exit
  sync-summary lines, and the new "photo"/"corrected" alias records; then
  re-run `python -m partsmatcher match my_inventory.json` — BUILD NOW
  should finally light up after reconciliation.
- Fix whatever that test surfaces. Likely levers: the photo-intake and
  intake protocol text in `chat.py` (`build_context_markdown`), confidence
  guidance, kit handling.

## Next

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

- `main` = v0.4.1 (PRs #1–#4 merged: matcher → chat mode → conversational
  intake → photo intake → vocabulary alignment / kit expansion /
  reconcile guidance).
- 72 stdlib `unittest` tests; the chat tests inject fakes, so the suite
  never needs Claude installed.
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json` (56 part types / 542 parts), its `.bak`, and
  `my_inventory.aliases.jsonl` (55 records).
