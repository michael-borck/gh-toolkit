"""Unit tests for DescriptionGenerator."""

import responses

from gh_toolkit.core.description_generator import DescriptionGenerator
from gh_toolkit.core.github_client import GitHubClient


class TestDescriptionGenerator:
    """Test DescriptionGenerator functionality."""

    def test_init_with_anthropic_key(
        self, mock_github_token, mock_anthropic_key, mocker
    ):
        """Test DescriptionGenerator initialization with Anthropic key."""
        # Patch where Anthropic is imported from, not where it's used
        mock_anthropic_class = mocker.patch("anthropic.Anthropic")

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, mock_anthropic_key)

        assert generator.client == client
        assert generator.anthropic_api_key == mock_anthropic_key
        assert generator.rate_limit == 0.5
        mock_anthropic_class.assert_called_once_with(api_key=mock_anthropic_key)

    def test_init_without_anthropic_key(self, mock_github_token):
        """Test DescriptionGenerator initialization without Anthropic key."""
        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, None)

        assert generator.client == client
        assert generator.anthropic_api_key is None
        assert generator._anthropic_client is None

    def test_init_custom_rate_limit(self, mock_github_token):
        """Test DescriptionGenerator with custom rate limit."""
        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, None, rate_limit=1.0)

        assert generator.rate_limit == 1.0

    def test_generate_fallback_with_language(self, mock_github_token):
        """Test fallback description generation with language."""
        repo_data = {
            "name": "my-cool-project",
            "language": "Python",
            "topics": [],
        }

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        description = generator._generate_fallback(repo_data)

        assert "Python" in description
        assert "my cool project" in description

    def test_generate_fallback_with_topics(self, mock_github_token):
        """Test fallback description generation with topics."""
        repo_data = {
            "name": "test-repo",
            "language": "JavaScript",
            "topics": ["react", "typescript", "web-app"],
        }

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        description = generator._generate_fallback(repo_data)

        assert "JavaScript" in description
        assert "react" in description

    def test_generate_fallback_no_language(self, mock_github_token):
        """Test fallback description generation without language."""
        repo_data = {
            "name": "simple-project",
            "language": None,
            "topics": ["utility", "automation"],
        }

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        description = generator._generate_fallback(repo_data)

        assert "Project for utility" in description

    def test_generate_fallback_no_language_no_topics(self, mock_github_token):
        """Test fallback description generation with nothing."""
        repo_data = {
            "name": "my_project",
            "language": None,
            "topics": [],
        }

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        description = generator._generate_fallback(repo_data)

        assert "Project: my project" in description

    def test_generate_with_llm_success(self, mock_github_token, mocker):
        """Test successful LLM description generation."""
        mock_anthropic_client = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = [
            mocker.Mock(text="Manage GitHub repositories efficiently")
        ]
        mock_anthropic_client.messages.create.return_value = mock_response

        repo_data = {
            "name": "gh-toolkit",
            "language": "Python",
            "topics": ["github", "cli"],
        }

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, "mock-key")
        generator._anthropic_client = mock_anthropic_client

        description = generator._generate_with_llm(repo_data, "This is a CLI tool...")

        assert description == "Manage GitHub repositories efficiently"
        mock_anthropic_client.messages.create.assert_called_once()

    def test_generate_with_llm_strips_quotes(self, mock_github_token, mocker):
        """Test that LLM response quotes are stripped."""
        mock_anthropic_client = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = [mocker.Mock(text='"A quoted description"')]
        mock_anthropic_client.messages.create.return_value = mock_response

        repo_data = {"name": "test", "language": "Python", "topics": []}

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, "mock-key")
        generator._anthropic_client = mock_anthropic_client

        description = generator._generate_with_llm(repo_data, "")

        assert description == "A quoted description"

    def test_generate_with_llm_truncates_long(self, mock_github_token, mocker):
        """Test that LLM response is truncated to 250 chars."""
        mock_anthropic_client = mocker.Mock()
        long_desc = "A" * 300  # 300 chars
        mock_response = mocker.Mock()
        mock_response.content = [mocker.Mock(text=long_desc)]
        mock_anthropic_client.messages.create.return_value = mock_response

        repo_data = {"name": "test", "language": "Python", "topics": []}

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, "mock-key")
        generator._anthropic_client = mock_anthropic_client

        description = generator._generate_with_llm(repo_data, "")

        assert len(description) == 250

    def test_generate_with_llm_error_returns_none(self, mock_github_token, mocker):
        """Test that LLM errors return None."""
        mock_anthropic_client = mocker.Mock()
        mock_anthropic_client.messages.create.side_effect = Exception("API Error")

        repo_data = {"name": "test", "language": "Python", "topics": []}

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client, "mock-key")
        generator._anthropic_client = mock_anthropic_client

        description = generator._generate_with_llm(repo_data, "")

        assert description is None

    @responses.activate
    def test_update_description_success(self, mock_github_token):
        """Test successful description update."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/testuser/test-repo",
            json={"description": "New description"},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        result = generator.update_description(
            "testuser", "test-repo", "New description"
        )

        assert result is True

    def test_update_description_dry_run(self, mock_github_token):
        """Test description update in dry run mode."""
        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        result = generator.update_description(
            "testuser", "test-repo", "New description", dry_run=True
        )

        assert result is True

    @responses.activate
    def test_process_repository_success(self, mock_github_token):
        """Test successful repository processing."""
        # Mock repo info
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": None,
                "language": "Python",
                "topics": ["cli", "tool"],
            },
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        result = generator.process_repository("testuser", "test-repo", dry_run=True)

        assert result["status"] == "dry_run"
        assert result["repo"] == "testuser/test-repo"
        assert result["old_description"] is None
        assert result["new_description"] is not None

    @responses.activate
    def test_process_repository_skipped_has_description(self, mock_github_token):
        """Test repository processing skipped due to existing description."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "Existing description",
                "language": "Python",
            },
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        result = generator.process_repository(
            "testuser", "test-repo", dry_run=True, force=False
        )

        assert result["status"] == "skipped"
        assert result["old_description"] == "Existing description"

    @responses.activate
    def test_process_repository_force_update(self, mock_github_token):
        """Test repository processing with force update."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "Old description",
                "language": "Python",
                "topics": [],
            },
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        result = generator.process_repository(
            "testuser", "test-repo", dry_run=True, force=True
        )

        assert result["status"] == "dry_run"
        assert result["old_description"] == "Old description"
        assert result["new_description"] is not None

    def test_process_multiple_repositories(self, mock_github_token, mocker):
        """Test processing multiple repositories."""
        mock_process = mocker.patch.object(DescriptionGenerator, "process_repository")
        mock_process.side_effect = [
            {"status": "success", "repo": "user/repo1", "message": "Updated"},
            {"status": "skipped", "repo": "user/repo2", "message": "Skipped"},
        ]

        mock_sleep = mocker.patch("time.sleep")

        client = GitHubClient(mock_github_token)
        generator = DescriptionGenerator(client)

        repo_list = [("user", "repo1"), ("user", "repo2")]
        results = generator.process_multiple_repositories(repo_list, dry_run=True)

        assert len(results) == 2
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "skipped"
        mock_sleep.assert_called_once_with(0.5)  # Rate limiting
