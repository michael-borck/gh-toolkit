"""Pytest configuration and shared fixtures."""

import pytest
import responses


@pytest.fixture
def mock_github_token():
    """Provide a mock GitHub token for testing."""
    return "ghp_mock_token_1234567890abcdef"


@pytest.fixture
def mock_anthropic_key():
    """Provide a mock Anthropic API key for testing."""
    return "sk-mock-anthropic-key-1234567890abcdef"


@pytest.fixture
def sample_repo_data():
    """Sample repository data for testing."""
    return {
        "name": "test-repo",
        "full_name": "testuser/test-repo",
        "description": "A test repository for unit testing",
        "language": "Python",
        "stargazers_count": 42,
        "forks_count": 8,
        "topics": ["python", "testing", "mock"],
        "html_url": "https://github.com/testuser/test-repo",
        "homepage": "https://test-repo.example.com",
        "license": {"spdx_id": "MIT"},
        "private": False,
        "fork": False,
        "archived": False,
        "disabled": False,
        "pushed_at": "2023-12-01T10:00:00Z",
        "created_at": "2023-01-01T10:00:00Z",
        "updated_at": "2023-12-01T10:00:00Z",
    }


@pytest.fixture
def sample_user_repos():
    """Sample list of user repositories."""
    return [
        {
            "name": "repo1",
            "full_name": "testuser/repo1",
            "description": "First test repo",
            "language": "Python",
            "stargazers_count": 10,
            "forks_count": 2,
            "private": False,
        },
        {
            "name": "repo2",
            "full_name": "testuser/repo2",
            "description": "Second test repo",
            "language": "JavaScript",
            "stargazers_count": 5,
            "forks_count": 1,
            "private": False,
        },
    ]


@pytest.fixture
def sample_languages():
    """Sample repository languages data."""
    return {"Python": 15432, "JavaScript": 8901, "HTML": 2345, "CSS": 1234}


@pytest.fixture
def sample_repo_topics():
    """Sample repository topics response."""
    return {"names": ["python", "cli", "tool", "github"]}


@pytest.fixture
def sample_readme_content():
    """Sample README content for testing."""
    return """# Test Repository

This is a test repository for demonstrating the gh-toolkit functionality.

## Features

- Python CLI tool
- GitHub API integration
- Automated testing

## Installation

```bash
pip install test-repo
```

## Usage

```python
from test_repo import main
main()
```
"""


@pytest.fixture
def mock_github_api():
    """Mock GitHub API responses using responses library."""
    with responses.RequestsMock() as rsps:
        # Mock rate limit headers
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": "1640995200",
        }

        # Add common API endpoints
        rsps.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "testuser", "id": 12345},
            headers=headers,
        )

        yield rsps


@pytest.fixture
def mock_anthropic_client(mocker):
    """Mock Anthropic client for testing LLM functionality."""
    mock_client = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.content = [mocker.Mock(text="python, cli, tool, testing, automation")]
    mock_client.messages.create.return_value = mock_response

    # Anthropic is imported lazily inside __init__, so patch the source module
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    yield mock_client


@pytest.fixture
def temp_repo_file(tmp_path):
    """Create a temporary file with repository list."""
    repo_file = tmp_path / "repos.txt"
    repo_file.write_text("testuser/repo1\ntestuser/repo2\n# comment\n\n")
    return repo_file


@pytest.fixture
def temp_output_file(tmp_path):
    """Create a temporary output file path."""
    return tmp_path / "output.json"


@pytest.fixture
def sample_extracted_repos():
    """Sample extracted repository data with categories."""
    return [
        {
            "name": "web-app",
            "description": "A React web application",
            "url": "https://github.com/user/web-app",
            "stars": 45,
            "forks": 12,
            "category": "Web Application",
            "category_confidence": 0.92,
            "topics": ["react", "javascript", "web"],
            "languages": ["JavaScript", "CSS", "HTML"],
            "license": "MIT",
        },
        {
            "name": "data-tool",
            "description": "Python data analysis toolkit",
            "url": "https://github.com/user/data-tool",
            "stars": 78,
            "forks": 23,
            "category": "Python Package",
            "category_confidence": 0.88,
            "topics": ["python", "data", "analysis"],
            "languages": ["Python", "Jupyter Notebook"],
            "license": "Apache-2.0",
        },
    ]


@pytest.fixture
def sample_site_metadata():
    """Sample metadata for site generation."""
    return {
        "web-app": {
            "icon": "🌐",
            "key_features": [
                "Responsive design",
                "Modern React hooks",
                "TypeScript support",
            ],
        },
        "data-tool": {
            "icon": "📊",
            "key_features": [
                "Pandas integration",
                "Jupyter notebooks",
                "Statistical analysis",
            ],
        },
    }


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_mock_token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mock-key")


@pytest.fixture
def no_env_vars(monkeypatch):
    """Simulate no credentials available from any source.

    Clears the env vars and also neutralizes the config-file and `gh` CLI
    token fallbacks so resolve_token() genuinely returns None — otherwise a
    developer's real `gh` login would leak into "missing token" tests.
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("gh_toolkit.core.config.load_config", lambda: {})
    monkeypatch.setattr("gh_toolkit.core.config._gh_cli_token", lambda: None)
