"""Integration tests for CLI commands."""

import json

import responses
from typer.testing import CliRunner

from gh_toolkit import __version__
from gh_toolkit.cli import app


class TestCLIIntegration:
    """Test CLI command integration."""

    def test_cli_help(self):
        """Test main CLI help."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "gh-toolkit" in result.stdout
        assert "GitHub repository portfolio management" in result.stdout

    def test_repo_help(self):
        """Test repo subcommand help."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "--help"])

        assert result.exit_code == 0
        assert "Repository management commands" in result.stdout
        assert "list" in result.stdout
        assert "extract" in result.stdout
        assert "tag" in result.stdout
        assert "health" in result.stdout
        assert "clone" in result.stdout

    def test_invite_help(self):
        """Test invite subcommand help."""
        runner = CliRunner()
        result = runner.invoke(app, ["invite", "--help"])

        assert result.exit_code == 0
        assert "Invitation management commands" in result.stdout
        assert "accept" in result.stdout
        assert "leave" in result.stdout

    def test_site_help(self):
        """Test site subcommand help."""
        runner = CliRunner()
        result = runner.invoke(app, ["site", "--help"])

        assert result.exit_code == 0
        assert "Site generation commands" in result.stdout
        assert "generate" in result.stdout

    def test_version_command(self):
        """Test version command."""
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "gh-toolkit version" in result.stdout
        assert __version__ in result.stdout

    def test_info_command(self):
        """Test info command."""
        runner = CliRunner()
        result = runner.invoke(app, ["info"])

        assert result.exit_code == 0
        assert "gh-toolkit Information" in result.stdout
        assert "Version" in result.stdout
        assert __version__ in result.stdout

    @responses.activate
    def test_repo_list_missing_token(self, no_env_vars):
        """Test repo list command warns but proceeds without GitHub token."""
        # Authenticated-user lookup fails without a token
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "Requires authentication"},
            status=401,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser",
            json={"login": "testuser", "type": "User"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(app, ["repo", "list", "testuser"])

        assert result.exit_code == 0
        assert "No GitHub token provided" in result.stdout
        assert "No repositories found" in result.stdout

    def test_repo_tag_missing_token(self, no_env_vars):
        """Test repo tag command without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "tag", "testuser/repo"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_invite_accept_missing_token(self, no_env_vars):
        """Test invite accept command without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["invite", "accept"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_site_generate_missing_file(self):
        """Test site generate command with missing file."""
        runner = CliRunner()
        result = runner.invoke(app, ["site", "generate", "nonexistent.json"])

        assert result.exit_code == 1
        assert "Repository data file not found" in result.stdout

    def test_site_generate_with_valid_data(self, tmp_path):
        """Test site generation with valid data."""
        # Create test data file
        repos_data = [
            {
                "name": "test-repo",
                "description": "A test repository",
                "url": "https://github.com/user/test-repo",
                "stars": 10,
                "forks": 2,
                "category": "Python Package",
                "topics": ["python", "test"],
                "languages": ["Python"],
                "license": "MIT",
            }
        ]

        data_file = tmp_path / "repos.json"
        data_file.write_text(json.dumps(repos_data))

        output_file = tmp_path / "output.html"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "site",
                "generate",
                str(data_file),
                "--output",
                str(output_file),
                "--theme",
                "educational",
            ],
        )

        assert result.exit_code == 0
        assert "Portfolio site generated successfully" in result.stdout
        assert output_file.exists()

        content = output_file.read_text()
        assert "test-repo" in content
        assert "Educational Tools Collection" in content

    @responses.activate
    def test_repo_list_integration(self, mock_github_token):
        """Test repo list command integration."""
        # Mock user info check
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser",
            json={"login": "testuser", "type": "User"},
            status=200,
        )
        # Mock GitHub API response - page 1
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[
                {
                    "name": "repo1",
                    "full_name": "testuser/repo1",
                    "description": "First repo",
                    "stargazers_count": 10,
                    "forks_count": 2,
                    "language": "Python",
                    "private": False,
                    "archived": False,
                },
                {
                    "name": "repo2",
                    "full_name": "testuser/repo2",
                    "description": "Second repo",
                    "stargazers_count": 5,
                    "forks_count": 1,
                    "language": "JavaScript",
                    "private": False,
                    "archived": False,
                },
            ],
            status=200,
        )
        # Mock empty page 2 to stop pagination
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["repo", "list", "testuser", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "repo1" in result.stdout
        assert "repo2" in result.stdout
        assert "Found 2 repositories" in result.stdout

    @responses.activate
    def test_repo_list_json_output(self, mock_github_token):
        """`repo list --json` emits clean, parseable JSON on stdout."""
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser",
            json={"login": "testuser", "type": "User"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[
                {
                    "name": "repo1",
                    "full_name": "testuser/repo1",
                    "description": "First repo",
                    "stargazers_count": 10,
                    "forks_count": 2,
                    "language": "Python",
                    "html_url": "https://github.com/testuser/repo1",
                    "topics": ["cli"],
                    "private": False,
                    "archived": False,
                },
            ],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["repo", "list", "testuser", "--json", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)  # stdout must be valid JSON, status on stderr
        assert isinstance(data, list)
        assert data[0]["name"] == "repo1"
        assert data[0]["stars"] == 10
        assert data[0]["url"] == "https://github.com/testuser/repo1"
        assert data[0]["topics"] == ["cli"]

    def test_workflow_integration(self, tmp_path):
        """Test full workflow: extract -> site generation."""
        # Step 1: Create mock extracted data (simulating repo extract output)
        extracted_data = [
            {
                "name": "python-cli",
                "description": "A Python CLI tool",
                "url": "https://github.com/user/python-cli",
                "stars": 25,
                "forks": 5,
                "category": "Desktop Application",
                "category_confidence": 0.85,
                "topics": ["python", "cli", "tool"],
                "languages": ["Python", "Shell"],
                "license": "MIT",
            },
            {
                "name": "web-dashboard",
                "description": "A React dashboard application",
                "url": "https://github.com/user/web-dashboard",
                "stars": 67,
                "forks": 12,
                "category": "Web Application",
                "category_confidence": 0.92,
                "topics": ["react", "dashboard", "web"],
                "languages": ["JavaScript", "CSS", "HTML"],
                "license": "Apache-2.0",
            },
        ]

        data_file = tmp_path / "extracted_repos.json"
        data_file.write_text(json.dumps(extracted_data))

        # Step 2: Generate site from extracted data
        site_file = tmp_path / "portfolio.html"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "site",
                "generate",
                str(data_file),
                "--output",
                str(site_file),
                "--theme",
                "portfolio",
                "--title",
                "My Projects",
                "--description",
                "My awesome software projects",
            ],
        )

        assert result.exit_code == 0
        assert site_file.exists()

        content = site_file.read_text()

        # Verify content from both repos
        assert "python-cli" in content
        assert "web-dashboard" in content
        assert "My Projects" in content
        assert "My awesome software projects" in content

        # Verify categories
        assert "Desktop Application" in content
        assert "Web Application" in content

        # Verify interactive features
        assert "searchInput" in content
        assert "filterByCategory" in content

        # Verify styling
        assert "Tailwind" in content or "tailwindcss" in content
        assert "indigo" in content  # Portfolio theme accent color

    def test_repo_health_help(self):
        """Test repo health command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "health", "--help"])

        assert result.exit_code == 0
        assert "Check repository health" in result.stdout
        assert "--rules" in result.stdout
        assert "--min-score" in result.stdout
        assert "--output" in result.stdout

    def test_repo_health_missing_token(self, no_env_vars):
        """Test repo health command without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "health", "testuser/repo"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    @responses.activate
    def test_repo_health_single_repo(self, mock_github_token):
        """Test health check for single repository."""
        # Mock repository API response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "full_name": "testuser/test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 5,
                "forks_count": 1,
                "watchers_count": 3,
                "size": 1024,
                "license": {"name": "MIT"},
                "topics": ["python", "test"],
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
                "homepage": "https://test-repo.example.com",
                "has_issues": True,
                "has_releases": False,
                "archived": False,
                "fork": False,
                "private": False,
            },
            status=200,
        )

        # Mock README API response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            json={
                "content": "IyBUZXN0IFJlcG8KCkEgc2ltcGxlIHRlc3QgcmVwb3NpdG9yeS4=",  # base64 for "# Test Repo\n\nA simple test repository."
                "size": 35,
            },
            status=200,
        )

        # Mock contents API response - page 1
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents",
            json=[
                {"name": "README.md", "type": "file"},
                {"name": ".gitignore", "type": "file"},
                {"name": "src", "type": "dir"},
                {"name": "tests", "type": "dir"},
            ],
            status=200,
        )
        # Mock contents API response - page 2 (empty to stop pagination)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents",
            json=[],
            status=200,
        )

        # Mock workflows API response - page 1
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/actions/workflows",
            json={"workflows": [{"name": "CI", "state": "active"}]},
            status=200,
        )
        # Mock workflows API response - page 2 (empty to stop pagination)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/actions/workflows",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["repo", "health", "testuser/test-repo", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "testuser/test-repo" in result.stdout
        assert "Grade:" in result.stdout
        assert "Category Breakdown:" in result.stdout

    @responses.activate
    def test_repo_health_json_output(self, mock_github_token):
        """`repo health --json` emits clean, parseable JSON on stdout."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "full_name": "testuser/test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 5,
                "forks_count": 1,
                "watchers_count": 3,
                "size": 1024,
                "license": {"name": "MIT"},
                "topics": ["python", "test"],
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
                "homepage": "https://test-repo.example.com",
                "has_issues": True,
                "has_releases": False,
                "archived": False,
                "fork": False,
                "private": False,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            json={
                "content": "IyBUZXN0IFJlcG8KCkEgc2ltcGxlIHRlc3QgcmVwb3NpdG9yeS4=",
                "size": 35,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents",
            json=[{"name": "README.md", "type": "file"}],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents",
            json=[],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/actions/workflows",
            json={"workflows": [{"name": "CI", "state": "active"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/actions/workflows",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                "testuser/test-repo",
                "--json",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)  # stdout must be valid JSON
        assert isinstance(data, list)
        assert data[0]["repository"] == "testuser/test-repo"
        assert "percentage" in data[0]
        assert "grade" in data[0]
        assert isinstance(data[0]["checks"], list)

    def test_repo_health_file_input(self, tmp_path, mock_github_token):
        """Test health check with file input."""
        # Create test repo list file
        repo_file = tmp_path / "repos.txt"
        repo_file.write_text("testuser/repo1\ntestuser/repo2\n")

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                str(repo_file),
                "--token",
                mock_github_token,
                "--no-details",  # Simplify output for test
            ],
        )

        # Should fail because repos don't exist, but should process the file
        assert "Reading repository list" in result.stdout
        assert "testuser/repo1" in result.stdout or "Failed to check" in result.stdout

    def test_repo_health_rules_option(self, mock_github_token):
        """Test health check with different rule sets."""
        runner = CliRunner()

        # Test academic rules
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                "testuser/repo",
                "--token",
                mock_github_token,
                "--rules",
                "academic",
            ],
        )
        assert "Rule set: academic" in result.stdout

        # Test professional rules
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                "testuser/repo",
                "--token",
                mock_github_token,
                "--rules",
                "professional",
            ],
        )
        assert "Rule set: professional" in result.stdout

    def test_repo_health_min_score_filtering(self, mock_github_token):
        """Test health check with minimum score filtering."""
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                "testuser/repo",
                "--token",
                mock_github_token,
                "--min-score",
                "90",
                "--only-failed",
            ],
        )

        assert "Minimum score threshold: 90%" in result.stdout

    def test_repo_health_output_options(self, tmp_path, mock_github_token):
        """Test health check output options."""
        output_file = tmp_path / "health_report.json"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "health",
                "testuser/repo",
                "--token",
                mock_github_token,
                "--output",
                str(output_file),
                "--no-details",
                "--no-fixes",
            ],
        )

        # Should mention output file even if health check fails
        assert str(output_file) in result.stdout or "Failed to check" in result.stdout

    def test_repo_health_invalid_repo_format(self, mock_github_token):
        """Test health check with invalid repository format."""
        runner = CliRunner()
        result = runner.invoke(
            app, ["repo", "health", "invalid-repo-format", "--token", mock_github_token]
        )

        assert result.exit_code == 1
        assert "Repository must be in 'owner/repo' format" in result.stdout

    def test_repo_clone_help(self):
        """Test repo clone command help."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "clone", "--help"])

        assert result.exit_code == 0
        assert "Clone GitHub repositories" in result.stdout
        assert "--target-dir" in result.stdout
        assert "--parallel" in result.stdout
        assert "--branch" in result.stdout
        assert "--depth" in result.stdout
        assert "--dry-run" in result.stdout

    def test_repo_clone_invalid_format(self):
        """Test clone command with invalid repository format."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "clone", "invalid-format"])

        assert result.exit_code == 1
        assert "Error:" in result.stdout

    def test_repo_clone_single_repo_dry_run(self, tmp_path):
        """Test cloning single repository in dry-run mode."""
        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run mode" in result.stdout
        assert "Clone Preview" in result.stdout
        assert "microsoft/vscode" in result.stdout
        assert "Would clone" in result.stdout

    def test_repo_clone_file_input_dry_run(self, tmp_path):
        """Test cloning from file input in dry-run mode."""
        # Create test repo list file
        repo_file = tmp_path / "repos.txt"
        repo_file.write_text(
            "microsoft/vscode\nfacebook/react\n# Comment\n\npython/cpython\n"
        )

        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Reading repository list" in result.stdout
        assert "Found 3 repository(ies) to clone" in result.stdout
        assert "Clone Preview" in result.stdout
        assert "microsoft/vscode" in result.stdout
        assert "facebook/react" in result.stdout
        assert "python/cpython" in result.stdout

    def test_repo_clone_with_options_dry_run(self, tmp_path):
        """Test clone command with various options in dry-run mode."""
        target_dir = tmp_path / "custom_repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--branch",
                "main",
                "--depth",
                "1",
                "--parallel",
                "2",
                "--ssh",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Target directory:" in result.stdout
        # Rich wraps long paths across lines; join before asserting
        assert str(target_dir) in result.stdout.replace("\n", "")
        assert "Parallel operations: 2" in result.stdout
        assert "Branch: main" in result.stdout
        assert "Clone depth: 1" in result.stdout
        assert "git@github.com:microsof" in result.stdout  # Truncated in table

    def test_repo_clone_force_https_dry_run(self, tmp_path):
        """Test clone command forcing HTTPS in dry-run mode."""
        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--https",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "https://github.com/micr" in result.stdout  # Truncated in table

    def test_repo_clone_missing_git(self, tmp_path, monkeypatch):
        """Test clone command when git is not available."""
        target_dir = tmp_path / "repos"

        # Mock subprocess.run to simulate git not found
        def mock_run(*args, **kwargs):
            if args[0][0] == "git" and args[0][1] == "--version":
                raise FileNotFoundError("git command not found")
            return type(
                "MockResult", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()

        import subprocess

        monkeypatch.setattr(subprocess, "run", mock_run)

        runner = CliRunner()
        result = runner.invoke(
            app, ["repo", "clone", "microsoft/vscode", "--target-dir", str(target_dir)]
        )

        assert result.exit_code == 1
        assert "Git is not available" in result.stdout

    def test_repo_clone_nonexistent_file(self):
        """Test clone command with non-existent file."""
        runner = CliRunner()
        result = runner.invoke(app, ["repo", "clone", "nonexistent_file.txt"])

        assert result.exit_code == 1
        assert "Invalid repository format" in result.stdout

    def test_repo_clone_empty_file(self, tmp_path):
        """Test clone command with empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("# Only comments\n\n")

        runner = CliRunner()
        result = runner.invoke(app, ["repo", "clone", str(empty_file)])

        assert result.exit_code == 1
        assert "Error reading file" in result.stdout

    def test_repo_clone_url_formats(self, tmp_path):
        """Test clone command with different URL formats in dry-run mode."""
        repo_file = tmp_path / "repo_urls.txt"
        repo_file.write_text("""
# Different URL formats
microsoft/vscode
https://github.com/facebook/react
git@github.com:python/cpython.git
https://github.com/django/django.git
""")

        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "microsoft/vscode" in result.stdout
        assert "facebook/react" in result.stdout
        assert "python/cpython" in result.stdout
        assert "django/django" in result.stdout

    def test_repo_clone_existing_directory_preview(self, tmp_path):
        """Test clone preview with existing directories."""
        target_dir = tmp_path / "repos"

        # Create existing directory structure
        existing_repo = target_dir / "microsoft" / "vscode"
        existing_repo.mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "(exists)" in result.stdout

    def test_repo_clone_skip_vs_overwrite_options(self, tmp_path):
        """Test skip vs overwrite options in dry-run mode."""
        repo_file = tmp_path / "repos.txt"
        repo_file.write_text("microsoft/vscode\nfacebook/react\n")

        target_dir = tmp_path / "repos"

        # Test with skip-existing (default)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--skip-existing",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert (
            "skip-existing" in result.stdout
            or "Found 2 repository(ies)" in result.stdout
        )

        # Test with overwrite
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--overwrite",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Found 2 repository(ies)" in result.stdout

    def test_repo_clone_error_handling_options(self, tmp_path):
        """Test error handling options in dry-run mode."""
        target_dir = tmp_path / "repos"

        # Test continue on error (default)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--continue",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

        # Test fail-fast
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--fail-fast",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

    def test_repo_clone_cleanup_options(self, tmp_path):
        """Test cleanup options in dry-run mode."""
        target_dir = tmp_path / "repos"

        # Test with cleanup (default)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--cleanup",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

        # Test without cleanup
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                "microsoft/vscode",
                "--target-dir",
                str(target_dir),
                "--no-cleanup",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

    def test_repo_clone_estimate_disk_space(self, tmp_path):
        """Test disk space estimation in dry-run mode."""
        repo_file = tmp_path / "many_repos.txt"
        repos = [f"user{i}/repo{i}" for i in range(50)]
        repo_file.write_text("\n".join(repos))

        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Estimated disk space:" in result.stdout
        assert "MB" in result.stdout or "GB" in result.stdout

    def test_repo_clone_organization_structure(self, tmp_path):
        """Test organization structure preview."""
        repo_file = tmp_path / "repos.txt"
        repo_file.write_text("microsoft/vscode\nmicrosoft/typescript\nfacebook/react\n")

        target_dir = tmp_path / "repos"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "repo",
                "clone",
                str(repo_file),
                "--target-dir",
                str(target_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Organization: owner/repository directory structure" in result.stdout
        assert "microsoft/vscode" in result.stdout
        assert "microsoft/typescri" in result.stdout  # Truncated in table
        assert "facebook/react" in result.stdout
