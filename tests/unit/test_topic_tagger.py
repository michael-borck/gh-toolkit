"""Unit tests for TopicTagger."""

import responses

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.topic_tagger import TopicTagger


class TestTopicTagger:
    """Test TopicTagger functionality."""

    def test_init_with_anthropic_key(
        self, mock_github_token, mock_anthropic_key, mocker
    ):
        """Test TopicTagger initialization with Anthropic key."""
        mock_anthropic_class = mocker.patch("anthropic.Anthropic")

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, mock_anthropic_key)

        assert tagger.client == client
        assert tagger.anthropic_api_key == mock_anthropic_key
        mock_anthropic_class.assert_called_once_with(api_key=mock_anthropic_key)

    def test_init_without_anthropic_key(self, mock_github_token):
        """Test TopicTagger initialization without Anthropic key."""
        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, None)

        assert tagger.client == client
        assert tagger.anthropic_api_key is None
        assert tagger._anthropic_client is None
        assert tagger.rate_limit == 0.5  # Default rate limit

    def test_init_custom_rate_limit(self, mock_github_token):
        """Test TopicTagger initialization with custom rate limit."""
        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, None, rate_limit=1.0)

        assert tagger.rate_limit == 1.0

    def test_init_anthropic_import_error(
        self, mock_github_token, mock_anthropic_key, mocker
    ):
        """Test handling of missing Anthropic package."""
        mocker.patch("anthropic.Anthropic", side_effect=ImportError)

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, mock_anthropic_key)

        assert tagger._anthropic_client is None

    @responses.activate
    def test_get_readme_content_success(self, mock_github_token):
        """Test successful README content retrieval."""
        readme_content = "VGVzdCBSRUFETUU="  # base64 encoded "Test README"

        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            json={"content": readme_content},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.get_readme_content("testuser", "test-repo")
        assert result == "Test README"

    @responses.activate
    def test_get_readme_content_not_found(self, mock_github_token):
        """Test README content retrieval when file not found."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.get_readme_content("testuser", "test-repo")
        assert result == ""

    def test_generate_fallback_topics_python(self, mock_github_token):
        """Test fallback topic generation for Python repository."""
        repo_data = {
            "name": "python-cli-tool",
            "description": "A command-line tool for data analysis",
            "language": "Python",
            "stargazers_count": 45,
            "forks_count": 12,
            "languages": {"Python": 15000, "Shell": 500},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        topics = tagger._generate_fallback_topics(repo_data)

        assert "python" in topics
        assert "cli" in topics
        assert "tool" in topics
        assert "data-science" in topics
        assert len(topics) <= 8

    def test_generate_fallback_topics_javascript(self, mock_github_token):
        """Test fallback topic generation for JavaScript web app."""
        repo_data = {
            "name": "react-webapp",
            "description": "A modern web application built with React",
            "language": "JavaScript",
            "stargazers_count": 123,
            "forks_count": 34,
            "languages": {"JavaScript": 20000, "CSS": 5000, "HTML": 3000},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        topics = tagger._generate_fallback_topics(repo_data)

        assert "javascript" in topics
        assert "web" in topics
        assert len(topics) <= 8

    def test_generate_topics_with_llm_success(
        self, mock_github_token, mock_anthropic_client
    ):
        """Test successful LLM topic generation."""
        repo_data = {
            "name": "test-repo",
            "description": "A test repository",
            "language": "Python",
            "stargazers_count": 10,
            "forks_count": 2,
            "languages": {"Python": 1000},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, "mock-key")
        tagger._anthropic_client = mock_anthropic_client

        topics = tagger.generate_topics_with_llm(repo_data, "Test README content")

        assert topics == ["python", "cli", "tool", "testing", "automation"]
        mock_anthropic_client.messages.create.assert_called_once()

    def test_max_topics_default_is_8(self, mock_github_token):
        """Default max_topics is 8."""
        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)
        assert tagger.max_topics == 8

    def test_max_topics_caps_llm_output(
        self, mock_github_token, mock_anthropic_client, mocker
    ):
        """max_topics caps the number of topics returned by the LLM."""
        many = ", ".join(f"topic{i}" for i in range(20))
        mock_anthropic_client.messages.create.return_value = mocker.Mock(
            content=[mocker.Mock(text=many)]
        )
        repo_data = {
            "name": "big-repo",
            "description": "A repo",
            "language": "Python",
            "stargazers_count": 1,
            "forks_count": 0,
            "languages": {"Python": 100},
        }
        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, "mock-key", max_topics=3)
        tagger._anthropic_client = mock_anthropic_client

        topics = tagger.generate_topics_with_llm(repo_data, "readme")
        assert len(topics) == 3
        assert topics == ["topic0", "topic1", "topic2"]

    def test_generate_topics_with_llm_fallback_on_error(
        self, mock_github_token, mock_anthropic_client
    ):
        """Test fallback when LLM throws exception."""
        mock_anthropic_client.messages.create.side_effect = Exception("API Error")

        repo_data = {
            "name": "python-tool",
            "description": "A Python tool",
            "language": "Python",
            "stargazers_count": 5,
            "forks_count": 1,
            "languages": {"Python": 1000},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, "mock-key")
        tagger._anthropic_client = mock_anthropic_client

        topics = tagger.generate_topics_with_llm(repo_data, "")

        # Should fall back to rule-based generation
        assert "python" in topics
        assert "tool" in topics

    def test_generate_topics_without_llm(self, mock_github_token):
        """Test topic generation without LLM client."""
        repo_data = {
            "name": "test-tool",
            "description": "A testing tool",
            "language": "Python",
            "stargazers_count": 5,
            "forks_count": 1,
            "languages": {"Python": 1000},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)  # No Anthropic key

        topics = tagger.generate_topics_with_llm(repo_data, "")

        assert "python" in topics
        assert "tool" in topics

    @responses.activate
    def test_get_repo_topics_success(self, mock_github_token):
        """Test successful repository topics retrieval."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": ["python", "cli", "tool"]},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        topics = tagger.get_repo_topics("testuser", "test-repo")
        assert topics == ["python", "cli", "tool"]

    @responses.activate
    def test_get_repo_topics_error(self, mock_github_token):
        """Test repository topics retrieval with API error."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        topics = tagger.get_repo_topics("testuser", "test-repo")
        assert topics == []

    @responses.activate
    def test_update_repo_topics_success(self, mock_github_token):
        """Test successful repository topics update."""
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": ["python", "cli", "testing"]},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.update_repo_topics(
            "testuser", "test-repo", ["python", "cli", "testing"]
        )
        assert result is True

    @responses.activate
    def test_update_repo_topics_failure(self, mock_github_token):
        """Test repository topics update failure."""
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/testuser/test-repo/topics",
            status=403,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.update_repo_topics("testuser", "test-repo", ["python", "cli"])
        assert result is False

    @responses.activate
    def test_process_repository_success(self, mock_github_token):
        """Test successful repository processing."""
        # Mock repo info
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
            },
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 1000},
            status=200,
        )

        # Mock current topics (empty)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": []},
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.process_repository("testuser", "test-repo", dry_run=True)

        assert result["status"] == "dry_run"
        assert "testuser/test-repo" in result["repo"]
        assert result["current_topics"] == []
        assert len(result["suggested_topics"]) > 0
        assert "python" in result["suggested_topics"]

    @responses.activate
    def test_process_repository_skipped_existing_topics(self, mock_github_token):
        """Test repository processing skipped due to existing topics."""
        # Mock repo info
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
            },
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 1000},
            status=200,
        )

        # Mock current topics (has topics)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": ["existing", "topics"]},
            status=200,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.process_repository(
            "testuser", "test-repo", dry_run=True, force=False
        )

        assert result["status"] == "skipped"
        assert result["current_topics"] == ["existing", "topics"]

    @responses.activate
    def test_process_repository_force_update(self, mock_github_token):
        """Test repository processing with force update."""
        # Mock repo info
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
            },
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 1000},
            status=200,
        )

        # Mock current topics (has topics)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": ["existing", "topic"]},
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.process_repository(
            "testuser", "test-repo", dry_run=True, force=True
        )

        assert result["status"] == "dry_run"
        assert result["current_topics"] == ["existing", "topic"]
        assert len(result["suggested_topics"]) > 0
        # Final topics should merge existing + suggested
        assert len(result["final_topics"]) > len(result["current_topics"])

    def test_process_multiple_repositories(self, mock_github_token, mocker):
        """Test processing multiple repositories."""
        mock_process = mocker.patch.object(TopicTagger, "process_repository")
        mock_process.side_effect = [
            {"status": "success", "repo": "user/repo1"},
            {"status": "skipped", "repo": "user/repo2"},
        ]

        mock_sleep = mocker.patch("time.sleep")

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        repo_list = [("user", "repo1"), ("user", "repo2")]
        results = tagger.process_multiple_repositories(repo_list, dry_run=True)

        assert len(results) == 2
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "skipped"
        mock_sleep.assert_called_once_with(0.5)  # Default rate limiting

    def test_process_multiple_repositories_custom_rate(self, mock_github_token, mocker):
        """Test processing with custom rate limit."""
        mock_process = mocker.patch.object(TopicTagger, "process_repository")
        mock_process.side_effect = [
            {"status": "success", "repo": "user/repo1"},
            {"status": "success", "repo": "user/repo2"},
        ]

        mock_sleep = mocker.patch("time.sleep")

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, rate_limit=1.5)

        repo_list = [("user", "repo1"), ("user", "repo2")]
        results = tagger.process_multiple_repositories(repo_list, dry_run=True)

        assert len(results) == 2
        mock_sleep.assert_called_once_with(1.5)

    def test_process_multiple_repositories_zero_rate(self, mock_github_token, mocker):
        """Test processing with zero rate limit (no sleep)."""
        mock_process = mocker.patch.object(TopicTagger, "process_repository")
        mock_process.side_effect = [
            {"status": "success", "repo": "user/repo1"},
            {"status": "success", "repo": "user/repo2"},
        ]

        mock_sleep = mocker.patch("time.sleep")

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, rate_limit=0)

        repo_list = [("user", "repo1"), ("user", "repo2")]
        results = tagger.process_multiple_repositories(repo_list, dry_run=True)

        assert len(results) == 2
        mock_sleep.assert_not_called()  # No sleep when rate_limit is 0

    def test_topic_validation(self, mock_github_token, mock_anthropic_client):
        """Test topic validation and filtering."""
        # Mock LLM response with invalid topics
        mock_response = mock_anthropic_client.messages.create.return_value
        mock_response.content[
            0
        ].text = "python, cli, tool, -invalid-, too-long-topic-name-that-exceeds-fifty-characters-limit, valid-topic"

        repo_data = {
            "name": "test-repo",
            "description": "Test repository",
            "language": "Python",
            "stargazers_count": 10,
            "forks_count": 2,
            "languages": {"Python": 1000},
        }

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client, "mock-key")
        tagger._anthropic_client = mock_anthropic_client

        topics = tagger.generate_topics_with_llm(repo_data, "")

        # Should filter out invalid topics
        assert "python" in topics
        assert "cli" in topics
        assert "tool" in topics
        assert "valid-topic" in topics
        assert "-invalid-" not in topics
        assert "too-long-topic-name-that-exceeds-fifty-characters-limit" not in topics

    @responses.activate
    def test_process_repository_warns_missing_description(self, mock_github_token):
        """Test that processing warns when description is missing."""
        # Mock repo info without description
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": None,  # Missing description
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
            },
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 1000},
            status=200,
        )

        # Mock current topics (empty)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": []},
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.process_repository("testuser", "test-repo", dry_run=True)

        assert result["status"] == "dry_run"
        assert "warnings" in result
        assert "missing_description" in result["warnings"]

    @responses.activate
    def test_process_repository_no_warning_with_description(self, mock_github_token):
        """Test that processing does not warn when description exists."""
        # Mock repo info with description
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "description": "A test repository",  # Has description
                "language": "Python",
                "stargazers_count": 10,
                "forks_count": 2,
            },
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 1000},
            status=200,
        )

        # Mock current topics (empty)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": []},
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        tagger = TopicTagger(client)

        result = tagger.process_repository("testuser", "test-repo", dry_run=True)

        assert result["status"] == "dry_run"
        assert "warnings" not in result or len(result.get("warnings", [])) == 0
