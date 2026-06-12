"""README preview screen for organization README generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual.worker import Worker, WorkerState

from gh_toolkit.core.readme_generator import OrgReadmeGenerator

if TYPE_CHECKING:
    from gh_toolkit.tui.app import GhToolkitApp


class PreviewScreen(Screen[None]):
    """Screen for previewing and saving generated README."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("s", "save", "Save"),
        Binding("t", "cycle_template", "Template"),
        Binding("g", "cycle_grouping", "Group By"),
        Binding("r", "regenerate", "Regenerate"),
    ]

    TEMPLATES = ["default", "minimal", "detailed"]
    GROUPINGS = ["category", "language", "topic"]

    def __init__(self, org_name: str, org_data: dict[str, Any]) -> None:
        super().__init__()
        self.org_name = org_name
        self.org_data = org_data
        self._readme_content: str = ""
        self._template_idx = 0
        self._grouping_idx = 0
        self._is_generating = False

    @property
    def app(self) -> GhToolkitApp:
        """Get the app instance with proper typing."""
        return super().app  # type: ignore[return-value]

    @property
    def template(self) -> str:
        """Get current template."""
        return self.TEMPLATES[self._template_idx]

    @property
    def grouping(self) -> str:
        """Get current grouping."""
        return self.GROUPINGS[self._grouping_idx]

    def compose(self) -> ComposeResult:
        """Compose the preview screen."""
        yield Vertical(
            Static(f"README Preview - {self.org_name}", classes="screen-title"),
            Static("", id="options-bar", classes="options-bar"),
            VerticalScroll(
                Static(
                    "Generating README...",
                    id="preview-content",
                    classes="preview-content",
                ),
                id="preview-scroll",
            ),
            classes="content",
        )

    def on_mount(self) -> None:
        """Generate README when screen is mounted."""
        self._update_options_bar()
        self._generate_readme()

    def _update_options_bar(self) -> None:
        """Update the options display bar."""
        options_bar = self.query_one("#options-bar", Static)
        options_bar.update(
            f"Template: [{self.template}]  Group by: [{self.grouping}]  "
            f"| s Save | t Template | g Group | r Regenerate | Esc Back"
        )

    def _generate_readme(self) -> None:
        """Start README generation in a worker."""
        if self._is_generating:
            return

        self._is_generating = True
        preview = self.query_one("#preview-content", Static)
        preview.update("Generating README...")

        self.run_worker(
            self._do_generate_readme,
            name="generate_readme",
            exclusive=True,
        )

    async def _do_generate_readme(self) -> str:
        """Generate README content (runs in worker)."""
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        generator = OrgReadmeGenerator(
            self.app.github_client,
            anthropic_api_key=anthropic_key,
        )

        # Generate without printing to console (TUI mode)
        try:
            content = generator.generate_readme(
                self.org_name,
                template=self.template,
                group_by=self.grouping,
                include_stats=True,
                exclude_forks=True,
            )
            return content
        except Exception as e:
            return f"Error generating README: {e}"

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "generate_readme":  # type: ignore[union-attr]
            if event.state == WorkerState.SUCCESS:
                # Worker result typing is incomplete in Textual
                self._readme_content = str(event.worker.result or "")  # type: ignore[union-attr]
                preview = self.query_one("#preview-content", Static)
                preview.update(self._readme_content)
                self._is_generating = False
            elif event.state == WorkerState.ERROR:
                preview = self.query_one("#preview-content", Static)
                error_msg = str(event.worker.error or "Unknown error")  # type: ignore[union-attr]
                preview.update(f"Error: {error_msg}")
                self._is_generating = False

    def action_go_back(self) -> None:
        """Go back to organization screen."""
        self.app.pop_screen()

    def action_cycle_template(self) -> None:
        """Cycle through template options."""
        self._template_idx = (self._template_idx + 1) % len(self.TEMPLATES)
        self._update_options_bar()
        self.app.notify(f"Template: {self.template}", timeout=1)

    def action_cycle_grouping(self) -> None:
        """Cycle through grouping options."""
        self._grouping_idx = (self._grouping_idx + 1) % len(self.GROUPINGS)
        self._update_options_bar()
        self.app.notify(f"Group by: {self.grouping}", timeout=1)

    def action_regenerate(self) -> None:
        """Regenerate README with current options."""
        if not self._is_generating:
            self.app.notify("Regenerating README...", timeout=1)
            self._generate_readme()

    def action_save(self) -> None:
        """Save README to file."""
        if not self._readme_content:
            self.app.notify("No content to save", severity="error", timeout=2)
            return

        # Default output path
        output_path = Path.cwd() / f"{self.org_name}-README.md"

        try:
            output_path.write_text(self._readme_content, encoding="utf-8")
            self.app.notify(
                f"Saved to {output_path.name}",
                title="README Saved",
                timeout=3,
            )
        except Exception as e:
            self.app.notify(
                f"Failed to save: {e}",
                severity="error",
                timeout=3,
            )
