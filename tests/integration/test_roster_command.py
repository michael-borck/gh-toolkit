"""Integration tests for `gh-toolkit repo roster`."""

import json

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app

API = "https://api.github.com"


def _mock_repo_health(owner_repo: str, *, readme: bool = True):
    """Register the endpoints check_repository_health calls for one repo."""
    responses.add(
        responses.GET,
        f"{API}/repos/{owner_repo}",
        json={
            "name": owner_repo.split("/")[1],
            "full_name": owner_repo,
            "description": "A submission",
            "language": "Python",
            "stargazers_count": 0,
            "forks_count": 0,
            "watchers_count": 0,
            "size": 100,
            "license": {"name": "MIT"},
            "topics": ["python"],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-02-01T00:00:00Z",
            "pushed_at": "2024-02-01T00:00:00Z",
            "homepage": "",
            "has_issues": True,
            "has_releases": False,
            "archived": False,
            "fork": False,
            "private": False,
        },
        status=200,
    )
    if readme:
        responses.add(
            responses.GET,
            f"{API}/repos/{owner_repo}/readme",
            json={"content": "IyBSZXBv", "size": 6},  # "# Repo"
            status=200,
        )
    else:
        responses.add(responses.GET, f"{API}/repos/{owner_repo}/readme", status=404)
    for endpoint in ("contents", "actions/workflows"):
        responses.add(
            responses.GET, f"{API}/repos/{owner_repo}/{endpoint}", json=[], status=200
        )
        responses.add(
            responses.GET, f"{API}/repos/{owner_repo}/{endpoint}", json=[], status=200
        )


class TestRosterCommand:
    def test_help(self):
        result = CliRunner().invoke(app, ["repo", "roster", "--help"])
        assert result.exit_code == 0
        assert "Submission/hygiene report" in result.stdout
        assert "--repo-pattern" in result.stdout

    def test_missing_token(self, no_env_vars, tmp_path):
        roster = tmp_path / "roster.csv"
        roster.write_text("github\nalice\n")
        result = CliRunner().invoke(app, ["repo", "roster", str(roster)])
        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_missing_roster_file(self, mock_github_token):
        result = CliRunner().invoke(
            app, ["repo", "roster", "nope.csv", "--token", mock_github_token]
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_bad_roster_no_username_column(self, mock_github_token, tmp_path):
        roster = tmp_path / "roster.csv"
        roster.write_text("name,email\nAlice,a@x.com\n")
        result = CliRunner().invoke(
            app, ["repo", "roster", str(roster), "--token", mock_github_token]
        )
        assert result.exit_code == 1
        assert "GitHub username column" in result.stdout

    @responses.activate
    def test_json_report_submitted_and_missing(self, mock_github_token, tmp_path):
        # alice submitted (repo exists), bob did not (404)
        _mock_repo_health("myclass/lab1-alice", readme=True)
        responses.add(responses.GET, f"{API}/repos/myclass/lab1-bob", status=404)

        roster = tmp_path / "roster.csv"
        roster.write_text("name,github\nAlice,alice\nBob,bob\n")

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "roster",
                str(roster),
                "--org",
                "myclass",
                "--repo-pattern",
                "lab1-{github}",
                "--json",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)  # stdout must be clean JSON
        by_user = {r["github_username"]: r for r in data}
        assert by_user["alice"]["status"] == "found"
        assert by_user["alice"]["repository"] == "myclass/lab1-alice"
        assert by_user["alice"]["score_percent"] is not None
        assert by_user["bob"]["status"] == "not_found"
        assert by_user["bob"]["score_percent"] is None

    @responses.activate
    def test_csv_output_written(self, mock_github_token, tmp_path):
        _mock_repo_health("myclass/lab1-alice", readme=True)

        roster = tmp_path / "roster.csv"
        roster.write_text("name,github\nAlice,alice\n")
        out = tmp_path / "report.csv"

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "roster",
                str(roster),
                "--org",
                "myclass",
                "--repo-pattern",
                "lab1-{github}",
                "--output",
                str(out),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert out.exists()
        csv_text = out.read_text()
        assert "github_username" in csv_text  # header
        assert "alice" in csv_text
        # Console shows the summary table
        assert "Submitted:" in result.stdout

    def test_unresolved_when_no_org_or_pattern(self, mock_github_token, tmp_path):
        roster = tmp_path / "roster.csv"
        roster.write_text("github\nalice\n")
        result = CliRunner().invoke(
            app,
            [
                "repo",
                "roster",
                str(roster),
                "--json",
                "--token",
                mock_github_token,
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["status"] == "unresolved"
