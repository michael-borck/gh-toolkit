"""Unit tests for roster parsing and report-row assembly."""

import pytest

from gh_toolkit.core.health_checker import HealthCheck, HealthReport
from gh_toolkit.core.roster import (
    ROW_FIELDS,
    Student,
    parse_roster,
    report_row,
    resolve_repo,
    rows_to_csv,
)


def _write(tmp_path, text, name="roster.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestParseRoster:
    def test_basic_columns(self, tmp_path):
        path = _write(
            tmp_path,
            "name,student_id,github\nAlice,1001,alice-gh\nBob,1002,bob-gh\n",
        )
        students = parse_roster(path)
        assert len(students) == 2
        assert students[0] == Student(
            github_username="alice-gh", name="Alice", student_id="1001"
        )

    def test_header_aliases_and_case(self, tmp_path):
        path = _write(
            tmp_path,
            "Full Name,SID,GitHub Username,Repository\nAlice,1,alice,org/alice-lab\n",
        )
        (student,) = parse_roster(path)
        assert student.name == "Alice"
        assert student.student_id == "1"
        assert student.github_username == "alice"
        assert student.repo == "org/alice-lab"

    def test_bom_is_stripped(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text("github\nalice\n", encoding="utf-8-sig")
        (student,) = parse_roster(path)
        assert student.github_username == "alice"

    def test_rows_without_username_skipped(self, tmp_path):
        path = _write(tmp_path, "name,github\nAlice,alice\nBob,\n")
        students = parse_roster(path)
        assert [s.github_username for s in students] == ["alice"]

    def test_missing_username_column_raises(self, tmp_path):
        path = _write(tmp_path, "name,email\nAlice,a@x.com\n")
        with pytest.raises(ValueError, match="GitHub username column"):
            parse_roster(path)

    def test_no_data_rows_raises(self, tmp_path):
        path = _write(tmp_path, "github\n")
        with pytest.raises(ValueError, match="No roster entries"):
            parse_roster(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_roster(tmp_path / "nope.csv")


class TestResolveRepo:
    def test_explicit_full_repo_wins(self):
        s = Student(github_username="alice", repo="someorg/custom")
        assert resolve_repo(s, "myorg", "lab-{github}") == "someorg/custom"

    def test_bare_repo_column_prefixed_with_org(self):
        s = Student(github_username="alice", repo="alice-lab")
        assert resolve_repo(s, "myorg", None) == "myorg/alice-lab"

    def test_bare_repo_without_org_is_unresolved(self):
        s = Student(github_username="alice", repo="alice-lab")
        assert resolve_repo(s, None, None) is None

    def test_pattern_with_org(self):
        s = Student(github_username="alice")
        assert resolve_repo(s, "myorg", "lab1-{github}") == "myorg/lab1-alice"

    def test_pattern_with_id_field(self):
        s = Student(github_username="alice", student_id="42")
        assert resolve_repo(s, "myorg", "sub-{id}") == "myorg/sub-42"

    def test_pattern_with_owner_in_template(self):
        s = Student(github_username="alice")
        assert resolve_repo(s, None, "fixedorg/lab-{github}") == "fixedorg/lab-alice"

    def test_org_only_uses_username(self):
        s = Student(github_username="alice")
        assert resolve_repo(s, "myorg", None) == "myorg/alice"

    def test_nothing_resolves_to_none(self):
        s = Student(github_username="alice")
        assert resolve_repo(s, None, None) is None

    def test_unknown_pattern_field_raises(self):
        s = Student(github_username="alice")
        with pytest.raises(ValueError, match="unknown field"):
            resolve_repo(s, "myorg", "lab-{email}")


def _report(percentage: float, grade: str, passed: bool) -> HealthReport:
    check = HealthCheck(
        name="README Existence",
        category="Documentation",
        description="Has README",
        passed=passed,
        score=10 if passed else 0,
        max_score=10,
        message="",
    )
    return HealthReport(
        repository="org/alice-lab",
        total_score=10 if passed else 0,
        max_score=10,
        percentage=percentage,
        grade=grade,
        checks=[check],
        summary={},
    )


class TestReportRow:
    def test_found_row_has_score_and_checks(self):
        s = Student(github_username="alice", name="Alice", student_id="1")
        row = report_row(s, "org/alice-lab", "found", _report(90.0, "A", True))
        assert row["status"] == "found"
        assert row["score_percent"] == 90.0
        assert row["grade"] == "A"
        assert row["checks_passed"] == 1
        assert row["checks_failed"] == 0
        assert row["failed_checks"] == ""

    def test_failed_checks_listed(self):
        s = Student(github_username="alice")
        row = report_row(s, "org/alice-lab", "found", _report(0.0, "F", False))
        assert row["checks_failed"] == 1
        assert "README Existence" in row["failed_checks"]

    def test_missing_repo_row_has_no_score(self):
        s = Student(github_username="alice", name="Alice")
        row = report_row(s, "org/alice-lab", "not_found", None, error="Not Found")
        assert row["status"] == "not_found"
        assert row["score_percent"] is None
        assert row["grade"] is None
        assert row["error"] == "Not Found"

    def test_row_has_all_fields(self):
        s = Student(github_username="alice")
        row = report_row(s, None, "unresolved", None)
        assert set(row.keys()) == set(ROW_FIELDS)


class TestRowsToCsv:
    def test_writes_header_and_rows(self, tmp_path):
        s = Student(github_username="alice", name="Alice", student_id="1")
        rows = [
            report_row(s, "org/alice-lab", "found", _report(80.0, "B", True)),
            report_row(
                Student(github_username="bob"), "org/bob-lab", "not_found", None
            ),
        ]
        out = tmp_path / "report.csv"
        rows_to_csv(rows, out)

        content = out.read_text()
        lines = content.strip().splitlines()
        assert lines[0] == ",".join(ROW_FIELDS)
        assert "alice" in content
        assert "bob" in content
        # None values render as empty strings, not the literal "None"
        assert "None" not in content
