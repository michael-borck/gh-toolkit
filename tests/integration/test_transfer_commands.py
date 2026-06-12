"""Integration tests for transfer CLI commands."""

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app

GITHUB_API = "https://api.github.com"


def _mock_authenticated_user(login: str = "testuser") -> None:
    """Register the authenticated-user endpoint used by all transfer commands."""
    responses.add(
        responses.GET,
        f"{GITHUB_API}/user",
        json={"login": login, "id": 12345},
        status=200,
    )


def _sample_invitations() -> list[dict]:
    """Pending repository transfer invitations payload."""
    return [
        {
            "id": 101,
            "repository": {"full_name": "my-org/repo-one"},
            "inviter": {"login": "alice"},
            "permissions": "admin",
            "created_at": "2024-01-15T10:00:00Z",
        },
        {
            "id": 202,
            "repository": {"full_name": "other-org/repo-two"},
            "inviter": {"login": "bob"},
            "permissions": "write",
            "created_at": "2024-02-20T12:30:00Z",
        },
    ]


class TestTransferHelp:
    """Test help output for transfer commands."""

    def test_transfer_help(self):
        """Test transfer subcommand help lists all commands."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "--help"])

        assert result.exit_code == 0
        assert "Transfer management commands" in result.stdout
        assert "initiate" in result.stdout
        assert "list" in result.stdout
        assert "accept" in result.stdout

    def test_transfer_initiate_help(self):
        """Test transfer initiate help shows flags."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "initiate", "--help"])

        assert result.exit_code == 0
        assert "Initiate repository transfers" in result.stdout
        assert "--file" in result.stdout
        assert "--new-name" in result.stdout
        assert "--token" in result.stdout
        assert "--dry-run" in result.stdout

    def test_transfer_list_help(self):
        """Test transfer list help shows flags."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "list", "--help"])

        assert result.exit_code == 0
        assert "List pending repository transfers" in result.stdout
        assert "--org" in result.stdout
        assert "--token" in result.stdout

    def test_transfer_accept_help(self):
        """Test transfer accept help shows flags."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "accept", "--help"])

        assert result.exit_code == 0
        assert "Accept pending repository transfers" in result.stdout
        assert "--org" in result.stdout
        assert "--all" in result.stdout
        assert "--dry-run" in result.stdout


class TestTransferMissingToken:
    """Test error paths when no GitHub token is available."""

    def test_initiate_missing_token(self, no_env_vars):
        """Test transfer initiate without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "initiate", "testuser/repo", "dest-org"]
        )

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_list_missing_token(self, no_env_vars):
        """Test transfer list without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "list"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout

    def test_accept_missing_token(self, no_env_vars):
        """Test transfer accept without GitHub token."""
        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "accept"])

        assert result.exit_code == 1
        assert "GitHub token required" in result.stdout


class TestTransferInitiate:
    """Test transfer initiate command."""

    @responses.activate
    def test_initiate_missing_arguments(self, mock_github_token):
        """Test initiate without repo/destination or file."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "initiate", "--token", mock_github_token]
        )

        assert result.exit_code == 1
        assert "Must specify either repo and destination" in result.stdout

    @responses.activate
    def test_initiate_single_repo_dry_run(self, mock_github_token):
        """Test dry-run for a single repository transfer."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "testuser/my-repo",
                "dest-org",
                "--token",
                mock_github_token,
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Planned Repository Transfers" in result.stdout
        assert "testuser/my-repo" in result.stdout
        assert "dest-org" in result.stdout
        assert "Dry run mode" in result.stdout

    @responses.activate
    def test_initiate_legacy_comma_format_dry_run(self, mock_github_token):
        """Test dry-run with legacy 'owner/repo,destination' format."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "testuser/my-repo,dest-org",
                "--token",
                mock_github_token,
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "testuser/my-repo" in result.stdout
        assert "dest-org" in result.stdout
        assert "Dry run mode" in result.stdout

    @responses.activate
    def test_initiate_single_repo_success(self, mock_github_token):
        """Test a successful single repository transfer."""
        _mock_authenticated_user()
        responses.add(
            responses.POST,
            f"{GITHUB_API}/repos/testuser/my-repo/transfer",
            json={
                "name": "my-repo",
                "full_name": "dest-org/my-repo",
                "html_url": "https://github.com/dest-org/my-repo",
            },
            status=202,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "testuser/my-repo",
                "dest-org",
                "--token",
                mock_github_token,
            ],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Transfer initiated" in result.stdout
        assert "Successful: 1" in result.stdout
        assert "Failed" not in result.stdout
        assert "require acceptance" in result.stdout

    @responses.activate
    def test_initiate_single_repo_with_new_name(self, mock_github_token):
        """Test transfer with --new-name sends new_name in payload."""
        _mock_authenticated_user()
        responses.add(
            responses.POST,
            f"{GITHUB_API}/repos/testuser/my-repo/transfer",
            json={
                "name": "renamed-repo",
                "full_name": "dest-org/renamed-repo",
                "html_url": "https://github.com/dest-org/renamed-repo",
            },
            status=202,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "testuser/my-repo",
                "dest-org",
                "--new-name",
                "renamed-repo",
                "--token",
                mock_github_token,
            ],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Successful: 1" in result.stdout
        assert "renamed-repo" in result.stdout

        # Verify the transfer request body included the new name
        transfer_calls = [
            call for call in responses.calls if call.request.url.endswith("/transfer")
        ]
        assert len(transfer_calls) == 1
        assert b'"new_owner": "dest-org"' in transfer_calls[0].request.body
        assert b'"new_name": "renamed-repo"' in transfer_calls[0].request.body

    @responses.activate
    def test_initiate_cancelled_at_confirmation(self, mock_github_token):
        """Test that answering 'n' at the prompt cancels the transfer."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "testuser/my-repo",
                "dest-org",
                "--token",
                mock_github_token,
            ],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Transfer cancelled" in result.stdout

    @responses.activate
    def test_initiate_invalid_repo_format(self, mock_github_token):
        """Test transfer with repo missing 'owner/' prefix is counted as failed."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "no-owner-repo",
                "dest-org",
                "--token",
                mock_github_token,
            ],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Invalid repository format" in result.stdout
        assert "Failed: 1" in result.stdout

    @responses.activate
    def test_initiate_file_not_found(self, mock_github_token):
        """Test initiate with non-existent CSV file."""
        _mock_authenticated_user()

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "--file",
                "nonexistent_transfers.csv",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 1
        assert "not found" in result.stdout

    @responses.activate
    def test_initiate_csv_dry_run(self, tmp_path, mock_github_token):
        """Test dry-run bulk transfer from a CSV file (example_transfers.csv format)."""
        _mock_authenticated_user()

        csv_file = tmp_path / "transfers.csv"
        csv_file.write_text(
            "# Example repository transfer file\n"
            "# Format: owner/repo,destination_org,new_name\n"
            "user/my-python-project,my-org,\n"
            "user/data-analysis-tool,my-org,analysis-toolkit\n"
            "org1/shared-library,org2,\n"
            "# Lines starting with # are ignored\n"
            "user/skip-this-repo,\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "--file",
                str(csv_file),
                "--token",
                mock_github_token,
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        # Row with empty destination is skipped with a warning
        assert "Warning" in result.stdout
        assert "Planned Repository Transfers" in result.stdout
        assert "user/my-python-project" in result.stdout
        assert "analysis-toolkit" in result.stdout
        assert "org1/shared-library" in result.stdout
        assert "skip-this-repo" not in result.stdout.split("Planned")[1]
        assert "Dry run mode" in result.stdout

    @responses.activate
    def test_initiate_csv_partial_failure(self, tmp_path, mock_github_token):
        """Test bulk transfer where one repo succeeds and another 404s."""
        _mock_authenticated_user()
        responses.add(
            responses.POST,
            f"{GITHUB_API}/repos/user/good-repo/transfer",
            json={
                "name": "good-repo",
                "full_name": "my-org/good-repo",
                "html_url": "https://github.com/my-org/good-repo",
            },
            status=202,
        )
        responses.add(
            responses.POST,
            f"{GITHUB_API}/repos/user/missing-repo/transfer",
            json={"message": "Not Found"},
            status=404,
        )

        csv_file = tmp_path / "transfers.csv"
        csv_file.write_text("user/good-repo,my-org,\nuser/missing-repo,my-org,\n")

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "initiate",
                "--file",
                str(csv_file),
                "--token",
                mock_github_token,
            ],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Transfer initiated" in result.stdout
        assert "Failed to transfer" in result.stdout
        assert "Successful: 1" in result.stdout
        assert "Failed: 1" in result.stdout


class TestTransferList:
    """Test transfer list command."""

    @responses.activate
    def test_list_no_pending_transfers(self, mock_github_token):
        """Test list when there are no pending transfers."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "list", "--token", mock_github_token])

        assert result.exit_code == 0
        assert "Checking transfers for user: testuser" in result.stdout
        assert "No pending repository transfers found" in result.stdout

    @responses.activate
    def test_list_with_pending_transfers(self, mock_github_token):
        """Test list shows pending transfer invitations."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(app, ["transfer", "list", "--token", mock_github_token])

        assert result.exit_code == 0
        assert "my-org/repo-one" in result.stdout
        assert "other-org/repo-two" in result.stdout
        assert "alice" in result.stdout
        assert "bob" in result.stdout
        assert "2024-01-15" in result.stdout
        assert "Found 2 pending transfer(s)" in result.stdout

    @responses.activate
    def test_list_filtered_by_org(self, mock_github_token):
        """Test list with --org filters transfers to that organization."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "list", "--org", "my-org", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "my-org/repo-one" in result.stdout
        assert "other-org/repo-two" not in result.stdout
        assert "Found 1 pending repository transfer(s)" in result.stdout
        assert "Filtered from 2 total pending transfers" in result.stdout

    @responses.activate
    def test_list_org_filter_no_matches(self, mock_github_token):
        """Test list with --org that matches no transfers."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "list",
                "--org",
                "unrelated-org",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "No pending repository transfers found for organization" in result.stdout
        assert "Found 2 transfer(s) for other organizations" in result.stdout


class TestTransferAccept:
    """Test transfer accept command."""

    @responses.activate
    def test_accept_no_pending_transfers(self, mock_github_token):
        """Test accept when there are no pending transfers."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=[],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "accept", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "No pending repository transfers found" in result.stdout

    @responses.activate
    def test_accept_dry_run(self, mock_github_token):
        """Test accept dry-run shows transfers without accepting."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "accept", "--dry-run", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "Transfers to Accept" in result.stdout
        assert "my-org/repo-one" in result.stdout
        assert "2 transfer(s) would be accepted" in result.stdout
        # Only GET requests were made (user info + invitations)
        assert all(call.request.method == "GET" for call in responses.calls)

    @responses.activate
    def test_accept_all_transfers(self, mock_github_token):
        """Test accepting all pending transfers with --all (no confirmation)."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/101",
            status=204,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/202",
            status=204,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "accept", "--all", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "Accepted transfer" in result.stdout
        assert "Successful: 2" in result.stdout
        assert "Failed" not in result.stdout

    @responses.activate
    def test_accept_with_confirmation(self, mock_github_token):
        """Test accepting transfers after confirming the prompt."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=[_sample_invitations()[0]],
            status=200,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/101",
            status=204,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["transfer", "accept", "--token", mock_github_token],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Successful: 1" in result.stdout

    @responses.activate
    def test_accept_cancelled_at_confirmation(self, mock_github_token):
        """Test answering 'n' at the prompt cancels acceptance."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=[_sample_invitations()[0]],
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["transfer", "accept", "--token", mock_github_token],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Transfer acceptance cancelled" in result.stdout

    @responses.activate
    def test_accept_filtered_by_org(self, mock_github_token):
        """Test accept with --org only accepts that organization's transfers."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/101",
            status=204,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "accept",
                "--org",
                "my-org",
                "--all",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Filtered to 1 transfer(s) for organization 'my-org'" in result.stdout
        assert "Successful: 1" in result.stdout
        # Only invitation 101 was accepted
        patch_calls = [
            call for call in responses.calls if call.request.method == "PATCH"
        ]
        assert len(patch_calls) == 1
        assert patch_calls[0].request.url.endswith("/101")

    @responses.activate
    def test_accept_org_filter_no_matches(self, mock_github_token):
        """Test accept with --org that matches no transfers."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "transfer",
                "accept",
                "--org",
                "unrelated-org",
                "--all",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert (
            "No pending transfers found for organization 'unrelated-org'"
            in result.stdout
        )

    @responses.activate
    def test_accept_partial_failure(self, mock_github_token):
        """Test acceptance where one invitation succeeds and another 404s."""
        _mock_authenticated_user()
        responses.add(
            responses.GET,
            f"{GITHUB_API}/user/repository_invitations",
            json=_sample_invitations(),
            status=200,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/101",
            status=204,
        )
        responses.add(
            responses.PATCH,
            f"{GITHUB_API}/user/repository_invitations/202",
            json={"message": "Not Found"},
            status=404,
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["transfer", "accept", "--all", "--token", mock_github_token]
        )

        assert result.exit_code == 0
        assert "Successful: 1" in result.stdout
        assert "Failed: 1" in result.stdout
