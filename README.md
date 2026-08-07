# PartsMatcher

A small, zero-dependency Python CLI that matches the parts you own against a
database of projects and answers the workbench question: **what can I build
right now, and what am I one or two parts away from?** A chat mode layers
your locally installed Claude Code on top for improvised project ideas —
no API key involved.

One inventory JSON is the shared source of truth for both modes:

- `partsmatcher match` — fast deterministic report, fully offline
- `partsmatcher chat` — hands the same inventory to your local `claude`

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
   report, and workbench-assistant guidance — plus copies of `inventory.json`
   and `projects.json`.
3. `claude` is spawned in that workspace with your real terminal attached.
   Claude Code reads `CLAUDE.md` at session start, so the chat opens already
   knowing every part you own, quantities included.

Then just talk: ask for project ideas beyond the database, pin-by-pin wiring
explanations, or a substitute when you discover a part is missing — Claude
adapts using only the parts on hand and flags anything you'd have to buy.

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
  --workdir DIR    session workspace (default: fresh temp dir)
  --prompt TEXT    opening prompt for the Claude session
  --claude-bin P   Claude Code binary to launch (default: claude)
  --               everything after this is passed to claude verbatim

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

## Feeding inventory from a vision module (future)

Photo-based part identification is out of scope for now, but the inventory
schema is designed to be its contract. A future scanner just emits the same
JSON — no matcher changes needed:

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
no further changes.

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
