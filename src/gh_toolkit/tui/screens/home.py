"""Home screen showing organizations list."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static

if TYPE_CHECKING:
    from gh_toolkit.tui.app import GhToolkitApp


class OrgListItem(ListItem):
    """A list item representing an organization."""

    def __init__(self, org_data: dict[str, Any], selected: bool = False) -> None:
        super().__init__()
        self.org_data = org_data
        self.selected = selected

    def compose(self) -> ComposeResult:
        """Compose the org list item."""
        login = self.org_data.get("login", "Unknown")
        description = self.org_data.get("description", "") or ""

        # Truncate description if too long
        if len(description) > 45:
            description = description[:42] + "..."

        checkbox = "[x]" if self.selected else "[ ]"
        display = f"{checkbox} {login}"
        if description:
            display = f"{checkbox} {login} - {description}"

        yield Label(display)


class HomeScreen(Screen[None]):
    """Home screen displaying list of organizations."""

    BINDINGS = [
        Binding("enter", "select_org", "View"),
        Binding("escape", "cancel_or_quit", "Quit"),
        Binding("space", "toggle_selection", "Toggle"),
        Binding("a", "open_actions", "Actions"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "toggle_search", "Search"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("ctrl+d", "deselect_all", "Deselect"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._orgs: list[dict[str, Any]] = []
        self._filtered_orgs: list[dict[str, Any]] = []
        self._selected_orgs: set[str] = set()  # Set of org login names
        self._search_active = False

    @property
    def app(self) -> GhToolkitApp:
        """Get the app instance with proper typing."""
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        """Compose the home screen."""
        yield Vertical(
            Static("Organizations", classes="screen-title"),
            Input(
                placeholder="Search organizations...",
                id="search-input",
                classes="search-input hidden",
            ),
            Static("Loading...", id="stats-bar", classes="stats-bar"),
            ListView(id="org-list", classes="org-list"),
            classes="content",
        )

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.load_organizations()

    def load_organizations(self) -> None:
        """Load organizations from GitHub API."""
        list_view = self.query_one("#org-list", ListView)
        stats_bar = self.query_one("#stats-bar", Static)
        search_input = self.query_one("#search-input", Input)

        list_view.clear()
        stats_bar.update("Loading organizations...")

        try:
            self._orgs = self.app.get_organizations()

            if not self._orgs:
                stats_bar.update("No organizations found")
                return

            # Sort by login name
            self._orgs.sort(key=lambda x: x.get("login", "").lower())

            # Apply any existing search filter
            self._filter_orgs(search_input.value if self._search_active else "")

            # Focus the list
            list_view.focus()

        except Exception as e:
            stats_bar.update(f"Error: {e}")

    def _is_selected(self, org: dict[str, Any]) -> bool:
        """Check if an organization is selected."""
        return org.get("login", "") in self._selected_orgs

    def action_select_org(self) -> None:
        """Select the highlighted organization."""
        list_view = self.query_one("#org-list", ListView)

        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, OrgListItem):
                from gh_toolkit.tui.screens.org import OrgScreen

                self.app.push_screen(OrgScreen(item.org_data))

    def action_toggle_selection(self) -> None:
        """Toggle selection of highlighted item."""
        list_view = self.query_one("#org-list", ListView)

        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, OrgListItem):
                org_name = item.org_data.get("login", "")
                if org_name in self._selected_orgs:
                    self._selected_orgs.remove(org_name)
                    item.selected = False
                else:
                    self._selected_orgs.add(org_name)
                    item.selected = True
                item.refresh()
                self._update_stats_bar()

    def action_select_all(self) -> None:
        """Select all visible organizations."""
        list_view = self.query_one("#org-list", ListView)
        orgs = self._filtered_orgs if self._filtered_orgs else self._orgs

        for org in orgs:
            self._selected_orgs.add(org.get("login", ""))

        # Update all list items
        for child in list_view.children:
            if isinstance(child, OrgListItem):
                child.selected = True
                child.refresh()

        self._update_stats_bar()
        self.app.notify(f"Selected {len(orgs)} organizations", timeout=2)

    def action_deselect_all(self) -> None:
        """Deselect all organizations."""
        list_view = self.query_one("#org-list", ListView)
        self._selected_orgs.clear()

        # Update all list items
        for child in list_view.children:
            if isinstance(child, OrgListItem):
                child.selected = False
                child.refresh()

        self._update_stats_bar()
        self.app.notify("Cleared selection", timeout=2)

    def action_open_actions(self) -> None:
        """Open the actions modal for bulk operations across orgs."""
        from gh_toolkit.tui.widgets.action_modal import ActionModal

        # Determine which orgs to process
        if self._selected_orgs:
            target_orgs = [
                org
                for org in (self._filtered_orgs if self._filtered_orgs else self._orgs)
                if org.get("login", "") in self._selected_orgs
            ]
            scope_desc = f"repos in {len(target_orgs)} selected orgs"
        else:
            target_orgs = self._filtered_orgs if self._filtered_orgs else self._orgs
            scope_desc = f"repos in {len(target_orgs)} orgs"

        if not target_orgs:
            self.app.notify("No organizations to act on", severity="warning", timeout=2)
            return

        # Gather all repos from selected/visible orgs
        all_repos: list[tuple[str, str]] = []
        self.app.notify("Loading repositories from organizations...", timeout=2)

        for org in target_orgs:
            org_name = org.get("login", "")
            try:
                repos = self.app.get_org_repos(org_name)
                for repo in repos:
                    all_repos.append((org_name, repo.get("name", "")))
            except Exception:
                pass  # Skip orgs we can't access

        if not all_repos:
            self.app.notify(
                "No repositories found in selected organizations",
                severity="warning",
                timeout=2,
            )
            return

        def handle_result(result: Any) -> None:
            if result is not None:
                self._execute_actions(result)

        self.app.push_screen(ActionModal(all_repos, scope_desc), handle_result)

    def _execute_actions(self, action_result: Any) -> None:
        """Execute the selected actions."""
        from gh_toolkit.tui.screens.results import ResultsScreen
        from gh_toolkit.tui.widgets.action_executor import ActionExecutor

        executor = ActionExecutor()
        results = executor.execute(action_result)

        # Show results
        self.app.push_screen(ResultsScreen(results))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        if isinstance(event.item, OrgListItem):
            from gh_toolkit.tui.screens.org import OrgScreen

            self.app.push_screen(OrgScreen(event.item.org_data))

    def refresh_data(self) -> None:
        """Refresh organizations data."""
        self.load_organizations()

    def action_toggle_search(self) -> None:
        """Toggle the search input visibility."""
        search_input = self.query_one("#search-input", Input)
        if search_input.has_class("hidden"):
            search_input.remove_class("hidden")
            search_input.focus()
            self._search_active = True
        else:
            search_input.add_class("hidden")
            search_input.value = ""
            self._search_active = False
            self._filter_orgs("")
            list_view = self.query_one("#org-list", ListView)
            list_view.focus()

    def action_cancel_or_quit(self) -> None:
        """Cancel search or quit the app."""
        if self._search_active:
            self.action_toggle_search()
        else:
            self.app.exit()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self._filter_orgs(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "search-input":
            # Focus the list and select first item
            list_view = self.query_one("#org-list", ListView)
            list_view.focus()

    def _filter_orgs(self, query: str) -> None:
        """Filter organizations based on search query."""
        list_view = self.query_one("#org-list", ListView)

        list_view.clear()

        if not self._orgs:
            return

        # Filter orgs by login or description
        query_lower = query.lower()
        self._filtered_orgs = [
            org
            for org in self._orgs
            if query_lower in org.get("login", "").lower()
            or query_lower in (org.get("description") or "").lower()
        ]

        # Populate list with selection state
        for org in self._filtered_orgs:
            is_selected = self._is_selected(org)
            list_view.append(OrgListItem(org, selected=is_selected))

        self._update_stats_bar()

    def _update_stats_bar(self) -> None:
        """Update the stats bar with current info."""
        stats_bar = self.query_one("#stats-bar", Static)
        orgs = self._filtered_orgs if self._filtered_orgs else self._orgs
        selected_count = len(self._selected_orgs)

        parts = []

        if self._search_active and self._filtered_orgs:
            parts.append(f"{len(self._filtered_orgs)}/{len(self._orgs)} orgs")
        else:
            parts.append(f"{len(orgs)} organizations")

        if selected_count > 0:
            parts.append(f"[bold cyan]{selected_count} selected[/bold cyan]")

        stats_bar.update("  ".join(parts))
