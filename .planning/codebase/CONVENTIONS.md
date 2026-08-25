# Coding Conventions

**Analysis Date:** 2026-08-25

## Naming Patterns

**Files:**
- Lowercase, single-word module names: `partsmatcher/matcher.py`, `partsmatcher/chat.py`, `partsmatcher/cli.py`, `partsmatcher/mcp.py`
- Subpackage for the local web app: `partsmatcher/app/` with role-named modules (`server.py`, `runner.py`, `page.py`)
- Test files mirror modules 1:1: `tests/test_matcher.py`, `tests/test_chat.py`, `tests/test_cli.py`, `tests/test_app.py`, `tests/test_mcp.py`

**Functions:**
- `snake_case` throughout: `parse_inventory`, `build_context_markdown`, `normalize_name`, `write_permission_settings`
- Private module helpers get a leading underscore: `_entry_list`, `_parse_part`, `_gap_order`, `_render_report_section`, `_add_input_arguments` (see `partsmatcher/matcher.py`, `partsmatcher/cli.py`)
- Verb-first names for actions (`parse_*`, `build_*`, `run_*`, `find_*`, `make_*`, `write_*`)

**Variables:**
- `snake_case` locals; loop indices reported 1-based for humans: `for index, entry in enumerate(entries, start=1)` (`partsmatcher/matcher.py:125`)
- Module-level constants in `UPPER_SNAKE_CASE`: `DEFAULT_ALMOST_THRESHOLD` (`partsmatcher/matcher.py:20`), `CONTEXT_MARKER`, `ALIAS_FILENAME`, `WORKSPACE_PREFIX`, `IMAGE_SUFFIXES`, `DEFAULT_KICKOFF_PROMPT` (`partsmatcher/chat.py:36-63`), `SAMPLE_DIR`/`SAMPLE_INVENTORY`/`SAMPLE_PROJECTS` (`partsmatcher/cli.py:35-37`)
- Multi-line user-facing text stored as module-level string constants (e.g. `CLAUDE_NOT_FOUND_HINT` in `partsmatcher/chat.py:67`)

**Types:**
- `PascalCase` classes, mostly `@dataclass`: `Inventory`, `Project`, `MissingPart` (frozen), `ProjectMatch`, `MatchReport` (`partsmatcher/matcher.py`); `ClaudeTurnRunner` (`partsmatcher/app/runner.py`); `MCPServer` (`partsmatcher/mcp.py`); `AppState` (`partsmatcher/app/server.py`)
- One custom exception, subclassing a stdlib type: `class PartsMatcherError(ValueError)` (`partsmatcher/matcher.py:23`)

## Code Style

**Formatting:**
- No formatter config present (no black/ruff/flake8/isort files). Style is hand-kept, Black-compatible in practice: 4-space indent, double quotes, trailing commas in multi-line calls, ~88-column lines
- Long strings are broken with implicit adjacent-string concatenation inside parentheses

**Linting:**
- No linter configured. CI (`.github/workflows/tests.yml`) runs only `python -m unittest` plus a CLI smoke run — match existing style by eye

**Type hints:**
- Every public function is annotated. `from __future__ import annotations` at the top of each module (`partsmatcher/matcher.py:15`, `partsmatcher/chat.py:15`, `partsmatcher/cli.py:15`)
- Python 3.9 compatibility is preserved by quoting generic builtins in annotations: `"dict[str, int]"`, `"list[Project]"`, `"tuple[str, int]"`, `"Optional[str]"` — follow this pattern; do not use bare `dict[str, int]` in contexts evaluated at runtime, and do not raise the floor above `requires-python = ">=3.9"` (`pyproject.toml:10`)
- `typing` imports kept minimal: `Iterable`, `Callable`, `Optional`, `Sequence`

## Import Organization

**Order:**
1. `from __future__ import annotations`
2. Stdlib imports, alphabetized, one per line (`import json`, `import shutil`, ...)
3. `from x import a, b` stdlib forms (`dataclasses`, `pathlib`, `typing`)
4. Relative package imports: `from .matcher import (...)` with parenthesized, alphabetized names (`partsmatcher/chat.py:28-34`, `partsmatcher/cli.py:23-33`)

**Path Aliases:**
- None. Intra-package imports are relative (`from . import __version__`, `from .matcher import ...`); tests import absolutely (`from partsmatcher import chat, cli, match, ...`)

**Hard rule — zero runtime dependencies:**
- The package is stdlib-only by design (`CONTRIBUTING.md`): "A PR that adds a runtime dependency needs to argue for it first, in an issue." Never import third-party packages in `partsmatcher/`

## Error Handling

**Patterns:**
- Schema/validation failures raise `PartsMatcherError` (a `ValueError`) with precise, located messages that name the offending entry: `f"{where} ({display!r}): 'quantity' must be an integer"` (`partsmatcher/matcher.py:64`). Build the `where` string incrementally (`project #2 ('LED Dice'), part #3`)
- Programming-contract violations raise plain `ValueError` (`match()` on negative threshold, `partsmatcher/matcher.py:284`)
- The CLI catches `PartsMatcherError`/`OSError`/JSON errors at the top of each subcommand handler, prints `partsmatcher: error: {exc}` to stderr, and returns exit code `2` (`partsmatcher/cli.py:436-437, 539-540, 556-557, 592-593`)
- `main()` returns an int exit code; `sys.exit(main())` only at the entry point (`partsmatcher/cli.py:628`). Conventional codes: `0` success, `2` usage/input error, `130` for `KeyboardInterrupt`, child exit codes propagated as-is (see `chat.run_chat`)
- Long-running loops convert failures into data, not exceptions: `ClaudeTurnRunner.run_turn` yields `{"type": "error", "message": ...}` events instead of raising (`partsmatcher/app/runner.py`); garbage stream-json lines are skipped silently
- User-facing error text is didactic — the missing-`claude` message explains what chat does, how to install, and that `match` still works offline (`partsmatcher/chat.py:67-80`)

## Logging

**Framework:** none — `print()` only

- Status/progress messages to stdout; errors and "using bundled sample" notices to stderr (`print(..., file=sys.stderr)`)
- No `logging` module usage anywhere; keep it that way unless a phase explicitly introduces it

## Comments

**When to Comment:**
- Comments explain *why*, not *what*, and often record a design decision or the bug being prevented: the `distinct_parts` counting rationale (`partsmatcher/matcher.py:110-112`), the `_gap_order` tie-break rule (`partsmatcher/matcher.py:273`), the CSRF rationale in tests (`tests/test_app.py:265-267`)
- Tests carry the same style: short comments state the invariant being pinned (`tests/test_matcher.py:50-51, 65-66`)

**Docstrings:**
- Every module opens with a substantial docstring stating its purpose and design constraints (`partsmatcher/matcher.py:1-13`, `partsmatcher/chat.py:1-13`, `partsmatcher/cli.py:1-13`, `tests/test_app.py:1-5`)
- Public functions and dataclasses get one-line-or-more plain-prose docstrings; no Sphinx/Google field markup. Double backticks for identifiers inside docstrings (``parse_inventory``)
- Trivial property accessors may go undocumented

## Function Design

**Size:** small, single-purpose functions; validation helpers factored out (`_entry_list`, `_parse_part`) and reused across inventory and project parsing

**Parameters:**
- Keyword-only arguments (after `*`) for context/config parameters: `_parse_part(entry, *, where, min_quantity)` (`partsmatcher/matcher.py:47`)
- **Dependency injection via callable parameters with stdlib defaults** — the house pattern that makes everything testable without patching: `find_claude(binary="claude", which=shutil.which)` (`partsmatcher/chat.py:83`), `run_chat(..., which=..., launch=...)`, `ClaudeTurnRunner(..., popen=...)`. New code that shells out or touches the environment must accept the effectful callable as a parameter

**Return Values:**
- Parsers return rich dataclasses, never raw dicts; serialization is an explicit method (`ProjectMatch.to_dict`, `partsmatcher/matcher.py:226`)
- Command handlers return int exit codes
- Computed values exposed as `@property` on dataclasses (`buildable`, `total_missing`, `missing_kinds`)

## Module Design

**Exports:**
- `partsmatcher/__init__.py` re-exports the matcher's public API with an explicit `__all__` and holds `__version__ = "0.7.1"` (keep in sync with `pyproject.toml`)
- Core rule from `partsmatcher/matcher.py` docstring: **no I/O in the matcher** — parsers accept already-decoded JSON; all file/subprocess/network work lives in `cli.py`, `chat.py`, `mcp.py`, `app/`
- Unknown JSON fields are tolerated on input (forward compatibility for richer producers, `partsmatcher/matcher.py:50-52`); required fields are validated strictly

**Barrel Files:** only the package `__init__.py`; subpackage `partsmatcher/app/__init__.py` also contains real code (`write_permission_settings`, `run_app`)

## Process Conventions

- **Gates:** behavior changes ship with `GATES.md`-style evidence — a claim, a CHECK command, an EXPECT, and the recorded EVIDENCE (see `GATES.md`, `CONTRIBUTING.md`). Matcher behavior changes must show CLI output is byte-identical or explain the move
- **Never commit inventory data:** `my_*.json`, `*.aliases.jsonl`, `*.bak`, `photos/`, `data/` are gitignored; only `partsmatcher/samples/*.json` ships

---

*Convention analysis: 2026-08-25*
