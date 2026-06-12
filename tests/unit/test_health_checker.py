"""Unit tests for RepositoryHealthChecker."""

import base64
from datetime import UTC, datetime, timedelta

import pytest

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.health_checker import (
    HealthCheck,
    HealthReport,
    RepositoryHealthChecker,
)


class TestRepositoryHealthChecker:
    """Test RepositoryHealthChecker functionality."""

    @pytest.fixture
    def mock_github_client(self, mocker):
        """Mock GitHub client for testing."""
        return mocker.Mock(spec=GitHubClient)

    @pytest.fixture
    def health_checker(self, mock_github_client):
        """Create RepositoryHealthChecker instance for testing."""
        return RepositoryHealthChecker(mock_github_client, "general")

    @pytest.fixture
    def sample_repo_data(self):
        """Sample repository data for testing."""
        return {
            "name": "test-repo",
            "full_name": "user/test-repo",
            "description": "A test repository for health checking",
            "language": "Python",
            "stargazers_count": 42,
            "forks_count": 8,
            "watchers_count": 15,
            "size": 1024,
            "license": {"name": "MIT"},
            "topics": ["python", "testing", "health"],
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "homepage": "https://test-repo.example.com",
            "has_issues": True,
            "has_releases": True,
            "archived": False,
            "fork": False,
            "private": False,
            "readme_content": base64.b64encode(
                b"# Test Repo\n\nA comprehensive test repository.\n\n## Installation\n\npip install test-repo\n\n## Usage\n\n```python\nimport test_repo\ntest_repo.run()\n```"
            ).decode(),
            "readme_size": 150,
            "root_files": ["README.md", ".gitignore", "setup.py", "requirements.txt"],
            "root_dirs": ["src", "tests", "docs"],
            "workflows": [{"name": "CI", "state": "active"}],
        }

    def test_init_general_rules(self, mock_github_client):
        """Test initialization with general rules."""
        checker = RepositoryHealthChecker(mock_github_client, "general")
        assert checker.rules == "general"
        assert checker.client == mock_github_client
        assert "documentation" in checker.weights
        assert "structure" in checker.weights
        assert "quality" in checker.weights
        assert "metadata" in checker.weights

    def test_init_academic_rules(self, mock_github_client):
        """Test initialization with academic rules."""
        checker = RepositoryHealthChecker(mock_github_client, "academic")
        assert checker.rules == "academic"
        # Academic rules should emphasize documentation
        assert checker.weights["documentation"]["readme"] == 15
        assert checker.weights["quality"]["tests"] == 5

    def test_init_professional_rules(self, mock_github_client):
        """Test initialization with professional rules."""
        checker = RepositoryHealthChecker(mock_github_client, "professional")
        assert checker.rules == "professional"
        # Professional rules should emphasize quality
        assert checker.weights["quality"]["tests"] == 12
        assert checker.weights["quality"]["ci_cd"] == 10

    def test_assess_readme_quality_good(self, health_checker):
        """Test README quality assessment with good content."""
        readme_content = base64.b64encode(b"""# Awesome Project

This is a comprehensive project with great documentation.

## Installation

Install using pip:

```bash
pip install awesome-project
```

## Usage

Here's how to use it:

```python
import awesome
awesome.do_something()
```

## Features

- Feature 1
- Feature 2

## Contributing

Please read our contributing guide.
""").decode()

        quality = health_checker._assess_readme_quality(readme_content)
        assert quality > 0.8  # Should score highly

    def test_assess_readme_quality_poor(self, health_checker):
        """Test README quality assessment with poor content."""
        readme_content = base64.b64encode(b"# Project\n\nBasic project.").decode()
        quality = health_checker._assess_readme_quality(readme_content)
        assert quality < 0.5  # Should score poorly

    def test_assess_readme_quality_empty(self, health_checker):
        """Test README quality assessment with empty content."""
        quality = health_checker._assess_readme_quality("")
        assert quality == 0.0

    def test_assess_organization_good(self, health_checker, sample_repo_data):
        """Test organization assessment with good structure."""
        score = health_checker._assess_organization(
            sample_repo_data["root_files"],
            sample_repo_data["root_dirs"],
            sample_repo_data,
        )
        assert score > 0.6  # Should score well

    def test_assess_organization_poor(self, health_checker):
        """Test organization assessment with poor structure."""
        # Too many files in root, no source directory
        root_files = [f"file{i}.py" for i in range(20)]
        root_dirs = ["random", "stuff"]
        repo_data = {"language": "Python"}

        score = health_checker._assess_organization(root_files, root_dirs, repo_data)
        assert score < 0.5  # Should score poorly

    def test_assess_naming_conventions_good(self, health_checker):
        """Test naming conventions with good names."""
        assert health_checker._assess_naming_conventions("awesome-project") > 0.8
        assert health_checker._assess_naming_conventions("my-cool-tool") > 0.8

    def test_assess_naming_conventions_poor(self, health_checker):
        """Test naming conventions with poor names."""
        assert (
            health_checker._assess_naming_conventions("My_Project") < 0.5
        )  # Mixed case and underscore
        assert (
            health_checker._assess_naming_conventions("project!!!") < 0.7
        )  # Special characters
        assert health_checker._assess_naming_conventions("a") < 0.7  # Too short

    def test_assess_activity_recent(self, health_checker):
        """Test activity assessment with recent activity."""
        recent_date = (datetime.now(UTC) - timedelta(days=15)).isoformat()
        repo_data = {
            "updated_at": recent_date,
            "pushed_at": recent_date,
            "archived": False,
        }

        score = health_checker._assess_activity(repo_data)
        assert score > 0.8  # Should score highly for recent activity

    def test_assess_activity_old(self, health_checker):
        """Test activity assessment with old activity."""
        old_date = (datetime.now(UTC) - timedelta(days=400)).isoformat()
        repo_data = {"updated_at": old_date, "pushed_at": old_date, "archived": False}

        score = health_checker._assess_activity(repo_data)
        assert score < 0.5  # Should score poorly for old activity

    def test_assess_activity_archived(self, health_checker):
        """Test activity assessment with archived repository."""
        repo_data = {
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "archived": True,
        }

        score = health_checker._assess_activity(repo_data)
        assert score < 1.0  # Should lose points for being archived

    def test_assess_code_quality_good(self, health_checker):
        """Test code quality assessment with good indicators."""
        repo_data = {
            "size": 50000,  # Good size
            "stargazers_count": 25,  # Some stars
            "language": "Python",
            "fork": False,
        }

        score = health_checker._assess_code_quality(repo_data)
        assert score > 0.8  # Should score well

    def test_assess_code_quality_poor(self, health_checker):
        """Test code quality assessment with poor indicators."""
        repo_data = {
            "size": 1,  # Too small
            "stargazers_count": 0,  # No stars
            "language": None,
            "fork": True,
        }

        score = health_checker._assess_code_quality(repo_data)
        assert score < 0.5  # Should score poorly

    def test_calculate_grade(self, health_checker):
        """Test grade calculation."""
        assert health_checker._calculate_grade(95) == "A"
        assert health_checker._calculate_grade(85) == "B"
        assert health_checker._calculate_grade(75) == "C"
        assert health_checker._calculate_grade(65) == "D"
        assert health_checker._calculate_grade(55) == "F"

    def test_check_documentation_all_good(self, health_checker, sample_repo_data):
        """Test documentation checks with all criteria met."""
        checks = health_checker._check_documentation(sample_repo_data)

        # Should have README, description, license, and topics checks
        assert len(checks) >= 4

        # Most checks should pass
        passed_checks = [c for c in checks if c.passed]
        assert len(passed_checks) >= 3

    def test_check_documentation_missing_readme(self, health_checker, sample_repo_data):
        """Test documentation checks with missing README."""
        sample_repo_data["readme_size"] = 0
        sample_repo_data["readme_content"] = ""

        checks = health_checker._check_documentation(sample_repo_data)

        readme_check = next(c for c in checks if c.name == "README Existence")
        assert not readme_check.passed
        assert readme_check.fix_suggestion is not None

    def test_check_structure_good(self, health_checker, sample_repo_data):
        """Test structure checks with good repository structure."""
        checks = health_checker._check_structure(sample_repo_data)

        # Should have gitignore, organization, and naming checks
        assert len(checks) == 3

        # Most should pass for good structure
        passed_checks = [c for c in checks if c.passed]
        assert len(passed_checks) >= 2

    def test_check_quality_with_tests_and_ci(self, health_checker, sample_repo_data):
        """Test quality checks with tests and CI/CD."""
        checks = health_checker._check_quality(sample_repo_data)

        # Should have tests, CI/CD, activity, and code quality checks
        assert len(checks) == 4

        # Tests and CI/CD should pass
        tests_check = next(c for c in checks if c.name == "Tests")
        ci_check = next(c for c in checks if c.name == "CI/CD")
        assert tests_check.passed
        assert ci_check.passed

    def test_check_metadata_complete(self, health_checker, sample_repo_data):
        """Test metadata checks with complete metadata."""
        checks = health_checker._check_metadata(sample_repo_data)

        # Should have homepage, releases, and issues checks
        assert len(checks) == 3

        # All should pass for complete metadata
        passed_checks = [c for c in checks if c.passed]
        assert len(passed_checks) == 3

    def test_check_repository_health_comprehensive(
        self, health_checker, sample_repo_data, mocker
    ):
        """Test comprehensive repository health check."""
        # Mock the _fetch_repository_data method to return our sample data
        health_checker._fetch_repository_data = mocker.Mock(
            return_value=sample_repo_data
        )

        report = health_checker.check_repository_health("user/test-repo")

        assert isinstance(report, HealthReport)
        assert report.repository == "user/test-repo"
        assert report.total_score > 0
        assert report.max_score > 0
        assert 0 <= report.percentage <= 100
        assert report.grade in ["A", "B", "C", "D", "F"]
        assert len(report.checks) > 0
        assert "by_category" in report.summary

    def test_check_repository_health_with_provided_data(
        self, health_checker, sample_repo_data
    ):
        """Test health check with provided repository data."""
        report = health_checker.check_repository_health(
            "user/test-repo", sample_repo_data
        )

        assert report.repository == "user/test-repo"
        assert report.percentage > 70  # Should score well with good sample data
        assert report.grade in ["A", "B"]

    def test_fetch_repository_data_invalid_format(self, health_checker):
        """Malformed repo names raise a clear error instead of ValueError on unpack."""
        for bad_name in ["owner/sub/repo", "just-a-name", "", "owner//"]:
            with pytest.raises(ValueError, match="expected 'owner/repo'"):
                health_checker._fetch_repository_data(bad_name)

    def test_generate_summary(self, health_checker, sample_repo_data):
        """Test summary generation."""
        # Create some mock checks
        checks = [
            HealthCheck(
                "Test 1", "Documentation", "Test check", True, 10, 10, "Passed"
            ),
            HealthCheck(
                "Test 2",
                "Documentation",
                "Test check",
                False,
                0,
                10,
                "Failed",
                "Fix suggestion",
            ),
            HealthCheck("Test 3", "Quality", "Test check", True, 8, 10, "Passed"),
        ]

        summary = health_checker._generate_summary(checks, sample_repo_data)

        assert "by_category" in summary
        assert "Documentation" in summary["by_category"]
        assert "Quality" in summary["by_category"]
        assert summary["total_checks"] == 3
        assert summary["passed_checks"] == 2
        assert summary["failed_checks"] == 1
        assert len(summary["top_issues"]) == 1  # One failed check with fix suggestion

    def test_health_check_categories_coverage(self, health_checker, sample_repo_data):
        """Test that all expected categories are covered in health checks."""
        report = health_checker.check_repository_health(
            "user/test-repo", sample_repo_data
        )

        categories = {check.category for check in report.checks}
        expected_categories = {"Documentation", "Structure", "Quality", "Metadata"}

        assert categories == expected_categories

    def test_academic_rules_weighting(self, mock_github_client, sample_repo_data):
        """Test that academic rules weight documentation more heavily."""
        academic_checker = RepositoryHealthChecker(mock_github_client, "academic")
        general_checker = RepositoryHealthChecker(mock_github_client, "general")

        academic_report = academic_checker.check_repository_health(
            "user/test", sample_repo_data
        )
        general_report = general_checker.check_repository_health(
            "user/test", sample_repo_data
        )

        # Academic should weight documentation more heavily
        academic_doc_score = academic_report.summary["by_category"]["Documentation"][
            "max_score"
        ]
        general_doc_score = general_report.summary["by_category"]["Documentation"][
            "max_score"
        ]

        assert academic_doc_score > general_doc_score

    def test_professional_rules_weighting(self, mock_github_client, sample_repo_data):
        """Test that professional rules weight quality more heavily."""
        professional_checker = RepositoryHealthChecker(
            mock_github_client, "professional"
        )
        general_checker = RepositoryHealthChecker(mock_github_client, "general")

        professional_report = professional_checker.check_repository_health(
            "user/test", sample_repo_data
        )
        general_report = general_checker.check_repository_health(
            "user/test", sample_repo_data
        )

        # Professional should weight quality more heavily
        professional_quality_score = professional_report.summary["by_category"][
            "Quality"
        ]["max_score"]
        general_quality_score = general_report.summary["by_category"]["Quality"][
            "max_score"
        ]

        assert professional_quality_score > general_quality_score
