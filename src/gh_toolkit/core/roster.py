"""Roster parsing and submission-report assembly.

Pure logic for the classroom workflow: read a roster CSV (students + GitHub
usernames), resolve each student to a repository, and flatten a health report
into a per-student row. This is *submission / hygiene tracking* — did the repo
get set up — not marking of the work itself.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gh_toolkit.core.health_checker import HealthReport

# Accepted header spellings (normalized: lowercased, spaces/hyphens -> underscore)
_GITHUB_KEYS = {
    "github",
    "github_username",
    "github_handle",
    "username",
    "handle",
    "login",
}
_NAME_KEYS = {"name", "student_name", "full_name", "student"}
_ID_KEYS = {"id", "student_id", "sid", "number", "student_number"}
_REPO_KEYS = {"repo", "repository", "repo_full_name", "repository_name"}


@dataclass
class Student:
    """One roster entry."""

    github_username: str
    name: str = ""
    student_id: str = ""
    repo: str = ""  # explicit owner/repo or bare repo name, if the roster has it


def _normalize(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _match_column(headers: Sequence[str], candidates: set[str]) -> str | None:
    """Return the first original header whose normalized form is in candidates."""
    for h in headers:
        if _normalize(h) in candidates:
            return h
    return None


def parse_roster(path: str | Path) -> list[Student]:
    """Parse a roster CSV into Student records.

    The only required column is a GitHub username (any of: github,
    github_username, github_handle, username, handle, login). Name, id, and an
    explicit repo column are optional and auto-detected. Rows missing a
    username are skipped.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if no usable header or username column is found.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Roster file not found: {path}")

    # utf-8-sig strips a BOM, which Excel exports often include
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        if not headers:
            raise ValueError(f"Roster file has no header row: {path}")

        github_col = _match_column(headers, _GITHUB_KEYS)
        if github_col is None:
            raise ValueError(
                "Roster needs a GitHub username column "
                f"(one of: {', '.join(sorted(_GITHUB_KEYS))}). Found: "
                f"{', '.join(headers)}"
            )
        name_col = _match_column(headers, _NAME_KEYS)
        id_col = _match_column(headers, _ID_KEYS)
        repo_col = _match_column(headers, _REPO_KEYS)

        students: list[Student] = []
        for row in reader:
            username = (row.get(github_col) or "").strip()
            if not username:
                continue
            students.append(
                Student(
                    github_username=username,
                    name=(row.get(name_col) or "").strip() if name_col else "",
                    student_id=(row.get(id_col) or "").strip() if id_col else "",
                    repo=(row.get(repo_col) or "").strip() if repo_col else "",
                )
            )

    if not students:
        raise ValueError(f"No roster entries with a GitHub username in: {path}")
    return students


def resolve_repo(
    student: Student, org: str | None, repo_pattern: str | None
) -> str | None:
    """Resolve a student to an ``owner/repo`` string, or None if not possible.

    Precedence:
      1. An explicit repo from the roster (prefixed with ``org`` if it has no owner).
      2. ``repo_pattern`` formatted with the student's fields, e.g.
         ``"assignment1-{github}"`` -> ``"<org>/assignment1-<username>"``.
      3. ``org/<github_username>`` when only an org is given.
    """
    if student.repo:
        if "/" in student.repo:
            return student.repo
        return f"{org}/{student.repo}" if org else None

    if repo_pattern:
        fields = {
            "github": student.github_username,
            "username": student.github_username,
            "id": student.student_id,
            "name": student.name,
        }
        try:
            name = repo_pattern.format(**fields)
        except (KeyError, IndexError) as e:
            raise ValueError(
                f"repo pattern {repo_pattern!r} references unknown field {e}; "
                "available: {github}, {username}, {id}, {name}"
            ) from e
        if "/" in name:
            return name
        return f"{org}/{name}" if org else None

    if org:
        return f"{org}/{student.github_username}"

    return None


def report_row(
    student: Student,
    repo: str | None,
    status: str,
    report: HealthReport | None,
    error: str = "",
) -> dict[str, Any]:
    """Flatten a student + health report into one stable, serializable row.

    ``status`` is one of ``found`` / ``not_found`` / ``unresolved`` / ``error``.
    Score/grade/check fields are None when there is no report.
    """
    checks_passed = checks_failed = None
    failed_checks = ""
    score_percent = grade = None
    if report is not None:
        checks_passed = sum(1 for c in report.checks if c.passed)
        checks_failed = sum(1 for c in report.checks if not c.passed)
        failed_checks = "; ".join(c.name for c in report.checks if not c.passed)
        score_percent = round(report.percentage, 1)
        grade = report.grade

    return {
        "student_name": student.name,
        "student_id": student.student_id,
        "github_username": student.github_username,
        "repository": repo or "",
        "status": status,
        "score_percent": score_percent,
        "grade": grade,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "failed_checks": failed_checks,
        "error": error,
    }


# Column order for CSV output (keys of report_row, in a sensible reading order)
ROW_FIELDS = [
    "student_name",
    "student_id",
    "github_username",
    "repository",
    "status",
    "score_percent",
    "grade",
    "checks_passed",
    "checks_failed",
    "failed_checks",
    "error",
]


def rows_to_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    """Write report rows to a CSV file with a stable column order."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ROW_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: ("" if row.get(k) is None else row[k]) for k in ROW_FIELDS}
            )
