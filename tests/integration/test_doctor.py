"""Integration tests for gh-toolkit doctor."""

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app


class TestDoctor:
    def test_missing_token(self, no_env_vars):
        result = CliRunner().invoke(app, ["doctor"])

        assert result.exit_code == 1
        assert "GitHub token" in result.stdout
        assert "missing" in result.stdout

    @responses.activate
    def test_valid_token(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "testuser"},
            headers={"X-OAuth-Scopes": "repo, read:org"},
            status=200,
        )

        result = CliRunner().invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "testuser" in result.stdout
        assert "repo, read:org" in result.stdout

    @responses.activate
    def test_invalid_token(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "Bad credentials"},
            status=401,
        )

        result = CliRunner().invoke(app, ["doctor"])

        assert result.exit_code == 1
        assert "invalid" in result.stdout
