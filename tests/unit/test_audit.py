"""Unit tests for repository audit and backup payloads."""

import json

from gh_toolkit.core.audit import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    REPORT_FORMAT,
    analyze_description,
    analyze_topics,
    audit_repository,
    build_backup,
    build_report,
    write_json_atomic,
)


class TestDescriptionAudit:
    def test_missing_description(self):
        status, issues = analyze_description(None)

        assert status == "missing"
        assert "empty" in issues[0]

    def test_blank_description(self):
        status, _ = analyze_description("   ")

        assert status == "missing"

    def test_valid_description(self):
        status, issues = analyze_description("A small CLI for GitHub workflows.")

        assert status == "ok"
        assert issues == []

    def test_ellipsis_is_truncated(self):
        status, issues = analyze_description("A description that was cut...")

        assert status == "truncated"
        assert any("ellipsis" in issue for issue in issues)

    def test_at_limit_is_truncated(self):
        status, issues = analyze_description("x" * 250)

        assert status == "truncated"
        assert any("250" in issue for issue in issues)

    def test_near_limit_is_flagged(self):
        status, issues = analyze_description("x" * 235)

        assert status == "near_limit"
        assert any("close to" in issue for issue in issues)

    def test_incomplete_token_is_truncated(self):
        status, issues = analyze_description("A description ending with a colon:")

        assert status == "truncated"
        assert any("incomplete token" in issue for issue in issues)


class TestTopicAudit:
    def test_missing_topics(self):
        assert analyze_topics([]) == ["no topics"]

    def test_valid_topics(self):
        assert analyze_topics(["python", "cli-tool", "teaching"]) == []

    def test_invalid_case_and_spaces(self):
        issues = analyze_topics(["Python", "bad topic"])

        assert any("invalid topics" in issue for issue in issues)
        assert "Python" in issues[0]
        assert "bad topic" in issues[0]

    def test_topic_too_long(self):
        issues = analyze_topics(["a" * 51])

        assert any("invalid topics" in issue for issue in issues)

    def test_too_many_topics(self):
        issues = analyze_topics([f"topic-{i}" for i in range(21)])

        assert "more than 20 topics" in issues

    def test_duplicate_topics(self):
        issues = analyze_topics(["python", "python"])

        assert "duplicate topics" in issues


class TestRepositoryAudit:
    def test_audits_description_spelling_and_topics(self):
        audit = audit_repository(
            {
                "full_name": "owner/repo",
                "description": "An organization tool for color analysis",
                "topics": ["Python"],
                "private": True,
                "archived": False,
                "fork": True,
                "html_url": "https://github.com/owner/repo",
            }
        )

        assert audit.full_name == "owner/repo"
        assert audit.description_status == "ok"
        assert [issue.word for issue in audit.spelling] == [
            "organization",
            "color",
        ]
        assert audit.topic_issues
        assert audit.private is True
        assert audit.fork is True
        assert audit.has_issues is True

    def test_clean_repository_has_no_issues(self):
        audit = audit_repository(
            {
                "full_name": "owner/clean",
                "description": "A small, focused tool.",
                "topics": ["python", "cli-tool"],
            }
        )

        assert audit.has_issues is False


class TestBackup:
    def test_build_backup_includes_restore_fields(self):
        repos = [
            {
                "full_name": "owner/repo",
                "name": "repo",
                "description": "Old description",
                "topics": ["python"],
                "private": False,
                "archived": False,
                "fork": False,
                "html_url": "https://github.com/owner/repo",
                "default_branch": "main",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]

        backup = build_backup(repos, {"user": True, "orgs": []})

        assert backup["format"] == BACKUP_FORMAT
        assert backup["version"] == BACKUP_VERSION
        assert backup["sources"] == {"user": True, "orgs": []}
        assert backup["repos"][0]["description"] == "Old description"
        assert backup["repos"][0]["topics"] == ["python"]

    def test_write_json_atomic(self, tmp_path):
        path = tmp_path / "nested" / "backup.json"

        write_json_atomic({"format": BACKUP_FORMAT}, path)

        assert json.loads(path.read_text())["format"] == BACKUP_FORMAT
        assert not path.with_name(path.name + ".tmp").exists()


class TestReport:
    def test_summary_counts(self):
        audits = [
            audit_repository(
                {
                    "full_name": "owner/missing",
                    "description": None,
                    "topics": [],
                }
            ),
            audit_repository(
                {
                    "full_name": "owner/spelling",
                    "description": "An organization tool.",
                    "topics": ["python"],
                }
            ),
            audit_repository(
                {
                    "full_name": "owner/clean",
                    "description": "A clean repository.",
                    "topics": ["python"],
                }
            ),
        ]

        report = build_report(audits, {"user": True, "orgs": []})

        assert report["format"] == REPORT_FORMAT
        assert report["summary"]["total"] == 3
        assert report["summary"]["missing_description"] == 1
        assert report["summary"]["with_spelling"] == 1
        assert report["summary"]["with_topic_issues"] == 1
        assert report["summary"]["clean"] == 1
