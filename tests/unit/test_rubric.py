"""Unit tests for custom health rubrics."""

import pytest

from gh_toolkit.core.health_checker import (
    DEFAULT_GRADE_THRESHOLDS,
    DEFAULT_WEIGHTS,
    RepositoryHealthChecker,
)
from gh_toolkit.core.rubric import Rubric, load_rubric


def _write(tmp_path, text, name="rubric.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestLoadRubric:
    def test_full_rubric(self, tmp_path):
        path = _write(
            tmp_path,
            """
name: Assignment 2
weights:
  documentation:
    readme: 20
    license: 0
  quality:
    tests: 15
grades:
  A: 90
  B: 75
required:
  - README Existence
  - Tests
""",
        )
        r = load_rubric(path)
        assert r.name == "Assignment 2"
        assert r.weights["documentation"]["readme"] == 20
        assert r.weights["documentation"]["license"] == 0
        assert r.weights["quality"]["tests"] == 15
        assert r.grades == {"A": 90.0, "B": 75.0}
        assert r.required == ["README Existence", "Tests"]

    def test_empty_file_is_empty_rubric(self, tmp_path):
        path = _write(tmp_path, "")
        r = load_rubric(path)
        assert r.weights == {}
        assert r.grades == {}
        assert r.required == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_rubric(tmp_path / "nope.yaml")

    def test_non_mapping_raises(self, tmp_path):
        path = _write(tmp_path, "- just\n- a list\n")
        with pytest.raises(ValueError, match="mapping at the top level"):
            load_rubric(path)

    def test_unknown_top_level_key_raises(self, tmp_path):
        path = _write(tmp_path, "weighted: {}\n")
        with pytest.raises(ValueError, match="Unknown rubric keys"):
            load_rubric(path)

    def test_unknown_category_raises(self, tmp_path):
        path = _write(tmp_path, "weights:\n  docs:\n    readme: 5\n")
        with pytest.raises(ValueError, match="Unknown weight category"):
            load_rubric(path)

    def test_unknown_check_raises(self, tmp_path):
        path = _write(tmp_path, "weights:\n  documentation:\n    readmee: 5\n")
        with pytest.raises(ValueError, match="Unknown check"):
            load_rubric(path)

    def test_negative_weight_raises(self, tmp_path):
        path = _write(tmp_path, "weights:\n  documentation:\n    readme: -1\n")
        with pytest.raises(ValueError, match="non-negative integer"):
            load_rubric(path)

    def test_bad_grade_threshold_raises(self, tmp_path):
        path = _write(tmp_path, "grades:\n  A: 150\n")
        with pytest.raises(ValueError, match="between 0 and 100"):
            load_rubric(path)

    def test_unknown_required_check_raises(self, tmp_path):
        path = _write(tmp_path, "required:\n  - Nonexistent Check\n")
        with pytest.raises(ValueError, match="Unknown required check"):
            load_rubric(path)

    def test_invalid_yaml_raises(self, tmp_path):
        path = _write(tmp_path, "weights: {: :}\n")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_rubric(path)


class TestCheckerWithRubric:
    def test_rubric_overrides_weight_on_top_of_preset(self, mocker):
        client = mocker.Mock()
        rubric = Rubric(weights={"documentation": {"readme": 50}})
        checker = RepositoryHealthChecker(client, "academic", rubric=rubric)
        # academic sets readme to 15, rubric overrides to 50
        assert checker.weights["documentation"]["readme"] == 50
        # untouched academic value remains
        assert checker.weights["documentation"]["description"] == 8

    def test_no_rubric_uses_defaults(self, mocker):
        client = mocker.Mock()
        checker = RepositoryHealthChecker(client, "general")
        assert (
            checker.weights["documentation"]["readme"]
            == DEFAULT_WEIGHTS["documentation"]["readme"]
        )
        assert checker.grade_thresholds == DEFAULT_GRADE_THRESHOLDS
        assert checker.required_checks == set()

    def test_custom_grade_thresholds_applied(self, mocker):
        client = mocker.Mock()
        rubric = Rubric(grades={"A": 50, "B": 25})
        checker = RepositoryHealthChecker(client, "general", rubric=rubric)
        assert checker._calculate_grade(60) == "A"
        assert checker._calculate_grade(30) == "B"
        assert checker._calculate_grade(10) == "F"

    def test_required_failures_recorded_in_summary(self, mocker):
        client = mocker.Mock()
        rubric = Rubric(required=["README Existence", "Tests"])
        checker = RepositoryHealthChecker(client, "general", rubric=rubric)

        # Repo with no README and no tests -> both required checks fail
        repo_data = {
            "name": "empty",
            "full_name": "u/empty",
            "description": "",
            "language": None,
            "stargazers_count": 0,
            "forks_count": 0,
            "watchers_count": 0,
            "size": 0,
            "license": None,
            "topics": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "homepage": "",
            "has_issues": True,
            "archived": False,
            "fork": False,
            "private": False,
            "readme_content": "",
            "readme_size": 0,
            "root_files": [],
            "root_dirs": [],
            "workflows": [],
        }
        report = checker.check_repository_health("u/empty", repo_data)
        assert "README Existence" in report.summary["required_failures"]
        assert "Tests" in report.summary["required_failures"]
