"""Unit tests for GitHubClient."""

import json
import time

import pytest
import responses
from requests.exceptions import RequestException

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient


class TestGitHubClient:
    """Test GitHubClient functionality."""

    def test_init_with_token(self, mock_github_token):
        """Test client initialization with token."""
        client = GitHubClient(mock_github_token)
        assert client.token == mock_github_token
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == f"token {mock_github_token}"

    def test_init_without_token(self, no_env_vars):
        """Test client initialization without token."""
        client = GitHubClient()
        assert client.token is None
        assert "Authorization" not in client.headers

    @responses.activate
    def test_make_request_success(self, mock_github_token):
        """Test successful API request."""
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "testuser"},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        response = client._make_request("GET", "/user")
        result = response.json()
        assert result["login"] == "testuser"

    @responses.activate
    def test_make_request_404_error(self, mock_github_token):
        """Test 404 error handling."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/nonexistent",
            json={"message": "Not Found"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        with pytest.raises(GitHubAPIError) as exc_info:
            client._make_request("GET", "/repos/user/nonexistent")

        assert "404" in str(exc_info.value)
        assert "Not Found" in exc_info.value.message

    @responses.activate
    def test_rate_limit_handling(self, mock_github_token, mocker):
        """Test rate limit handling with retry."""
        # First request hits rate limit
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "API rate limit exceeded"},
            status=403,
            headers={"X-RateLimit-Reset": str(int(time.time()) + 1)},
        )

        # Second request succeeds
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "testuser"},
            status=200,
        )

        client = GitHubClient(mock_github_token)

        # pytest-mock provides the mocker fixture
        mock_sleep = mocker.patch("time.sleep")
        response = client._make_request("GET", "/user")
        result = response.json()
        assert result["login"] == "testuser"
        mock_sleep.assert_called_once()

    @responses.activate
    def test_get_user_info(self, mock_github_token):
        """Test getting user information."""
        user_data = {
            "login": "testuser",
            "id": 12345,
            "name": "Test User",
            "email": "test@example.com",
        }

        responses.add(
            responses.GET, "https://api.github.com/user", json=user_data, status=200
        )

        client = GitHubClient(mock_github_token)
        result = client.get_user_info()
        assert result == user_data

    @responses.activate
    def test_get_repo_info(self, mock_github_token, sample_repo_data):
        """Test getting repository information."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json=sample_repo_data,
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_repo_info("testuser", "test-repo")
        assert result == sample_repo_data

    @responses.activate
    def test_get_user_repos(self, mock_github_token, sample_user_repos):
        """Test getting user repositories."""
        # Page 1 returns data
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=sample_user_repos,
            status=200,
        )
        # Page 2 returns empty to stop pagination
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_user_repos("testuser")
        assert result == sample_user_repos

    @responses.activate
    def test_set_repo_archived(self, mock_github_token):
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )

        client = GitHubClient(mock_github_token)

        assert client.set_repo_archived("user", "repo", False) is True
        assert json.loads(responses.calls[0].request.body) == {"archived": False}

    @responses.activate
    def test_get_repo_languages(self, mock_github_token, sample_languages):
        """Test getting repository languages."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json=sample_languages,
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_repo_languages("testuser", "test-repo")
        assert result == sample_languages

    @responses.activate
    def test_get_repo_topics(self, mock_github_token, sample_repo_topics):
        """Test getting repository topics."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json=sample_repo_topics,
            status=200,
            headers={"Accept": "application/vnd.github.mercy-preview+json"},
        )

        client = GitHubClient(mock_github_token)
        result = client.get_repo_topics("testuser", "test-repo")
        assert result == sample_repo_topics["names"]

    @responses.activate
    def test_get_paginated_repos(self, mock_github_token):
        """Test paginated repository fetching."""
        # Page 1
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[{"name": "repo1"}, {"name": "repo2"}],
            status=200,
            headers={
                "Link": '<https://api.github.com/users/testuser/repos?page=2>; rel="next"'
            },
        )

        # Page 2
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[{"name": "repo3"}],
            status=200,
        )

        # Page 3 returns empty to stop pagination
        responses.add(
            responses.GET,
            "https://api.github.com/users/testuser/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_user_repos("testuser")
        assert len(result) == 3
        assert [r["name"] for r in result] == ["repo1", "repo2", "repo3"]

    @responses.activate
    def test_network_error_handling(self, mock_github_token):
        """Test network error handling."""
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            body=RequestException("Network error"),
        )

        client = GitHubClient(mock_github_token)
        with pytest.raises(GitHubAPIError) as exc_info:
            client._make_request("GET", "/user")

        assert "Network error" in str(exc_info.value)

    def test_github_api_error_creation(self):
        """Test GitHubAPIError creation."""
        error = GitHubAPIError("Test error", 404)
        assert str(error) == "GitHub API Error (404): Test error"
        assert error.status_code == 404
        assert error.message == "Test error"

    # Transfer functionality tests

    @responses.activate
    def test_transfer_repository_success(self, mock_github_token):
        """Test successful repository transfer."""
        transfer_response = {
            "id": 123456789,
            "name": "test-repo",
            "full_name": "dest-org/test-repo",
            "description": "A transferred repository",
            "private": False,
            "html_url": "https://github.com/dest-org/test-repo",
            "clone_url": "https://github.com/dest-org/test-repo.git",
            "ssh_url": "git@github.com:dest-org/test-repo.git",
            "owner": {"id": 987654321, "login": "dest-org", "type": "Organization"},
            "created_at": "2023-01-01T10:00:00Z",
            "updated_at": "2023-12-01T10:00:00Z",
        }

        responses.add(
            responses.POST,
            "https://api.github.com/repos/testuser/test-repo/transfer",
            json=transfer_response,
            status=202,
        )

        client = GitHubClient(mock_github_token)
        result = client.transfer_repository("testuser", "test-repo", "dest-org")

        assert result["name"] == "test-repo"
        assert result["full_name"] == "dest-org/test-repo"
        assert result["owner"]["login"] == "dest-org"

        # Verify request payload
        request = responses.calls[0].request
        import json

        payload = json.loads(request.body)
        assert payload == {"new_owner": "dest-org"}

    @responses.activate
    def test_transfer_repository_with_new_name(self, mock_github_token):
        """Test repository transfer with new name."""
        transfer_response = {
            "id": 123456789,
            "name": "new-repo-name",
            "full_name": "dest-org/new-repo-name",
            "description": "A transferred repository",
            "private": False,
            "html_url": "https://github.com/dest-org/new-repo-name",
            "clone_url": "https://github.com/dest-org/new-repo-name.git",
            "ssh_url": "git@github.com:dest-org/new-repo-name.git",
            "owner": {"id": 987654321, "login": "dest-org", "type": "Organization"},
            "created_at": "2023-01-01T10:00:00Z",
            "updated_at": "2023-12-01T10:00:00Z",
        }

        responses.add(
            responses.POST,
            "https://api.github.com/repos/testuser/test-repo/transfer",
            json=transfer_response,
            status=202,
        )

        client = GitHubClient(mock_github_token)
        result = client.transfer_repository(
            "testuser", "test-repo", "dest-org", "new-repo-name"
        )

        assert result["name"] == "new-repo-name"
        assert result["full_name"] == "dest-org/new-repo-name"

        # Verify request payload includes new_name
        request = responses.calls[0].request
        import json

        payload = json.loads(request.body)
        assert payload == {"new_owner": "dest-org", "new_name": "new-repo-name"}

    @responses.activate
    def test_transfer_repository_error(self, mock_github_token):
        """Test repository transfer error handling."""
        responses.add(
            responses.POST,
            "https://api.github.com/repos/testuser/test-repo/transfer",
            json={"message": "Repository not found or access denied"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        with pytest.raises(GitHubAPIError) as exc_info:
            client.transfer_repository("testuser", "test-repo", "dest-org")

        assert "Repository not found or access denied" in str(exc_info.value)
        assert exc_info.value.status_code == 404

    @responses.activate
    def test_get_repository_transfers(self, mock_github_token):
        """Test getting repository transfers."""
        invitations_response = [
            {
                "id": 123,
                "repository": {
                    "id": 456,
                    "name": "test-repo",
                    "full_name": "testuser/test-repo",
                },
                "invitee": {"id": 789, "login": "dest-user"},
                "inviter": {"id": 101112, "login": "source-user"},
                "permissions": "write",
                "created_at": "2023-12-01T10:00:00Z",
            }
        ]

        responses.add(
            responses.GET,
            "https://api.github.com/user/repository_invitations",
            json=invitations_response,
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_repository_transfers()

        assert len(result) == 1
        assert result[0]["id"] == 123
        assert result[0]["repository"]["name"] == "test-repo"
        assert result[0]["permissions"] == "write"

    @responses.activate
    def test_get_organization_transfers(self, mock_github_token):
        """Test getting organization transfers."""
        org_invitations_response = [
            {
                "id": 456,
                "login": "invited-user",
                "email": "user@example.com",
                "role": "direct_member",
                "created_at": "2023-12-01T10:00:00Z",
                "inviter": {"id": 789, "login": "admin-user"},
                "team_count": 2,
                "invitation_teams_url": "https://api.github.com/organizations/123/invitations/456/teams",
            }
        ]

        # Page 1 returns data
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/invitations",
            json=org_invitations_response,
            status=200,
        )
        # Page 2 returns empty to stop pagination
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/invitations",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_organization_transfers("test-org")

        assert len(result) == 1
        assert result[0]["id"] == 456
        assert result[0]["login"] == "invited-user"
        assert result[0]["role"] == "direct_member"

    @responses.activate
    def test_get_organization_transfers_error(self, mock_github_token):
        """Test organization transfers error handling."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/private-org/invitations",
            json={"message": "Not Found"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_organization_transfers("private-org")

        # Should return empty list on error
        assert result == []

    # Organization methods tests

    @responses.activate
    def test_get_user_organizations(self, mock_github_token):
        """Test getting user organizations."""
        orgs_response = [
            {
                "login": "org-one",
                "id": 1001,
                "description": "First organization",
                "url": "https://api.github.com/orgs/org-one",
            },
            {
                "login": "org-two",
                "id": 1002,
                "description": "Second organization",
                "url": "https://api.github.com/orgs/org-two",
            },
        ]

        responses.add(
            responses.GET,
            "https://api.github.com/user/orgs",
            json=orgs_response,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user/orgs",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_user_organizations()

        assert len(result) == 2
        assert result[0]["login"] == "org-one"
        assert result[1]["login"] == "org-two"

    @responses.activate
    def test_get_org_info(self, mock_github_token):
        """Test getting organization information."""
        org_response = {
            "login": "test-org",
            "id": 12345,
            "description": "A test organization",
            "html_url": "https://github.com/test-org",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            "blog": "https://test-org.example.com",
            "location": "San Francisco",
            "public_repos": 50,
        }

        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org",
            json=org_response,
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.get_org_info("test-org")

        assert result["login"] == "test-org"
        assert result["description"] == "A test organization"
        assert result["public_repos"] == 50

    @responses.activate
    def test_get_org_info_not_found(self, mock_github_token):
        """Test getting organization information for non-existent org."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/nonexistent-org",
            json={"message": "Not Found"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        with pytest.raises(GitHubAPIError) as exc_info:
            client.get_org_info("nonexistent-org")

        assert "404" in str(exc_info.value)
        assert "Not Found" in exc_info.value.message

    # Repository description tests

    @responses.activate
    def test_update_repo_description_success(self, mock_github_token):
        """Test successful repository description update."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/testuser/test-repo",
            json={"description": "New description"},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        result = client.update_repo_description(
            "testuser", "test-repo", "New description"
        )

        assert result is True

        # Verify request payload
        request = responses.calls[0].request
        import json

        payload = json.loads(request.body)
        assert payload == {"description": "New description"}

    @responses.activate
    def test_update_repo_description_truncates_long(self, mock_github_token):
        """Test that long descriptions are truncated to 250 chars."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/testuser/test-repo",
            json={"description": "A" * 250},
            status=200,
        )

        long_description = "A" * 300  # 300 chars

        client = GitHubClient(mock_github_token)
        result = client.update_repo_description(
            "testuser", "test-repo", long_description
        )

        assert result is True

        # Verify description was truncated
        request = responses.calls[0].request
        import json

        payload = json.loads(request.body)
        assert len(payload["description"]) == 250

    @responses.activate
    def test_update_repo_description_error(self, mock_github_token):
        """Test repository description update error handling."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/testuser/test-repo",
            json={"message": "Not Found"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        result = client.update_repo_description(
            "testuser", "test-repo", "New description"
        )

        assert result is False


class TestOwnerRepoHelpers:
    """Tests for owner/org detection and topic updates."""

    @responses.activate
    def test_get_repos_for_owner_detects_organization(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/users/acme",
            json={"login": "acme", "type": "Organization"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=[{"name": "org-repo"}],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/acme/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        repos = client.get_repos_for_owner("acme")

        assert repos == [{"name": "org-repo"}]

    @responses.activate
    def test_get_repos_for_owner_detects_user(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/users/alice",
            json={"login": "alice", "type": "User"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/alice/repos",
            json=[{"name": "user-repo"}],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/users/alice/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        repos = client.get_repos_for_owner("alice")

        assert repos == [{"name": "user-repo"}]

    @responses.activate
    def test_set_repo_topics(self, mock_github_token):
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/user/repo/topics",
            json={"names": ["python"]},
            status=200,
        )

        client = GitHubClient(mock_github_token)

        assert client.set_repo_topics("user", "repo", ["python"]) is True
