"""Integration tests for gh-toolkit repo audit."""

import json

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app

REPOS = [
    {
        "name": "org-tool",
        "full_name": "user/org-tool",
        "description": "An organization tool for color analysis",
        "topics": ["python", "cli"],
        "private": False,
        "archived": False,
        "fork": False,
        "html_url": "https://github.com/user/org-tool",
    },
    {
        "name": "clean",
        "full_name": "user/clean",
        "description": "A clean repository.",
        "topics": ["python"],
        "private": False,
        "archived": False,
        "fork": False,
        "html_url": "https://github.com/user/clean",
    },
    {
        "name": "missing",
        "full_name": "user/missing",
        "description": None,
        "topics": [],
        "private": True,
        "archived": False,
        "fork": False,
        "html_url": "https://github.com/user/missing",
    },
]


def _add_user_repos() -> None:
    responses.add(
        responses.GET,
        "https://api.github.com/user/repos",
        json=REPOS,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/user/repos",
        json=[],
        status=200,
    )


class TestRepoAudit:
    @responses.activate
    def test_user_audit_json(self, mock_github_token):
        _add_user_repos()

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "audit",
                "--user",
                "--include-private",
                "--json",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        report = json.loads(result.stdout)
        assert report["format"] == "gh-toolkit-audit"
        assert report["summary"]["total"] == 3
        assert report["summary"]["missing_description"] == 1
        assert report["summary"]["with_spelling"] == 1
        assert report["summary"]["with_topic_issues"] == 1
        assert report["summary"]["clean"] == 1

    @responses.activate
    def test_backup_file(self, mock_github_token, tmp_path):
        _add_user_repos()
        backup_path = tmp_path / "backup.json"

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "audit",
                "--user",
                "--include-private",
                "--backup",
                str(backup_path),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        backup = json.loads(backup_path.read_text())
        assert backup["format"] == "gh-toolkit-backup"
        assert backup["version"] == 1
        assert backup["sources"] == {"user": True, "orgs": []}
        assert len(backup["repos"]) == 3
        by_name = {repo["full_name"]: repo for repo in backup["repos"]}
        assert by_name["user/org-tool"]["description"] == (
            "An organization tool for color analysis"
        )
        assert by_name["user/org-tool"]["topics"] == ["python", "cli"]

    @responses.activate
    def test_org_audit_filters_private_by_default(self, mock_github_token):
        org_repos = [
            {
                "name": "public-repo",
                "full_name": "acme/public-repo",
                "description": "Public repo",
                "topics": ["python"],
                "private": False,
            },
            {
                "name": "private-repo",
                "full_name": "acme/private-repo",
                "description": "Private repo",
                "topics": ["python"],
                "private": True,
            },
        ]
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=[],
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "audit",
                "--org",
                "acme",
                "--json",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        report = json.loads(result.stdout)
        assert report["summary"]["total"] == 1
        assert report["repos"][0]["full_name"] == "acme/public-repo"

    @responses.activate
    def test_org_audit_can_include_private(self, mock_github_token):
        org_repos = [
            {
                "name": "public-repo",
                "full_name": "acme/public-repo",
                "description": "Public repo",
                "topics": ["python"],
                "private": False,
            },
            {
                "name": "private-repo",
                "full_name": "acme/private-repo",
                "description": "Private repo",
                "topics": ["python"],
                "private": True,
            },
        ]
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=[],
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "audit",
                "--org",
                "acme",
                "--include-private",
                "--json",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        report = json.loads(result.stdout)
        assert report["summary"]["total"] == 2

    @responses.activate
    def test_output_file(self, mock_github_token, tmp_path):
        _add_user_repos()
        output_path = tmp_path / "audit.json"

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "audit",
                "--user",
                "--include-private",
                "--output",
                str(output_path),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        report = json.loads(output_path.read_text())
        assert report["summary"]["total"] == 3

    def test_missing_token(self, no_env_vars):
        result = CliRunner().invoke(app, ["repo", "audit", "--user"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_missing_source(self, mock_github_token):
        result = CliRunner().invoke(
            app, ["repo", "audit", "--token", mock_github_token]
        )

        assert result.exit_code == 1
        assert "specify --user, --org, or both" in result.stdout
