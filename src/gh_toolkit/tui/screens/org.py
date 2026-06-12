"""Organization screen showing repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static

if TYPE_CHECKING:
    from gh_toolkit.tui.app import GhToolkitApp


class RepoListItem(ListItem):
    """A list item representing a repository."""

    def __init__(self, repo_data: dict[str, Any], selected: bool = False) -> None:
        super().__init__()
        self.repo_data = repo_data
        self.selected = selected

    def compose(self) -> ComposeResult:
        """Compose the repo list item."""
        name = self.repo_data.get("name", "Unknown")
        stars = self.repo_data.get("stargazers_count", 0)
        language = self.repo_data.get("language") or "—"
        description = self.repo_data.get("description", "") or ""

        # Truncate description
        if len(description) > 35:
            description = description[:32] + "..."

        # Format: [x] name  ⭐ N  Language  Description
        star_display = f"⭐{stars}" if stars > 0 else "   "
        checkbox = "[x]" if self.selected else "[ ]"

        display = (
            f"{checkbox} {name:<18} {star_display:>4}  {language:<10} {description}"
        )
        yield Label(display)

    def toggle_selection(self) -> None:
        """Toggle the selection state."""
        self.selected = not self.selected
        # Refresh the display
        self.refresh()


class OrgScreen(Screen[None]):
    """Screen displaying an organization's repositories."""

    BINDINGS = [
        Binding("enter", "select_repo", "View"),
        Binding("escape", "cancel_or_back", "Back"),
        Binding("space", "toggle_selection", "Toggle"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("g", "generate_readme", "README"),
        Binding("a", "open_actions", "Actions"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "toggle_search", "Search"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("ctrl+d", "deselect_all", "Deselect"),
    ]

    def __init__(self, org_data: dict[str, Any]) -> None:
        super().__init__()
        self.org_data = org_data
        self.org_name = org_data.get("login", "Unknown")
        self._repos: list[dict[str, Any]] = []
        self._filtered_repos: list[dict[str, Any]] = []
        self._selected_repos: set[str] = set()  # Set of "owner/repo" strings
        self._sort_by = "stars"  # stars, name, updated
        self._search_active = False

    @property
    def app(self) -> GhToolkitApp:
        """Get the app instance with proper typing."""
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        """Compose the organization screen."""
        yield Vertical(
            Static(f"← {self.org_name}", classes="screen-title"),
            Input(
                placeholder="Search repositories...",
                id="search-input",
                classes="search-input hidden",
            ),
            Static("Loading...", id="stats-bar", classes="stats-bar"),
            ListView(id="repo-list", classes="repo-list"),
            classes="content",
        )

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.load_repositories()

    def load_repositories(self) -> None:
        """Load repositories for this organization."""
        list_view = self.query_one("#repo-list", ListView)
        stats_bar = self.query_one("#stats-bar", Static)
        search_input = self.query_one("#search-input", Input)

        list_view.clear()
        stats_bar.update("Loading repositories...")

        try:
            self._repos = self.app.get_org_repos(self.org_name)

            if not self._repos:
                stats_bar.update("No repositories found")
                return

            # Sort repos
            self._sort_repos()

            # Apply any existing search filter
            self._filter_repos(search_input.value if self._search_active else "")

            # Focus the list
            list_view.focus()

        except Exception as e:
            stats_bar.update(f"Error: {e}")

    def _sort_repos(self) -> None:
        """Sort repositories based on current sort setting."""
        if self._sort_by == "stars":
            self._repos.sort(key=lambda x: x.get("stargazers_count", 0), reverse=True)
        elif self._sort_by == "name":
            self._repos.sort(key=lambda x: x.get("name", "").lower())
        elif self._sort_by == "updated":
            self._repos.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

    def _get_repo_key(self, repo: dict[str, Any]) -> str:
        """Get unique key for a repository."""
        return f"{self.org_name}/{repo.get('name', '')}"

    def _is_selected(self, repo: dict[str, Any]) -> bool:
        """Check if a repository is selected."""
        return self._get_repo_key(repo) in self._selected_repos

    def action_select_repo(self) -> None:
        """View the highlighted repository."""
        list_view = self.query_one("#repo-list", ListView)

        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, RepoListItem):
                from gh_toolkit.tui.screens.repo import RepoScreen

                self.app.push_screen(RepoScreen(item.repo_data, self.org_name))

    def action_toggle_selection(self) -> None:
        """Toggle selection of highlighted item."""
        list_view = self.query_one("#repo-list", ListView)

        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, RepoListItem):
                repo_key = self._get_repo_key(item.repo_data)
                if repo_key in self._selected_repos:
                    self._selected_repos.remove(repo_key)
                    item.selected = False
                else:
                    self._selected_repos.add(repo_key)
                    item.selected = True
                item.refresh()
                self._update_stats_bar()

    def action_select_all(self) -> None:
        """Select all visible repositories."""
        list_view = self.query_one("#repo-list", ListView)
        repos = self._filtered_repos if self._filtered_repos else self._repos

        for repo in repos:
            self._selected_repos.add(self._get_repo_key(repo))

        # Update all list items
        for child in list_view.children:
            if isinstance(child, RepoListItem):
                child.selected = True
                child.refresh()

        self._update_stats_bar()
        self.app.notify(f"Selected {len(repos)} repositories", timeout=2)

    def action_deselect_all(self) -> None:
        """Deselect all repositories."""
        list_view = self.query_one("#repo-list", ListView)
        self._selected_repos.clear()

        # Update all list items
        for child in list_view.children:
            if isinstance(child, RepoListItem):
                child.selected = False
                child.refresh()

        self._update_stats_bar()
        self.app.notify("Cleared selection", timeout=2)

    def action_open_actions(self) -> None:
        """Open the actions modal."""
        from gh_toolkit.tui.widgets.action_modal import ActionModal

        # Determine scope: selected repos or all visible repos
        if self._selected_repos:
            repos = [
                (self.org_name, repo.get("name", ""))
                for repo in (
                    self._filtered_repos if self._filtered_repos else self._repos
                )
                if self._get_repo_key(repo) in self._selected_repos
            ]
            scope_desc = f"selected in {self.org_name}"
        else:
            repos_list = self._filtered_repos if self._filtered_repos else self._repos
            repos = [(self.org_name, repo.get("name", "")) for repo in repos_list]
            scope_desc = f"repos in {self.org_name}"

        if not repos:
            self.app.notify("No repositories to act on", severity="warning", timeout=2)
            return

        def handle_result(result: Any) -> None:
            if result is not None:
                self._execute_actions(result)

        self.app.push_screen(ActionModal(repos, scope_desc), handle_result)

    def _execute_actions(self, action_result: Any) -> None:
        """Execute the selected actions."""
        from gh_toolkit.tui.screens.results import ResultsScreen
        from gh_toolkit.tui.widgets.action_executor import ActionExecutor

        executor = ActionExecutor()
        results = executor.execute(action_result)

        # Show results
        self.app.push_screen(ResultsScreen(results))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item double-click/enter."""
        if isinstance(event.item, RepoListItem):
            from gh_toolkit.tui.screens.repo import RepoScreen

            self.app.push_screen(RepoScreen(event.item.repo_data, self.org_name))

    def action_cancel_or_back(self) -> None:
        """Cancel search or go back to home screen."""
        if self._search_active:
            self.action_toggle_search()
        else:
            self.app.pop_screen()

    def action_cycle_sort(self) -> None:
        """Cycle through sort options."""
        sort_options = ["stars", "name", "updated"]
        current_idx = sort_options.index(self._sort_by)
        self._sort_by = sort_options[(current_idx + 1) % len(sort_options)]
        self.load_repositories()

    def refresh_data(self) -> None:
        """Refresh repository data."""
        # Clear cache for this org
        self.app.clear_org_cache(self.org_name)
        self.load_repositories()

    def action_generate_readme(self) -> None:
        """Generate README for this organization."""
        from gh_toolkit.tui.screens.preview import PreviewScreen

        self.app.push_screen(PreviewScreen(self.org_name, self.org_data))

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
            self._filter_repos("")
            list_view = self.query_one("#repo-list", ListView)
            list_view.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self._filter_repos(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "search-input":
            # Focus the list and select first item
            list_view = self.query_one("#repo-list", ListView)
            list_view.focus()

    def _filter_repos(self, query: str) -> None:
        """Filter repositories based on search query."""
        list_view = self.query_one("#repo-list", ListView)

        list_view.clear()

        if not self._repos:
            return

        # Filter repos by name or description
        query_lower = query.lower()
        self._filtered_repos = [
            repo
            for repo in self._repos
            if query_lower in repo.get("name", "").lower()
            or query_lower in (repo.get("description") or "").lower()
        ]

        # Populate list with selection state
        for repo in self._filtered_repos:
            is_selected = self._is_selected(repo)
            list_view.append(RepoListItem(repo, selected=is_selected))

        self._update_stats_bar()

    def _update_stats_bar(self) -> None:
        """Update the stats bar with current info."""
        stats_bar = self.query_one("#stats-bar", Static)
        repos = self._filtered_repos if self._filtered_repos else self._repos

        # Calculate stats
        total_stars = sum(r.get("stargazers_count", 0) for r in repos)
        languages = {r.get("language") for r in repos if r.get("language")}
        selected_count = len(self._selected_repos)

        # Build stats string
        sort_indicator = {"stars": "⭐", "name": "A-Z", "updated": "📅"}
        parts = []

        if self._search_active and self._filtered_repos:
            parts.append(f"{len(self._filtered_repos)}/{len(self._repos)} repos")
        else:
            parts.append(f"{len(repos)} repos")

        parts.append(f"⭐{total_stars}")
        parts.append(f"{len(languages)} lang")
        parts.append(f"Sort: {sort_indicator.get(self._sort_by, '')}")

        if selected_count > 0:
            parts.append(f"[bold cyan]{selected_count} selected[/bold cyan]")

        stats_bar.update("  ".join(parts))
