"""Integration tests for `org` and `portfolio` CLI commands."""

import json
from typing import Any

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app

GITHUB_API = "https://api.github.com"


def make_repo(
    name: str,
    org: str = "test-org",
    description: str | None = "A test repository",
    language: str | None = "Python",
    stars: int = 10,
    forks: int = 2,
    fork: bool = False,
    archived: bool = False,
    private: bool = False,
    topics: list[str] | None = None,
    license_spdx: str | None = "MIT",
) -> dict[str, Any]:
    """Build a GitHub API repository payload."""
    return {
        "name": name,
        "full_name": f"{org}/{name}",
        "description": description,
        "language": language,
        "stargazers_count": stars,
        "forks_count": forks,
        "watchers_count": stars,
        "fork": fork,
        "archived": archived,
        "private": private,
        "topics": topics if topics is not None else ["python", "cli"],
        "license": {"spdx_id": license_spdx} if license_spdx else None,
        "html_url": f"https://github.com/{org}/{name}",
        "homepage": None,
        "has_pages": False,
    }


def mock_org_info(org: str = "test-org", **overrides: Any) -> None:
    """Register the GET /orgs/{org} endpoint."""
    payload: dict[str, Any] = {
        "login": org,
        "description": "A test organization",
        "blog": "https://example.com",
        "location": "Earth",
        "public_repos": 2,
        "avatar_url": f"https://avatars.githubusercontent.com/u/{org}",
    }
    payload.update(overrides)
    responses.add(
        responses.GET,
        f"{GITHUB_API}/orgs/{org}",
        json=payload,
        status=200,
    )


def mock_org_repos(repos: list[dict[str, Any]], org: str = "test-org") -> None:
    """Register paginated GET /orgs/{org}/repos (page 1 + empty page 2)."""
    responses.add(
        responses.GET,
        f"{GITHUB_API}/orgs/{org}/repos",
        json=repos,
        status=200,
    )
    responses.add(
        responses.GET,
        f"{GITHUB_API}/orgs/{org}/repos",
        json=[],
        status=200,
    )


def mock_authenticated_user() -> None:
    """Register the GET /user endpoint."""
    responses.add(
        responses.GET,
        f"{GITHUB_API}/user",
        json={"login": "testuser", "name": "Test User"},
        status=200,
    )


class TestOrgReadmeCommand:
    """Tests for `gh-toolkit org readme`."""

    def test_org_help(self):
        """Test org subcommand help."""
        runner = CliRunner()
        result = runner.invoke(app, ["org", "--help"])

        assert result.exit_code == 0
        assert "Organization management commands" in result.stdout
        assert "readme" in result.stdout

    @responses.activate
    def test_readme_dry_run(self, no_env_vars, mock_github_token):
        """Test dry-run preview with mocked org and repos endpoints."""
        mock_org_info()
        mock_org_repos(
            [
                make_repo("alpha-tool", stars=15),
                make_repo("beta-lib", stars=5, language="Rust"),
            ]
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["org", "readme", "test-org", "--dry-run", "--token", mock_github_token],
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Found 2 repositories" in result.stdout
        # Preview prints with markup disabled, so markdown links keep
        # their [name] part and repo names are visible
        assert "alpha-tool" in result.stdout
        assert "https://github.com/test-org/alpha-tool" in result.stdout

    @responses.activate
    def test_readme_writes_output_file(self, no_env_vars, mock_github_token, tmp_path):
        """Test README is written to the requested output path."""
        mock_org_info()
        mock_org_repos([make_repo("alpha-tool", stars=15)])

        output_file = tmp_path / "README.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "org",
                "readme",
                "test-org",
                "--output",
                str(output_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "README generated successfully" in result.stdout
        assert output_file.exists()

        content = output_file.read_text()
        assert "# test-org" in content
        assert "A test organization" in content
        assert "[alpha-tool](https://github.com/test-org/alpha-tool)" in content
        assert "## Stats" in content

    @responses.activate
    def test_readme_filters_forks_stars_archived(
        self, no_env_vars, mock_github_token, tmp_path
    ):
        """Test fork/min-stars/archived filtering of org repos."""
        mock_org_info()
        mock_org_repos(
            [
                make_repo("kept-repo", stars=10),
                make_repo("forked-repo", stars=50, fork=True),
                make_repo("lowstar-repo", stars=1),
                make_repo("archived-repo", stars=20, archived=True),
            ]
        )

        output_file = tmp_path / "README.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "org",
                "readme",
                "test-org",
                "--min-stars",
                "5",
                "--output",
                str(output_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Found 1 repositories" in result.stdout

        content = output_file.read_text()
        assert "kept-repo" in content
        assert "forked-repo" not in content
        assert "lowstar-repo" not in content
        assert "archived-repo" not in content

    @responses.activate
    def test_readme_max_repos_limit(self, no_env_vars, mock_github_token, tmp_path):
        """Test --max-repos keeps only the highest-starred repos."""
        mock_org_info()
        mock_org_repos(
            [
                make_repo("popular-repo", stars=100),
                make_repo("modest-repo", stars=3),
            ]
        )

        output_file = tmp_path / "README.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "org",
                "readme",
                "test-org",
                "--max-repos",
                "1",
                "--output",
                str(output_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0

        content = output_file.read_text()
        assert "popular-repo" in content
        assert "modest-repo" not in content

    @responses.activate
    def test_readme_minimal_template(self, no_env_vars, mock_github_token, tmp_path):
        """Test the minimal template output."""
        mock_org_info()
        mock_org_repos([make_repo("alpha-tool")])

        output_file = tmp_path / "README.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "org",
                "readme",
                "test-org",
                "--template",
                "minimal",
                "--output",
                str(output_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0

        content = output_file.read_text()
        assert "## Projects" in content
        assert "alpha-tool" in content

    def test_readme_invalid_template(self):
        """Test invalid template is rejected before any API call."""
        runner = CliRunner()
        result = runner.invoke(
            app, ["org", "readme", "test-org", "--template", "bogus"]
        )

        assert result.exit_code == 1
        assert "Invalid template" in result.stdout

    def test_readme_invalid_group_by(self):
        """Test invalid group-by is rejected before any API call."""
        runner = CliRunner()
        result = runner.invoke(
            app, ["org", "readme", "test-org", "--group-by", "bogus"]
        )

        assert result.exit_code == 1
        assert "Invalid group-by" in result.stdout

    @responses.activate
    def test_readme_nonexistent_org(self, no_env_vars, mock_github_token):
        """Test error path for an organization that does not exist."""
        responses.add(
            responses.GET,
            f"{GITHUB_API}/orgs/no-such-org",
            json={"message": "Not Found"},
            status=404,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["org", "readme", "no-such-org", "--token", mock_github_token]
        )

        assert result.exit_code == 1
        assert "Failed to get organization info" in result.stdout

    @responses.activate
    def test_readme_org_with_no_repos(self, no_env_vars, mock_github_token):
        """Test error path when the organization has no repositories."""
        mock_org_info()
        mock_org_repos([])

        runner = CliRunner()
        result = runner.invoke(
            app, ["org", "readme", "test-org", "--token", mock_github_token]
        )

        assert result.exit_code == 1
        assert "No repositories found" in result.stdout

    def test_readme_missing_token(self, no_env_vars):
        """Test org readme without a GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["org", "readme", "test-org"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    @responses.activate
    def test_readme_with_mocked_llm(
        self, mock_github_token, mock_anthropic_client, tmp_path
    ):
        """Test LLM path: non-JSON LLM reply falls back to rule-based text."""
        mock_org_info()
        mock_org_repos([make_repo("alpha-tool")])

        output_file = tmp_path / "README.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "org",
                "readme",
                "test-org",
                "--output",
                str(output_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert mock_anthropic_client.messages.create.called
        # Mocked LLM returns non-JSON text, so the fallback description is used
        content = output_file.read_text()
        assert "# test-org" in content
        assert "alpha-tool" in content


class TestPortfolioGenerateCommand:
    """Tests for `gh-toolkit portfolio generate`."""

    def test_portfolio_help(self):
        """Test portfolio subcommand help."""
        runner = CliRunner()
        result = runner.invoke(app, ["portfolio", "--help"])

        assert result.exit_code == 0
        assert "Portfolio generation commands" in result.stdout
        assert "generate" in result.stdout
        assert "audit" in result.stdout

    def test_generate_requires_org_or_discover(self):
        """Test generate fails without --org or --discover."""
        runner = CliRunner()
        result = runner.invoke(app, ["portfolio", "generate"])

        assert result.exit_code == 1
        assert "Specify --org names or use --discover" in result.stdout

    def test_generate_missing_token(self, no_env_vars):
        """Test generate without a GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["portfolio", "generate", "--org", "test-org"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_generate_invalid_theme(self):
        """Test generate rejects an invalid theme."""
        runner = CliRunner()
        result = runner.invoke(
            app, ["portfolio", "generate", "--org", "test-org", "--theme", "bogus"]
        )

        assert result.exit_code == 1
        assert "Invalid theme" in result.stdout

    @responses.activate
    def test_generate_writes_readme(self, no_env_vars, mock_github_token, tmp_path):
        """Test portfolio generate writes a README for a single org."""
        mock_org_info()
        mock_org_repos(
            [
                make_repo("alpha-tool", stars=15),
                make_repo("beta-lib", stars=5, language="Rust"),
            ]
        )
        mock_authenticated_user()

        readme_file = tmp_path / "PORTFOLIO.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "portfolio",
                "generate",
                "--org",
                "test-org",
                "--readme",
                str(readme_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Portfolio generated successfully" in result.stdout
        assert readme_file.exists()

        content = readme_file.read_text()
        assert "Test User's Project Portfolio" in content
        assert "### test-org" in content
        assert "[alpha-tool](https://github.com/test-org/alpha-tool)" in content
        assert "[beta-lib](https://github.com/test-org/beta-lib)" in content
        assert "| Total Projects | 2 |" in content

    @responses.activate
    def test_generate_with_html_output(self, no_env_vars, mock_github_token, tmp_path):
        """Test portfolio generate also writes an HTML portfolio."""
        mock_org_info()
        mock_org_repos([make_repo("alpha-tool", stars=15)])
        mock_authenticated_user()

        readme_file = tmp_path / "PORTFOLIO.md"
        html_file = tmp_path / "portfolio.html"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "portfolio",
                "generate",
                "--org",
                "test-org",
                "--readme",
                str(readme_file),
                "--html",
                str(html_file),
                "--theme",
                "resume",
                "--title",
                "My Portfolio",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert readme_file.exists()
        assert html_file.exists()

        html_content = html_file.read_text()
        assert "alpha-tool" in html_content
        assert "My Portfolio" in html_content

    @responses.activate
    def test_generate_discover_organizations(
        self, no_env_vars, mock_github_token, tmp_path
    ):
        """Test --discover pulls orgs from user memberships."""
        # Paginated GET /user/orgs
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/orgs",
            json=[{"login": "discovered-org"}],
            status=200,
        )
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/orgs",
            json=[],
            status=200,
        )
        mock_org_info(org="discovered-org")
        mock_org_repos(
            [make_repo("alpha-tool", org="discovered-org")], org="discovered-org"
        )
        mock_authenticated_user()

        readme_file = tmp_path / "PORTFOLIO.md"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "portfolio",
                "generate",
                "--discover",
                "--readme",
                str(readme_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "discovered-org" in result.stdout
        assert readme_file.exists()
        assert "### discovered-org" in readme_file.read_text()

    @responses.activate
    def test_generate_no_matching_repos(self, no_env_vars, mock_github_token):
        """Test generate when filters exclude every repo."""
        mock_org_info()
        mock_org_repos([make_repo("lowstar-repo", stars=1)])

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "portfolio",
                "generate",
                "--org",
                "test-org",
                "--min-stars",
                "100",
                "--token",
                mock_github_token,
            ],
        )

        assert "No repositories found matching criteria" in result.stdout
        assert result.exit_code == 0
        assert "Unexpected error" not in result.stdout


class TestPortfolioAuditCommand:
    """Tests for `gh-toolkit portfolio audit`."""

    def test_audit_requires_source(self):
        """Test audit fails without --org, --discover, or --user."""
        runner = CliRunner()
        result = runner.invoke(app, ["portfolio", "audit"])

        assert result.exit_code == 1
        assert "Specify --org names" in result.stdout

    def test_audit_missing_token(self, no_env_vars):
        """Test audit without a GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["portfolio", "audit", "--org", "test-org"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    @responses.activate
    def test_audit_org_with_json_output(self, no_env_vars, mock_github_token, tmp_path):
        """Test audit flags missing metadata and writes a JSON report."""
        mock_org_repos(
            [
                make_repo("clean-repo"),
                make_repo(
                    "bad-repo",
                    description=None,
                    topics=[],
                    license_spdx=None,
                ),
            ]
        )

        report_file = tmp_path / "audit-report.json"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "portfolio",
                "audit",
                "--org",
                "test-org",
                "--output",
                str(report_file),
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Portfolio Audit Report" in result.stdout
        assert "Audit report saved" in result.stdout
        assert report_file.exists()

        report = json.loads(report_file.read_text())
        assert report["total_repos"] == 2
        assert report["repos_with_issues"] == 1
        assert report["summary"]["missing_description"] == 1
        assert report["summary"]["missing_topics"] == 1
        assert report["summary"]["missing_license"] == 1
        issue_repos = {issue["repo"] for issue in report["issues"]}
        assert issue_repos == {"test-org/bad-repo"}

    @responses.activate
    def test_audit_user_repos(self, no_env_vars, mock_github_token):
        """Test audit includes personal repositories with --user."""
        # Paginated GET /user/repos
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repos",
            json=[
                make_repo("personal-repo", org="testuser", description=None),
                make_repo("personal-fork", org="testuser", fork=True),
            ],
            status=200,
        )
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repos",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["portfolio", "audit", "--user", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "personal repositories" in result.stdout
        # Fork is excluded by default, so only one repo is audited
        assert "Total repositories: 1" in result.stdout
        assert "missing description" in result.stdout.replace("\n", " ")

    @responses.activate
    def test_audit_no_repos_found(self, no_env_vars, mock_github_token):
        """Test audit when no repos are found."""
        mock_org_repos([])

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["portfolio", "audit", "--org", "test-org", "--token", mock_github_token],
        )

        assert "No repositories found" in result.stdout
        assert result.exit_code == 0
        assert "Unexpected error" not in result.stdout
