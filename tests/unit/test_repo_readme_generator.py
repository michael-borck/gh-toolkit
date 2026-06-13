"""Unit tests for RepoReadmeGenerator."""

import base64

import pytest

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL
from gh_toolkit.core.repo_readme_generator import RepoReadmeGenerator

GOOD_README = """# Awesome Project

This project provides a comprehensive toolkit for managing GitHub \
repositories at scale, including bulk operations, data extraction, and \
portfolio generation for educators and developers.

## Installation

```bash
pip install awesome-project
```

## Usage

```python
import awesome

awesome.run()
```

## Configuration

Set the GITHUB_TOKEN environment variable before running any commands. The
toolkit reads configuration from environment variables and command line flags.

## License

MIT License. See the LICENSE file for details.
"""

POOR_README = "# x\n\nTODO: write docs"


@pytest.fixture
def mock_client(mocker):
    """Provide a mocked GitHubClient."""
    return mocker.Mock(spec=GitHubClient)


@pytest.fixture
def generator(mock_client):
    """Provide a RepoReadmeGenerator with a mocked client and no LLM key."""
    return RepoReadmeGenerator(mock_client)


@pytest.fixture
def sample_context():
    """Provide a representative repo context dictionary."""
    return {
        "owner": "testuser",
        "repo": "test-repo",
        "description": "A test repository",
        "languages": ["Python", "Shell"],
        "topics": ["cli", "github"],
        "has_license": True,
        "license_name": "MIT License",
        "default_branch": "main",
        "is_fork": False,
        "homepage": "https://example.com",
        "key_files": ["pyproject.toml", "src/main.py"],
        "key_dirs": ["src", "tests"],
    }


class TestInit:
    """Test RepoReadmeGenerator initialization."""

    def test_defaults(self, mock_client):
        generator = RepoReadmeGenerator(mock_client)

        assert generator.client is mock_client
        assert generator.anthropic_key is None
        assert generator.rate_limit == 0.5
        assert generator.model == DEFAULT_LLM_MODEL
        assert generator._anthropic_client is None

    def test_custom_arguments(self, mock_client, mock_anthropic_key):
        generator = RepoReadmeGenerator(
            mock_client,
            anthropic_key=mock_anthropic_key,
            rate_limit=1.5,
            model="custom-model",
        )

        assert generator.anthropic_key == mock_anthropic_key
        assert generator.rate_limit == 1.5
        assert generator.model == "custom-model"


class TestGetAnthropicClient:
    """Test lazy Anthropic client creation."""

    def test_returns_none_without_key(self, generator):
        assert generator._get_anthropic_client() is None

    def test_creates_client_with_key(
        self, mock_client, mock_anthropic_key, mock_anthropic_client
    ):
        generator = RepoReadmeGenerator(mock_client, anthropic_key=mock_anthropic_key)

        client = generator._get_anthropic_client()

        assert client is mock_anthropic_client

    def test_caches_client(
        self, mock_client, mock_anthropic_key, mock_anthropic_client
    ):
        generator = RepoReadmeGenerator(mock_client, anthropic_key=mock_anthropic_key)

        first = generator._get_anthropic_client()
        second = generator._get_anthropic_client()

        assert first is second


class TestAssessReadmeQuality:
    """Test README quality assessment."""

    def test_none_readme(self, generator):
        score, issues = generator.assess_readme_quality(None)

        assert score == 0.0
        assert issues == ["No README found"]

    def test_empty_readme(self, generator):
        score, issues = generator.assess_readme_quality("")

        assert score == 0.0
        assert issues == ["No README found"]

    def test_boilerplate_title_only(self, generator):
        score, issues = generator.assess_readme_quality("# myrepo")

        # Only the title check passes (1 of 8)
        assert score == pytest.approx(1.0 / 8.0)
        assert "Appears to be placeholder/boilerplate" in issues
        assert "Missing installation section" in issues
        assert "Missing usage section" in issues
        assert "Missing code examples" in issues
        assert "Content too short (likely placeholder)" in issues

    def test_todo_marks_boilerplate(self, generator):
        score, issues = generator.assess_readme_quality(POOR_README)

        assert score < 0.5
        assert "Appears to be placeholder/boilerplate" in issues

    def test_missing_title(self, generator):
        _score, issues = generator.assess_readme_quality(
            "Just some text without any heading at all."
        )

        assert "Missing title" in issues

    def test_full_featured_readme(self, generator):
        score, issues = generator.assess_readme_quality(GOOD_README)

        assert score == 1.0
        assert issues == []

    def test_partial_readme(self, generator):
        content = (
            "# Project\n\n"
            "A short intro paragraph that is definitely longer than fifty chars.\n\n"
            "## Installation\n\nRun the installer.\n"
        )

        score, issues = generator.assess_readme_quality(content)

        assert 0.0 < score < 1.0
        assert "Missing usage section" in issues
        assert "Missing code examples" in issues
        assert "Missing installation section" not in issues


class TestGetReadmeContent:
    """Test README content retrieval."""

    def test_returns_client_content_verbatim(self, generator, mock_client):
        # GitHubClient.get_repo_readme already base64-decodes; no re-decoding
        # happens here even if the text itself is valid base64
        readme = "# Hello World"
        mock_client.get_repo_readme.return_value = readme

        content = generator.get_readme_content("testuser", "test-repo")

        assert content == readme
        mock_client.get_repo_readme.assert_called_once_with("testuser", "test-repo")

    def test_base64_looking_text_not_corrupted(self, generator, mock_client):
        # 'abcd' is decodable base64; the old double-decode would corrupt it
        raw = "abcd"
        mock_client.get_repo_readme.return_value = raw

        content = generator.get_readme_content("testuser", "test-repo")

        assert content == raw

    def test_returns_none_for_empty_readme(self, generator, mock_client):
        mock_client.get_repo_readme.return_value = ""

        assert generator.get_readme_content("testuser", "test-repo") is None

    def test_returns_none_on_error(self, generator, mock_client):
        mock_client.get_repo_readme.side_effect = GitHubAPIError("Not found", 404)

        assert generator.get_readme_content("testuser", "test-repo") is None


class TestGetRepoContext:
    """Test repository context gathering."""

    def test_full_context(self, generator, mock_client):
        mock_client.get_repo.return_value = {
            "description": "A test repository",
            "default_branch": "develop",
            "fork": True,
            "homepage": "https://example.com",
            "license": {"name": "MIT License"},
        }
        mock_client.get_repo_languages.return_value = {"Python": 1000, "Shell": 50}
        mock_client.get_repo_topics.return_value = ["cli", "github"]
        mock_client.get_repo_tree.return_value = [
            {"path": "README.md", "type": "blob"},
            {"path": "src", "type": "tree"},
            {"path": "src/main.py", "type": "blob"},
        ]

        context = generator.get_repo_context("testuser", "test-repo")

        assert context["owner"] == "testuser"
        assert context["repo"] == "test-repo"
        assert context["description"] == "A test repository"
        assert context["default_branch"] == "develop"
        assert context["is_fork"] is True
        assert context["homepage"] == "https://example.com"
        assert context["has_license"] is True
        assert context["license_name"] == "MIT License"
        assert context["languages"] == ["Python", "Shell"]
        assert context["topics"] == ["cli", "github"]
        assert context["key_files"] == ["README.md", "src/main.py"]
        assert context["key_dirs"] == ["src"]

    def test_defaults_when_repo_missing(self, generator, mock_client):
        mock_client.get_repo.return_value = None
        mock_client.get_repo_languages.return_value = {}
        mock_client.get_repo_topics.return_value = []
        mock_client.get_repo_tree.return_value = []

        context = generator.get_repo_context("testuser", "test-repo")

        assert context["description"] == ""
        assert context["default_branch"] == "main"
        assert context["is_fork"] is False
        assert context["has_license"] is False
        assert context["license_name"] is None
        assert context["languages"] == []
        assert context["topics"] == []

    def test_tree_failure_yields_empty_lists(self, generator, mock_client):
        mock_client.get_repo.return_value = {"description": "x"}
        mock_client.get_repo_languages.return_value = {}
        mock_client.get_repo_topics.return_value = []
        mock_client.get_repo_tree.side_effect = GitHubAPIError("Boom", 500)

        context = generator.get_repo_context("testuser", "test-repo")

        assert context["key_files"] == []
        assert context["key_dirs"] == []

    def test_handles_client_error_gracefully(self, generator, mock_client):
        mock_client.get_repo.side_effect = GitHubAPIError("Server error", 500)

        context = generator.get_repo_context("testuser", "test-repo")

        assert context["owner"] == "testuser"
        assert context["repo"] == "test-repo"
        assert context["description"] == ""

    def test_limits_key_files_and_dirs(self, generator, mock_client):
        mock_client.get_repo.return_value = {}
        mock_client.get_repo_languages.return_value = {}
        mock_client.get_repo_topics.return_value = []
        mock_client.get_repo_tree.return_value = [
            {"path": f"file{i}.py", "type": "blob"} for i in range(30)
        ] + [{"path": f"dir{i}", "type": "tree"} for i in range(15)]

        context = generator.get_repo_context("testuser", "test-repo")

        assert len(context["key_files"]) == 20
        assert len(context["key_dirs"]) == 10


class TestGenerateReadmeWithLlm:
    """Test LLM-based README generation."""

    def test_returns_none_without_client(self, generator, sample_context):
        assert generator.generate_readme_with_llm(sample_context) is None

    def test_success(self, mock_client, sample_context, mocker):
        mock_llm = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = [mocker.Mock(text=GOOD_README)]
        mock_llm.messages.create.return_value = mock_response

        generator = RepoReadmeGenerator(mock_client, anthropic_key="mock-key")
        generator._anthropic_client = mock_llm

        result = generator.generate_readme_with_llm(sample_context)

        assert result == GOOD_README.strip()
        mock_llm.messages.create.assert_called_once()
        call_kwargs = mock_llm.messages.create.call_args.kwargs
        assert call_kwargs["model"] == DEFAULT_LLM_MODEL
        assert call_kwargs["max_tokens"] == 4000
        prompt = call_kwargs["messages"][0]["content"]
        assert "test-repo" in prompt
        assert "testuser" in prompt
        assert "Python, Shell" in prompt

    def test_strips_markdown_code_fence(self, mock_client, sample_context, mocker):
        mock_llm = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = [
            mocker.Mock(text="```markdown\n# Title\n\nBody text.\n```")
        ]
        mock_llm.messages.create.return_value = mock_response

        generator = RepoReadmeGenerator(mock_client, anthropic_key="mock-key")
        generator._anthropic_client = mock_llm

        result = generator.generate_readme_with_llm(sample_context)

        assert result == "# Title\n\nBody text."

    def test_strips_plain_code_fence(self, mock_client, sample_context, mocker):
        mock_llm = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = [mocker.Mock(text="```\n# Title\n```")]
        mock_llm.messages.create.return_value = mock_response

        generator = RepoReadmeGenerator(mock_client, anthropic_key="mock-key")
        generator._anthropic_client = mock_llm

        result = generator.generate_readme_with_llm(sample_context)

        assert result == "# Title"

    def test_empty_response_returns_none(self, mock_client, sample_context, mocker):
        mock_llm = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.content = []
        mock_llm.messages.create.return_value = mock_response

        generator = RepoReadmeGenerator(mock_client, anthropic_key="mock-key")
        generator._anthropic_client = mock_llm

        assert generator.generate_readme_with_llm(sample_context) is None

    def test_exception_returns_none(self, mock_client, sample_context, mocker):
        mock_llm = mocker.Mock()
        mock_llm.messages.create.side_effect = Exception("API Error")

        generator = RepoReadmeGenerator(mock_client, anthropic_key="mock-key")
        generator._anthropic_client = mock_llm

        assert generator.generate_readme_with_llm(sample_context) is None


class TestBuildGenerationPrompt:
    """Test prompt construction."""

    def test_includes_optional_fields(self, generator, sample_context):
        prompt = generator._build_generation_prompt(sample_context)

        assert "- Name: test-repo" in prompt
        assert "- Owner: testuser" in prompt
        assert "- Description: A test repository" in prompt
        assert "- License: MIT License" in prompt
        assert "- Homepage: https://example.com" in prompt
        assert "- Topics: cli, github" in prompt
        assert "- Key files: pyproject.toml, src/main.py" in prompt
        assert "- Key directories: src, tests" in prompt

    def test_omits_missing_fields(self, generator):
        context = {"owner": "testuser", "repo": "test-repo"}

        prompt = generator._build_generation_prompt(context)

        assert "- Description:" not in prompt
        assert "- License:" not in prompt
        assert "- Homepage:" not in prompt


class TestGenerateReadmeFallback:
    """Test template-based README generation."""

    def test_full_context(self, generator, sample_context):
        readme = generator.generate_readme_fallback(sample_context)

        assert readme.startswith("# test-repo")
        assert "A test repository" in readme
        assert "## Technologies" in readme
        assert "- Primary language: Python" in readme
        assert "- Also uses: Shell" in readme
        assert "## Installation" in readme
        assert "git clone https://github.com/testuser/test-repo.git" in readme
        assert "## Usage" in readme
        assert "## License" in readme
        assert "This project is licensed under the MIT License." in readme

    def test_minimal_context(self, generator):
        context = {"owner": "testuser", "repo": "bare-repo"}

        readme = generator.generate_readme_fallback(context)

        assert readme.startswith("# bare-repo")
        assert "## Technologies" not in readme
        assert "## License" not in readme
        assert "## Installation" in readme
        assert "## Usage" in readme

    def test_single_language(self, generator):
        context = {"owner": "testuser", "repo": "py-repo", "languages": ["Python"]}

        readme = generator.generate_readme_fallback(context)

        assert "- Primary language: Python" in readme
        assert "Also uses" not in readme


class TestUpdateReadme:
    """Test README create/update via the contents API."""

    def test_create_when_readme_missing(self, generator, mock_client, mocker):
        put_response = mocker.Mock(ok=True)

        def fake_request(method, endpoint, **kwargs):
            if method == "GET":
                raise GitHubAPIError("Not found", 404)
            return put_response

        mock_client.request.side_effect = fake_request

        result = generator.update_readme("testuser", "test-repo", "# New README")

        assert result is True
        put_call = mock_client.request.call_args_list[-1]
        assert put_call.args[0] == "PUT"
        assert put_call.args[1] == "/repos/testuser/test-repo/contents/README.md"
        data = put_call.kwargs["json_data"]
        assert "sha" not in data
        assert "branch" not in data
        decoded = base64.b64decode(data["content"]).decode("utf-8")
        assert decoded == "# New README"
        assert "Update README.md" in data["message"]

    def test_update_existing_readme_with_sha(self, generator, mock_client, mocker):
        get_response = mocker.Mock(ok=True)
        get_response.json.return_value = {"sha": "abc123"}
        put_response = mocker.Mock(ok=True)
        mock_client.request.side_effect = [get_response, put_response]

        result = generator.update_readme(
            "testuser", "test-repo", "# Updated", branch="develop"
        )

        assert result is True
        data = mock_client.request.call_args_list[-1].kwargs["json_data"]
        assert data["sha"] == "abc123"
        assert data["branch"] == "develop"

    def test_failure_when_put_not_ok(self, generator, mock_client, mocker):
        get_response = mocker.Mock(ok=False)
        put_response = mocker.Mock(ok=False)
        mock_client.request.side_effect = [get_response, put_response]

        result = generator.update_readme("testuser", "test-repo", "# Content")

        assert result is False

    def test_failure_when_put_raises(self, generator, mock_client, mocker):
        get_response = mocker.Mock(ok=False)
        mock_client.request.side_effect = [
            get_response,
            GitHubAPIError("Forbidden", 403),
        ]

        result = generator.update_readme("testuser", "test-repo", "# Content")

        assert result is False


class TestProcessRepository:
    """Test single repository processing."""

    def test_skips_when_quality_ok(self, generator, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=GOOD_README)
        mock_update = mocker.patch.object(generator, "update_readme")

        result = generator.process_repository("testuser", "test-repo")

        assert result["status"] == "skipped"
        assert result["action"] == "quality_ok"
        assert result["quality_before"] == 1.0
        assert result["quality_after"] is None
        mock_update.assert_not_called()

    def test_create_when_no_readme(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=None)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(
            generator, "generate_readme_with_llm", return_value=GOOD_README
        )
        mock_update = mocker.patch.object(generator, "update_readme", return_value=True)
        mocker.patch("time.sleep")

        result = generator.process_repository("testuser", "test-repo")

        assert result["status"] == "updated"
        assert result["action"] == "create"
        assert result["generation_method"] == "llm"
        assert result["quality_before"] == 0.0
        assert result["quality_after"] == 1.0
        assert result["generated_content"] == GOOD_README
        mock_update.assert_called_once_with("testuser", "test-repo", GOOD_README)

    def test_force_update_good_readme(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=GOOD_README)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(
            generator, "generate_readme_with_llm", return_value=GOOD_README
        )
        mocker.patch.object(generator, "update_readme", return_value=True)
        mocker.patch("time.sleep")

        result = generator.process_repository("testuser", "test-repo", force=True)

        assert result["status"] == "updated"
        assert result["action"] == "force_update"

    def test_quality_update_for_poor_readme(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=POOR_README)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(
            generator, "generate_readme_with_llm", return_value=GOOD_README
        )
        mocker.patch.object(generator, "update_readme", return_value=True)
        mocker.patch("time.sleep")

        result = generator.process_repository("testuser", "test-repo", min_quality=0.5)

        assert result["status"] == "updated"
        assert result["action"] == "quality_update"
        assert result["quality_before"] < 0.5

    def test_dry_run_makes_no_changes(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=None)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(
            generator, "generate_readme_with_llm", return_value=GOOD_README
        )
        mock_update = mocker.patch.object(generator, "update_readme")

        result = generator.process_repository("testuser", "test-repo", dry_run=True)

        assert result["status"] == "dry_run"
        assert result["action"] == "create"
        assert result["generated_content"] == GOOD_README
        mock_update.assert_not_called()

    def test_fallback_when_llm_unavailable(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=None)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(generator, "generate_readme_with_llm", return_value=None)
        mocker.patch.object(generator, "update_readme", return_value=True)
        mocker.patch("time.sleep")

        result = generator.process_repository("testuser", "test-repo")

        assert result["status"] == "updated"
        assert result["generation_method"] == "fallback"
        assert result["generated_content"].startswith("# test-repo")

    def test_failed_update(self, generator, sample_context, mocker):
        mocker.patch.object(generator, "get_readme_content", return_value=None)
        mocker.patch.object(generator, "get_repo_context", return_value=sample_context)
        mocker.patch.object(
            generator, "generate_readme_with_llm", return_value=GOOD_README
        )
        mocker.patch.object(generator, "update_readme", return_value=False)
        mocker.patch("time.sleep")

        result = generator.process_repository("testuser", "test-repo")

        assert result["status"] == "failed"


class TestProcessMultipleRepositories:
    """Test multi-repository processing."""

    def test_processes_all_repos(self, generator, mocker):
        mock_process = mocker.patch.object(generator, "process_repository")
        mock_process.side_effect = [
            {
                "owner": "user",
                "repo": "repo1",
                "status": "updated",
                "quality_before": 0.2,
                "quality_after": 0.9,
                "issues": ["Missing title"],
                "action": "quality_update",
            },
            {
                "owner": "user",
                "repo": "repo2",
                "status": "skipped",
                "quality_before": 0.9,
                "quality_after": None,
                "issues": [],
                "action": "quality_ok",
            },
        ]

        results = generator.process_multiple_repositories(
            [("user", "repo1"), ("user", "repo2")], dry_run=True, force=False
        )

        assert len(results) == 2
        assert results[0]["status"] == "updated"
        assert results[1]["status"] == "skipped"
        mock_process.assert_any_call("user", "repo1", True, False, 0.5)
        mock_process.assert_any_call("user", "repo2", True, False, 0.5)

    def test_records_errors_and_continues(self, generator, mocker):
        mock_process = mocker.patch.object(generator, "process_repository")
        mock_process.side_effect = [
            Exception("Boom"),
            {
                "owner": "user",
                "repo": "repo2",
                "status": "dry_run",
                "quality_before": 0.1,
                "quality_after": 1.0,
                "issues": ["Missing title"],
                "action": "create",
            },
        ]

        results = generator.process_multiple_repositories(
            [("user", "repo1"), ("user", "repo2")]
        )

        assert len(results) == 2
        assert results[0]["status"] == "error"
        assert results[0]["error"] == "Boom"
        assert results[1]["status"] == "dry_run"
