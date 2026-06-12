"""Repository details screen."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static
from textual.worker import Worker, WorkerState

from gh_toolkit.core.health_checker import HealthReport, RepositoryHealthChecker
from gh_toolkit.core.repo_cloner import CloneResult, RepoCloner

if TYPE_CHECKING:
    from gh_toolkit.tui.app import GhToolkitApp


class RepoScreen(Screen[None]):
    """Screen displaying repository details."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("o", "open_browser", "Open in Browser"),
        Binding("h", "health_check", "Health Check"),
        Binding("c", "clone_repo", "Clone"),
    ]

    def __init__(self, repo_data: dict[str, Any], org_name: str) -> None:
        super().__init__()
        self.repo_data = repo_data
        self.org_name = org_name
        self.repo_name = repo_data.get("name", "Unknown")
        self._health_report: HealthReport | None = None
        self._is_checking = False
        self._is_cloning = False

    @property
    def app(self) -> GhToolkitApp:
        """Get the app instance with proper typing."""
        return super().app  # type: ignore[return-value]

    @property
    def full_name(self) -> str:
        """Get full repository name."""
        return f"{self.org_name}/{self.repo_name}"

    def compose(self) -> ComposeResult:
        """Compose the repository details screen."""
        # Extract repo info
        description = self.repo_data.get("description") or "No description"
        stars = self.repo_data.get("stargazers_count", 0)
        forks = self.repo_data.get("forks_count", 0)
        watchers = self.repo_data.get("watchers_count", 0)
        language = self.repo_data.get("language") or "Not specified"
        license_info = self.repo_data.get("license")
        license_name = license_info.get("name", "None") if license_info else "None"
        topics = self.repo_data.get("topics", [])
        updated_at = self.repo_data.get("updated_at", "")[:10]  # Just the date part

        # Format topics
        topics_str = ", ".join(topics) if topics else "None"

        yield Vertical(
            Static(f"\u2190 {self.repo_name}", classes="screen-title"),
            VerticalScroll(
                Vertical(
                    Static(self.full_name, classes="repo-header"),
                    Static("\u2500" * 60),
                    Static(""),
                    Static(description, classes="repo-description"),
                    Static(""),
                    Static(
                        f"\u2b50 {stars} stars   \U0001f374 {forks} forks   \U0001f441 {watchers} watchers",
                        classes="repo-stats",
                    ),
                    Static(""),
                    Static(f"Language:  {language}", classes="repo-meta"),
                    Static(f"License:   {license_name}", classes="repo-meta"),
                    Static(f"Topics:    {topics_str}", classes="repo-meta"),
                    Static(f"Updated:   {updated_at}", classes="repo-meta"),
                    Static(""),
                    Static("\u2500" * 60),
                    Static("Actions", classes="repo-header"),
                    Static(""),
                    Horizontal(
                        Button("[h] Health Check", id="btn-health", variant="default"),
                        Button("[c] Clone", id="btn-clone", variant="default"),
                        Button("[o] Open in Browser", id="btn-open", variant="default"),
                        classes="actions",
                    ),
                    Static(""),
                    Static("\u2500" * 60),
                    Static("", id="health-header", classes="repo-header"),
                    Static("", id="health-results", classes="health-results"),
                    classes="repo-details",
                ),
                id="repo-scroll",
            ),
            classes="content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-health":
            self.action_health_check()
        elif event.button.id == "btn-open":
            self.action_open_browser()
        elif event.button.id == "btn-clone":
            self.action_clone_repo()

    def action_go_back(self) -> None:
        """Go back to organization screen."""
        self.app.pop_screen()

    def action_open_browser(self) -> None:
        """Open repository in web browser."""
        url = self.repo_data.get("html_url", "")
        if url:
            webbrowser.open(url)
            self.app.notify(f"Opened {self.repo_name} in browser", timeout=2)
        else:
            self.app.notify("No URL available", severity="error", timeout=2)

    def action_health_check(self) -> None:
        """Run health check on the repository."""
        if self._is_checking:
            return

        self._is_checking = True
        health_header = self.query_one("#health-header", Static)
        health_results = self.query_one("#health-results", Static)

        health_header.update("Health Check")
        health_results.update("Running health check...")

        self.run_worker(
            self._do_health_check,
            name="health_check",
            exclusive=True,
        )

    async def _do_health_check(self) -> HealthReport:
        """Run health check (in worker)."""
        checker = RepositoryHealthChecker(self.app.github_client)
        return checker.check_repository_health(self.full_name, self.repo_data)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        worker_name = event.worker.name  # type: ignore[union-attr]

        if worker_name == "health_check":
            if event.state == WorkerState.SUCCESS:
                self._health_report = event.worker.result  # type: ignore[union-attr]
                self._display_health_results()
                self._is_checking = False
            elif event.state == WorkerState.ERROR:
                health_results = self.query_one("#health-results", Static)
                error_msg = str(event.worker.error or "Unknown error")  # type: ignore[union-attr]
                health_results.update(f"Error: {error_msg}")
                self._is_checking = False

        elif worker_name == "clone_repo":
            if event.state == WorkerState.SUCCESS:
                result: CloneResult = event.worker.result  # type: ignore[union-attr]
                self._handle_clone_result(result)
            elif event.state == WorkerState.ERROR:
                self._is_cloning = False
                error_msg = str(event.worker.error or "Unknown error")  # type: ignore[union-attr]
                self.app.notify(
                    error_msg,
                    title="Clone Failed",
                    severity="error",
                    timeout=5,
                )

    def _display_health_results(self) -> None:
        """Display health check results inline."""
        if not self._health_report:
            return

        report = self._health_report
        health_header = self.query_one("#health-header", Static)
        health_results = self.query_one("#health-results", Static)

        # Build grade display
        grade_colors = {
            "A": "\u2705",
            "B": "\u2705",
            "C": "\u26a0",
            "D": "\u26a0",
            "F": "\u26d4",
        }
        grade_icon = grade_colors.get(report.grade, "")

        health_header.update(
            f"Health Check: {grade_icon} Grade {report.grade} ({report.percentage:.0f}%)"
        )

        # Build results text
        lines: list[str] = []
        lines.append(f"Score: {report.total_score}/{report.max_score}")
        lines.append("")

        # Group checks by category
        by_category: dict[str, list[str]] = {}
        for check in report.checks:
            if check.category not in by_category:
                by_category[check.category] = []
            icon = "\u2705" if check.passed else "\u274c"
            by_category[check.category].append(
                f"  {icon} {check.name}: {check.message}"
            )

        for category, check_lines in by_category.items():
            lines.append(f"{category}:")
            lines.extend(check_lines)
            lines.append("")

        # Show top issues to fix
        top_issues = report.summary.get("top_issues", [])
        if top_issues:
            lines.append("Suggested fixes:")
            for issue in top_issues[:3]:
                if issue.fix_suggestion:
                    lines.append(f"  \u2022 {issue.name}: {issue.fix_suggestion}")

        health_results.update("\n".join(lines))

    def action_clone_repo(self) -> None:
        """Clone repository to local directory."""
        if self._is_cloning:
            return

        self._is_cloning = True
        self.app.notify(f"Cloning {self.full_name}...", timeout=2)

        self.run_worker(
            self._do_clone,
            name="clone_repo",
            exclusive=True,
        )

    async def _do_clone(self) -> CloneResult:
        """Clone repository (in worker)."""
        cloner = RepoCloner(target_dir="./repos")
        return cloner.clone_repository(self.full_name)

    def _handle_clone_result(self, result: CloneResult) -> None:
        """Handle clone result and notify user."""
        self._is_cloning = False

        if result.success:
            self.app.notify(
                f"Cloned to {result.target_path}",
                title="Clone Successful",
                timeout=5,
            )
        elif result.skipped:
            self.app.notify(
                result.skip_reason or "Already exists",
                title="Clone Skipped",
                severity="warning",
                timeout=3,
            )
        else:
            self.app.notify(
                result.error or "Unknown error",
                title="Clone Failed",
                severity="error",
                timeout=5,
            )
