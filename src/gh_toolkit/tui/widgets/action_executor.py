"""Action executor for running CLI operations from TUI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gh_toolkit.core.llm import (
    DEFAULT_LLM_MODEL,
)

if TYPE_CHECKING:
    from gh_toolkit.tui.widgets.action_modal import ActionResult


@dataclass
class ExecutionResult:
    """Result of executing an action."""

    action: str
    success_count: int
    error_count: int
    skipped_count: int
    results: list[dict[str, Any]]
    dry_run: bool


class ActionExecutor:
    """Executes actions on repositories."""

    def __init__(self) -> None:
        """Initialize the executor."""
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def execute(self, action_result: ActionResult) -> list[ExecutionResult]:
        """Execute the actions specified in the result.

        Args:
            action_result: The action configuration from the modal

        Returns:
            List of execution results for each action
        """
        results = []
        actions = action_result.action.split(",")

        for action in actions:
            if action == "describe":
                results.append(self._execute_describe(action_result))
            elif action == "readme":
                results.append(self._execute_readme(action_result))
            elif action == "license":
                results.append(self._execute_license(action_result))
            elif action == "tag":
                results.append(self._execute_tag(action_result))
            elif action == "badges":
                results.append(self._execute_badges(action_result))
            elif action == "health":
                results.append(self._execute_health(action_result))
            elif action == "audit":
                results.append(self._execute_audit(action_result))

        return results

    def _execute_describe(self, action_result: ActionResult) -> ExecutionResult:
        """Execute description generation."""
        from gh_toolkit.core.github_client import GitHubClient

        try:
            from gh_toolkit.core.description_generator import DescriptionGenerator
        except ImportError:
            return ExecutionResult(
                action="describe",
                success_count=0,
                error_count=1,
                skipped_count=0,
                results=[{"error": "DescriptionGenerator not available"}],
                dry_run=action_result.dry_run,
            )

        client = GitHubClient(self.github_token)
        model = action_result.options.get("describe_model", DEFAULT_LLM_MODEL)
        generator = DescriptionGenerator(client, self.anthropic_key, 0.5, model)

        results = generator.process_multiple_repositories(
            action_result.repos,
            action_result.dry_run,
            action_result.options.get("describe_force", False),
        )

        success = len([r for r in results if r.get("status") == "success"])
        errors = len([r for r in results if r.get("status") == "error"])
        skipped = len([r for r in results if r.get("status") == "skipped"])

        return ExecutionResult(
            action="describe",
            success_count=success,
            error_count=errors,
            skipped_count=skipped,
            results=results,
            dry_run=action_result.dry_run,
        )

    def _execute_tag(self, action_result: ActionResult) -> ExecutionResult:
        """Execute topic tagging."""
        from gh_toolkit.core.github_client import GitHubClient
        from gh_toolkit.core.topic_tagger import TopicTagger

        client = GitHubClient(self.github_token)
        model = action_result.options.get("tag_model", DEFAULT_LLM_MODEL)
        preferred = action_result.options.get("tag_preferred", "")

        tagger = TopicTagger(client, self.anthropic_key, 0.5, model, preferred or None)

        results = tagger.process_multiple_repositories(
            action_result.repos,
            action_result.dry_run,
            action_result.options.get("tag_force", False),
            False,  # add_description
        )

        success = len([r for r in results if r.get("status") == "success"])
        errors = len([r for r in results if r.get("status") == "error"])
        skipped = len([r for r in results if r.get("status") == "skipped"])

        return ExecutionResult(
            action="tag",
            success_count=success,
            error_count=errors,
            skipped_count=skipped,
            results=results,
            dry_run=action_result.dry_run,
        )

    def _execute_badges(self, action_result: ActionResult) -> ExecutionResult:
        """Execute badge generation."""
        from gh_toolkit.core.github_client import GitHubClient

        # Import badge functions from repo commands
        try:
            from gh_toolkit.commands.repo import (
                _apply_badges_to_readme,
                generate_badge_markdown,
            )
        except ImportError:
            return ExecutionResult(
                action="badges",
                success_count=0,
                error_count=1,
                skipped_count=0,
                results=[{"error": "Badge functions not available"}],
                dry_run=action_result.dry_run,
            )

        client = GitHubClient(self.github_token)
        style = action_result.options.get("badges_style", "flat-square")
        apply = (
            action_result.options.get("badges_apply", False)
            and not action_result.dry_run
        )

        results = []
        success_count = 0
        error_count = 0

        for owner, repo in action_result.repos:
            try:
                topics = client.get_repo_topics(owner, repo)
                if not topics:
                    results.append(
                        {
                            "repo": f"{owner}/{repo}",
                            "status": "skipped",
                            "message": "No topics found",
                        }
                    )
                    continue

                # Limit to 10 topics
                topics = topics[:10]

                # Generate badges
                badges = [
                    generate_badge_markdown(topic, style, True) for topic in topics
                ]
                badge_line = " ".join(badges)

                if apply:
                    _apply_badges_to_readme(client, owner, repo, badge_line)
                    results.append(
                        {
                            "repo": f"{owner}/{repo}",
                            "status": "success",
                            "message": f"Applied {len(badges)} badges",
                            "badges": badge_line,
                        }
                    )
                else:
                    results.append(
                        {
                            "repo": f"{owner}/{repo}",
                            "status": "dry_run" if action_result.dry_run else "success",
                            "message": f"Generated {len(badges)} badges",
                            "badges": badge_line,
                        }
                    )
                success_count += 1

            except Exception as e:
                results.append(
                    {
                        "repo": f"{owner}/{repo}",
                        "status": "error",
                        "message": str(e),
                    }
                )
                error_count += 1

        return ExecutionResult(
            action="badges",
            success_count=success_count,
            error_count=error_count,
            skipped_count=len([r for r in results if r.get("status") == "skipped"]),
            results=results,
            dry_run=action_result.dry_run,
        )

    def _execute_health(self, action_result: ActionResult) -> ExecutionResult:
        """Execute health checks."""
        from gh_toolkit.core.github_client import GitHubClient
        from gh_toolkit.core.health_checker import RepositoryHealthChecker

        client = GitHubClient(self.github_token)
        checker = RepositoryHealthChecker(client)

        results = []
        for owner, repo in action_result.repos:
            try:
                report = checker.check_repository(owner, repo)
                results.append(
                    {
                        "repo": f"{owner}/{repo}",
                        "status": "success",
                        "score": report.overall_score,
                        "grade": report.grade,
                        "passed": report.passed_checks,
                        "failed": report.failed_checks,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "repo": f"{owner}/{repo}",
                        "status": "error",
                        "message": str(e),
                    }
                )

        success = len([r for r in results if r.get("status") == "success"])
        errors = len([r for r in results if r.get("status") == "error"])

        return ExecutionResult(
            action="health",
            success_count=success,
            error_count=errors,
            skipped_count=0,
            results=results,
            dry_run=False,  # Health checks are always "real"
        )

    def _execute_audit(self, action_result: ActionResult) -> ExecutionResult:
        """Execute repository audit."""
        from gh_toolkit.core.github_client import GitHubClient

        client = GitHubClient(self.github_token)

        results = []
        issues_found = 0

        for owner, repo in action_result.repos:
            try:
                repo_data = client.get_repo(owner, repo)
                repo_issues = []

                # Check for missing description
                if not repo_data.get("description"):
                    repo_issues.append("missing_description")

                # Check for missing topics
                topics = client.get_repo_topics(owner, repo)
                if not topics:
                    repo_issues.append("missing_topics")

                # Check for missing license
                if not repo_data.get("license"):
                    repo_issues.append("missing_license")

                if repo_issues:
                    issues_found += 1
                    results.append(
                        {
                            "repo": f"{owner}/{repo}",
                            "status": "issues_found",
                            "issues": repo_issues,
                        }
                    )
                else:
                    results.append(
                        {
                            "repo": f"{owner}/{repo}",
                            "status": "success",
                            "issues": [],
                        }
                    )

            except Exception as e:
                results.append(
                    {
                        "repo": f"{owner}/{repo}",
                        "status": "error",
                        "message": str(e),
                    }
                )

        return ExecutionResult(
            action="audit",
            success_count=len([r for r in results if r.get("status") == "success"]),
            error_count=len([r for r in results if r.get("status") == "error"]),
            skipped_count=0,
            results=results,
            dry_run=False,
        )

    def _execute_readme(self, action_result: ActionResult) -> ExecutionResult:
        """Execute README generation."""
        from gh_toolkit.core.github_client import GitHubClient

        try:
            from gh_toolkit.core.repo_readme_generator import RepoReadmeGenerator
        except ImportError:
            return ExecutionResult(
                action="readme",
                success_count=0,
                error_count=1,
                skipped_count=0,
                results=[{"error": "RepoReadmeGenerator not available"}],
                dry_run=action_result.dry_run,
            )

        client = GitHubClient(self.github_token)
        model = action_result.options.get("readme_model", DEFAULT_LLM_MODEL)
        generator = RepoReadmeGenerator(client, self.anthropic_key, 0.5, model)

        results = generator.process_multiple_repositories(
            action_result.repos,
            action_result.dry_run,
            action_result.options.get("readme_force", False),
            0.5,  # min_quality threshold
        )

        success = len([r for r in results if r.get("status") == "updated"])
        errors = len([r for r in results if r.get("status") in ("failed", "error")])
        skipped = len([r for r in results if r.get("status") == "skipped"])
        dry_run_count = len([r for r in results if r.get("status") == "dry_run"])

        return ExecutionResult(
            action="readme",
            success_count=success + dry_run_count,
            error_count=errors,
            skipped_count=skipped,
            results=results,
            dry_run=action_result.dry_run,
        )

    def _execute_license(self, action_result: ActionResult) -> ExecutionResult:
        """Execute license addition."""
        from gh_toolkit.core.github_client import GitHubClient

        try:
            from gh_toolkit.core.license_manager import LicenseManager
        except ImportError:
            return ExecutionResult(
                action="license",
                success_count=0,
                error_count=1,
                skipped_count=0,
                results=[{"error": "LicenseManager not available"}],
                dry_run=action_result.dry_run,
            )

        client = GitHubClient(self.github_token)
        license_type = action_result.options.get("license_type", "mit")
        manager = LicenseManager(client, 0.5)

        results = manager.process_multiple_repositories(
            action_result.repos,
            license_type,
            None,  # name (will default to owner)
            action_result.dry_run,
            action_result.options.get("license_force", False),
        )

        created = len([r for r in results if r.get("status") == "created"])
        updated = len([r for r in results if r.get("status") == "updated"])
        errors = len([r for r in results if r.get("status") == "error"])
        skipped = len([r for r in results if r.get("status") == "skipped"])
        dry_run_count = len([r for r in results if r.get("status") == "dry_run"])

        return ExecutionResult(
            action="license",
            success_count=created + updated + dry_run_count,
            error_count=errors,
            skipped_count=skipped,
            results=results,
            dry_run=action_result.dry_run,
        )
