"""Topic tagging commands for GitHub repositories."""

import json
import os
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL
from gh_toolkit.core.topic_tagger import TopicTagger

console = Console()


def tag_repos(
    repos_input: str = typer.Argument(
        help="Repository (owner/repo), file with repo list, or 'username/*' for all user repos"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    anthropic_key: str | None = typer.Option(
        None,
        "--anthropic-key",
        help="Anthropic API key for LLM tagging (or set ANTHROPIC_API_KEY env var)",
    ),
    model: str = typer.Option(
        DEFAULT_LLM_MODEL,
        "--model",
        "-m",
        help="Anthropic model to use (e.g., claude-sonnet-4-6)",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Preferred tags to consider (e.g., 'edtech: Educational tools, curtin: Curtin materials')",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what topics would be added without making changes",
    ),
    force: bool = typer.Option(
        False, "--force", help="Update topics even if repository already has topics"
    ),
    add_description: bool = typer.Option(
        False,
        "--add-description",
        help="Generate and add description if missing before tagging",
    ),
    rate_limit: float = typer.Option(
        0.5,
        "--rate-limit",
        "-r",
        help="Seconds between API requests (default: 0.5)",
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Save results to JSON file"
    ),
) -> None:
    """Add relevant topic tags to GitHub repositories using LLM analysis.

    Automatically generates and applies topic tags to repositories based on their
    content, description, README, and programming languages used.

    Examples:
        gh-toolkit repo tag user/repo --dry-run
        gh-toolkit repo tag repos.txt --force
        gh-toolkit repo tag michael-borck/* --anthropic-key=sk-...
    """
    try:
        # Get tokens
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]✗ GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]"
            )
            console.print("[dim]Required scopes: repo[/dim]")
            raise typer.Exit(1)

        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            console.print(
                "[yellow]⚠ No Anthropic API key provided. Will use rule-based topic generation.[/yellow]"
            )
            console.print(
                "[dim]For better results, set ANTHROPIC_API_KEY env var or use --anthropic-key[/dim]"
            )

        # Initialize clients
        client = GitHubClient(github_token)
        tagger = TopicTagger(client, anthropic_api_key, rate_limit, model, tags)

        # Parse repository input
        repo_list = _parse_repos_input(repos_input, client)

        if not repo_list:
            console.print("[red]✗ No repositories found to process[/red]")
            raise typer.Exit(1)

        # Show what we're about to do
        console.print(f"\n[blue]Found {len(repo_list)} repositories to process[/blue]")
        console.print(f"[blue]Using model: {model}[/blue]")
        if tags:
            console.print(
                f"[blue]Preferred tags: {tags[:80]}...[/blue]"
                if len(tags) > 80
                else f"[blue]Preferred tags: {tags}[/blue]"
            )
        if dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        if force:
            console.print(
                "[yellow]FORCE MODE - Will update repositories that already have topics[/yellow]"
            )
        if add_description:
            console.print(
                "[blue]ADD DESCRIPTION - Will generate descriptions for repos without one[/blue]"
            )

        # Process repositories
        results = tagger.process_multiple_repositories(
            repo_list, dry_run, force, add_description
        )

        # Show summary
        _show_summary(results, dry_run)

        # Save results if requested
        if output:
            _save_results(results, output, dry_run, force)

    except KeyboardInterrupt as e:
        console.print("\n[yellow]⚠ Operation cancelled by user[/yellow]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _parse_repos_input(repos_input: str, client: GitHubClient) -> list[tuple[str, str]]:
    """Parse repository input and return list of (owner, repo) tuples."""
    repos: list[tuple[str, str]] = []

    # Check if it's a file
    if Path(repos_input).exists():
        console.print(f"[blue]📂 Loading repositories from file: {repos_input}[/blue]")
        with open(repos_input, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        owner, repo = _parse_repo_string(line)
                        repos.append((owner, repo))
                    except ValueError as e:
                        console.print(f"[yellow]⚠ Line {line_num}: {e}[/yellow]")
        return repos

    # Check if it's a wildcard pattern (user/*)
    if repos_input.endswith("/*"):
        owner = repos_input[:-2]
        console.print(
            f"[blue]🔍 Fetching all repositories for user/org: {owner}[/blue]"
        )
        try:
            # Check if owner is the authenticated user - if so, include private repos
            authenticated_user = client.get_authenticated_user()
            if authenticated_user and authenticated_user.lower() == owner.lower():
                console.print("[dim]Including private repositories[/dim]")
                user_repos = client.get_user_repos(
                    None, visibility="all", affiliation="owner"
                )
            else:
                user_repos = client.get_user_repos(owner)
            repos = [(owner, repo["name"]) for repo in user_repos]
            console.print(
                f"[green]✓ Found {len(repos)} repositories for {owner}[/green]"
            )
            return repos
        except Exception as e:
            console.print(f"[red]✗ Error fetching repositories for {owner}: {e}[/red]")
            return []

    # Single repository
    try:
        owner, repo = _parse_repo_string(repos_input)
        return [(owner, repo)]
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        return []


def _parse_repo_string(repo_string: str) -> tuple[str, str]:
    """Parse 'owner/repo' format into owner and repo name."""
    parts = repo_string.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format: {repo_string}. Expected 'owner/repo'")
    return parts[0], parts[1]


def _show_summary(results: list[dict[str, Any]], dry_run: bool) -> None:
    """Display summary of tagging results."""
    console.print("\n[bold]📊 SUMMARY[/bold]")

    # Count results by status
    status_counts: dict[str, int] = {}
    for result in results:
        status: str = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    # Create summary table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Description", style="dim")

    # Add rows
    if not dry_run:
        table.add_row(
            "✓ Success",
            str(status_counts.get("success", 0)),
            "Topics successfully updated",
        )
        table.add_row(
            "⏭ Skipped",
            str(status_counts.get("skipped", 0)),
            "Already has topics (use --force to update)",
        )
    else:
        dry_run_count = status_counts.get("dry_run", 0)
        table.add_row(
            "🔍 Would Update", str(dry_run_count), "Topics would be added/updated"
        )

    table.add_row("✗ Errors", str(status_counts.get("error", 0)), "Failed to process")
    table.add_row("📋 Total", str(len(results)), "Repositories processed")

    console.print(table)

    # Show error details if any
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        console.print("\n[red]❌ Error Details:[/red]")
        for error in errors:
            console.print(
                f"  [red]•[/red] {error['repo']}: {error.get('message', 'Unknown error')}"
            )


def _save_results(
    results: list[dict[str, Any]], output_path: str, dry_run: bool, force: bool
) -> None:
    """Save results to JSON file."""
    from datetime import datetime

    output_data = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "force_update": force,
        "total_processed": len(results),
        "summary": {
            "success": len([r for r in results if r["status"] == "success"]),
            "skipped": len([r for r in results if r["status"] == "skipped"]),
            "errors": len([r for r in results if r["status"] == "error"]),
            "dry_run": len([r for r in results if r["status"] == "dry_run"]),
        },
        "results": results,
    }

    output_file = Path(output_path)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    console.print(f"\n[green]💾 Results saved to: {output_file.absolute()}[/green]")
