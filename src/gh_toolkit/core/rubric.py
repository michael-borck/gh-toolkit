"""Custom health rubrics loaded from YAML.

A rubric lets an educator tune the repository health checker per assignment:
re-weight checks, set custom grade thresholds, and mark checks as required.
It is a *hygiene* rubric (is the repo set up well), not a marking rubric for
the work itself — see docs/ROADMAP.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from gh_toolkit.core.health_checker import CHECK_NAMES, DEFAULT_WEIGHTS

_TOP_LEVEL_KEYS = {"name", "description", "weights", "grades", "required"}


@dataclass
class Rubric:
    """A custom health rubric: weight/grade/required overrides."""

    name: str = "Custom Rubric"
    weights: dict[str, dict[str, int]] = field(default_factory=dict)
    grades: dict[str, float] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)


def load_rubric(path: str | Path) -> Rubric:
    """Load and validate a rubric from a YAML file.

    Schema (all sections optional except that the file must parse to a mapping)::

        name: "Assignment 2"
        weights:           # partial override of category -> check -> points
          documentation:
            readme: 20
            license: 0
          quality:
            tests: 15
        grades:            # letter -> minimum percentage
          A: 90
          B: 75
        required:          # check names that must pass
          - README Existence
          - Tests

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: on malformed content or unknown category/check/grade keys.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Rubric file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in rubric {path}: {e}") from e

    if data is None:
        return Rubric()
    if not isinstance(data, dict):
        raise ValueError(f"Rubric {path} must be a mapping at the top level")
    data = cast(dict[str, Any], data)

    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"Unknown rubric keys: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_TOP_LEVEL_KEYS))}"
        )

    weights = _parse_weights(data.get("weights", {}) or {})
    grades = _parse_grades(data.get("grades", {}) or {})
    required = _parse_required(data.get("required", []) or [])
    name = str(data.get("name") or "Custom Rubric")

    return Rubric(name=name, weights=weights, grades=grades, required=required)


def _parse_weights(raw: Any) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict):
        raise ValueError("rubric 'weights' must be a mapping of category -> checks")
    raw = cast(dict[str, Any], raw)
    weights: dict[str, dict[str, int]] = {}
    for category, checks in raw.items():
        if category not in DEFAULT_WEIGHTS:
            raise ValueError(
                f"Unknown weight category {category!r}. "
                f"Valid: {', '.join(sorted(DEFAULT_WEIGHTS))}"
            )
        if not isinstance(checks, dict):
            raise ValueError(f"weights.{category} must be a mapping of check -> points")
        checks = cast(dict[str, Any], checks)
        valid_checks = DEFAULT_WEIGHTS[category]
        parsed: dict[str, int] = {}
        for check_key, value in checks.items():
            if check_key not in valid_checks:
                raise ValueError(
                    f"Unknown check {check_key!r} in category {category!r}. "
                    f"Valid: {', '.join(sorted(valid_checks))}"
                )
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"weights.{category}.{check_key} must be a non-negative integer"
                )
            parsed[check_key] = value
        weights[category] = parsed
    return weights


def _parse_grades(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError("rubric 'grades' must be a mapping of letter -> percentage")
    raw = cast(dict[str, Any], raw)
    grades: dict[str, float] = {}
    for letter, threshold in raw.items():
        if not isinstance(threshold, int | float) or isinstance(threshold, bool):
            raise ValueError(f"grade {letter!r} threshold must be a number")
        if not 0 <= threshold <= 100:
            raise ValueError(f"grade {letter!r} threshold must be between 0 and 100")
        grades[str(letter)] = float(threshold)
    return grades


def _parse_required(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("rubric 'required' must be a list of check names")
    raw = cast(list[Any], raw)
    required: list[str] = []
    for name in raw:
        name = str(name)
        if name not in CHECK_NAMES:
            raise ValueError(
                f"Unknown required check {name!r}. "
                f"Valid: {', '.join(sorted(CHECK_NAMES))}"
            )
        required.append(name)
    return required
