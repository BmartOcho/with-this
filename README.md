# PartsMatcher

A small, zero-dependency Python CLI that matches the parts you own against a
database of projects and answers the workbench question: **what can I build
right now, and what am I one or two parts away from?** A chat mode layers
your locally installed Claude Code on top for improvised project ideas —
no API key involved.

One inventory JSON is the shared source of truth for both modes:

- `partsmatcher match` — fast deterministic report, fully offline
- `partsmatcher chat` — hands the same inventory to your local `claude`
- `partsmatcher app` — the same chat session in your browser: embedded chat
  beside a live inventory and match report (still your local `claude`,
  driven headlessly one turn at a time; still zero dependencies)

The matcher reads two JSON files — your parts inventory and a project
database — and sorts every project into three groups:

1. **BUILD NOW** — every required part is covered by your inventory.
2. **ALMOST THERE** — you're short at most 2 parts total (configurable), with
   the exact shopping list per project. Sorted by fewest missing parts first.
3. **NOT YET** — everything else.

Quantities count: if a project needs 3 LEDs and you own 2, that's 1 missing
part, not zero and not "missing LEDs."

## Quick start

Runs out of the box on the bundled sample data (Python 3.9+, no dependencies):

```console
$ python -m partsmatcher
```

```text
Matched 10 projects against 15 part types (93 parts on hand).

BUILD NOW (3)
  ✔ Blink Badge — The hello-world wearable: one red LED pulsing on a Nano...
  ✔ Reaction Timer — Two players, two buttons, one LED — first press after the light wins.
  ✔ Sunset Night-Light — A photoresistor watches the room and fades the LED up as it gets dark.

ALMOST THERE (4) — short at most 2 parts, fewest missing first
  ≈ LED Dice — short 1 part
      Mash the button to roll seven LEDs arranged like dice pips.
      needs Red LED: have 6 of 7 (short 1)
  ≈ Servo Radar Sweep — short 1 part
      ...
      needs 16x2 I2C LCD: have 0 of 1 (short 1)
  ...

NOT YET (3)
  ✘ Desk Weather Station — short 3 parts across 3 part types
  ...
```

With your own files:

```console
$ python -m partsmatcher my_inventory.json my_projects.json
```

Optionally install it as a `partsmatcher` command:

```console
$ pip install -e .
$ partsmatcher --help
```

## Chat mode — project ideas grounded in exactly what you own

```console
$ python -m partsmatcher chat
```

`partsmatcher chat` does **not** call the Anthropic API and needs no API key.
It launches the Claude Code CLI (`claude`) you already have installed and
logged in as an interactive child process, so your existing subscription auth
applies and this tool bills nothing per token.

What happens at startup:

1. The tool verifies `claude` exists on PATH, and exits with an install hint
   if it doesn't (`npm install -g @anthropic-ai/claude-code`).
2. A session workspace is prepared (a fresh temp directory by default) with a
   generated `CLAUDE.md` containing the inventory, the deterministic match
   report, workbench-assistant guidance, and a ready-to-run matcher command
   (so Claude can re-check the report itself as the inventory changes) —
   plus copies of `inventory.json` and `projects.json`.
3. `claude` is spawned in that workspace with your real terminal attached.
   Claude Code reads `CLAUDE.md` at session start, so the chat opens already
   knowing every part you own, quantities included. Without a `--prompt` of
   your own, the session opens by introducing what it knows and what it can
   do (photo sessions open with photo identification instead).

Then just talk: ask for project ideas beyond the database, pin-by-pin wiring
explanations, or a substitute when you discover a part is missing — Claude
adapts using only the parts on hand and flags anything you'd have to buy.

### Conversational inventory intake

Describe parts in plain language and Claude folds them into your inventory:

```text
you> picked up a strip of neopixels and a bag of resistors, and add two more nanos
claude> A couple of questions before I write anything:
        - the resistors — what value, and roughly how many?
        - the NeoPixel strip — how long / how many LEDs?
        ...
        raw phrasing            → normalized entry
        "a strip of neopixels"  → WS2812B LED strip (1 m) ×1
        "a bag of resistors"    → 470 ohm resistor ×25
        "two more nanos"        → Arduino Nano ×2 (merged into existing entry)
        Write these to inventory.json?
```

The generated `CLAUDE.md` instructs Claude to normalize each described part
against the schema (reusing existing canonical names where the part already
exists), ask clarifying questions for anything ambiguous — vague quantities,
missing specs, unclear board identity — confirm the batch, then update
`inventory.json`. "Used up four red LEDs" decrements the same way.

**Vocabulary alignment.** The deterministic matcher matches part names
exactly, so run intake *with* your project database loaded (skip
`--no-projects`) once you have one: the session then prefers the project
database's part names for the same physical part, offers to expand
assortment kits into the specific values projects reference (a
`resistor kit ×1` entry can't satisfy `220 ohm resistor ×7`), and — if you
ask it to "reconcile" — walks the match report's missing parts one by one to
find the ones you actually own under a different name, logging each rename
as a `corrected` alias.

**Naming-alias dataset.** Every normalized entry is also logged as one JSON
line in `aliases.jsonl`, pairing your raw phrasing with the canonical name:

```json
{"raw": "a strip of neopixels", "name": "WS2812B LED strip (1 m)", "quantity": 1, "action": "added"}
```

Corrections and casual references get logged too — this file grows into the
naming dataset a future vision module will use to map detected parts onto
your inventory vocabulary.

**Sync-back.** When the session ends, PartsMatcher validates the edited
`inventory.json` and writes it back to your inventory file (previous version
saved alongside as `<name>.bak`), does the same for `projects.json` when
your own project database is loaded, and appends the session's new alias
records to `<stem>.aliases.jsonl` next to it. Invalid edits never overwrite
your file — you get a warning and the workspace path instead. When you're on the
bundled sample data nothing is overwritten either; the summary tells you
where the updated files live. `--no-sync` disables write-back entirely.

**Recovery.** If a session dies before that exit sync can run — a closed
terminal window, a crash — nothing is lost. Every session records what the
sync needs inside its workspace, so afterward:

```console
$ python -m partsmatcher recover
```

re-runs the same validate-and-sync against the newest recoverable workspace
(pass a workspace path to pick a specific one). It's safe to re-run:
files already in sync are detected and left alone.

Workspaces accumulate in the temp directory — one per session, each holding a
full copy of the inventory. To see what's piled up and what each one still
owes your files:

```console
$ python -m partsmatcher recover --list
2 recoverable chat workspace(s) under /tmp:
  /tmp/partsmatcher-chat-9k2f1a  (just now) — unsynced
      inventory edits not yet written to /Users/you/my_inventory.json
      1 naming-alias record(s) not yet appended to /Users/you/my_inventory.aliases.jsonl
  /tmp/partsmatcher-chat-3d81cc  (4d ago) — synced

`partsmatcher recover --clean` would remove 1 of 2 (nothing left to sync).
```

(The temp directory is wherever Python puts it: `/tmp` on most Linux,
but `/var/folders/.../T/` on macOS — so a `/tmp/partsmatcher-chat-*` glob
finds nothing there. `recover --list` prints the real paths; so does the
`Session workspace:` line at startup.)

`recover --clean` deletes the disposable ones. A workspace whose changes
haven't reached your files is kept and reported — including sessions on the
bundled sample, where the workspace holds the only copy — so cleaning can't
throw away work you haven't recovered yet. `--force` overrides that and
deletes everything.

### Photo intake — vision v1

Photos are another intake source, flowing through the same confirmation
loop:

```console
$ python -m partsmatcher chat my_inventory.json --photo bench.jpg --photo drawer.png
```

Staged photos are copied into the session workspace under `photos/`, and the
session opens by identifying them (Claude Code reads images natively — no
extra tooling). Each detected part comes back as a **draft** entry with the
identification confidence and reasoning:

```text
photos/bench.jpg → 470 ohm resistor ×25 (confidence 0.7 — blue axial body, bands unreadable)
```

Uncertain identifications go through the usual clarifying questions ("about
20 axial resistors, but I can't read the bands — what value?"), and nothing
is written without your confirmation. Confirmed photo entries land in
`inventory.json` with provenance the schema already tolerates —
`"source": "photo"` and `"confidence"` — and their alias records use the
visual description as the raw phrasing:

```json
{"raw": "blue axial resistor, 4-band", "name": "470 ohm resistor", "quantity": 25, "action": "photo", "photo": "bench.jpg", "confidence": 0.7}
```

You can also hand Claude an image path mid-session (or drop a file into the
workspace `photos/` folder) — same flow. Supported types: `.png`, `.jpg`,
`.jpeg`, `.gif`, `.webp`.

### A personal project database

The bundled sample projects are generic — written around parts you may not
own (a "USB cable" that really means a Nano's Mini-B). The honest fix is
your own database, and chat mode can author it:

```console
$ python -m partsmatcher chat my_inventory.json my_projects.json
```

If `my_projects.json` doesn't exist yet, the session starts from an empty
database and the file is created on first sync. Describe what you want to
build ("add a project: plant waterer on the Uno with the pump and a soil
sensor") and Claude drafts the complete parts list — quantities and hookup
consumables included — using your inventory's exact part names for parts
you own, which is what makes the resulting BUILD NOW rows honest: the
matcher matches names exactly, so a personal project written around your
real "USB Type-B cable" matches it, where the sample's generic "USB cable"
never will. Ambiguities go through the usual clarifying questions, the
drafted project is confirmed before writing, and adapting a sample project
to your parts is a normal move ("Blink Badge (UNO)" with substitutions
noted in the description).

Project edits sync back like inventory edits — validated first, previous
version saved as `<name>.bak`, created fresh on first sync, covered by
`recover`. Edits made while the bundled sample is loaded stay in the
workspace instead; the sample is never modified.

```console
$ python -m partsmatcher chat my_inventory.json my_projects.json
$ python -m partsmatcher chat --no-projects            # inventory only
$ python -m partsmatcher chat --prompt "What could I build in an hour?"
$ python -m partsmatcher chat --workdir ~/bench/chat   # persistent workspace
$ python -m partsmatcher chat -- --continue            # extra args go to claude
```

Safety note: a `CLAUDE.md` that PartsMatcher didn't generate is never
overwritten — pick a different `--workdir` instead.

The deterministic matcher never requires Claude to be installed; `match`
stays fully offline.

## The local app

`partsmatcher app` serves the same session as a browser page instead of
handing over the terminal:

```console
$ python -m partsmatcher app my_inventory.json my_projects.json
```

The page pairs an embedded chat with a live sidebar — your inventory and
the deterministic match report, re-read from the workspace after every
turn, so intake and reconciliation update them as you talk. Under the
hood each message runs your local `claude` headlessly for one turn
(`claude -p --resume` — same login, no API key, no new dependencies:
the server is stdlib `http.server`, the page a single embedded file).

The workspace mechanics are chat's, unchanged: generated `CLAUDE.md`
context, alias logging, validated sync-back with `.bak` backups, and
`recover` if the app dies uncleanly. Because headless turns can't show
interactive permission prompts, the workspace pre-authorizes exactly what
sessions do anyway (editing the workspace files, re-running the matcher)
via a generated `.claude/settings.local.json`.

Sync runs when you click **End session & sync** (which also stops the
app) or on Ctrl-C in the terminal. Flags mirror `chat` (`--photo`,
`--prompt`, `--workdir`, `--no-projects`, `--no-sync`), plus `--port N`
and `--no-browser`.

## Input formats

### Inventory — the parts you own

A list of parts, either bare or wrapped in a `parts` key:

```json
{
  "parts": [
    { "name": "Red LED", "quantity": 6 },
    { "name": "220 ohm resistor", "quantity": 20 }
  ]
}
```

- `name` (required): matched case-insensitively, with surrounding/repeated
  whitespace ignored — `"red  led"` and `"Red LED"` are the same part.
- `quantity` (optional, default `1`): a non-negative integer.
- Repeated names are **merged by summing** quantities.
- Unknown fields (`source`, `confidence`, `bin`, ...) are tolerated and
  ignored, so richer producers can annotate parts freely.

### Project database

A list of projects (bare, or wrapped in a `projects` key). Each project has a
`name`, an optional `description`, and a non-empty `parts` list
(`required_parts` works as an alias) with the same part shape as the
inventory (`quantity` defaults to 1, must be at least 1):

```json
{
  "projects": [
    {
      "name": "LED Dice",
      "description": "Mash the button to roll seven LEDs arranged like dice pips.",
      "parts": [
        { "name": "Red LED", "quantity": 7 },
        { "name": "Tactile pushbutton", "quantity": 1 }
      ]
    }
  ]
}
```

The bundled samples live at [`partsmatcher/samples/`](partsmatcher/samples/)
— copy them as a starting point for your own files.

## How the matching works

Each project is a multiset-coverage check (set cover with quantities) against
your inventory: for every required part, the deficit is
`max(0, required − owned)`.

- **BUILD NOW**: every deficit is 0.
- **ALMOST THERE**: total deficit (summed in units across part types) is
  between 1 and `--almost N` (default 2). Needing 3 LEDs while owning 2
  contributes 1; needing a yellow and a green LED you don't own contributes 2.
- **NOT YET**: total deficit exceeds the threshold.

The ALMOST THERE and NOT YET groups are sorted by fewest missing units first,
breaking ties by fewer distinct part types to buy, then by name. BUILD NOW is
sorted by name.

Projects are evaluated **independently** — each one is checked as if it alone
gets your whole inventory. Two projects that both need your only servo both
count as buildable; the tool doesn't (yet) compute which *combination* of
projects you could build simultaneously.

## CLI reference

```text
python -m partsmatcher match [INVENTORY_JSON] [PROJECTS_JSON] [options]

  --almost N     max total missing parts for the ALMOST THERE group (default: 2)
  --json         emit the report as JSON on stdout (notes go to stderr)
  -v, --verbose  also list exactly what each NOT YET project is missing
  --no-color     disable ANSI colors (NO_COLOR env var works too)

python -m partsmatcher chat [INVENTORY_JSON] [PROJECTS_JSON] [options] [-- CLAUDE_ARGS...]

  --almost N       threshold used for the match report handed to Claude
  --no-projects    give Claude only the inventory, no project database
  --photo IMAGE    stage a photo of parts for identification (repeatable)
  --workdir DIR    session workspace (default: fresh temp dir)
  --prompt TEXT    opening prompt for the Claude session
  --claude-bin P   Claude Code binary to launch (default: claude)
  --no-sync        keep inventory edits and alias records in the workspace
  --               everything after this is passed to claude verbatim

python -m partsmatcher recover [WORKSPACE_DIR]

  re-run the end-of-session sync for a chat session that ended without a
  clean exit — closed terminal, crash — validating and backing up exactly
  like the normal exit path (default: the newest recoverable workspace)

  --list           show every leftover workspace, its age, and what it
                   still owes your files; writes nothing
  --clean          delete leftover workspaces that are already synced back;
                   ones still holding changes are kept and reported
  --force          with --clean, delete those too

  --version        show version
```

Running without a subcommand behaves as `match`, so
`python -m partsmatcher inv.json proj.json --json` keeps working.

Exit codes: `0` on success, `2` on bad input (unreadable file, invalid JSON,
schema errors — reported with the file, project, and part that caused them)
or when `claude` isn't installed; chat otherwise returns claude's own exit
code.

### JSON output

`--json` emits a machine-readable report, handy for piping into other tools:

```json
{
  "summary": {
    "projects": 10,
    "build_now": 3,
    "almost": 4,
    "not_yet": 3,
    "almost_threshold": 2,
    "inventory_part_types": 15,
    "inventory_total_parts": 93
  },
  "build_now": [{ "name": "Blink Badge", "description": "...", "total_missing": 0, "missing": [] }],
  "almost": [
    {
      "name": "LED Dice",
      "description": "...",
      "total_missing": 1,
      "missing": [{ "name": "Red LED", "required": 7, "have": 6, "missing": 1 }]
    }
  ],
  "not_yet": ["..."]
}
```

## The vision path

Vision v1 ships as photo intake inside chat mode (above): identification
runs through your Claude Code session, drafts flow through the confirmation
loop, and confirmed entries carry `source`/`confidence` provenance. A future
*standalone* scanner (batch photo → inventory, no conversation) stays easy
because the inventory schema was designed as its contract — it just emits
the same JSON, and no matcher changes are needed:

- It may write **one entry per detection** with `quantity: 1`; duplicates are
  merged by summing, so aggregation comes for free.
- It may attach extra fields per part (`source`, `confidence`, a photo
  reference, a bin location); the matcher ignores what it doesn't know.
- Name normalization absorbs harmless labeling differences in case and
  whitespace.

```json
{
  "parts": [
    { "name": "Red LED", "quantity": 1, "source": "vision", "confidence": 0.93 },
    { "name": "Red LED", "quantity": 1, "source": "vision", "confidence": 0.88 }
  ]
}
```

The core logic is importable independently of the CLI
(`from partsmatcher import parse_inventory, parse_projects, match`), so a
vision pipeline can also call it directly. Chat mode already treats the
inventory file as the shared source of truth — a future vision module that
rewrites `inventory.json` feeds both the matcher and the Claude session with
no further changes. And the `*.aliases.jsonl` dataset that conversational
intake accumulates (raw human phrasing → canonical part name) is exactly the
vocabulary-mapping data that module will need to label what it sees.

## Development

```console
$ python -m unittest        # run the test suite (no Claude required)
$ python -m partsmatcher    # smoke-test against the bundled samples
```

Layout: `partsmatcher/matcher.py` holds the pure matching logic (no I/O),
`partsmatcher/cli.py` the argument parsing and rendering,
`partsmatcher/chat.py` the Claude Code session preparation and launch, and
`partsmatcher/samples/` the bundled demo data pinned by the tests. The chat
tests inject fake `which`/`launch` callables, so the suite runs without
Claude installed.
