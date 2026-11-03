"""Repository metadata audit and backup.

Pure logic for the read-only audit: description quality, American spelling,
and topic hygiene. The same payloads are written by the CLI so the audit and
the backup can be tested without touching the network.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from gh_toolkit.core.spelling import SpellingIssue, find_american_spellings

BACKUP_FORMAT = "gh-toolkit-backup"
BACKUP_VERSION = 1
REPORT_FORMAT = "gh-toolkit-audit"
REPORT_VERSION = 1

DESCRIPTION_MAX = 250
DESCRIPTION_NEAR_LIMIT = 230
TOPIC_MAX = 20
TOPIC_MAX_LENGTH = 50

_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass
class RepoAudit:
    """Audit result for one repository."""

    full_name: str
    description: str | None
    description_status: str
    description_issues: list[str]
    spelling: list[SpellingIssue]
    topics: list[str]
    topic_issues: list[str]
    private: bool
    archived: bool
    fork: bool
    html_url: str | None

    @property
    def has_issues(self) -> bool:
        return bool(self.description_issues or self.spelling or self.topic_issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "description": self.description,
            "description_status": self.description_status,
            "description_issues": self.description_issues,
            "spelling": [
                {"word": issue.word, "suggestion": issue.suggestion}
                for issue in self.spelling
            ],
            "topics": self.topics,
            "topic_issues": self.topic_issues,
            "private": self.private,
            "archived": self.archived,
            "fork": self.fork,
            "html_url": self.html_url,
        }


def analyze_description(description: str | None) -> tuple[str, list[str]]:
    """Return a status and issue list for a repository description."""
    if not description or not description.strip():
        return "missing", ["description is empty"]

    text = description.strip()
    issues: list[str] = []
    status = "ok"

    if text.endswith(("...", "…")):
        issues.append("description ends with an ellipsis, likely truncated")
        status = "truncated"

    if len(text) >= DESCRIPTION_MAX:
        issues.append(f"description is at the {DESCRIPTION_MAX}-character limit")
        status = "truncated"
    elif len(text) >= DESCRIPTION_NEAR_LIMIT:
        issues.append(f"description is close to the {DESCRIPTION_MAX}-character limit")
        if status == "ok":
            status = "near_limit"

    if text.endswith(("-", "/", ",", ":", "(", "[", "{")):
        issues.append("description ends with an incomplete token")
        status = "truncated"

    return status, issues


def analyze_topics(topics: list[str]) -> list[str]:
    """Return topic hygiene issues."""
    issues: list[str] = []

    if not topics:
        return ["no topics"]

    if len(topics) > TOPIC_MAX:
        issues.append(f"more than {TOPIC_MAX} topics")

    invalid = [
        topic
        for topic in topics
        if len(topic) > TOPIC_MAX_LENGTH or not _TOPIC_RE.fullmatch(topic)
    ]
    if invalid:
        issues.append(f"invalid topics: {', '.join(invalid)}")

    lowered = [topic.lower() for topic in topics]
    if len(lowered) != len(set(lowered)):
        issues.append("duplicate topics")

    return issues


def audit_repository(repo: dict[str, Any]) -> RepoAudit:
    """Audit one repository payload from the GitHub API."""
    description = repo.get("description")
    status, description_issues = analyze_description(description)
    raw_topics = repo.get("topics")
    topics = (
        [str(topic) for topic in cast(list[Any], raw_topics)]
        if isinstance(raw_topics, list)
        else []
    )

    return RepoAudit(
        full_name=str(repo.get("full_name") or repo.get("name") or "unknown"),
        description=description,
        description_status=status,
        description_issues=description_issues,
        spelling=find_american_spellings(description),
        topics=topics,
        topic_issues=analyze_topics(topics),
        private=bool(repo.get("private", False)),
        archived=bool(repo.get("archived", False)),
        fork=bool(repo.get("fork", False)),
        html_url=repo.get("html_url"),
    )


def build_backup(
    repos: list[dict[str, Any]], sources: dict[str, Any]
) -> dict[str, Any]:
    """Build a restore-ready snapshot of descriptions and topics."""
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "sources": sources,
        "repos": [
            {
                "full_name": repo.get("full_name") or repo.get("name"),
                "name": repo.get("name"),
                "description": repo.get("description"),
                "topics": list(repo.get("topics") or []),
                "private": bool(repo.get("private", False)),
                "archived": bool(repo.get("archived", False)),
                "fork": bool(repo.get("fork", False)),
                "html_url": repo.get("html_url"),
                "default_branch": repo.get("default_branch"),
                "updated_at": repo.get("updated_at"),
            }
            for repo in repos
        ],
    }


def build_report(audits: list[RepoAudit], sources: dict[str, Any]) -> dict[str, Any]:
    """Build the JSON audit report."""
    summary = {
        "total": len(audits),
        "missing_description": sum(
            1 for audit in audits if audit.description_status == "missing"
        ),
        "truncated_description": sum(
            1 for audit in audits if audit.description_status == "truncated"
        ),
        "near_limit_description": sum(
            1 for audit in audits if audit.description_status == "near_limit"
        ),
        "with_spelling": sum(1 for audit in audits if audit.spelling),
        "with_topic_issues": sum(1 for audit in audits if audit.topic_issues),
        "clean": sum(1 for audit in audits if not audit.has_issues),
    }

    return {
        "format": REPORT_FORMAT,
        "version": REPORT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "sources": sources,
        "summary": summary,
        "repos": [audit.to_dict() for audit in audits],
    }


def write_json_atomic(payload: dict[str, Any], path: str | Path) -> None:
    """Write JSON through a sibling temp file so a crash cannot truncate it."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
