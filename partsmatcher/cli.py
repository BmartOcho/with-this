"""Command-line interface for PartsMatcher."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .matcher import (
    DEFAULT_ALMOST_THRESHOLD,
    Inventory,
    MatchReport,
    PartsMatcherError,
    ProjectMatch,
    match,
    parse_inventory,
    parse_projects,
)

SAMPLE_DIR = Path(__file__).resolve().parent / "samples"
SAMPLE_INVENTORY = SAMPLE_DIR / "inventory.json"
SAMPLE_PROJECTS = SAMPLE_DIR / "projects.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="partsmatcher",
        description=(
            "Match the parts you own against a project database and see what "
            "you can build now, what you are a couple of parts away from, and "
            "what will have to wait."
        ),
        epilog=(
            "With no file arguments the bundled sample data is used, so "
            "`python -m partsmatcher` runs out of the box."
        ),
    )
    parser.add_argument(
        "inventory",
        nargs="?",
        metavar="INVENTORY_JSON",
        help="parts you own (default: bundled sample inventory)",
    )
    parser.add_argument(
        "projects",
        nargs="?",
        metavar="PROJECTS_JSON",
        help="project database (default: bundled sample projects)",
    )
    parser.add_argument(
        "--almost",
        type=int,
        default=DEFAULT_ALMOST_THRESHOLD,
        metavar="N",
        help=(
            "max total missing parts (in units, summed over part types) for "
            "the ALMOST THERE group (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the report as JSON on stdout",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also list exactly what each NOT YET project is missing",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors (the NO_COLOR env var is honored too)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _load_json(path: Path, what: str) -> object:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise PartsMatcherError(f"could not read {what} file {str(path)!r}: {reason}")
    except json.JSONDecodeError as exc:
        raise PartsMatcherError(f"{what} file {str(path)!r} is not valid JSON: {exc}")


def _want_color(no_color_flag: bool) -> bool:
    if no_color_flag or "NO_COLOR" in os.environ:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _make_painter(enabled: bool):
    def paint(text: str, code: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if enabled else text

    return paint


def _pick_marks(stream) -> "tuple[str, str, str]":
    marks = ("✔", "≈", "✘")  # ✔ ≈ ✘
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "".join(marks).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return ("[OK]", "[~]", "[X]")
    return marks


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _report_to_dict(report: MatchReport, inventory: Inventory) -> dict:
    total = len(report.build_now) + len(report.almost) + len(report.not_yet)
    return {
        "summary": {
            "projects": total,
            "build_now": len(report.build_now),
            "almost": len(report.almost),
            "not_yet": len(report.not_yet),
            "almost_threshold": report.almost_threshold,
            "inventory_part_types": inventory.distinct_parts,
            "inventory_total_parts": inventory.total_units,
        },
        "build_now": [result.to_dict() for result in report.build_now],
        "almost": [result.to_dict() for result in report.almost],
        "not_yet": [result.to_dict() for result in report.not_yet],
    }


def _print_missing_lines(result: ProjectMatch) -> None:
    for part in result.missing:
        print(
            f"      needs {part.name}: have {part.have} of {part.required} "
            f"(short {part.missing})"
        )


def _print_human(
    report: MatchReport, inventory: Inventory, *, verbose: bool, color: bool
) -> None:
    paint = _make_painter(color)
    ok_mark, near_mark, far_mark = _pick_marks(sys.stdout)
    total = len(report.build_now) + len(report.almost) + len(report.not_yet)
    print(
        f"Matched {_n(total, 'project')} against "
        f"{_n(inventory.distinct_parts, 'part type')} "
        f"({_n(inventory.total_units, 'part')} on hand)."
    )

    print()
    print(paint(f"BUILD NOW ({len(report.build_now)})", "1;32"))
    if not report.build_now:
        print("  (none)")
    for result in report.build_now:
        suffix = f" — {result.description}" if result.description else ""
        print(f"  {paint(ok_mark, '32')} {result.name}{suffix}")

    print()
    print(
        paint(f"ALMOST THERE ({len(report.almost)})", "1;33")
        + f" — short at most {_n(report.almost_threshold, 'part')}, fewest missing first"
    )
    if not report.almost:
        print("  (none)")
    for result in report.almost:
        print(
            f"  {paint(near_mark, '33')} {result.name} — "
            f"short {_n(result.total_missing, 'part')}"
        )
        if result.description:
            print(f"      {result.description}")
        _print_missing_lines(result)

    print()
    print(paint(f"NOT YET ({len(report.not_yet)})", "1;31"))
    if not report.not_yet:
        print("  (none)")
    for result in report.not_yet:
        print(
            f"  {paint(far_mark, '31')} {result.name} — "
            f"short {_n(result.total_missing, 'part')} across "
            f"{_n(result.missing_kinds, 'part type')}"
        )
        if result.description:
            print(f"      {result.description}")
        if verbose:
            _print_missing_lines(result)

    if report.not_yet and not verbose:
        print()
        print(paint("(re-run with --verbose to see what NOT YET projects need)", "2"))


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.almost < 0:
        parser.error("--almost must be >= 0")

    inventory_path = Path(args.inventory) if args.inventory else SAMPLE_INVENTORY
    projects_path = Path(args.projects) if args.projects else SAMPLE_PROJECTS
    if args.inventory is None:
        print(
            f"note: no inventory file given, using bundled sample: {inventory_path}",
            file=sys.stderr,
        )
    if args.projects is None:
        print(
            f"note: no projects file given, using bundled sample: {projects_path}",
            file=sys.stderr,
        )

    try:
        inventory = parse_inventory(_load_json(inventory_path, "inventory"))
        projects = parse_projects(_load_json(projects_path, "project database"))
    except PartsMatcherError as exc:
        print(f"partsmatcher: error: {exc}", file=sys.stderr)
        return 2

    report = match(inventory, projects, almost_threshold=args.almost)

    if args.as_json:
        print(json.dumps(_report_to_dict(report, inventory), indent=2))
    else:
        _print_human(
            report, inventory, verbose=args.verbose, color=_want_color(args.no_color)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
