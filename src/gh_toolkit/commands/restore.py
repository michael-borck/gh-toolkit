"""Restore repository descriptions and topics from an audit backup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit.core.audit import write_json_atomic
from gh_toolkit.core.config import resolve_token
from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient

console = Console()

RESTORE_FORMAT = "gh-toolkit-restore"
RESTORE_VERSION = 1


def restore_repos(
    backup: str = typer.Argument(..., help="Backup JSON from repo audit --backup"),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    only: Annotated[
        list[str] | None,
        typer.Option(
            "--only",
            help="Restore only descriptions or topics (repeatable)",
        ),
    ] = None,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Temporarily unarchive archived repos, restore them, then rearchive",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
    output: str | None = typer.Option(
        None, "--output", "-O", help="Write the restore report as JSON"
    ),
) -> None:
    """Restore descriptions and topics from a gh-toolkit backup.

    The backup is created by ``gh-toolkit repo audit --backup FILE``. Restore
    only writes fields that differ from the current repository state.

    Examples:
        gh-toolkit repo restore backup.json --dry-run
        gh-toolkit repo restore backup.json --yes
        gh-toolkit repo restore backup.json --only topics
    """
    kinds = set(only or ["descriptions", "topics"])
    unknown = kinds - {"descriptions", "topics"}
    if unknown:
        console.print(
            f"[red]Error: unknown --only values: {', '.join(sorted(unknown))}[/red]"
        )
        raise typer.Exit(1)

    try:
        payload = json.loads(Path(backup).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        console.print(f"[red]Could not read backup {backup}: {e}[/red]")
        raise typer.Exit(1) from e

    if payload.get("format") != "gh-toolkit-backup":
        console.print("[red]Not a gh-toolkit backup file[/red]")
        raise typer.Exit(1)

    raw_repos = payload.get("repos")
    if not isinstance(raw_repos, list) or not raw_repos:
        console.print("[yellow]No repositories in the backup[/yellow]")
        raise typer.Exit(0)

    github_token = resolve_token(token)
    if not github_token:
        console.print("[red]Error: GitHub token required for restore[/red]")
        console.print("Set GITHUB_TOKEN environment variable or use --token option")
        raise typer.Exit(1)

    client = GitHubClient(github_token)
    changes: list[dict[str, Any]] = []
    skipped = 0

    for raw_repo in cast(list[Any], raw_repos):
        if not isinstance(raw_repo, dict):
            continue
        repo = cast(dict[str, Any], raw_repo)
        full_name = repo.get("full_name")
        if not isinstance(full_name, str) or "/" not in full_name:
            continue
        owner, _, name = full_name.partition("/")

        try:
            current = client.get_repo_info(owner, name)
        except GitHubAPIError as e:
            console.print(f"[red]✗ {full_name}: {e.message}[/red]")
            skipped += 1
            continue

        archived = bool(current.get("archived"))
        if archived and not include_archived:
            console.print(f"[dim]Skipped archived repository: {full_name}[/dim]")
            skipped += 1
            continue

        current_description = current.get("description")
        current_topics = list(current.get("topics") or [])
        desired_description = (
            repo.get("description") if "descriptions" in kinds else current_description
        )
        desired_topics = (
            list(repo.get("topics") or []) if "topics" in kinds else current_topics
        )

        description_changed = desired_description != current_description
        topics_changed = desired_topics != current_topics
        if not description_changed and not topics_changed:
            continue

        changes.append(
            {
                "full_name": full_name,
                "owner": owner,
                "repo": name,
                "archived": archived,
                "current_description": current_description,
                "desired_description": desired_description,
                "current_topics": current_topics,
                "desired_topics": desired_topics,
                "description_changed": description_changed,
                "topics_changed": topics_changed,
            }
        )

    if not changes:
        console.print("[green]Nothing to restore.[/green]")
        return

    _display_restore_changes(changes)

    if dry_run:
        console.print("[yellow]Dry run - no repositories changed.[/yellow]")
        return

    if not yes:
        if not typer.confirm(f"\nRestore {len(changes)} repositories?"):
            console.print("[yellow]Aborted; nothing changed.[/yellow]")
            return

    updated = failed = 0
    for change in changes:
        if _restore_one(client, change, include_archived):
            console.print(f"[green]✓[/green] {change['full_name']}")
            updated += 1
        else:
            console.print(f"[red]✗[/red] {change['full_name']}")
            failed += 1

    report = {
        "format": RESTORE_FORMAT,
        "version": RESTORE_VERSION,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "changes": changes,
    }
    if output:
        write_json_atomic(report, output)
        console.print(f"[green]Report written to {output}[/green]")

    console.print(f"\n[bold]Updated:[/bold] {updated}, [red]failed: {failed}[/red]")
    if failed:
        raise typer.Exit(1)


def _display_restore_changes(changes: list[dict[str, Any]]) -> None:
    table = Table(title=f"Restore changes ({len(changes)} repositories)")
    table.add_column("Repository", style="cyan")
    table.add_column("Description", style="white", max_width=45)
    table.add_column("Topics", style="magenta", max_width=45)
    table.add_column("Archived", style="yellow")

    for change in changes:
        description = (
            f"{change['current_description'] or '-'} -> "
            f"{change['desired_description'] or '-'}"
            if change["description_changed"]
            else "-"
        )
        topics = (
            f"{', '.join(change['current_topics']) or '-'} -> "
            f"{', '.join(change['desired_topics']) or '-'}"
            if change["topics_changed"]
            else "-"
        )
        table.add_row(
            change["full_name"],
            description[:42] + "..." if len(description) > 45 else description,
            topics[:42] + "..." if len(topics) > 45 else topics,
            "yes" if change["archived"] else "no",
        )
    console.print(table)


def _restore_one(
    client: GitHubClient,
    change: dict[str, Any],
    include_archived: bool,
) -> bool:
    owner = change["owner"]
    repo = change["repo"]
    full_name = change["full_name"]
    archived = bool(change["archived"])

    if archived:
        if not include_archived:
            console.print(f"[dim]Skipped archived repository: {full_name}[/dim]")
            return False
        if not client.set_repo_archived(owner, repo, False):
            console.print(f"[red]✗ {full_name}: could not unarchive[/red]")
            return False

    try:
        if change["description_changed"] and not client.update_repo_description(
            owner, repo, change["desired_description"]
        ):
            return False
        if change["topics_changed"] and not client.set_repo_topics(
            owner, repo, change["desired_topics"]
        ):
            return False
        return True
    finally:
        if archived and not client.set_repo_archived(owner, repo, True):
            console.print(f"[red]⚠ Could not rearchive {full_name}[/red]")
