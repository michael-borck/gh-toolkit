"""Unit tests for OrgReadmeGenerator."""

import pytest
import responses

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.readme_generator import OrgReadmeGenerator


@pytest.fixture
def sample_org_info():
    """Sample organization data for testing."""
    return {
        "login": "test-org",
        "id": 12345,
        "description": "A test organization for demonstration",
        "html_url": "https://github.com/test-org",
        "avatar_url": "https://avatars.githubusercontent.com/u/12345",
        "blog": "https://test-org.example.com",
        "location": "San Francisco, CA",
        "public_repos": 10,
        "name": "Test Organization",
        "email": "contact@test-org.example.com",
    }


@pytest.fixture
def sample_org_repos():
    """Sample organization repositories for testing."""
    return [
        {
            "name": "python-lib",
            "full_name": "test-org/python-lib",
            "description": "A Python library for testing",
            "language": "Python",
            "stargazers_count": 100,
            "forks_count": 25,
            "topics": ["python", "library", "testing"],
            "html_url": "https://github.com/test-org/python-lib",
            "private": False,
            "fork": False,
            "archived": False,
            "license": {"spdx_id": "MIT"},
        },
        {
            "name": "web-app",
            "full_name": "test-org/web-app",
            "description": "A web application built with React",
            "language": "JavaScript",
            "stargazers_count": 50,
            "forks_count": 10,
            "topics": ["react", "javascript", "web-app"],
            "html_url": "https://github.com/test-org/web-app",
            "private": False,
            "fork": False,
            "archived": False,
            "license": {"spdx_id": "Apache-2.0"},
        },
        {
            "name": "forked-repo",
            "full_name": "test-org/forked-repo",
            "description": "A forked repository",
            "language": "Python",
            "stargazers_count": 5,
            "forks_count": 1,
            "topics": [],
            "html_url": "https://github.com/test-org/forked-repo",
            "private": False,
            "fork": True,
            "archived": False,
            "license": None,
        },
    ]


class TestOrgReadmeGenerator:
    """Test OrgReadmeGenerator functionality."""

    def test_init_without_anthropic(self, mock_github_token):
        """Test initialization without Anthropic API key."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        assert generator.client == client
        assert generator._anthropic_client is None

    @responses.activate
    def test_fetch_org_repos(self, mock_github_token, sample_org_repos):
        """Test fetching organization repositories."""
        # Add initial response
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        # Add empty second page to end pagination
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = generator.fetch_org_repos("test-org")

        # Should exclude forks by default
        assert len(repos) == 2
        assert all(not r.get("fork") for r in repos)

    @responses.activate
    def test_fetch_org_repos_include_forks(self, mock_github_token, sample_org_repos):
        """Test fetching organization repositories including forks."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = generator.fetch_org_repos("test-org", exclude_forks=False)

        assert len(repos) == 3

    @responses.activate
    def test_fetch_org_repos_min_stars(self, mock_github_token, sample_org_repos):
        """Test fetching organization repositories with minimum stars filter."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = generator.fetch_org_repos("test-org", min_stars=60)

        # Only python-lib has 100 stars
        assert len(repos) == 1
        assert repos[0]["name"] == "python-lib"

    @responses.activate
    def test_fetch_org_repos_max_repos(self, mock_github_token, sample_org_repos):
        """Test fetching organization repositories with max repos limit."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = generator.fetch_org_repos("test-org", max_repos=1)

        assert len(repos) == 1
        # Should be sorted by stars, so python-lib should be first
        assert repos[0]["name"] == "python-lib"

    def test_categorize_repos_by_category(self, mock_github_token, sample_org_repos):
        """Test categorizing repositories by inferred category."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        # Use only non-forked repos
        repos = [r for r in sample_org_repos if not r.get("fork")]
        grouped = generator.categorize_repos(repos, group_by="category")

        assert len(grouped) > 0

    def test_categorize_repos_by_language(self, mock_github_token, sample_org_repos):
        """Test categorizing repositories by language."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = [r for r in sample_org_repos if not r.get("fork")]
        grouped = generator.categorize_repos(repos, group_by="language")

        assert "Python" in grouped
        assert "JavaScript" in grouped
        assert len(grouped["Python"]) == 1
        assert len(grouped["JavaScript"]) == 1

    def test_categorize_repos_by_topic(self, mock_github_token, sample_org_repos):
        """Test categorizing repositories by topic."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = [r for r in sample_org_repos if not r.get("fork")]
        grouped = generator.categorize_repos(repos, group_by="topic")

        # Uses first topic
        assert "python" in grouped or "react" in grouped

    def test_infer_category_library(self, mock_github_token):
        """Test inferring library category."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repo = {
            "name": "my-lib",
            "description": "A library for doing things",
            "language": "Python",
            "topics": ["library"],
        }

        category = generator.infer_category(repo)
        assert category == "Libraries"

    def test_infer_category_template(self, mock_github_token):
        """Test inferring template category."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repo = {
            "name": "python-template",
            "description": "A starter template for Python projects",
            "language": "Python",
            "topics": [],
        }

        category = generator.infer_category(repo)
        assert category == "Templates"

    def test_infer_category_web_app(self, mock_github_token):
        """Test inferring web application category."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repo = {
            "name": "my-site",
            "description": "A web app for managing tasks",
            "language": "JavaScript",
            "topics": ["web-app"],
        }

        category = generator.infer_category(repo)
        assert category == "Web Applications"

    def test_generate_fallback_description(
        self, mock_github_token, sample_org_info, sample_org_repos
    ):
        """Test generating fallback description without LLM."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        repos = [r for r in sample_org_repos if not r.get("fork")]
        description = generator._generate_fallback_description(sample_org_info, repos)

        assert "title" in description
        assert "tagline" in description
        assert "focus_areas" in description
        assert "mission" in description
        assert description["title"] == "test-org"

    @responses.activate
    def test_generate_readme_default_template(
        self, mock_github_token, sample_org_info, sample_org_repos
    ):
        """Test generating README with default template."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org",
            json=sample_org_info,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        readme = generator.generate_readme("test-org", template="default")

        # Check structure
        assert "# test-org" in readme
        assert "## Repositories" in readme
        assert "## Stats" in readme
        assert "gh-toolkit" in readme
        # Check repos are included
        assert "python-lib" in readme
        assert "web-app" in readme

    @responses.activate
    def test_generate_readme_minimal_template(
        self, mock_github_token, sample_org_info, sample_org_repos
    ):
        """Test generating README with minimal template."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org",
            json=sample_org_info,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        readme = generator.generate_readme("test-org", template="minimal")

        # Minimal template is simpler
        assert "# test-org" in readme
        assert "## Projects" in readme

    @responses.activate
    def test_generate_readme_detailed_template(
        self, mock_github_token, sample_org_info, sample_org_repos
    ):
        """Test generating README with detailed template."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org",
            json=sample_org_info,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        readme = generator.generate_readme("test-org", template="detailed")

        # Detailed template includes more info
        assert "# test-org" in readme
        assert "## About" in readme
        assert "## Statistics" in readme

    @responses.activate
    def test_generate_readme_no_stats(
        self, mock_github_token, sample_org_info, sample_org_repos
    ):
        """Test generating README without statistics."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org",
            json=sample_org_info,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=sample_org_repos,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        readme = generator.generate_readme("test-org", include_stats=False)

        # Stats section should not be present
        assert "## Stats" not in readme

    @responses.activate
    def test_generate_readme_no_repos_error(self, mock_github_token, sample_org_info):
        """Test error when organization has no repositories."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/empty-org",
            json=sample_org_info,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/empty-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        with pytest.raises(ValueError, match="No repositories found"):
            generator.generate_readme("empty-org")

    def test_save_readme(self, mock_github_token, tmp_path):
        """Test saving README to file."""
        client = GitHubClient(mock_github_token)
        generator = OrgReadmeGenerator(client)

        content = "# Test README\n\nThis is a test."
        output_path = tmp_path / "README.md"

        generator.save_readme(content, str(output_path))

        assert output_path.exists()
        assert output_path.read_text() == content
