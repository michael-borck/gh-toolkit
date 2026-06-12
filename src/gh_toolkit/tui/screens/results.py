"""Results screen showing action execution outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

if TYPE_CHECKING:
    from gh_toolkit.tui.widgets.action_executor import ExecutionResult


class ResultsScreen(ModalScreen[None]):
    """Modal screen showing action execution results."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]

    def __init__(self, results: list[ExecutionResult]) -> None:
        """Initialize results screen.

        Args:
            results: List of execution results to display
        """
        super().__init__()
        self.results = results

    def compose(self) -> ComposeResult:
        """Compose the results screen."""
        yield Vertical(
            Static("Action Results", classes="modal-title"),
            VerticalScroll(
                Static(self._format_results(), classes="results-content", markup=True),
                id="results-scroll",
            ),
            Button("Close", variant="primary", id="btn-close"),
            classes="results-modal",
        )

    def _format_results(self) -> str:
        """Format results for display."""
        lines = []

        for result in self.results:
            # Action header
            action_name = result.action.replace("_", " ").title()
            if result.dry_run:
                lines.append(
                    f"[bold cyan]{action_name}[/bold cyan] [dim](dry run)[/dim]"
                )
            else:
                lines.append(f"[bold cyan]{action_name}[/bold cyan]")

            # Summary
            lines.append(
                f"  [green]{result.success_count}[/green] success, "
                f"[red]{result.error_count}[/red] errors, "
                f"[yellow]{result.skipped_count}[/yellow] skipped"
            )
            lines.append("")

            # Details for each repo
            for item in result.results[:20]:  # Limit to 20 items
                repo = item.get("repo", "unknown")
                status = item.get("status", "unknown")

                if status == "success":
                    icon = "[green]\u2713[/green]"
                elif status == "dry_run":
                    icon = "[cyan]\u2713[/cyan]"
                elif status == "error":
                    icon = "[red]\u2717[/red]"
                elif status == "skipped":
                    icon = "[yellow]\u2192[/yellow]"
                elif status == "issues_found":
                    icon = "[yellow]![/yellow]"
                else:
                    icon = "[dim]?[/dim]"

                detail = ""
                if "message" in item:
                    detail = f" - {item['message']}"
                elif "issues" in item and item["issues"]:
                    detail = f" - {', '.join(item['issues'])}"
                elif "grade" in item:
                    detail = f" - Grade: {item['grade']} ({item['score']}%)"

                lines.append(f"  {icon} {repo}{detail}")

            if len(result.results) > 20:
                lines.append(f"  [dim]... and {len(result.results) - 20} more[/dim]")

            lines.append("")

        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-close":
            self.dismiss()

    def action_close(self) -> None:
        """Close the results screen."""
        self.dismiss()
