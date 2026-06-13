"""Format repository health feedback for delivery as GitHub issues.

Pure formatting + lookup logic, kept separate from the API calls so it can be
unit-tested. The feedback covers repository *hygiene* (is the repo set up well)
with the checker's own fix suggestions — it is not a mark for the work.
"""

from __future__ import annotations

from typing import Any

from gh_toolkit.core.health_checker import HealthReport

# Hidden marker placed in every issue body so re-runs find and update the same
# issue instead of opening duplicates.
MARKER = "<!-- gh-toolkit-health -->"

_FOOTER = (
    "_Posted by [gh-toolkit](https://github.com/michael-borck/gh-toolkit). "
    "This reports repository setup/hygiene, not a grade for your work._"
)


def feedback_title(report: HealthReport) -> str:
    """Issue title summarizing the health grade."""
    return f"Repository health: {report.grade} ({report.percentage:.0f}%)"


def feedback_body(report: HealthReport) -> str:
    """Build the markdown issue body for a health report."""
    passed = [c for c in report.checks if c.passed]
    failed = [c for c in report.checks if not c.passed]

    lines: list[str] = [
        MARKER,
        "## 🔍 Repository health report",
        "",
        f"**Grade: {report.grade} ({report.percentage:.0f}%)** — "
        f"{len(passed)}/{len(report.checks)} checks passed.",
        "",
    ]

    required_failures: list[str] = report.summary.get("required_failures") or []
    if required_failures:
        lines.append("> ⚠️ **Required checks not met:** " + ", ".join(required_failures))
        lines.append("")

    if failed:
        lines.append("### Needs attention")
        for check in failed:
            if check.fix_suggestion:
                lines.append(f"- **{check.name}** — {check.fix_suggestion}")
            else:
                lines.append(f"- **{check.name}** — {check.message}")
        lines.append("")

    if passed:
        lines.append("<details><summary>Passing checks</summary>")
        lines.append("")
        for check in passed:
            lines.append(f"- {check.name}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append(_FOOTER)
    return "\n".join(lines)


def find_marker_issue(
    issues: list[dict[str, Any]], marker: str = MARKER
) -> dict[str, Any] | None:
    """Return the first issue whose body contains the marker, or None."""
    for issue in issues:
        if marker in (issue.get("body") or ""):
            return issue
    return None
