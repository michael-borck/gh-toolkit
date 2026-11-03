# Releasing gh-toolkit

1. `uv sync --group dev`
2. `uv run pytest`
3. `uv run ruff check src tests`
4. `uv run ruff format --check src tests`
5. `uv run basedpyright src/`
6. Bump `version` in `pyproject.toml` and `src/gh_toolkit/__init__.py`.
7. Update `CHANGELOG.md`.
8. Commit, tag, and push:
   ```bash
   git tag -a vX.Y.Z -m "gh-toolkit X.Y.Z"
   git push origin main --tags
   ```
9. The `release` workflow publishes to PyPI through trusted publishing.
10. Create a GitHub release: `gh release create vX.Y.Z --generate-notes`

PyPI trusted publishing must be configured for this repository, workflow
`release.yml`, and environment `pypi`.
