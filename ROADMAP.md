# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.6.x)

- **v0.6.0: chat mode authors project databases.**
  `partsmatcher chat my_inventory.json my_projects.json` — a path that
  doesn't exist yet starts an empty database, created on first sync. The
  session protocol drafts projects in the INVENTORY's exact vocabulary
  (the honest resolution of the coarse-vocabulary tension from the photo
  test: a project written around "USB Type-B cable" instead of a generic
  "USB cable"), confirms before writing, syncs edits back with a `.bak`
  backup, and `recover` covers the project database too.
- **Real-world test next (Ben's Mac):** the authoring session — build
  `my_projects.json` conversationally, adapting the sample projects worth
  keeping to the parts on hand (UNO + Type-B where that's the real
  build), then `python -m partsmatcher match my_inventory.json
  my_projects.json` for the first honest BUILD NOW rows. Fix what the
  session surfaces, same as the photo test.
- **Still open on the bench:** a Mini-B cable would flip six sample
  projects instantly; the personal database makes that moot for projects
  authored around the UNO.

## Next

- (Fed by the authoring test — protocol fixes land here first.)

## Later

- **Standalone batch scanner** — photos in, inventory JSON out, no
  conversation. The inventory schema is already its contract (one entry per
  detection, `quantity: 1`, `source`/`confidence` fields, duplicates merge
  by summing) and `*.aliases.jsonl` supplies the naming vocabulary.
- Ideas parked: richer kit/assortment modeling, substitution modeling
  (a UNO standing in for a Nano, passive buzzer for piezo), shopping-list
  export for a chosen project, alias-frequency-informed normalization,
  specificity-preserving renames (reconcile currently trades detail for
  match-ability: "Breadboard (830 tie-points)" → "Breadboard").

## State notes (2026-08-07)

- `main` = v0.6.0 (matcher → chat mode → conversational intake → photo
  intake → vocabulary alignment/reconcile → recover + mid-session matcher
  command → CI → project-database intake).
- 104 stdlib `unittest` tests; the chat tests inject fakes, so the suite
  never needs Claude installed. CI: GitHub Actions runs the suite plus a
  sample-data smoke run on every PR and push to main (Python 3.9 + 3.13).
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json` (58 part types / 544 parts, two entries with photo
  provenance), its `.bak`, and `my_inventory.aliases.jsonl` (64 records).
