"""Unit tests for PortfolioGenerator."""

import pytest
import responses

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.portfolio_generator import PortfolioGenerator


@pytest.fixture
def sample_user_orgs():
    """Sample user organizations data."""
    return [
        {
            "login": "org-one",
            "id": 1001,
            "description": "First organization",
            "url": "https://api.github.com/orgs/org-one",
            "html_url": "https://github.com/org-one",
            "avatar_url": "https://avatars.githubusercontent.com/u/1001",
        },
        {
            "login": "org-two",
            "id": 1002,
            "description": "Second organization",
            "url": "https://api.github.com/orgs/org-two",
            "html_url": "https://github.com/org-two",
            "avatar_url": "https://avatars.githubusercontent.com/u/1002",
        },
    ]


@pytest.fixture
def sample_multi_org_repos():
    """Sample repositories from multiple organizations."""
    return {
        "org-one": [
            {
                "name": "repo-a",
                "full_name": "org-one/repo-a",
                "description": "Repository A from org-one",
                "language": "Python",
                "stargazers_count": 100,
                "forks_count": 20,
                "topics": ["python", "api"],
                "html_url": "https://github.com/org-one/repo-a",
                "private": False,
                "fork": False,
                "archived": False,
                "license": {"spdx_id": "MIT"},
            },
            {
                "name": "repo-b",
                "full_name": "org-one/repo-b",
                "description": None,  # Missing description for audit
                "language": "JavaScript",
                "stargazers_count": 50,
                "forks_count": 10,
                "topics": [],  # Missing topics for audit
                "html_url": "https://github.com/org-one/repo-b",
                "private": False,
                "fork": False,
                "archived": False,
                "license": None,  # Missing license for audit
            },
        ],
        "org-two": [
            {
                "name": "repo-c",
                "full_name": "org-two/repo-c",
                "description": "Repository C from org-two",
                "language": "Go",
                "stargazers_count": 200,
                "forks_count": 40,
                "topics": ["golang", "cli"],
                "html_url": "https://github.com/org-two/repo-c",
                "private": False,
                "fork": False,
                "archived": False,
                "license": {"spdx_id": "Apache-2.0"},
            },
            {
                "name": "forked-repo",
                "full_name": "org-two/forked-repo",
                "description": "A forked repo",
                "language": "Python",
                "stargazers_count": 5,
                "forks_count": 1,
                "topics": [],
                "html_url": "https://github.com/org-two/forked-repo",
                "private": False,
                "fork": True,
                "archived": False,
                "license": None,
            },
        ],
    }


class TestPortfolioGenerator:
    """Test PortfolioGenerator functionality."""

    def test_init_without_anthropic(self, mock_github_token):
        """Test initialization without Anthropic API key."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        assert generator.client == client

    @responses.activate
    def test_discover_organizations(self, mock_github_token, sample_user_orgs):
        """Test discovering user organizations."""
        responses.add(
            responses.GET,
            "https://api.github.com/user/orgs",
            json=sample_user_orgs,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user/orgs",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        orgs = generator.discover_organizations()

        assert len(orgs) == 2
        assert orgs[0]["login"] == "org-one"
        assert orgs[1]["login"] == "org-two"

    @responses.activate
    def test_aggregate_repos(self, mock_github_token, sample_multi_org_repos):
        """Test aggregating repositories from multiple organizations."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=sample_multi_org_repos["org-one"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=[],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=sample_multi_org_repos["org-two"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = generator.aggregate_repos(["org-one", "org-two"])

        # Should exclude forks by default
        assert len(repos) == 3
        assert all(r.get("source_org") for r in repos)
        assert all("category" in r for r in repos)

    @responses.activate
    def test_aggregate_repos_include_forks(
        self, mock_github_token, sample_multi_org_repos
    ):
        """Test aggregating repositories including forks."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=sample_multi_org_repos["org-two"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = generator.aggregate_repos(["org-two"], exclude_forks=False)

        assert len(repos) == 2

    @responses.activate
    def test_aggregate_repos_min_stars(self, mock_github_token, sample_multi_org_repos):
        """Test aggregating repositories with minimum stars filter."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=sample_multi_org_repos["org-one"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=[],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=sample_multi_org_repos["org-two"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = generator.aggregate_repos(["org-one", "org-two"], min_stars=100)

        # Only repos with 100+ stars
        assert len(repos) == 2
        assert all(r["stargazers_count"] >= 100 for r in repos)

    @responses.activate
    def test_aggregate_repos_sorted_by_stars(
        self, mock_github_token, sample_multi_org_repos
    ):
        """Test that aggregated repositories are sorted by stars."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=sample_multi_org_repos["org-one"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-one/repos",
            json=[],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=sample_multi_org_repos["org-two"],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/org-two/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = generator.aggregate_repos(["org-one", "org-two"])

        # Should be sorted by stars descending
        stars = [r["stargazers_count"] for r in repos]
        assert stars == sorted(stars, reverse=True)

    def test_audit_repos(self, mock_github_token):
        """Test auditing repositories for issues."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "good-repo",
                "full_name": "org/good-repo",
                "description": "A well documented repo",
                "topics": ["python"],
                "license": {"spdx_id": "MIT"},
                "source_org": "org",
            },
            {
                "name": "bad-repo",
                "full_name": "org/bad-repo",
                "description": None,  # Missing
                "topics": [],  # Missing
                "license": None,  # Missing
                "source_org": "org",
            },
        ]

        report = generator.audit_repos(repos)

        assert report["total_repos"] == 2
        assert report["repos_with_issues"] == 1
        assert len(report["issues"]) == 3  # 3 issues in bad-repo
        assert report["summary"]["missing_description"] == 1
        assert report["summary"]["missing_topics"] == 1
        assert report["summary"]["missing_license"] == 1

    def test_audit_repos_all_good(self, mock_github_token):
        """Test auditing repositories with no issues."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "good-repo",
                "full_name": "org/good-repo",
                "description": "A well documented repo",
                "topics": ["python"],
                "license": {"spdx_id": "MIT"},
                "source_org": "org",
            },
        ]

        report = generator.audit_repos(repos)

        assert report["total_repos"] == 1
        assert report["repos_with_issues"] == 0
        assert len(report["issues"]) == 0

    def test_generate_readme_grouped_by_org(self, mock_github_token):
        """Test generating README grouped by organization."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "repo-a",
                "full_name": "org-one/repo-a",
                "description": "Repository A",
                "stargazers_count": 100,
                "category": "Libraries",
                "html_url": "https://github.com/org-one/repo-a",
                "source_org": "org-one",
            },
            {
                "name": "repo-b",
                "full_name": "org-two/repo-b",
                "description": "Repository B",
                "stargazers_count": 50,
                "category": "CLI Tools",
                "html_url": "https://github.com/org-two/repo-b",
                "source_org": "org-two",
            },
        ]

        org_infos = {
            "org-one": {"login": "org-one", "description": "First org"},
            "org-two": {"login": "org-two", "description": "Second org"},
        }

        readme = generator.generate_readme(repos, org_infos, group_by="org")

        assert "# " in readme
        assert "## Organizations" in readme
        assert "## Projects" in readme
        assert "### org-one" in readme
        assert "### org-two" in readme
        assert "repo-a" in readme
        assert "repo-b" in readme

    def test_generate_readme_grouped_by_category(self, mock_github_token):
        """Test generating README grouped by category."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "repo-a",
                "full_name": "org/repo-a",
                "description": "Repository A",
                "stargazers_count": 100,
                "category": "Libraries",
                "html_url": "https://github.com/org/repo-a",
                "source_org": "org",
            },
            {
                "name": "repo-b",
                "full_name": "org/repo-b",
                "description": "Repository B",
                "stargazers_count": 50,
                "category": "CLI Tools",
                "html_url": "https://github.com/org/repo-b",
                "source_org": "org",
            },
        ]

        org_infos = {"org": {"login": "org", "description": "Test org"}}

        readme = generator.generate_readme(repos, org_infos, group_by="category")

        assert "### Libraries" in readme
        assert "### CLI Tools" in readme

    def test_generate_readme_grouped_by_language(self, mock_github_token):
        """Test generating README grouped by language."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "repo-a",
                "full_name": "org/repo-a",
                "description": "Repository A",
                "language": "Python",
                "stargazers_count": 100,
                "category": "Libraries",
                "html_url": "https://github.com/org/repo-a",
                "source_org": "org",
            },
            {
                "name": "repo-b",
                "full_name": "org/repo-b",
                "description": "Repository B",
                "language": "JavaScript",
                "stargazers_count": 50,
                "category": "Web Applications",
                "html_url": "https://github.com/org/repo-b",
                "source_org": "org",
            },
        ]

        org_infos = {"org": {"login": "org", "description": "Test org"}}

        readme = generator.generate_readme(repos, org_infos, group_by="language")

        assert "### Python" in readme
        assert "### JavaScript" in readme

    def test_generate_readme_custom_title(self, mock_github_token):
        """Test generating README with custom title."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "repo-a",
                "full_name": "org/repo-a",
                "description": "Repository A",
                "stargazers_count": 100,
                "category": "Libraries",
                "html_url": "https://github.com/org/repo-a",
                "source_org": "org",
            },
        ]

        org_infos = {"org": {"login": "org", "description": "Test org"}}

        readme = generator.generate_readme(
            repos, org_infos, title="My Custom Portfolio"
        )

        assert "# My Custom Portfolio" in readme

    def test_generate_readme_summary(self, mock_github_token):
        """Test that README includes summary statistics."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {
                "name": "repo-a",
                "full_name": "org/repo-a",
                "description": "Repository A",
                "language": "Python",
                "stargazers_count": 100,
                "category": "Libraries",
                "html_url": "https://github.com/org/repo-a",
                "source_org": "org",
            },
        ]

        org_infos = {"org": {"login": "org", "description": "Test org"}}

        readme = generator.generate_readme(repos, org_infos)

        assert "## Summary" in readme
        assert "Total Projects" in readme
        assert "Organizations" in readme
        assert "Total Stars" in readme

    def test_group_repos_by_org(self, mock_github_token):
        """Test grouping repositories by organization."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {"name": "a", "source_org": "org1"},
            {"name": "b", "source_org": "org1"},
            {"name": "c", "source_org": "org2"},
        ]

        grouped = generator._group_repos(repos, "org")

        assert len(grouped) == 2
        assert len(grouped["org1"]) == 2
        assert len(grouped["org2"]) == 1

    def test_group_repos_by_language(self, mock_github_token):
        """Test grouping repositories by language."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        repos = [
            {"name": "a", "language": "Python"},
            {"name": "b", "language": "Python"},
            {"name": "c", "language": None},
        ]

        grouped = generator._group_repos(repos, "language")

        assert "Python" in grouped
        assert "Other" in grouped

    def test_save_readme(self, mock_github_token, tmp_path):
        """Test saving README to file."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        content = "# Portfolio\n\nTest content."
        output_path = tmp_path / "portfolio" / "README.md"

        generator.save_readme(content, str(output_path))

        assert output_path.exists()
        assert output_path.read_text() == content

    def test_save_html(self, mock_github_token, tmp_path):
        """Test saving HTML to file."""
        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        content = "<html><body>Test</body></html>"
        output_path = tmp_path / "portfolio" / "index.html"

        generator.save_html(content, str(output_path))

        assert output_path.exists()
        assert output_path.read_text() == content

    @responses.activate
    def test_aggregate_repos_handles_api_error(self, mock_github_token):
        """Test that aggregate_repos handles API errors gracefully."""
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/bad-org/repos",
            json={"message": "Not Found"},
            status=404,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/good-org/repos",
            json=[
                {
                    "name": "repo",
                    "full_name": "good-org/repo",
                    "description": "Test",
                    "language": "Python",
                    "stargazers_count": 10,
                    "forks_count": 1,
                    "topics": [],
                    "html_url": "https://github.com/good-org/repo",
                    "private": False,
                    "fork": False,
                    "archived": False,
                    "license": None,
                }
            ],
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/good-org/repos",
            json=[],
            status=200,
        )

        client = GitHubClient(mock_github_token)
        generator = PortfolioGenerator(client)

        # Should not raise, should continue with good org
        repos = generator.aggregate_repos(["bad-org", "good-org"])

        assert len(repos) == 1
        assert repos[0]["source_org"] == "good-org"
