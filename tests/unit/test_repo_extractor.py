"""Unit tests for RepositoryExtractor."""

import pytest
import responses

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.repo_extractor import RepositoryExtractor


class TestRepositoryExtractor:
    """Test RepositoryExtractor functionality."""

    def test_init_with_anthropic_key(
        self, mock_github_token, mock_anthropic_key, mocker
    ):
        """Test RepositoryExtractor initialization with Anthropic key."""
        mock_anthropic_class = mocker.patch("anthropic.Anthropic")

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client, mock_anthropic_key)

        assert extractor.client == client
        assert extractor.anthropic_api_key == mock_anthropic_key
        mock_anthropic_class.assert_called_once_with(api_key=mock_anthropic_key)

    def test_init_without_anthropic_key(self, mock_github_token):
        """Test RepositoryExtractor initialization without Anthropic key."""
        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client, None)

        assert extractor.client == client
        assert extractor.anthropic_api_key is None
        assert extractor._anthropic_client is None

    def test_categorize_repository_fallback(self, mock_github_token):
        """Test rule-based categorization without LLM."""
        repo_data = {
            "name": "react-webapp",
            "description": "A React web application for e-commerce",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)  # No Anthropic key

        category, details = extractor._categorize_repository(
            repo_data, "", ["react", "javascript", "web"], {"JavaScript": 20000}
        )

        assert category == "Web Application"
        assert 0.0 < details["confidence"] <= 1.0
        assert details["reason"]

    def test_categorize_repository_python_package(self, mock_github_token):
        """Test categorization of Python package."""
        repo_data = {
            "name": "data-analysis-lib",
            "description": "A Python library for data analysis and visualization",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_repository(
            repo_data, "", ["python", "data-science"], {"Python": 15000}
        )

        assert category == "Python Package"
        assert details["confidence"] > 0.0

    def test_categorize_repository_native_language(self, mock_github_token):
        """Test categorization of repo in a native language."""
        repo_data = {
            "name": "git-helper",
            "description": "A helper for Git workflows",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_repository(
            repo_data, "", [], {"Go": 9000}
        )

        assert category == "Desktop Application"  # Native language fallback
        assert details["confidence"] > 0.0

    def test_categorize_repository_with_llm(
        self, mock_github_token, mock_anthropic_client
    ):
        """Test LLM-based categorization."""
        mock_response = mock_anthropic_client.messages.create.return_value
        mock_response.content[0].text = "Web Application"

        repo_data = {
            "name": "webapp",
            "description": "A web application",
            "language": "JavaScript",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client, "mock-key")
        extractor._anthropic_client = mock_anthropic_client

        category, details = extractor._categorize_repository(
            repo_data, "README content", ["react", "web"], {"JavaScript": 1000}
        )

        assert category == "Web Application"
        assert details["confidence"] == 0.9
        assert "LLM" in details["reason"]
        mock_anthropic_client.messages.create.assert_called_once()

    def test_categorize_repository_llm_fallback_on_error(
        self, mock_github_token, mock_anthropic_client
    ):
        """Test fallback when LLM throws exception."""
        mock_anthropic_client.messages.create.side_effect = Exception("API Error")

        repo_data = {
            "name": "python-tool",
            "description": "A Python library for things",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client, "mock-key")
        extractor._anthropic_client = mock_anthropic_client

        category, details = extractor._categorize_repository(
            repo_data, "", ["python"], {"Python": 1000}
        )

        # Should fall back to rule-based categorization
        assert category == "Python Package"
        assert details["confidence"] > 0.0

    def test_categorize_repository_llm_invalid_response(
        self, mock_github_token, mock_anthropic_client
    ):
        """Test handling of LLM response that isn't a valid category."""
        mock_response = mock_anthropic_client.messages.create.return_value
        mock_response.content[0].text = "Invalid response format"

        repo_data = {
            "name": "test-repo",
            "description": "Test repository",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client, "mock-key")
        extractor._anthropic_client = mock_anthropic_client

        category, details = extractor._categorize_repository(
            repo_data, "", ["python"], {"Python": 1000}
        )

        # Should fall back to rule-based categorization
        assert category == "Python Package"
        assert details["confidence"] > 0.0

    def test_rules_categorization_desktop_app(self, mock_github_token):
        """Test rule-based categorization for desktop applications."""
        repo_data = {
            "name": "electron-app",
            "description": "A desktop application built with Electron",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_with_rules(
            repo_data, "", ["electron", "desktop", "app"], {"JavaScript": 5000}
        )

        assert category == "Desktop Application"
        assert details["confidence"] > 0.0

    def test_rules_categorization_learning_resource(self, mock_github_token):
        """Test rule-based categorization for learning resources."""
        repo_data = {
            "name": "python-tutorial",
            "description": "Learn Python programming with examples and exercises",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_with_rules(
            repo_data, "", ["tutorial", "learning", "education"], {"Python": 1000}
        )

        assert category == "Learning Resource"
        assert details["confidence"] > 0.0

    def test_rules_categorization_notebook(self, mock_github_token):
        """Test rule-based categorization for notebooks."""
        repo_data = {
            "name": "data-analysis",
            "description": "Data analysis and visualization with Jupyter notebooks",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_with_rules(
            repo_data, "", [], {"Jupyter Notebook": 9000}
        )

        assert category == "Notebook/Analysis"
        assert details["confidence"] > 0.0

    def test_rules_categorization_other_tool(self, mock_github_token):
        """Test rule-based categorization for unrecognized repositories."""
        repo_data = {
            "name": "unknown-repo",
            "description": "Some unknown type of repository",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_with_rules(repo_data, "", [], {})

        assert category == "Other Tool"
        assert details["confidence"] > 0.0

    def test_rules_categorization_manual_override(self, mock_github_token):
        """Test manual category override via cat- topic."""
        repo_data = {
            "name": "anything",
            "description": "Whatever",
        }

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        category, details = extractor._categorize_with_rules(
            repo_data, "", ["cat-learning-resource"], {"Python": 100}
        )

        assert category == "Learning Resource"
        assert details["confidence"] == 1.0

    @responses.activate
    def test_extract_repository_data_success(self, mock_github_token):
        """Test successful repository data extraction."""
        # Mock repo info
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo",
            json={
                "name": "test-repo",
                "full_name": "testuser/test-repo",
                "description": "A test repository",
                "language": "Python",
                "stargazers_count": 42,
                "forks_count": 8,
                "watchers_count": 42,
                "open_issues_count": 3,
                "html_url": "https://github.com/testuser/test-repo",
                "homepage": "",
                "license": {"spdx_id": "MIT"},
                "private": False,
                "archived": False,
                "fork": False,
                "created_at": "2023-01-01T10:00:00Z",
                "updated_at": "2023-12-01T10:00:00Z",
                "pushed_at": "2023-12-01T10:00:00Z",
            },
            status=200,
        )

        # Mock README
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/readme",
            status=404,
        )

        # Mock releases
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/releases",
            json=[],
            status=200,
        )

        # Mock topics
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/topics",
            json={"names": ["python", "testing"]},
            status=200,
        )

        # Mock languages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/languages",
            json={"Python": 15000, "Shell": 500},
            status=200,
        )

        # Mock GitHub Pages
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/pages",
            status=404,
        )

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        result = extractor.extract_repository_data("testuser", "test-repo")

        assert result["name"] == "test-repo"
        assert result["full_name"] == "testuser/test-repo"
        assert result["description"] == "A test repository"
        assert result["primary_language"] == "Python"
        assert result["stars"] == 42
        assert result["forks"] == 8
        assert result["topics"] == ["python", "testing"]
        assert result["languages"] == ["Python", "Shell"]
        assert "category" in result
        assert "category_confidence" in result
        assert result["url"] == "https://github.com/testuser/test-repo"
        assert result["license"] == "MIT"
        assert result["pages_url"] is None
        assert result["is_fork"] is False

    @responses.activate
    def test_extract_repository_data_not_found(self, mock_github_token):
        """Test repository data extraction for non-existent repo."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/nonexistent",
            json={"message": "Not Found"},
            status=404,
        )

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        with pytest.raises(GitHubAPIError):
            extractor.extract_repository_data("testuser", "nonexistent")

    def test_extract_multiple_repositories(self, mock_github_token, mocker):
        """Test extraction of multiple repositories."""
        mock_extract = mocker.patch.object(
            RepositoryExtractor, "extract_repository_data"
        )
        mock_extract.side_effect = [
            {"name": "repo1", "category": "Web Application"},
            {"name": "repo2", "category": "Python Package"},
            GitHubAPIError("Not Found", 404),  # Failed extraction
        ]

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        repo_list = ["user/repo1", "user/repo2", "user/nonexistent"]
        results = extractor.extract_multiple_repositories(
            repo_list, show_progress=False
        )

        assert len(results) == 2  # Only successful extractions
        assert results[0]["name"] == "repo1"
        assert results[1]["name"] == "repo2"

    def test_extract_multiple_repositories_invalid_format(
        self, mock_github_token, mocker
    ):
        """Test that invalid 'owner/repo' strings are skipped."""
        mock_extract = mocker.patch.object(
            RepositoryExtractor, "extract_repository_data"
        )
        mock_extract.return_value = {"name": "repo1", "category": "Other Tool"}

        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        results = extractor.extract_multiple_repositories(
            ["not-a-repo-string", "user/repo1"], show_progress=False
        )

        assert len(results) == 1
        mock_extract.assert_called_once_with("user", "repo1")

    def test_confidence_scoring(self, mock_github_token):
        """Test confidence scoring for different scenarios."""
        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        # High confidence case - clear indicators
        high_confidence_repo = {
            "name": "django-webapp",
            "description": "A web application built with Django framework",
        }

        _category, details = extractor._categorize_with_rules(
            high_confidence_repo, "", ["django", "web", "webapp"], {"Python": 1000}
        )
        assert details["confidence"] >= 0.7  # Should be high confidence

        # Low confidence case - ambiguous
        low_confidence_repo = {
            "name": "utilities",
            "description": "Various utilities",
        }

        _category, details = extractor._categorize_with_rules(
            low_confidence_repo, "", [], {"Python": 1000}
        )
        assert details["confidence"] <= 0.6  # Should be lower confidence

    def test_download_links_extraction(self, mock_github_token):
        """Test platform download link extraction from releases."""
        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        releases = [
            {
                "tag_name": "v1.0.0",
                "assets": [
                    {
                        "name": "app-windows.exe",
                        "browser_download_url": "https://example.com/app.exe",
                    },
                    {
                        "name": "app-macos.dmg",
                        "browser_download_url": "https://example.com/app.dmg",
                    },
                    {
                        "name": "app-linux.deb",
                        "browser_download_url": "https://example.com/app.deb",
                    },
                ],
            }
        ]

        links = extractor._extract_download_links(releases)

        assert links["windows"] == "https://example.com/app.exe"
        assert links["mac"] == "https://example.com/app.dmg"
        assert links["linux"] == "https://example.com/app.deb"

        assert extractor._extract_download_links([]) == {}

    def test_latest_version_info(self, mock_github_token):
        """Test latest version extraction from releases."""
        client = GitHubClient(mock_github_token)
        extractor = RepositoryExtractor(client)

        releases = [
            {
                "tag_name": "v2.1.0",
                "name": "Release 2.1.0",
                "published_at": "2023-12-01T10:00:00Z",
                "prerelease": False,
                "draft": False,
            }
        ]

        version = extractor._get_latest_version_info(releases)

        assert version == {
            "tag": "v2.1.0",
            "name": "Release 2.1.0",
            "published": "2023-12-01T10:00:00Z",
            "prerelease": False,
            "draft": False,
        }

        assert extractor._get_latest_version_info([]) is None
