# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Development Commands

### Setup and Dependencies
```bash
# Initial setup with development dependencies
uv sync --group dev

# Install package in development mode
uv pip install -e .
```

### Testing
```bash
# Run all tests (unit + integration)
./scripts/test.sh

# Run specific test suites
uv run pytest tests/unit/ -v          # Unit tests only
uv run pytest tests/integration/ -v   # Integration tests only

# Run single test file or method
uv run pytest tests/unit/test_github_client.py -v
uv run pytest tests/unit/test_github_client.py::TestGitHubClient::test_make_request_success -v

# Generate coverage report
./scripts/coverage.sh
```

### Code Quality
```bash
# Type checking (strict mode enabled)
uv run basedpyright src/

# Linting and formatting
uv run ruff check src/
uv run ruff format src/

# Fix auto-fixable issues
uv run ruff check src/ --fix
```

### Building and Publishing
```bash
# Build package
uv build

# Publish to PyPI (use twine, not uv - see pyproject.toml notes)
twine upload dist/*
```

## High-Level Architecture

gh-toolkit follows a layered architecture with clear separation of concerns:

### CLI Layer (`cli.py`)
- **Entry point**: Typer-based CLI with rich terminal output
- **Subcommands**: `repo`, `site`, `page`, `invite`, `transfer`, `org`, `portfolio` - each with focused responsibilities
- **Command registration**: Clean separation using typer sub-applications

### Commands Layer (`commands/`)
- **Business logic**: Each command implements specific user workflows
- **Input validation**: Typer handles argument parsing and validation
- **Output formatting**: Rich console output with progress indicators
- **Error handling**: User-friendly error messages and exit codes

### Core Layer (`core/`)
- **GitHub API Client** (`github_client.py`): Centralized API access with rate limiting
- **Repository Operations**: Extraction (`repo_extractor.py`), cloning (`repo_cloner.py`), health checking (`health_checker.py`)
- **Content Generation**: Site generation (`site_generator.py`), page generation (`page_generator.py`), README generation (`readme_generator.py`), portfolio generation (`portfolio_generator.py`)
- **LLM Integration** (`topic_tagger.py`, `readme_generator.py`): Anthropic Claude for intelligent categorization and descriptions

### Type System (`types.py`)
- **Comprehensive TypedDict definitions**: All GitHub API responses and internal data structures
- **Protocol interfaces**: Callback protocols for progress reporting
- **Type aliases**: Convenient type aliases for common patterns

## Key Architectural Patterns

### Type Safety Strategy
- **Strict typing**: basedpyright in strict mode with comprehensive error checking
- **Modern Python syntax**: Uses `|` union syntax, `list[T]`, `dict[K,V]` (Python 3.12+)
- **Documented workarounds**: See `TYPE_SAFETY_DOCUMENTATION.md` for all type compromises
- **Defensive patterns**: Safe attribute access for external API responses

### LLM Integration Pattern
- **Primary + Fallback**: Anthropic Claude for smart categorization with rule-based fallbacks
- **Graceful degradation**: Works without API key using pattern-based classification
- **Safe API handling**: Defensive programming for uncertain response structures

### GitHub API Integration
- **Centralized client**: Single `GitHubClient` class handles all API interactions
- **Rate limiting**: Automatic handling of rate limits with sleep/retry
- **Pagination**: Transparent handling of paginated responses
- **Error handling**: Consistent error types and user-friendly messages

### Data Flow Architecture
```
CLI Input → Command Validation → Core Operations → GitHub API → LLM Processing → Output Generation
```

## Important Development Context

### Environment Variables
```bash
export GITHUB_TOKEN=ghp_...          # Required for GitHub API access
export ANTHROPIC_API_KEY=sk-ant-...  # Optional, enables LLM features
```

### GitHub Token Scopes Required
- `repo` - Access repositories
- `read:org` - Read organization membership
- `write:org` - Accept organization invitations

### Type Safety Implementation Notes
- **4 type ignores** in `src/gh_toolkit/commands/site.py` (lines 66, 68, 78, 80) for JSON/YAML loading
- **1 safe cast** in `src/gh_toolkit/commands/site.py` (line 97) after runtime validation
- **2 type ignores** in `src/gh_toolkit/core/portfolio_generator.py` for reusing SiteGenerator internals
- **`tui/` package excluded** from basedpyright (see `[tool.basedpyright]` in pyproject.toml): textual's dynamic widget/reactive APIs don't satisfy strict mode; everything else in `src/` is checked strictly and must stay at 0 errors
- **Defensive patterns** in `repo_extractor.py`, `topic_tagger.py`, and `readme_generator.py` for external API responses
- All documented in `TYPE_SAFETY_DOCUMENTATION.md` with risk assessment

### New Organization & Portfolio Commands

**Organization README Generator** (`gh-toolkit org readme`):
```bash
# Generate README for an organization
gh-toolkit org readme my-org --output README.md
gh-toolkit org readme my-org --template detailed --group-by language
gh-toolkit org readme my-org --max-repos 20 --min-stars 5 --dry-run
```

**Portfolio Generator** (`gh-toolkit portfolio generate`):
```bash
# Generate cross-org portfolio
gh-toolkit portfolio generate --discover  # Auto-discover user's orgs
gh-toolkit portfolio generate --org org1 --org org2
gh-toolkit portfolio generate --discover --html portfolio.html --theme resume
```

**Portfolio Audit** (`gh-toolkit portfolio audit`):
```bash
# Audit repos for missing metadata
gh-toolkit portfolio audit --discover
gh-toolkit portfolio audit --org my-org --output audit-report.json
```

### Academic Use Case Focus
- **GitHub Classroom Alternative**: Designed for educators managing student repositories
- **Bulk operations**: Accept invitations, extract data, generate portfolios
- **Portfolio themes**: Educational, resume, research, portfolio themes
- **Categorization**: Intelligent classification of repositories by type and purpose

### Testing Strategy
- **Comprehensive fixtures**: `tests/conftest.py` provides mocked GitHub API responses
- **Isolated unit tests**: Mock external dependencies (GitHub API, Anthropic API)
- **Integration tests**: Test full workflows with real API structure (but mocked responses)
- **Environment isolation**: Fixtures handle environment variable mocking

### Modern Python Tooling
- **uv**: Fast Python package manager for dependencies and virtual environments
- **typer + rich**: Modern CLI framework with beautiful terminal output
- **basedpyright**: Strict type checker (faster fork of pyright)
- **ruff**: Fast linter and formatter (replaces black, isort, flake8)

## Common Development Workflows

### Adding a New Command
1. Create command function in appropriate `commands/` file
2. Add comprehensive type hints using types from `types.py`
3. Register command in `cli.py`
4. Add unit tests with mocked dependencies
5. Update help text and documentation

### Working with GitHub API
- Use existing `GitHubClient` - don't create direct API calls
- Add new API methods to `github_client.py` if needed
- Follow existing patterns for pagination and error handling
- Add corresponding TypedDict definitions in `types.py`

### LLM Integration Guidelines
- Always provide fallback behavior for when API is unavailable
- Use defensive attribute access: `getattr(obj, 'attr', default) if hasattr(obj, 'attr') else default`
- Handle API errors gracefully with user-friendly messages
- Consider rate limits and costs in design

### Type Safety Best Practices
- Add new types to `types.py` using TypedDict
- Prefer type guards over `cast()` when possible
- Document any new type ignores in `TYPE_SAFETY_DOCUMENTATION.md`
- Use Protocol interfaces for callback patterns
- Follow modern Python typing syntax

## Testing New Features

### Unit Test Pattern
```bash
# Test specific functionality
uv run pytest tests/unit/test_new_feature.py -v

# Test with coverage
uv run pytest tests/unit/test_new_feature.py --cov=src/gh_toolkit.new_module -v
```

### Integration Test Pattern
```bash
# Test full command workflows
uv run pytest tests/integration/test_new_command.py -v
```

### Type Checking During Development
```bash
# Quick type check
uv run basedpyright src/gh_toolkit/new_module.py

# Full codebase check
uv run basedpyright src/
```