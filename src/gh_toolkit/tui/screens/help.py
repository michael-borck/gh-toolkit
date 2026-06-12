"""Help screen showing keybindings and feature information."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\
[bold cyan]gh-toolkit TUI[/bold cyan]
A terminal interface for managing GitHub repositories.

[bold yellow]Global Keybindings[/bold yellow]
[dim]These work on any screen:[/dim]

  [bold]q[/bold]        Quit the application
  [bold]?[/bold]        Show this help screen
  [bold]r[/bold]        Refresh current view
  [bold]Esc[/bold]      Go back / Cancel

[bold yellow]Navigation[/bold yellow]

  [bold]↑ / k[/bold]    Move up
  [bold]↓ / j[/bold]    Move down
  [bold]Enter[/bold]    Select / Drill down
  [bold]Esc[/bold]      Go back to previous screen

[bold yellow]Search & Filter[/bold yellow]

  [bold]/[/bold]        Toggle search input
  [bold]Esc[/bold]      Cancel search (when searching)
  [bold]Enter[/bold]    Focus list (when in search)

[bold yellow]Selection (Repository Lists)[/bold yellow]

  [bold]Space[/bold]    Toggle selection of current item
  [bold]Ctrl+A[/bold]   Select all visible items
  [bold]Ctrl+D[/bold]   Deselect all

[bold yellow]Actions[/bold yellow]

  [bold]a[/bold]        Open actions menu
               Actions apply to:
               • Selected items (if any selected)
               • All visible items (if none selected)

[bold yellow]Organization Screen[/bold yellow]

  [bold]s[/bold]        Cycle sort (stars → name → updated)
  [bold]g[/bold]        Generate org README
  [bold]a[/bold]        Open actions / Audit

[bold yellow]Repository Screen[/bold yellow]

  [bold]h[/bold]        Run health check
  [bold]c[/bold]        Clone repository
  [bold]a[/bold]        Open actions

[bold yellow]Available Actions[/bold yellow]

  [bold cyan]Generate Descriptions[/bold cyan]
  Use AI to create repository descriptions.
  Options: model, force update, dry-run

  [bold cyan]Add Topics[/bold cyan]
  Intelligently tag repositories with topics.
  Options: model, preferred tags, force, dry-run

  [bold cyan]Generate Badges[/bold cyan]
  Create shields.io badge markdown from topics.
  Options: style, max badges, auto-apply to README

  [bold cyan]Health Check[/bold cyan]
  Audit repository quality and best practices.
  Options: rule set, minimum score

  [bold cyan]Audit[/bold cyan]
  Find missing descriptions, topics, licenses.

[bold yellow]Tips[/bold yellow]

  • Use [bold]/[/bold] to quickly find repos by name
  • Use [bold]Space[/bold] to select multiple repos for bulk actions
  • Actions respect your selection scope
  • Press [bold]Esc[/bold] to cancel any modal or go back

[dim]Press Esc or q to close this help[/dim]
"""


class HelpScreen(ModalScreen[None]):
    """Modal help screen with keybindings and features."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the help screen."""
        yield Vertical(
            Static("Help", classes="help-title"),
            VerticalScroll(
                Static(HELP_TEXT, classes="help-content", markup=True),
                id="help-scroll",
            ),
            classes="help-container",
        )

    def action_close(self) -> None:
        """Close the help screen."""
        self.dismiss()
