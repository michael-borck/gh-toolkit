"""Repository health checker for quality audits and best practice validation."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

from gh_toolkit.core.github_client import GitHubClient

if TYPE_CHECKING:
    from gh_toolkit.core.rubric import Rubric


# Base scoring weights: category -> check -> points. The named rule sets below
# adjust these; a custom Rubric can override any of them (see core/rubric.py).
DEFAULT_WEIGHTS: dict[str, dict[str, int]] = {
    "documentation": {"readme": 10, "description": 5, "license": 5, "topics": 3},
    "structure": {"gitignore": 3, "organization": 5, "naming": 3},
    "quality": {"tests": 8, "ci_cd": 6, "activity": 4, "code_quality": 6},
    "metadata": {"homepage": 2, "releases": 4, "issues_enabled": 2},
}

# All HealthCheck.name values a report can contain (used to validate rubrics).
CHECK_NAMES: frozenset[str] = frozenset(
    {
        "README Existence",
        "README Quality",
        "Repository Description",
        "License",
        "Topics/Tags",
        "Gitignore File",
        "Organization",
        "Naming Conventions",
        "Tests",
        "CI/CD",
        "Activity",
        "Code Quality",
        "Homepage URL",
        "Releases",
        "Issues Enabled",
    }
)

# Letter grade -> minimum percentage. A Rubric may override these.
DEFAULT_GRADE_THRESHOLDS: dict[str, float] = {"A": 90, "B": 80, "C": 70, "D": 60}


@dataclass
class HealthCheck:
    """Individual health check result."""

    name: str
    category: str
    description: str
    passed: bool
    score: int  # Points awarded (0-10)
    max_score: int  # Maximum possible points
    message: str
    fix_suggestion: str | None = None


@dataclass
class HealthReport:
    """Complete health report for a repository."""

    repository: str
    total_score: int
    max_score: int
    percentage: float
    grade: str
    checks: list[HealthCheck]
    summary: dict[str, Any]


class RepositoryHealthChecker:
    """Comprehensive repository health and quality checker."""

    def __init__(
        self,
        github_client: GitHubClient,
        rules: str = "general",
        rubric: Rubric | None = None,
    ):
        """Initialize the health checker with a rule set and optional rubric.

        Args:
            github_client: GitHub API client
            rules: Named preset (general, academic, professional)
            rubric: Optional custom rubric. Its weight overrides are layered on
                top of the named preset; its grade thresholds and required
                checks replace the defaults when provided.
        """
        self.client = github_client
        self.rules = rules
        self.rubric = rubric
        self.grade_thresholds: dict[str, float] = dict(DEFAULT_GRADE_THRESHOLDS)
        self.required_checks: set[str] = set()
        self._init_rule_weights()

    def _init_rule_weights(self) -> None:
        """Initialize scoring weights from the preset, then any rubric overrides."""
        base_weights = copy.deepcopy(DEFAULT_WEIGHTS)

        if self.rules == "academic":
            # Emphasize documentation and structure for academic projects
            base_weights["documentation"]["readme"] = 15
            base_weights["documentation"]["description"] = 8
            base_weights["structure"]["organization"] = 8
            base_weights["quality"]["tests"] = 5  # Less emphasis on testing
        elif self.rules == "professional":
            # Emphasize quality and CI/CD for professional projects
            base_weights["quality"]["tests"] = 12
            base_weights["quality"]["ci_cd"] = 10
            base_weights["quality"]["code_quality"] = 8

        # Layer rubric weight overrides on top of the preset
        if self.rubric is not None:
            for category, checks in self.rubric.weights.items():
                for check_key, value in checks.items():
                    base_weights[category][check_key] = value
            if self.rubric.grades:
                self.grade_thresholds = dict(self.rubric.grades)
            self.required_checks = set(self.rubric.required)

        self.weights = base_weights

    def check_repository_health(
        self, repo_full_name: str, repo_data: dict[str, Any] | None = None
    ) -> HealthReport:
        """Check the health of a repository and return a comprehensive report."""
        if repo_data is None:
            repo_data = self._fetch_repository_data(repo_full_name)

        checks: list[HealthCheck] = []

        # Documentation checks
        checks.extend(self._check_documentation(repo_data))

        # Repository structure checks
        checks.extend(self._check_structure(repo_data))

        # Quality checks
        checks.extend(self._check_quality(repo_data))

        # Metadata checks
        checks.extend(self._check_metadata(repo_data))

        # Calculate scores
        total_score = sum(check.score for check in checks)
        max_score = sum(check.max_score for check in checks)
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        grade = self._calculate_grade(percentage)

        # Generate summary
        summary = self._generate_summary(checks, repo_data)

        # Flag any required checks (from a rubric) that did not pass
        if self.required_checks:
            summary["required_failures"] = [
                c.name
                for c in checks
                if c.name in self.required_checks and not c.passed
            ]

        return HealthReport(
            repository=repo_full_name,
            total_score=total_score,
            max_score=max_score,
            percentage=percentage,
            grade=grade,
            checks=checks,
            summary=summary,
        )

    def _fetch_repository_data(self, repo_full_name: str) -> dict[str, Any]:
        """Fetch repository data from GitHub API."""
        parts = [p for p in repo_full_name.strip().split("/") if p]
        if len(parts) != 2:
            raise ValueError(
                f"Invalid repository name '{repo_full_name}': expected 'owner/repo'"
            )
        owner, repo = parts

        # Get basic repository info
        repo_data = self.client.get_repo_info(owner, repo)

        # Get README content
        try:
            readme_content = self.client.get_repo_readme(owner, repo)
            repo_data["readme_content"] = readme_content
            repo_data["readme_size"] = len(readme_content)
        except Exception:
            repo_data["readme_content"] = ""
            repo_data["readme_size"] = 0

        # Get repository contents for structure analysis
        # Note: Using request() directly instead of get_paginated to avoid
        # progress bar issues; root contents are rarely paginated anyway
        try:
            response = self.client.request("GET", f"/repos/{owner}/{repo}/contents")
            contents = response.json()
            repo_data["root_files"] = [
                item["name"] for item in contents if item["type"] == "file"
            ]
            repo_data["root_dirs"] = [
                item["name"] for item in contents if item["type"] == "dir"
            ]
        except Exception:
            repo_data["root_files"] = []
            repo_data["root_dirs"] = []

        # Get workflow files for CI/CD analysis
        # Note: /actions/workflows returns {"total_count": N, "workflows": [...]}
        # not a list, so we can't use get_paginated
        try:
            response = self.client.request(
                "GET", f"/repos/{owner}/{repo}/actions/workflows"
            )
            workflows_data = response.json()
            repo_data["workflows"] = workflows_data.get("workflows", [])
        except Exception:
            repo_data["workflows"] = []

        return repo_data

    def _check_documentation(self, repo_data: dict[str, Any]) -> list[HealthCheck]:
        """Check documentation quality and completeness."""
        checks: list[HealthCheck] = []

        # README check
        has_readme = repo_data.get("readme_size", 0) > 0
        readme_quality = self._assess_readme_quality(
            repo_data.get("readme_content", "")
        )

        checks.append(
            HealthCheck(
                name="README Existence",
                category="Documentation",
                description="Repository has a README file",
                passed=has_readme,
                score=self.weights["documentation"]["readme"] if has_readme else 0,
                max_score=self.weights["documentation"]["readme"],
                message="README file found" if has_readme else "No README file found",
                fix_suggestion="Add a README.md file with project description, installation, and usage instructions"
                if not has_readme
                else None,
            )
        )

        if has_readme:
            readme_score = int(readme_quality * self.weights["documentation"]["readme"])
            checks.append(
                HealthCheck(
                    name="README Quality",
                    category="Documentation",
                    description="README content is comprehensive and well-structured",
                    passed=readme_quality >= 0.7,
                    score=readme_score,
                    max_score=self.weights["documentation"]["readme"],
                    message=f"README quality score: {readme_quality:.1%}",
                    fix_suggestion="Improve README with better structure, examples, and documentation"
                    if readme_quality < 0.7
                    else None,
                )
            )

        # Description check
        has_description = bool((repo_data.get("description") or "").strip())
        checks.append(
            HealthCheck(
                name="Repository Description",
                category="Documentation",
                description="Repository has a clear description",
                passed=has_description,
                score=self.weights["documentation"]["description"]
                if has_description
                else 0,
                max_score=self.weights["documentation"]["description"],
                message="Repository has description"
                if has_description
                else "No repository description",
                fix_suggestion="Add a clear, concise description of what the repository does"
                if not has_description
                else None,
            )
        )

        # License check
        has_license = repo_data.get("license") is not None
        checks.append(
            HealthCheck(
                name="License",
                category="Documentation",
                description="Repository has a license",
                passed=has_license,
                score=self.weights["documentation"]["license"] if has_license else 0,
                max_score=self.weights["documentation"]["license"],
                message=f"License: {repo_data.get('license', {}).get('name', 'None')}"
                if has_license
                else "No license specified",
                fix_suggestion="Add a LICENSE file to clarify usage terms"
                if not has_license
                else None,
            )
        )

        # Topics check
        topics = repo_data.get("topics", [])
        has_topics = len(topics) > 0
        topic_score = min(len(topics), 5) * (
            self.weights["documentation"]["topics"] // 5
        )

        checks.append(
            HealthCheck(
                name="Topics/Tags",
                category="Documentation",
                description="Repository has relevant topics for discoverability",
                passed=has_topics,
                score=topic_score,
                max_score=self.weights["documentation"]["topics"],
                message=f"{len(topics)} topics: {', '.join(topics[:3])}{'...' if len(topics) > 3 else ''}"
                if has_topics
                else "No topics assigned",
                fix_suggestion="Add relevant topics to improve repository discoverability"
                if not has_topics
                else None,
            )
        )

        return checks

    def _check_structure(self, repo_data: dict[str, Any]) -> list[HealthCheck]:
        """Check repository structure and organization."""
        checks: list[HealthCheck] = []
        root_files = repo_data.get("root_files", [])
        root_dirs = repo_data.get("root_dirs", [])

        # .gitignore check
        has_gitignore = ".gitignore" in root_files
        checks.append(
            HealthCheck(
                name="Gitignore File",
                category="Structure",
                description="Repository has a .gitignore file",
                passed=has_gitignore,
                score=self.weights["structure"]["gitignore"] if has_gitignore else 0,
                max_score=self.weights["structure"]["gitignore"],
                message=".gitignore file present"
                if has_gitignore
                else "No .gitignore file",
                fix_suggestion="Add a .gitignore file to exclude build artifacts and sensitive files"
                if not has_gitignore
                else None,
            )
        )

        # Organization check
        org_score = self._assess_organization(root_files, root_dirs, repo_data)
        checks.append(
            HealthCheck(
                name="Organization",
                category="Structure",
                description="Repository is well-organized with clear structure",
                passed=org_score >= 0.6,
                score=int(org_score * self.weights["structure"]["organization"]),
                max_score=self.weights["structure"]["organization"],
                message=f"Organization score: {org_score:.1%}",
                fix_suggestion="Improve repository organization with clear directory structure"
                if org_score < 0.6
                else None,
            )
        )

        # Naming conventions
        naming_score = self._assess_naming_conventions(repo_data.get("name", ""))
        checks.append(
            HealthCheck(
                name="Naming Conventions",
                category="Structure",
                description="Repository follows good naming conventions",
                passed=naming_score >= 0.7,
                score=int(naming_score * self.weights["structure"]["naming"]),
                max_score=self.weights["structure"]["naming"],
                message=f"Naming score: {naming_score:.1%}",
                fix_suggestion="Use descriptive, lowercase names with hyphens instead of underscores"
                if naming_score < 0.7
                else None,
            )
        )

        return checks

    def _check_quality(self, repo_data: dict[str, Any]) -> list[HealthCheck]:
        """Check code quality indicators."""
        checks: list[HealthCheck] = []
        root_dirs = repo_data.get("root_dirs", [])

        # Tests check
        test_dirs = [
            d
            for d in root_dirs
            if d.lower() in ["test", "tests", "spec", "specs", "__tests__"]
        ]
        has_tests = len(test_dirs) > 0
        checks.append(
            HealthCheck(
                name="Tests",
                category="Quality",
                description="Repository has test directory or test files",
                passed=has_tests,
                score=self.weights["quality"]["tests"] if has_tests else 0,
                max_score=self.weights["quality"]["tests"],
                message=f"Test directories: {', '.join(test_dirs)}"
                if has_tests
                else "No test directories found",
                fix_suggestion="Add a tests directory with unit tests for your code"
                if not has_tests
                else None,
            )
        )

        # CI/CD check
        workflows = repo_data.get("workflows", [])
        has_ci = len(workflows) > 0
        checks.append(
            HealthCheck(
                name="CI/CD",
                category="Quality",
                description="Repository has continuous integration setup",
                passed=has_ci,
                score=self.weights["quality"]["ci_cd"] if has_ci else 0,
                max_score=self.weights["quality"]["ci_cd"],
                message=f"GitHub Actions workflows: {len(workflows)}"
                if has_ci
                else "No CI/CD workflows",
                fix_suggestion="Add GitHub Actions workflows for automated testing and deployment"
                if not has_ci
                else None,
            )
        )

        # Activity check
        activity_score = self._assess_activity(repo_data)
        checks.append(
            HealthCheck(
                name="Activity",
                category="Quality",
                description="Repository shows recent development activity",
                passed=activity_score >= 0.5,
                score=int(activity_score * self.weights["quality"]["activity"]),
                max_score=self.weights["quality"]["activity"],
                message=f"Activity score: {activity_score:.1%}",
                fix_suggestion="Keep repository active with regular commits and updates"
                if activity_score < 0.5
                else None,
            )
        )

        # Code quality assessment
        code_score = self._assess_code_quality(repo_data)
        checks.append(
            HealthCheck(
                name="Code Quality",
                category="Quality",
                description="Repository shows good code quality practices",
                passed=code_score >= 0.6,
                score=int(code_score * self.weights["quality"]["code_quality"]),
                max_score=self.weights["quality"]["code_quality"],
                message=f"Code quality score: {code_score:.1%}",
                fix_suggestion="Improve code quality with better documentation and structure"
                if code_score < 0.6
                else None,
            )
        )

        return checks

    def _check_metadata(self, repo_data: dict[str, Any]) -> list[HealthCheck]:
        """Check repository metadata and configuration."""
        checks: list[HealthCheck] = []

        # Homepage URL check
        has_homepage = bool((repo_data.get("homepage") or "").strip())
        checks.append(
            HealthCheck(
                name="Homepage URL",
                category="Metadata",
                description="Repository has a homepage or demo URL",
                passed=has_homepage,
                score=self.weights["metadata"]["homepage"] if has_homepage else 0,
                max_score=self.weights["metadata"]["homepage"],
                message=f"Homepage: {repo_data.get('homepage', 'None')}"
                if has_homepage
                else "No homepage URL",
                fix_suggestion="Add a homepage URL for live demos or documentation"
                if not has_homepage
                else None,
            )
        )

        # Releases check
        # Note: This would require additional API call, simplified for now
        has_releases = repo_data.get("has_releases", False)
        checks.append(
            HealthCheck(
                name="Releases",
                category="Metadata",
                description="Repository uses releases for version management",
                passed=has_releases,
                score=self.weights["metadata"]["releases"] if has_releases else 0,
                max_score=self.weights["metadata"]["releases"],
                message="Uses releases" if has_releases else "No releases found",
                fix_suggestion="Create releases to track versions and changes"
                if not has_releases
                else None,
            )
        )

        # Issues enabled check
        has_issues = repo_data.get("has_issues", True)
        checks.append(
            HealthCheck(
                name="Issues Enabled",
                category="Metadata",
                description="Repository has issues enabled for community feedback",
                passed=has_issues,
                score=self.weights["metadata"]["issues_enabled"] if has_issues else 0,
                max_score=self.weights["metadata"]["issues_enabled"],
                message="Issues enabled" if has_issues else "Issues disabled",
                fix_suggestion="Enable issues to allow community feedback and bug reports"
                if not has_issues
                else None,
            )
        )

        return checks

    def _assess_readme_quality(self, readme_content: str) -> float:
        """Assess README quality based on content analysis."""
        if not readme_content:
            return 0.0

        # Decode base64 content if needed
        try:
            import base64

            readme_text = base64.b64decode(readme_content).decode("utf-8")
        except Exception:
            readme_text = readme_content

        score = 0.0
        max_score = 7.0

        # Has title
        if re.search(r"^#\s+.+", readme_text, re.MULTILINE):
            score += 1.0

        # Has description/introduction
        if len(readme_text.split("\n\n")) >= 2:
            score += 1.0

        # Has installation section
        if re.search(r"install", readme_text, re.IGNORECASE):
            score += 1.0

        # Has usage section
        if re.search(r"usage|example|getting started", readme_text, re.IGNORECASE):
            score += 1.0

        # Has code examples
        if re.search(r"```|`[^`]+`", readme_text):
            score += 1.0

        # Reasonable length (not too short)
        if len(readme_text) > 500:
            score += 1.0

        # Good structure (multiple sections)
        if len(re.findall(r"^##\s+", readme_text, re.MULTILINE)) >= 2:
            score += 1.0

        return score / max_score

    def _assess_organization(
        self, root_files: list[str], root_dirs: list[str], repo_data: dict[str, Any]
    ) -> float:
        """Assess repository organization quality."""
        score = 0.0
        max_score = 5.0

        # Has source directory
        if any(d in root_dirs for d in ["src", "lib", "source"]):
            score += 1.0

        # Not too many files in root
        if len(root_files) <= 10:
            score += 1.0

        # Has docs directory for larger projects
        if "docs" in root_dirs or "documentation" in root_dirs:
            score += 1.0

        # Has config files organization
        config_files = [f for f in root_files if f.startswith((".", "config", "setup"))]
        if len(config_files) <= 5:  # Not too many config files
            score += 1.0

        # Language-specific organization
        language = (repo_data.get("language") or "").lower()
        if language == "python" and any(
            f in root_files for f in ["setup.py", "pyproject.toml", "requirements.txt"]
        ):
            score += 1.0
        elif language == "javascript" and "package.json" in root_files:
            score += 1.0
        elif language in ["java", "kotlin", "scala"] and any(
            f in root_files for f in ["pom.xml", "build.gradle", "build.sbt"]
        ):
            score += 1.0
        elif language in ["c", "c++"] and any(
            f in root_files for f in ["Makefile", "CMakeLists.txt"]
        ):
            score += 1.0
        else:
            score += 0.5  # Partial credit for other languages

        return score / max_score

    def _assess_naming_conventions(self, repo_name: str) -> float:
        """Assess repository naming conventions."""
        score = 0.0
        max_score = 4.0

        # Uses lowercase
        if repo_name.islower():
            score += 1.0

        # Uses hyphens instead of underscores
        if "-" in repo_name and "_" not in repo_name:
            score += 1.0
        elif "_" not in repo_name:
            score += 0.5

        # Descriptive (reasonable length)
        if 3 <= len(repo_name) <= 50:
            score += 1.0

        # No special characters except hyphens
        if re.match(r"^[a-z0-9-]+$", repo_name):
            score += 1.0

        return score / max_score

    def _assess_activity(self, repo_data: dict[str, Any]) -> float:
        """Assess repository activity level."""
        from datetime import datetime

        score = 0.0
        max_score = 3.0

        # Recent updates
        updated_at = repo_data.get("updated_at", "")
        if updated_at:
            try:
                updated_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                days_since_update = (datetime.now(UTC) - updated_date).days

                if days_since_update < 30:
                    score += 1.0
                elif days_since_update < 90:
                    score += 0.7
                elif days_since_update < 365:
                    score += 0.3
            except Exception:
                pass

        # Not archived
        if not repo_data.get("archived", False):
            score += 1.0

        # Has recent commits (based on pushed_at)
        pushed_at = repo_data.get("pushed_at", "")
        if pushed_at:
            try:
                pushed_date = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (datetime.now(UTC) - pushed_date).days

                if days_since_push < 30:
                    score += 1.0
                elif days_since_push < 90:
                    score += 0.7
                elif days_since_push < 180:
                    score += 0.3
            except Exception:
                pass

        return score / max_score

    def _assess_code_quality(self, repo_data: dict[str, Any]) -> float:
        """Assess code quality indicators."""
        score = 0.0
        max_score = 4.0

        # Repository size (not too small, not too large)
        size_kb = repo_data.get("size", 0)
        if 10 <= size_kb <= 100000:  # 10KB to 100MB
            score += 1.0
        elif size_kb > 0:
            score += 0.5

        # Has stars (community validation)
        stars = repo_data.get("stargazers_count", 0)
        if stars >= 10:
            score += 1.0
        elif stars >= 1:
            score += 0.5

        # Language specified
        if repo_data.get("language"):
            score += 1.0

        # Multiple contributors or substantial single contribution
        # This is simplified - in real implementation we'd check contributors
        if not repo_data.get("fork", False):  # Original repository
            score += 1.0

        return score / max_score

    def _calculate_grade(self, percentage: float) -> str:
        """Calculate letter grade from the configured thresholds.

        Returns the highest-threshold letter the percentage meets, or "F" if it
        meets none. Thresholds come from the rubric when provided.
        """
        for letter, threshold in sorted(
            self.grade_thresholds.items(), key=lambda kv: kv[1], reverse=True
        ):
            if percentage >= threshold:
                return letter
        return "F"

    def _generate_summary(
        self, checks: list[HealthCheck], repo_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate summary statistics and insights."""
        by_category: dict[str, dict[str, Any]] = {}
        for check in checks:
            if check.category not in by_category:
                by_category[check.category] = {
                    "passed": 0,
                    "total": 0,
                    "score": 0,
                    "max_score": 0,
                }

            by_category[check.category]["total"] += 1
            by_category[check.category]["score"] += check.score
            by_category[check.category]["max_score"] += check.max_score
            if check.passed:
                by_category[check.category]["passed"] += 1

        # Calculate category percentages
        for cat_data in by_category.values():
            cat_data["percentage"] = (
                (cat_data["score"] / cat_data["max_score"] * 100)
                if cat_data["max_score"] > 0
                else 0
            )

        # Top issues to fix
        failed_checks: list[HealthCheck] = [
            check for check in checks if not check.passed and check.fix_suggestion
        ]
        failed_checks.sort(key=lambda x: x.max_score, reverse=True)  # Sort by impact

        return {
            "by_category": by_category,
            "total_checks": len(checks),
            "passed_checks": sum(1 for check in checks if check.passed),
            "failed_checks": len(checks) - sum(1 for check in checks if check.passed),
            "top_issues": failed_checks[:5],  # Top 5 issues to fix
            "repository_info": {
                "language": repo_data.get("language"),
                "size_kb": repo_data.get("size", 0),
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "created_at": repo_data.get("created_at"),
                "updated_at": repo_data.get("updated_at"),
            },
        }
