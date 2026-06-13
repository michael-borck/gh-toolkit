"""Invitation management commands."""

import os
from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient

console = Console()


def accept_invitations(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be accepted without making changes"
    ),
) -> None:
    """Accept GitHub repository and organization invitations."""

    try:
        # Use provided token or fallback to environment
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required for invitation management[/red]"
            )
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            console.print("Required scopes: repo, read:org, write:org")
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Get authenticated user info
        try:
            user_info = client.get_user_info()
            username = user_info["login"]
            console.print(f"[blue]Processing invitations for user: {username}[/blue]")
        except GitHubAPIError as e:
            console.print(f"[red]Error getting user info: {e.message}[/red]")
            raise typer.Exit(1) from e

        console.print()

        # Process repository invitations
        console.print("[bold]📄 Repository Invitations[/bold]")
        console.print("-" * 40)

        try:
            repo_invitations = client.get_repository_invitations()

            if not repo_invitations:
                console.print("[green]✓ No pending repository invitations[/green]")
            else:
                console.print(
                    f"Found {len(repo_invitations)} pending repository invitation(s)"
                )

                if dry_run:
                    _display_repo_invitations_table(repo_invitations)
                    console.print("[yellow]Dry run - no changes made[/yellow]")
                else:
                    success_count = 0
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                        transient=True,
                    ) as progress:
                        task = progress.add_task(
                            "Processing invitations...", total=len(repo_invitations)
                        )

                        for invite in repo_invitations:
                            invite_id = invite.get("id")
                            repo_full_name = invite.get("repository", {}).get(
                                "full_name", "N/A"
                            )

                            progress.update(
                                task, description=f"Accepting {repo_full_name}..."
                            )

                            if not invite_id:
                                console.print(
                                    f"[red]✗ Missing invitation id: {repo_full_name}[/red]"
                                )
                                progress.advance(task)
                                continue

                            accepted = client.accept_repository_invitation(invite_id)
                            if accepted:
                                console.print(
                                    f"[green]✓ Accepted repository invitation: {repo_full_name}[/green]"
                                )
                                success_count += 1
                            else:
                                console.print(
                                    f"[red]✗ Failed to accept repository invitation: {repo_full_name}"
                                )

                            progress.advance(task)

                    console.print(
                        f"\n[bold]Repository Summary: {success_count}/{len(repo_invitations)} accepted[/bold]"
                    )

        except GitHubAPIError as e:
            console.print(
                f"[red]Error fetching repository invitations: {e.message}[/red]"
            )
            console.print("Ensure your token has 'repo' scope")

        console.print()

        # Process organization invitations
        console.print("[bold]🏢 Organization Invitations[/bold]")
        console.print("-" * 40)

        try:
            org_invitations = client.get_organization_invitations()

            if not org_invitations:
                console.print("[green]✓ No pending organization invitations[/green]")
            else:
                console.print(
                    f"Found {len(org_invitations)} pending organization invitation(s)"
                )

                if dry_run:
                    _display_org_invitations_table(org_invitations)
                    console.print("[yellow]Dry run - no changes made[/yellow]")
                else:
                    success_count = 0
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                        transient=True,
                    ) as progress:
                        task = progress.add_task(
                            "Processing invitations...", total=len(org_invitations)
                        )

                        for invite in org_invitations:
                            invite_id = invite.get("id")
                            org_login = invite.get("organization", {}).get(
                                "login", "N/A"
                            )

                            progress.update(
                                task, description=f"Accepting {org_login}..."
                            )

                            if not invite_id:
                                console.print(
                                    f"[red]✗ Missing invitation id for org: {org_login}[/red]"
                                )
                                progress.advance(task)
                                continue

                            if client.accept_organization_invitation(invite_id):
                                console.print(
                                    f"[green]✓ Accepted organization invitation: {org_login}[/green]"
                                )
                                success_count += 1
                            else:
                                console.print(
                                    f"[red]✗ Failed to accept organization invitation: {org_login}[/red]"
                                )

                            progress.advance(task)

                    console.print(
                        f"\n[bold]Organization Summary: {success_count}/{len(org_invitations)} accepted[/bold]"
                    )

        except GitHubAPIError as e:
            console.print(
                f"[red]Error fetching organization invitations: {e.message}[/red]"
            )
            console.print("Ensure your token has 'read:org' and 'write:org' scopes")

        console.print("\n[bold green]✓ Invitation processing complete![/bold green]")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def leave_repositories(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what repositories would be left without making changes",
    ),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Leave GitHub repositories you're a collaborator on (not owned by you)."""

    try:
        # Use provided token or fallback to environment
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required for repository management[/red]"
            )
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            console.print("Required scope: repo")
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Get authenticated user info
        try:
            user_info = client.get_user_info()
            username = user_info["login"]
            console.print(
                f"[blue]Finding repositories to leave for user: {username}[/blue]"
            )
        except GitHubAPIError as e:
            console.print(f"[red]Error getting user info: {e.message}[/red]")
            raise typer.Exit(1) from e

        # Get all repositories where user is a collaborator
        console.print("[blue]Fetching repositories...[/blue]")
        try:
            all_repos = client.get_user_repos(
                visibility="all", affiliation="collaborator,organization_member"
            )
        except GitHubAPIError as e:
            console.print(f"[red]Error fetching repositories: {e.message}[/red]")
            raise typer.Exit(1) from e

        # Filter to repositories not owned by the user
        repos_to_leave = [
            repo for repo in all_repos if repo["owner"]["login"] != username
        ]

        if not repos_to_leave:
            console.print(
                "[green]✓ No repositories to leave (you only have access to your own repos)[/green]"
            )
            return

        console.print(
            f"\n[yellow]Found {len(repos_to_leave)} repositories to leave:[/yellow]"
        )

        # Display repositories in a table
        table = Table(title="Repositories to Leave")
        table.add_column("Repository", style="cyan")
        table.add_column("Owner", style="green")
        table.add_column("Description", style="white", max_width=40)
        table.add_column("Private", justify="center", style="red")

        for repo in repos_to_leave:
            description = repo.get("description", "") or ""
            if len(description) > 37:
                description = description[:34] + "..."

            private_status = "🔒" if repo.get("private", False) else "🌐"

            table.add_row(
                repo["name"], repo["owner"]["login"], description, private_status
            )

        console.print(table)

        if dry_run:
            console.print(
                f"\n[yellow]Dry run - would leave {len(repos_to_leave)} repositories[/yellow]"
            )
            return

        # Confirm action
        if not confirm:
            console.print(
                f"\n[bold red]Warning: This will remove you as a collaborator from {len(repos_to_leave)} repositories![/bold red]"
            )
            response = typer.confirm("Are you sure you want to continue?")
            if not response:
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        # Leave repositories
        console.print(f"\n[blue]Leaving {len(repos_to_leave)} repositories...[/blue]")
        success_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                "Leaving repositories...", total=len(repos_to_leave)
            )

            for repo in repos_to_leave:
                repo_name = repo["full_name"]
                owner, name = repo_name.split("/", 1)

                progress.update(task, description=f"Leaving {repo_name}...")

                if client.leave_repository(owner, name, username):
                    console.print(f"[green]✓ Left repository: {repo_name}[/green]")
                    success_count += 1
                else:
                    console.print(
                        f"[red]✗ Failed to leave repository: {repo_name}[/red]"
                    )

                progress.advance(task)

        console.print(
            f"\n[bold]Summary: Successfully left {success_count}/{len(repos_to_leave)} repositories[/bold]"
        )

        if success_count == len(repos_to_leave):
            console.print(
                "[bold green]✓ All repositories left successfully![/bold green]"
            )
        elif success_count > 0:
            console.print(
                "[yellow]⚠ Some repositories could not be left (may require different permissions)[/yellow]"
            )
        else:
            console.print("[red]✗ No repositories were left successfully[/red]")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def _display_repo_invitations_table(invitations: list[dict[str, Any]]) -> None:
    """Display repository invitations in a table."""
    table = Table(title="Repository Invitations")
    table.add_column("Repository", style="cyan")
    table.add_column("Inviter", style="green")
    table.add_column("Description", style="white", max_width=40)
    table.add_column("Created", style="magenta")

    for invite in invitations:
        repo = invite.get("repository", {})
        inviter = invite.get("inviter", {})

        repo_name = repo.get("full_name", "N/A")
        inviter_name = inviter.get("login", "N/A")
        description = repo.get("description", "") or ""
        if len(description) > 37:
            description = description[:34] + "..."

        created_at = invite.get("created_at", "")
        if created_at:
            created_at = created_at.split("T")[0]  # Just the date

        table.add_row(repo_name, inviter_name, description, created_at)

    console.print(table)


def _display_org_invitations_table(invitations: list[dict[str, Any]]) -> None:
    """Display organization invitations in a table."""
    table = Table(title="Organization Invitations")
    table.add_column("Organization", style="cyan")
    table.add_column("Role", style="green")
    table.add_column("Inviter", style="yellow")
    table.add_column("Created", style="magenta")

    for invite in invitations:
        org = invite.get("organization", {})
        inviter = invite.get("inviter", {})

        org_name = org.get("login", "N/A")
        role = invite.get("role", "member")
        inviter_name = inviter.get("login", "N/A")

        created_at = invite.get("created_at", "")
        if created_at:
            created_at = created_at.split("T")[0]  # Just the date

        table.add_row(org_name, role, inviter_name, created_at)

    console.print(table)
