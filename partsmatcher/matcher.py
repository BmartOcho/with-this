"""Core matching logic for PartsMatcher — pure data in, grouped report out.

No I/O lives here: ``parse_inventory`` / ``parse_projects`` accept
already-decoded JSON values, and ``match`` works on the resulting objects.
That keeps the matching reusable by other frontends (tests, a future
vision-based inventory scanner, a web UI) without dragging the CLI along.

Matching model: each project is checked independently against the *full*
inventory — a multiset-coverage test. For every required part the deficit is
``max(0, required - owned)``; a project is buildable when every deficit is 0,
"almost" when the summed deficit is within the threshold, and "not yet"
otherwise. Projects never consume parts from each other's check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DEFAULT_ALMOST_THRESHOLD = 2


class PartsMatcherError(ValueError):
    """An input decoded fine as JSON but does not fit the expected schema."""


def normalize_name(name: str) -> str:
    """Canonical form for comparing part names: trimmed, single-spaced, casefolded."""
    return " ".join(name.split()).casefold()


def _entry_list(data: object, *, key: str, what: str) -> list:
    """Accept either a bare JSON list or an object wrapping the list under ``key``."""
    if isinstance(data, dict):
        if key not in data:
            raise PartsMatcherError(
                f"{what}: top-level object must contain a {key!r} list"
            )
        data = data[key]
    if not isinstance(data, list):
        raise PartsMatcherError(
            f"{what}: expected a list, or an object with a {key!r} list"
        )
    return data


def _parse_part(entry: object, *, where: str, min_quantity: int) -> "tuple[str, int]":
    """Validate one part entry and return (display name, quantity).

    Unknown fields (``source``, ``confidence``, ``bin``, ...) are deliberately
    tolerated so richer producers — e.g. a vision scanner — can annotate parts
    without breaking the matcher. ``quantity`` defaults to 1 when omitted.
    """
    if not isinstance(entry, dict):
        raise PartsMatcherError(
            f"{where}: each part must be an object with 'name' and 'quantity'"
        )
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PartsMatcherError(f"{where}: 'name' must be a non-empty string")
    display = " ".join(name.split())
    quantity = entry.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise PartsMatcherError(f"{where} ({display!r}): 'quantity' must be an integer")
    if quantity < min_quantity:
        raise PartsMatcherError(
            f"{where} ({display!r}): 'quantity' must be at least {min_quantity}"
        )
    return display, quantity


@dataclass
class Inventory:
    """Parts on hand, keyed by normalized name.

    Repeated names are merged by summing quantities, so a producer may emit
    one entry per detection (quantity 1 each) and still get correct totals.
    """

    quantities: "dict[str, int]"
    display_names: "dict[str, str]"

    def have(self, name: str) -> int:
        return self.quantities.get(normalize_name(name), 0)

    @property
    def distinct_parts(self) -> int:
        return len(self.quantities)

    @property
    def total_units(self) -> int:
        return sum(self.quantities.values())


def parse_inventory(data: object) -> Inventory:
    """Build an Inventory from decoded JSON: a list of parts, or {"parts": [...]}."""
    entries = _entry_list(data, key="parts", what="inventory")
    quantities: "dict[str, int]" = {}
    display_names: "dict[str, str]" = {}
    for index, entry in enumerate(entries, start=1):
        name, quantity = _parse_part(
            entry, where=f"inventory part #{index}", min_quantity=0
        )
        key = normalize_name(name)
        display_names.setdefault(key, name)
        quantities[key] = quantities.get(key, 0) + quantity
    return Inventory(quantities=quantities, display_names=display_names)


@dataclass
class Project:
    name: str
    description: str
    requirements: "dict[str, int]"  # normalized part name -> required quantity
    display_names: "dict[str, str]"  # normalized part name -> spelling in the file


def parse_projects(data: object) -> "list[Project]":
    """Build projects from decoded JSON: a list of projects, or {"projects": [...]}.

    Each project needs a ``name`` and a non-empty ``parts`` list
    (``required_parts`` is accepted as an alias); ``description`` is optional.
    """
    entries = _entry_list(data, key="projects", what="project database")
    projects: "list[Project]" = []
    for index, raw in enumerate(entries, start=1):
        where = f"project #{index}"
        if not isinstance(raw, dict):
            raise PartsMatcherError(f"{where}: each project must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PartsMatcherError(f"{where}: 'name' must be a non-empty string")
        name = " ".join(name.split())
        where = f"project #{index} ({name!r})"
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise PartsMatcherError(f"{where}: 'description' must be a string")
        parts_raw = raw.get("parts", raw.get("required_parts"))
        if parts_raw is None:
            raise PartsMatcherError(
                f"{where}: missing a 'parts' (or 'required_parts') list"
            )
        if not isinstance(parts_raw, list) or not parts_raw:
            raise PartsMatcherError(f"{where}: 'parts' must be a non-empty list")
        requirements: "dict[str, int]" = {}
        display_names: "dict[str, str]" = {}
        for part_index, entry in enumerate(parts_raw, start=1):
            part_name, quantity = _parse_part(
                entry, where=f"{where}, part #{part_index}", min_quantity=1
            )
            key = normalize_name(part_name)
            display_names.setdefault(key, part_name)
            requirements[key] = requirements.get(key, 0) + quantity
        projects.append(
            Project(
                name=name,
                description=description.strip(),
                requirements=requirements,
                display_names=display_names,
            )
        )
    return projects


@dataclass(frozen=True)
class MissingPart:
    name: str
    required: int
    have: int

    @property
    def missing(self) -> int:
        return self.required - self.have


@dataclass
class ProjectMatch:
    project: Project
    missing: "tuple[MissingPart, ...]"  # empty means buildable

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def description(self) -> str:
        return self.project.description

    @property
    def buildable(self) -> bool:
        return not self.missing

    @property
    def total_missing(self) -> int:
        return sum(part.missing for part in self.missing)

    @property
    def missing_kinds(self) -> int:
        return len(self.missing)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "total_missing": self.total_missing,
            "missing": [
                {
                    "name": part.name,
                    "required": part.required,
                    "have": part.have,
                    "missing": part.missing,
                }
                for part in self.missing
            ],
        }


def evaluate(project: Project, inventory: Inventory) -> ProjectMatch:
    """Compare one project against the full inventory."""
    missing = []
    for key, required in project.requirements.items():
        have = inventory.quantities.get(key, 0)
        if have < required:
            missing.append(
                MissingPart(name=project.display_names[key], required=required, have=have)
            )
    return ProjectMatch(project=project, missing=tuple(missing))


@dataclass
class MatchReport:
    build_now: "list[ProjectMatch]"
    almost: "list[ProjectMatch]"
    not_yet: "list[ProjectMatch]"
    almost_threshold: int


def _gap_order(result: ProjectMatch) -> "tuple[int, int, str]":
    # Fewest missing units first; ties go to fewer distinct parts to buy.
    return (result.total_missing, result.missing_kinds, result.name.casefold())


def match(
    inventory: Inventory,
    projects: "Iterable[Project]",
    almost_threshold: int = DEFAULT_ALMOST_THRESHOLD,
) -> MatchReport:
    """Group projects into build-now / almost / not-yet against one inventory."""
    if almost_threshold < 0:
        raise ValueError("almost_threshold must be >= 0")
    build_now: "list[ProjectMatch]" = []
    almost: "list[ProjectMatch]" = []
    not_yet: "list[ProjectMatch]" = []
    for project in projects:
        result = evaluate(project, inventory)
        if result.buildable:
            build_now.append(result)
        elif result.total_missing <= almost_threshold:
            almost.append(result)
        else:
            not_yet.append(result)
    build_now.sort(key=lambda result: result.name.casefold())
    almost.sort(key=_gap_order)
    not_yet.sort(key=_gap_order)
    return MatchReport(
        build_now=build_now,
        almost=almost,
        not_yet=not_yet,
        almost_threshold=almost_threshold,
    )
