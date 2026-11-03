"""Integration tests for repo describe --from-audit."""

import base64
import json
from unittest.mock import Mock

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app


def _write_audit(tmp_path, repos):
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps(
            {
                "format": "gh-toolkit-audit",
                "version": 1,
                "sources": {"user": True, "orgs": []},
                "summary": {},
                "repos": repos,
            }
        )
    )
    return path


class TestDescribeFromAudit:
    @responses.activate
    def test_spelling_only_dry_run(self, mock_github_token, tmp_path):
        audit = _write_audit(
            tmp_path,
            [
                {
                    "full_name": "user/repo",
                    "description": "An organization tool for color analysis",
                    "description_status": "ok",
                    "description_issues": [],
                    "spelling": [
                        {"word": "organization", "suggestion": "organisation"},
                        {"word": "color", "suggestion": "colour"},
                    ],
                    "topics": ["python"],
                    "topic_issues": [],
                }
            ],
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "An organization tool for color analysis",
                "topics": ["python"],
            },
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "describe",
                "--from-audit",
                str(audit),
                "--only",
                "spelling",
                "--spelling",
                "en-AU",
                "--dry-run",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Proposed descriptions" in result.stdout
        assert "organisation" in result.stdout
        assert "colour" in result.stdout
        assert not any(call.request.method == "PATCH" for call in responses.calls)

    @responses.activate
    def test_missing_description_regenerated_and_applied(
        self, mock_github_token, mock_anthropic_client, tmp_path
    ):
        mock_anthropic_client.messages.create.return_value.content = [
            Mock(text="A small tool for automating repository chores.")
        ]
        audit = _write_audit(
            tmp_path,
            [
                {
                    "full_name": "user/repo",
                    "description": None,
                    "description_status": "missing",
                    "description_issues": ["description is empty"],
                    "spelling": [],
                    "topics": ["python"],
                    "topic_issues": [],
                }
            ],
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": None,
                "language": "Python",
                "topics": ["python"],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo/readme",
            json={
                "content": base64.b64encode(b"# Repo\n\nA tool.").decode(),
            },
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "describe",
                "--from-audit",
                str(audit),
                "--only",
                "missing",
                "--spelling",
                "en-AU",
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        patch_calls = [
            call for call in responses.calls if call.request.method == "PATCH"
        ]
        assert len(patch_calls) == 1
        body = json.loads(patch_calls[0].request.body)
        assert body["description"] == "A small tool for automating repository chores."

    @responses.activate
    def test_apply_proposals_uses_saved_values(self, mock_github_token, tmp_path):
        proposals = {
            "format": "gh-toolkit-description-changes",
            "version": 1,
            "dry_run": True,
            "updated": 0,
            "failed": 0,
            "changes": [
                {
                    "full_name": "user/repo",
                    "owner": "user",
                    "repo": "repo",
                    "mode": "spelling",
                    "old": "An organization tool",
                    "new": "An organisation tool",
                    "issues": ["spelling"],
                }
            ],
        }
        proposals_path = tmp_path / "proposals.json"
        proposals_path.write_text(json.dumps(proposals))
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "An organization tool",
                "topics": ["python"],
            },
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "describe",
                "--apply-proposals",
                str(proposals_path),
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        patch_calls = [
            call for call in responses.calls if call.request.method == "PATCH"
        ]
        assert len(patch_calls) == 1
        body = json.loads(patch_calls[0].request.body)
        assert body["description"] == "An organisation tool"

    @responses.activate
    def test_apply_proposals_unarchives_updates_and_rearchives(
        self, mock_github_token, tmp_path
    ):
        proposals = {
            "format": "gh-toolkit-description-changes",
            "version": 1,
            "dry_run": True,
            "updated": 0,
            "failed": 0,
            "changes": [
                {
                    "full_name": "user/repo",
                    "owner": "user",
                    "repo": "repo",
                    "mode": "spelling",
                    "old": "An organization tool",
                    "new": "An organisation tool",
                    "issues": ["spelling"],
                    "archived": True,
                }
            ],
        }
        proposals_path = tmp_path / "proposals.json"
        proposals_path.write_text(json.dumps(proposals))
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "An organization tool",
                "archived": True,
                "topics": ["python"],
            },
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "describe",
                "--apply-proposals",
                str(proposals_path),
                "--include-archived",
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        patch_bodies = [
            json.loads(call.request.body)
            for call in responses.calls
            if call.request.method == "PATCH"
        ]
        assert patch_bodies == [
            {"archived": False},
            {"description": "An organisation tool"},
            {"archived": True},
        ]
