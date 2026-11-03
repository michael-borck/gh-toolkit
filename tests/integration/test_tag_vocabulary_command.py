"""Integration tests for vocabulary-driven tagging."""

import base64
import json
from unittest.mock import Mock

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app


def _write_vocabulary(tmp_path):
    path = tmp_path / "tags.yaml"
    path.write_text(
        """
name: Test tags
tags:
  web-app:
    description: Browser apps
  ai:
    description: AI tools
"""
    )
    return path


def _write_audit(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps(
            {
                "format": "gh-toolkit-audit",
                "version": 1,
                "sources": {"user": True, "orgs": []},
                "summary": {},
                "repos": [
                    {
                        "full_name": "user/repo",
                        "topics": [],
                        "topic_issues": ["no topics"],
                        "archived": False,
                    }
                ],
            }
        )
    )
    return path


class TestTagVocabularyCommand:
    @responses.activate
    def test_from_audit_dry_run(
        self, mock_github_token, mock_anthropic_client, tmp_path
    ):
        mock_anthropic_client.messages.create.return_value.content = [
            Mock(
                text=json.dumps(
                    {
                        "standard": {"web-app": 0.9, "ai": 0.85},
                        "free": ["python"],
                        "reason": "web AI tool",
                    }
                )
            )
        ]
        vocabulary = _write_vocabulary(tmp_path)
        audit = _write_audit(tmp_path)
        proposals = tmp_path / "proposals.json"
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "A web AI tool",
                "language": "Python",
                "topics": [],
                "archived": False,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo/readme",
            json={"content": base64.b64encode(b"# Repo\n\nA web AI tool.").decode()},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "tag",
                "--from-audit",
                str(audit),
                "--vocabulary",
                str(vocabulary),
                "--dry-run",
                "--output",
                str(proposals),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        data = json.loads(proposals.read_text())
        assert data["format"] == "gh-toolkit-tag-proposals"
        assert data["changes"][0]["final_topics"] == ["web-app", "ai", "python"]

    @responses.activate
    def test_apply_proposals(self, mock_github_token, tmp_path):
        proposals = tmp_path / "proposals.json"
        proposals.write_text(
            json.dumps(
                {
                    "format": "gh-toolkit-tag-proposals",
                    "version": 1,
                    "dry_run": True,
                    "changes": [
                        {
                            "full_name": "user/repo",
                            "owner": "user",
                            "repo": "repo",
                            "final_topics": ["web-app", "ai"],
                            "archived": False,
                        }
                    ],
                }
            )
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "topics": [],
                "archived": False,
            },
            status=200,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/user/repo/topics",
            json={"names": ["web-app", "ai"]},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "tag",
                "--apply-proposals",
                str(proposals),
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        put_calls = [call for call in responses.calls if call.request.method == "PUT"]
        assert len(put_calls) == 1
        assert json.loads(put_calls[0].request.body) == {"names": ["web-app", "ai"]}
