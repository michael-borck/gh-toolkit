"""Repository transfer management commands."""

import csv
import os
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.types import GitHubTransferResponse

console = Console()


def initiate_transfer(
    repo_spec: str | None = typer.Argument(
        None, help="Repository in format 'owner/repo' or path to CSV file"
    ),
    destination: str | None = typer.Argument(
        None, help="Destination organization (only used with single repo)"
    ),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="CSV file with format 'owner/repo,destination_org'"
    ),
    new_name: str | None = typer.Option(
        None, "--new-name", help="New repository name (optional)"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be transferred without making changes"
    ),
) -> None:
    """Initiate repository transfers to organizations.

    Examples:
        gh-toolkit transfer initiate owner/repo dest-org
        gh-toolkit transfer initiate --file repos.csv
        gh-toolkit transfer initiate owner/repo dest-org --new-name new-repo-name
    """

    try:
        # Use provided token or fallback to environment
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required for repository transfers[/red]"
            )
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            console.print("Required scopes: repo, write:org")
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Get authenticated user info
        try:
            user_info = client.get_user_info()
            username = user_info["login"]
            console.print(f"[blue]Initiating transfers for user: {username}[/blue]")
        except GitHubAPIError as e:
            console.print(f"[red]Error getting user info: {e.message}[/red]")
            raise typer.Exit(1) from e

        console.print()

        # Determine transfer list
        transfers: list[tuple[str, str, str | None]] = []

        if file:
            # Read from CSV file
            try:
                with open(file) as f:
                    reader = csv.reader(f)
                    for line_num, row in enumerate(reader, 1):
                        if not row or row[0].startswith("#"):
                            continue
                        if len(row) < 2:
                            console.print(
                                f"[yellow]Warning: Skipping line {line_num} - invalid format[/yellow]"
                            )
                            continue

                        repo_full_name = row[0].strip()
                        dest_org = row[1].strip()
                        repo_new_name = row[2].strip() if len(row) > 2 else None

                        if not dest_org:
                            console.print(
                                f"[yellow]Warning: Skipping line {line_num} - no destination organization[/yellow]"
                            )
                            continue

                        transfers.append((repo_full_name, dest_org, repo_new_name))

            except FileNotFoundError as e:
                console.print(f"[red]Error: File {file} not found[/red]")
                raise typer.Exit(1) from e
            except Exception as e:
                console.print(f"[red]Error reading file: {e}[/red]")
                raise typer.Exit(1) from e

        elif repo_spec and destination:
            # Single repository transfer
            transfers.append((repo_spec, destination, new_name))

        elif repo_spec and "," in repo_spec:
            # Legacy format: "owner/repo,destination"
            parts = repo_spec.split(",", 1)
            if len(parts) == 2:
                transfers.append((parts[0].strip(), parts[1].strip(), new_name))
            else:
                console.print("[red]Error: Invalid repository specification[/red]")
                raise typer.Exit(1)
        else:
            console.print(
                "[red]Error: Must specify either repo and destination, or use --file option[/red]"
            )
            console.print("Examples:")
            console.print("  gh-toolkit transfer initiate owner/repo dest-org")
            console.print("  gh-toolkit transfer initiate --file repos.csv")
            raise typer.Exit(1)

        if not transfers:
            console.print("[yellow]No transfers to process[/yellow]")
            return

        # Display planned transfers
        table = Table(title="Planned Repository Transfers")
        table.add_column("Repository", style="cyan")
        table.add_column("Destination", style="green")
        table.add_column("New Name", style="yellow")

        for repo_name, dest, new_repo_name in transfers:
            table.add_row(repo_name, dest, new_repo_name or "[dim]unchanged[/dim]")

        console.print(table)

        if dry_run:
            console.print(
                "\n[yellow]Dry run mode - no transfers will be initiated[/yellow]"
            )
            return

        # Confirm before proceeding
        if not Confirm.ask(f"\nProceed with {len(transfers)} transfer(s)?"):
            console.print("[yellow]Transfer cancelled[/yellow]")
            return

        # Process transfers
        successful = 0
        failed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing transfers...", total=len(transfers))

            for repo_name, dest_org, new_repo_name in transfers:
                progress.update(task, description=f"Transferring {repo_name}...")

                try:
                    # Parse owner/repo
                    if "/" not in repo_name:
                        console.print(
                            f"[red]Error: Invalid repository format '{repo_name}' - expected 'owner/repo'[/red]"
                        )
                        failed += 1
                        continue

                    owner, repo = repo_name.split("/", 1)

                    # Initiate transfer
                    result = client.transfer_repository(
                        owner=owner,
                        repo=repo,
                        new_owner=dest_org,
                        new_name=new_repo_name,
                    )
                    # Safe cast after API call validation
                    transfer_result = cast(GitHubTransferResponse, result)

                    console.print(
                        f"[green]✓ Transfer initiated: {repo_name} → {dest_org}[/green]"
                    )
                    if new_repo_name:
                        console.print(f"  New name: {new_repo_name}")
                    console.print(f"  Transfer URL: {transfer_result['html_url']}")
                    successful += 1

                except GitHubAPIError as e:
                    console.print(
                        f"[red]✗ Failed to transfer {repo_name}: {e.message}[/red]"
                    )
                    failed += 1
                except Exception as e:
                    console.print(
                        f"[red]✗ Unexpected error transferring {repo_name}: {e}[/red]"
                    )
                    failed += 1

                progress.advance(task)

        # Summary
        console.print("\n[bold]Transfer Summary:[/bold]")
        console.print(f"✓ Successful: {successful}")
        if failed > 0:
            console.print(f"✗ Failed: {failed}")

        if successful > 0:
            console.print(
                "\n[yellow]Note: Transfers require acceptance by the destination organization owners.[/yellow]"
            )
            console.print("Use 'gh-toolkit transfer list' to check pending transfers.")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def list_transfers(
    org: str | None = typer.Option(
        None, "--org", help="Filter pending repository transfers by organization"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
) -> None:
    """List pending repository transfers."""

    try:
        # Use provided token or fallback to environment
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required for checking transfers[/red]"
            )
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            console.print("Required scopes: repo, read:org")
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Get authenticated user info
        try:
            user_info = client.get_user_info()
            username = user_info["login"]
            console.print(f"[blue]Checking transfers for user: {username}[/blue]")
        except GitHubAPIError as e:
            console.print(f"[red]Error getting user info: {e.message}[/red]")
            raise typer.Exit(1) from e

        console.print()

        if org:
            # Check repository transfers for specific organization
            console.print(
                f"[bold]📋 Pending Repository Transfers from Organization: {org}[/bold]"
            )
            try:
                # Get all repository transfers and filter by current repository owner/organization
                all_invitations = client.get_repository_transfers()
                org_invitations: list[dict[str, Any]] = []

                for invitation in all_invitations:
                    repo_info = invitation.get("repository", {})
                    repo_full_name = repo_info.get("full_name", "")

                    # Filter by current repository owner/organization
                    # Shows transfers FROM the specified organization
                    if "/" in repo_full_name:
                        repo_owner = repo_full_name.split("/")[0]
                        if repo_owner.lower() == org.lower():
                            org_invitations.append(invitation)
                    else:
                        # Include repos without clear owner format
                        org_invitations.append(invitation)

                if not org_invitations:
                    console.print(
                        f"[yellow]No pending repository transfers found for organization '{org}'[/yellow]"
                    )
                    if all_invitations:
                        console.print(
                            f"[dim]Found {len(all_invitations)} transfer(s) for other organizations[/dim]"
                        )
                    return

                table = Table()
                table.add_column("Repository", style="cyan")
                table.add_column("From", style="yellow")
                table.add_column("Permissions", style="dim")
                table.add_column("Created", style="dim")

                for invitation in org_invitations:
                    repo_info = invitation.get("repository", {})
                    inviter_info = invitation.get("inviter", {})

                    table.add_row(
                        repo_info.get("full_name", "Unknown"),
                        inviter_info.get("login", "Unknown"),
                        invitation.get("permissions", "Unknown"),
                        invitation.get("created_at", "Unknown")[:10],  # Just the date
                    )

                console.print(table)
                console.print(
                    f"\n[dim]Found {len(org_invitations)} pending repository transfer(s)[/dim]"
                )
                if org_invitations and len(all_invitations) > len(org_invitations):
                    console.print(
                        f"[dim]Filtered from {len(all_invitations)} total pending transfers[/dim]"
                    )

            except GitHubAPIError as e:
                console.print(
                    f"[red]Error checking repository transfers: {e.message}[/red]"
                )

        else:
            # Check user repository invitations/transfers
            console.print("[bold]📄 Pending Repository Transfers[/bold]")
            try:
                invitations = client.get_repository_transfers()

                if not invitations:
                    console.print(
                        "[green]No pending repository transfers found[/green]"
                    )
                    return

                table = Table()
                table.add_column("Repository", style="cyan")
                table.add_column("From", style="yellow")
                table.add_column("Permissions", style="dim")
                table.add_column("Created", style="dim")

                for invitation in invitations:
                    repo_info = invitation.get("repository", {})
                    inviter_info = invitation.get("inviter", {})

                    table.add_row(
                        repo_info.get("full_name", "Unknown"),
                        inviter_info.get("login", "Unknown"),
                        invitation.get("permissions", "Unknown"),
                        invitation.get("created_at", "Unknown")[:10],  # Just the date
                    )

                console.print(table)
                console.print(
                    f"\n[dim]Found {len(invitations)} pending transfer(s)[/dim]"
                )

            except GitHubAPIError as e:
                console.print(
                    f"[red]Error checking repository transfers: {e.message}[/red]"
                )

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def accept_transfers(
    org: str | None = typer.Option(
        None, "--org", help="Accept transfers for this organization"
    ),
    all_transfers: bool = typer.Option(
        False, "--all", help="Accept all pending transfers"
    ),
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
    """Accept pending repository transfers."""

    try:
        # Use provided token or fallback to environment
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required for accepting transfers[/red]"
            )
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            console.print("Required scopes: repo, write:org")
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Get authenticated user info
        try:
            user_info = client.get_user_info()
            username = user_info["login"]
            console.print(f"[blue]Accepting transfers for user: {username}[/blue]")
        except GitHubAPIError as e:
            console.print(f"[red]Error getting user info: {e.message}[/red]")
            raise typer.Exit(1) from e

        console.print()

        # Get pending transfers
        try:
            invitations = client.get_repository_transfers()

            if not invitations:
                console.print("[green]No pending repository transfers found[/green]")
                return

            # Filter by organization if specified
            if org:
                original_count = len(invitations)
                invitations = [
                    inv
                    for inv in invitations
                    if inv.get("repository", {})
                    .get("full_name", "")
                    .startswith(f"{org}/")
                ]
                console.print(
                    f"[dim]Filtered to {len(invitations)} transfer(s) for organization '{org}' (from {original_count} total)[/dim]"
                )

            if not invitations:
                console.print(
                    f"[yellow]No pending transfers found for organization '{org}'[/yellow]"
                )
                return

            # Display transfers to accept
            table = Table(title="Transfers to Accept")
            table.add_column("ID", style="dim")
            table.add_column("Repository", style="cyan")
            table.add_column("From", style="yellow")
            table.add_column("Permissions", style="dim")

            for invitation in invitations:
                repo_info = invitation.get("repository", {})
                inviter_info = invitation.get("inviter", {})

                table.add_row(
                    str(invitation["id"]),
                    repo_info.get("full_name", "Unknown"),
                    inviter_info.get("login", "Unknown"),
                    invitation.get("permissions", "Unknown"),
                )

            console.print(table)

            if dry_run:
                console.print(
                    f"\n[yellow]Dry run mode - {len(invitations)} transfer(s) would be accepted[/yellow]"
                )
                return

            # Confirm before proceeding
            if not all_transfers:
                if not Confirm.ask(f"\nAccept {len(invitations)} transfer(s)?"):
                    console.print("[yellow]Transfer acceptance cancelled[/yellow]")
                    return

            # Accept transfers
            successful = 0
            failed = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Accepting transfers...", total=len(invitations)
                )

                for invitation in invitations:
                    invitation_id = invitation["id"]
                    repo_name = invitation.get("repository", {}).get(
                        "full_name", "Unknown"
                    )

                    progress.update(
                        task, description=f"Accepting transfer for {repo_name}..."
                    )

                    try:
                        success = client.accept_repository_invitation(invitation_id)

                        if success:
                            console.print(
                                f"[green]✓ Accepted transfer: {repo_name}[/green]"
                            )
                            successful += 1
                        else:
                            console.print(
                                f"[red]✗ Failed to accept transfer: {repo_name}[/red]"
                            )
                            failed += 1

                    except GitHubAPIError as e:
                        console.print(
                            f"[red]✗ Failed to accept {repo_name}: {e.message}[/red]"
                        )
                        failed += 1
                    except Exception as e:
                        console.print(
                            f"[red]✗ Unexpected error accepting {repo_name}: {e}[/red]"
                        )
                        failed += 1

                    progress.advance(task)

            # Summary
            console.print("\n[bold]Acceptance Summary:[/bold]")
            console.print(f"✓ Successful: {successful}")
            if failed > 0:
                console.print(f"✗ Failed: {failed}")

        except GitHubAPIError as e:
            console.print(f"[red]Error getting repository transfers: {e.message}[/red]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e
