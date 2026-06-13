"""Unit tests for health feedback formatting and issue matching."""

from gh_toolkit.core.feedback import (
    MARKER,
    feedback_body,
    feedback_title,
    find_marker_issue,
)
from gh_toolkit.core.health_checker import HealthCheck, HealthReport


def _report(percentage=80.0, grade="B", *, required_failures=None):
    checks = [
        HealthCheck(
            name="README Existence",
            category="Documentation",
            description="Has README",
            passed=True,
            score=10,
            max_score=10,
            message="Found",
        ),
        HealthCheck(
            name="License",
            category="Documentation",
            description="Has license",
            passed=False,
            score=0,
            max_score=5,
            message="No license",
            fix_suggestion="Add a LICENSE file",
        ),
    ]
    summary = {}
    if required_failures is not None:
        summary["required_failures"] = required_failures
    return HealthReport(
        repository="org/repo",
        total_score=10,
        max_score=15,
        percentage=percentage,
        grade=grade,
        checks=checks,
        summary=summary,
    )


class TestFeedbackFormatting:
    def test_title_has_grade_and_percentage(self):
        assert feedback_title(_report(82.4, "B")) == "Repository health: B (82%)"

    def test_body_contains_marker(self):
        assert MARKER in feedback_body(_report())

    def test_body_lists_failing_check_with_fix(self):
        body = feedback_body(_report())
        assert "Needs attention" in body
        assert "License" in body
        assert "Add a LICENSE file" in body

    def test_body_collapses_passing_checks(self):
        body = feedback_body(_report())
        assert "Passing checks" in body
        assert "README Existence" in body

    def test_body_flags_required_failures(self):
        body = feedback_body(_report(required_failures=["License"]))
        assert "Required checks not met" in body
        assert "License" in body

    def test_body_no_required_section_when_none(self):
        assert "Required checks not met" not in feedback_body(_report())


class TestFindMarkerIssue:
    def test_finds_issue_with_marker(self):
        issues = [
            {"number": 1, "body": "unrelated issue"},
            {"number": 2, "body": f"stuff\n{MARKER}\nmore"},
        ]
        found = find_marker_issue(issues)
        assert found is not None
        assert found["number"] == 2

    def test_returns_none_when_absent(self):
        issues = [{"number": 1, "body": "unrelated"}, {"number": 2, "body": None}]
        assert find_marker_issue(issues) is None

    def test_handles_empty_list(self):
        assert find_marker_issue([]) is None
