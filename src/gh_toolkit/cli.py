"""Main CLI entry point for gh-toolkit."""

# Import commands
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit import __version__
from gh_toolkit.commands.invite import accept_invitations, leave_repositories
from gh_toolkit.commands.org import readme as org_readme
from gh_toolkit.commands.page import generate_page
from gh_toolkit.commands.portfolio import audit as portfolio_audit
from gh_toolkit.commands.portfolio import generate as portfolio_generate
from gh_toolkit.commands.repo import (
    clone_repos,
    describe_repos,
    extract_repos,
    generate_badges,
    health_check,
    license_repos,
    list_repos,
    readme_repos,
)
from gh_toolkit.commands.site import generate_site
from gh_toolkit.commands.tag import tag_repos
from gh_toolkit.commands.transfer import (
    accept_transfers,
    initiate_transfer,
    list_transfers,
)

app = typer.Typer(
    name="gh-toolkit",
    help="GitHub repository portfolio management and presentation toolkit",
    no_args_is_help=True,
)
console = Console()

# Create subcommands
repo_app = typer.Typer(help="Repository management commands")
invite_app = typer.Typer(help="Invitation management commands")
transfer_app = typer.Typer(help="Transfer management commands")
org_app = typer.Typer(help="Organization management commands")
portfolio_app = typer.Typer(help="Portfolio generation commands")

site_app = typer.Typer(help="Site generation commands")
page_app = typer.Typer(help="Page generation commands")

# Register subcommands
app.add_typer(repo_app, name="repo")
app.add_typer(invite_app, name="invite")
app.add_typer(transfer_app, name="transfer")
app.add_typer(org_app, name="org")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(site_app, name="site")
app.add_typer(page_app, name="page")


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"gh-toolkit version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", help="Show version and exit", callback=version_callback
    ),
) -> None:
    """GitHub Toolkit - Repository portfolio management and presentation."""
    pass


@app.command()
def info() -> None:
    """Show information about gh-toolkit."""
    table = Table(title="gh-toolkit Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", __version__)
    table.add_row("Description", "GitHub repository portfolio management toolkit")
    table.add_row("Author", "Michael Borck")

    console.print(table)


@app.command()
def tui() -> None:
    """Launch interactive TUI for browsing organizations and repositories."""
    try:
        from gh_toolkit.tui import GhToolkitApp
    except ImportError as err:
        console.print("[red]TUI requires extra dependencies.[/red]")
        console.print("")
        console.print("Install with: [cyan]pip install gh-toolkit[tui][/cyan]")
        console.print("         or: [cyan]uv pip install gh-toolkit[tui][/cyan]")
        raise typer.Exit(1) from err

    # The tui package is excluded from strict type checking (textual is an
    # optional extra), so its types are unknown here
    tui_app: Any = GhToolkitApp()
    tui_app.run()


# Repo commands
repo_app.command("list")(list_repos)
repo_app.command("extract")(extract_repos)
repo_app.command("tag")(tag_repos)
repo_app.command("describe")(describe_repos)
repo_app.command("readme")(readme_repos)
repo_app.command("license")(license_repos)
repo_app.command("badges")(generate_badges)
repo_app.command("health")(health_check)
repo_app.command("clone")(clone_repos)

# Invite commands
invite_app.command("accept")(accept_invitations)
invite_app.command("leave")(leave_repositories)


# Transfer commands
transfer_app.command("initiate")(initiate_transfer)
transfer_app.command("list")(list_transfers)
transfer_app.command("accept")(accept_transfers)

# Site commands
site_app.command("generate")(generate_site)

# Page commands
page_app.command("generate")(generate_page)

# Org commands
org_app.command("readme")(org_readme)

# Portfolio commands
portfolio_app.command("generate")(portfolio_generate)
portfolio_app.command("audit")(portfolio_audit)


if __name__ == "__main__":
    app()
