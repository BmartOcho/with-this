# PartsMatcher — Roadmap

**Headline goal:** know what you can build from the parts you actually own —
a deterministic matcher plus conversational/photo intake through your local
Claude Code, quietly accumulating the naming-alias dataset a standalone
vision scanner will eventually consume.

## Now (v0.5.x)

- **Real-world photo test: run and passed (2026-08-07).** Vision v1
  identified an LM2596 buck module (confidence 0.95) and an 18650 cell
  (0.85) from one bench photo; reconcile applied seven renames; all nine
  alias records landed exactly per protocol (`corrected` with the old
  inventory name as raw, `photo` with visual description + filename +
  confidence). The match report went from one ALMOST THERE to seven —
  six of them short exactly "USB cable".
- **v0.5.0 ships the test's findings:** `partsmatcher recover` — the
  closed-terminal incident stranded the whole session in its temp
  workspace, so every workspace now carries a `.partsmatcher-session.json`
  record and the end-of-session sync can be re-run afterward,
  idempotently — plus a runnable matcher command embedded in the generated
  CLAUDE.md (the session couldn't invoke the matcher from the bare temp
  workspace and had to hand-simulate the post-rename report).
- **Open on the bench:** the "USB cable" call — six Nano projects need a
  Mini-B cable; renaming Ben's USB Type-B cables would make the report
  lie. Resolved by a board-accurate `my_projects.json`, not by a rename.

## Next

- Replace the sample project database with a personal `my_projects.json` —
  board-accurate cable/buzzer naming dissolves the coarse-vocabulary
  tension the test surfaced ("USB cable", "Piezo buzzer"). Repo side:
  teach chat mode to author and sync back a project database the same way
  it does the inventory.

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

- `main` = v0.5.0 (matcher → chat mode → conversational intake → photo
  intake → vocabulary alignment/reconcile → recover + mid-session matcher
  command).
- 90 stdlib `unittest` tests; the chat tests inject fakes, so the suite
  never needs Claude installed. CI: GitHub Actions runs the suite plus a
  sample-data smoke run on every PR and push to main (Python 3.9 + 3.13).
- User-side data lives on Ben's machine, not in this repo:
  `my_inventory.json` (58 part types / 544 parts, two entries with photo
  provenance), its `.bak`, and `my_inventory.aliases.jsonl` (64 records).
