"""PartsMatcher — match the parts you own against projects you could build."""

from .matcher import (
    DEFAULT_ALMOST_THRESHOLD,
    Inventory,
    MatchReport,
    MissingPart,
    PartsMatcherError,
    Project,
    ProjectMatch,
    evaluate,
    match,
    normalize_name,
    parse_inventory,
    parse_projects,
)

__version__ = "0.6.0"

__all__ = [
    "DEFAULT_ALMOST_THRESHOLD",
    "Inventory",
    "MatchReport",
    "MissingPart",
    "PartsMatcherError",
    "Project",
    "ProjectMatch",
    "evaluate",
    "match",
    "normalize_name",
    "parse_inventory",
    "parse_projects",
    "__version__",
]
