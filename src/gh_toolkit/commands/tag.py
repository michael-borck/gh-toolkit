"""Topic tagging commands for GitHub repositories."""

import json
import os
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit.core.audit import build_backup, write_json_atomic
from gh_toolkit.core.config import resolve_token
from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL
from gh_toolkit.core.tag_classifier import TagClassifier
from gh_toolkit.core.tag_vocabulary import load_vocabulary
from gh_toolkit.core.topic_tagger import TopicTagger

console = Console()


def tag_repos(
    repos_input: str | None = typer.Argument(
        None,
        help="Repository (owner/repo), file with repo list, or 'username/*' for all user repos",
    ),
    vocabulary: str | None = typer.Option(
        None,
        "--vocabulary",
        help="YAML standard tag vocabulary for controlled tagging",
    ),
    from_audit: str | None = typer.Option(
        None,
        "--from-audit",
        help="Tag repositories selected by a repo audit JSON report",
    ),
    apply_proposals: str | None = typer.Option(
        None,
        "--apply-proposals",
        help="Apply exact changes from a saved tag-proposals JSON file",
    ),
    only_missing: bool = typer.Option(
        False,
        "--only-missing",
        help="With --from-audit: only repositories with no topics",
    ),
    free_tags: int = typer.Option(
        2,
        "--free-tags",
        help="Maximum free tags per repository",
    ),
    min_prob: float = typer.Option(
        0.8,
        "--min-prob",
        help="Accept a standard tag at or above this probability",
    ),
    review_prob: float = typer.Option(
        0.3,
        "--review-prob",
        help="Show standard tags between this and --min-prob",
    ),
    backup: str | None = typer.Option(
        None,
        "--backup",
        help="Write current topics before applying changes",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Temporarily unarchive archived repos, tag them, then rearchive",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt",
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
    max_tags: int = typer.Option(
        8,
        "--max-tags",
        help="Maximum topics per repository (default: 8; GitHub hard max is 20)",
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
        if max_tags < 1:
            console.print("[red]✗ --max-tags must be at least 1[/red]")
            raise typer.Exit(1)

        # Get tokens
        github_token = resolve_token(token)
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

        if free_tags < 0:
            console.print("[red]✗ --free-tags must be zero or greater[/red]")
            raise typer.Exit(1)
        if not (0 <= review_prob <= min_prob <= 1):
            console.print(
                "[red]✗ thresholds must satisfy 0 <= review-prob <= min-prob <= 1[/red]"
            )
            raise typer.Exit(1)

        if vocabulary or from_audit or apply_proposals:
            _tag_with_vocabulary(
                token=github_token,
                repos_input=repos_input,
                anthropic_api_key=anthropic_api_key,
                model=model,
                vocabulary_path=vocabulary,
                from_audit=from_audit,
                apply_proposals=apply_proposals,
                only_missing=only_missing,
                free_tags=free_tags,
                min_prob=min_prob,
                review_prob=review_prob,
                backup_path=backup,
                include_archived=include_archived,
                dry_run=dry_run,
                assume_yes=yes,
                output=output,
            )
            return

        if not repos_input:
            console.print(
                "[red]✗ Provide a repository input or use --vocabulary, "
                "--from-audit, or --apply-proposals[/red]"
            )
            raise typer.Exit(1)

        # Initialize clients
        client = GitHubClient(github_token)
        tagger = TopicTagger(
            client, anthropic_api_key, rate_limit, model, tags, max_topics=max_tags
        )

        # Parse repository input
        repo_list = _parse_repos_input(repos_input, client)

        if not repo_list:
            console.print("[red]✗ No repositories found to process[/red]")
            raise typer.Exit(1)

        # Show what we're about to do
        console.print(f"\n[blue]Found {len(repo_list)} repositories to process[/blue]")
        console.print(f"[blue]Using model: {model}[/blue]")
        console.print(f"[blue]Max topics per repo: {max_tags}[/blue]")
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

        if any(result.get("status") == "error" for result in results):
            raise typer.Exit(1)

    except KeyboardInterrupt as e:
        console.print("\n[yellow]⚠ Operation cancelled by user[/yellow]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _tag_with_vocabulary(
    token: str,
    repos_input: str | None,
    anthropic_api_key: str | None,
    model: str,
    vocabulary_path: str | None,
    from_audit: str | None,
    apply_proposals: str | None,
    only_missing: bool,
    free_tags: int,
    min_prob: float,
    review_prob: float,
    backup_path: str | None,
    include_archived: bool,
    dry_run: bool,
    assume_yes: bool,
    output: str | None,
) -> None:
    """Generate or apply controlled tag proposals."""
    if apply_proposals:
        _apply_tag_proposals(
            token=token,
            proposals_path=apply_proposals,
            backup_path=backup_path,
            include_archived=include_archived,
            dry_run=dry_run,
            assume_yes=assume_yes,
            output=output,
        )
        return

    if vocabulary_path is None:
        console.print("[red]✗ --vocabulary is required to generate tag proposals[/red]")
        raise typer.Exit(1)

    try:
        vocabulary = load_vocabulary(vocabulary_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1) from e

    client = GitHubClient(token)
    classifier = TagClassifier(
        vocabulary=vocabulary,
        anthropic_api_key=anthropic_api_key,
        model=model,
        free_tag_limit=free_tags,
        min_probability=min_prob,
        review_probability=review_prob,
    )

    if from_audit:
        targets = _targets_from_audit(from_audit, only_missing)
    elif repos_input:
        repo_list = _parse_repos_input(repos_input, client)
        targets = [{"full_name": f"{owner}/{repo}"} for owner, repo in repo_list]
    else:
        console.print("[red]✗ provide --from-audit or a repository input[/red]")
        raise typer.Exit(1)

    if not targets:
        console.print("[green]No repositories selected.[/green]")
        return

    console.print(
        f"[blue]Tagging {len(targets)} repositories with "
        f"{len(vocabulary.tags)} standard tags[/blue]"
    )

    changes: list[dict[str, Any]] = []
    current_repos: list[dict[str, Any]] = []

    for target in targets:
        full_name = target.get("full_name")
        if not isinstance(full_name, str) or "/" not in full_name:
            continue
        owner, _, name = full_name.partition("/")

        try:
            repo_data = client.get_repo_info(owner, name)
        except GitHubAPIError as e:
            console.print(f"[red]✗ {full_name}: {e.message}[/red]")
            continue

        archived = bool(repo_data.get("archived"))
        if archived and not include_archived:
            console.print(f"[dim]Skipped archived repository: {full_name}[/dim]")
            continue

        current_repos.append(repo_data)
        readme = client.get_repo_readme(owner, name)
        existing = list(repo_data.get("topics") or [])
        proposal = classifier.classify(repo_data, readme, existing)

        if not proposal.selected:
            console.print(
                f"[yellow]No standard tag passed for {full_name}; "
                "free tags only[/yellow]"
            )

        changes.append(
            {
                "full_name": full_name,
                "owner": owner,
                "repo": name,
                "current_topics": existing,
                "standard_scores": proposal.standard,
                "selected_standard": proposal.selected,
                "review_standard": proposal.review,
                "free_tags": proposal.free,
                "final_topics": proposal.final,
                "reason": proposal.reason,
                "source": proposal.source,
                "archived": archived,
                "needs_review": not proposal.selected,
            }
        )

    if not changes:
        console.print("[yellow]No tag proposals generated.[/yellow]")
        return

    _display_tag_changes(changes)

    if backup_path:
        write_json_atomic(
            build_backup(current_repos, {"source": "tag", "audit": from_audit}),
            backup_path,
        )
        console.print(f"[green]Backup written to {backup_path}[/green]")

    if output:
        write_json_atomic(
            {
                "format": "gh-toolkit-tag-proposals",
                "version": 1,
                "dry_run": dry_run,
                "vocabulary": vocabulary.name,
                "changes": changes,
            },
            output,
        )
        console.print(f"[green]Proposed changes written to {output}[/green]")

    if dry_run:
        console.print("[yellow]Dry run - no topics changed.[/yellow]")
        return

    if not assume_yes:
        if not typer.confirm(f"\nUpdate topics on {len(changes)} repositories?"):
            console.print("[yellow]Aborted; no topics changed.[/yellow]")
            return

    updated = failed = 0
    for change in changes:
        if _apply_topic_change(client, change, include_archived):
            console.print(f"[green]✓[/green] {change['full_name']}")
            updated += 1
        else:
            console.print(f"[red]✗[/red] {change['full_name']}")
            failed += 1

    if output:
        write_json_atomic(
            {
                "format": "gh-toolkit-tag-proposals",
                "version": 1,
                "dry_run": False,
                "vocabulary": vocabulary.name,
                "updated": updated,
                "failed": failed,
                "changes": changes,
            },
            output,
        )
        console.print(f"[green]Results written to {output}[/green]")

    console.print(f"\n[bold]Updated:[/bold] {updated}, [red]failed: {failed}[/red]")
    if failed:
        raise typer.Exit(1)


def _targets_from_audit(audit_path: str, only_missing: bool) -> list[dict[str, Any]]:
    audit_file = Path(audit_path)
    try:
        report = json.loads(audit_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        console.print(f"[red]Could not read audit report {audit_file}: {e}[/red]")
        raise typer.Exit(1) from e

    if report.get("format") != "gh-toolkit-audit":
        console.print("[red]Not a gh-toolkit audit report[/red]")
        raise typer.Exit(1)

    targets: list[dict[str, Any]] = []
    for repo in report.get("repos", []):
        full_name = repo.get("full_name")
        if not isinstance(full_name, str):
            continue
        if only_missing:
            if repo.get("topics"):
                continue
        elif not repo.get("topic_issues"):
            continue
        targets.append({"full_name": full_name})

    return targets


def _apply_tag_proposals(
    token: str,
    proposals_path: str,
    backup_path: str | None,
    include_archived: bool,
    dry_run: bool,
    assume_yes: bool,
    output: str | None,
) -> None:
    proposals_file = Path(proposals_path)
    try:
        data = json.loads(proposals_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        console.print(f"[red]Could not read proposals {proposals_file}: {e}[/red]")
        raise typer.Exit(1) from e

    if data.get("format") != "gh-toolkit-tag-proposals":
        console.print("[red]Not a gh-toolkit tag-proposals file[/red]")
        raise typer.Exit(1)

    raw_changes = data.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        console.print("[green]No changes in the proposals file.[/green]")
        return

    changes = [
        cast(dict[str, Any], change)
        for change in cast(list[Any], raw_changes)
        if isinstance(change, dict)
    ]
    if not changes:
        console.print("[green]No usable changes in the proposals file.[/green]")
        return

    client = GitHubClient(token)
    current_repos: list[dict[str, Any]] = []
    usable: list[dict[str, Any]] = []

    for change in changes:
        owner = change.get("owner")
        repo = change.get("repo")
        if not isinstance(owner, str) or not isinstance(repo, str):
            continue
        try:
            repo_data = client.get_repo_info(owner, repo)
        except GitHubAPIError as e:
            console.print(f"[red]✗ {change.get('full_name')}: {e.message}[/red]")
            continue

        archived = bool(repo_data.get("archived"))
        change["archived"] = archived
        if archived and not include_archived:
            console.print(
                f"[dim]Skipped archived repository: {change.get('full_name')}[/dim]"
            )
            continue
        current_repos.append(repo_data)
        usable.append(change)

    if not usable:
        console.print("[red]No repositories could be read; nothing applied.[/red]")
        raise typer.Exit(1)

    _display_tag_changes(usable)

    if backup_path:
        write_json_atomic(
            build_backup(
                current_repos, {"source": "tag", "proposals": str(proposals_file)}
            ),
            backup_path,
        )
        console.print(f"[green]Backup written to {backup_path}[/green]")

    if dry_run:
        console.print("[yellow]Dry run - no topics changed.[/yellow]")
        return

    if not assume_yes:
        if not typer.confirm(f"\nUpdate topics on {len(usable)} repositories?"):
            console.print("[yellow]Aborted; no topics changed.[/yellow]")
            return

    updated = failed = 0
    for change in usable:
        if _apply_topic_change(client, change, include_archived):
            console.print(f"[green]✓[/green] {change['full_name']}")
            updated += 1
        else:
            console.print(f"[red]✗[/red] {change['full_name']}")
            failed += 1

    if output:
        write_json_atomic(
            {
                "format": "gh-toolkit-tag-proposals",
                "version": 1,
                "dry_run": False,
                "updated": updated,
                "failed": failed,
                "changes": usable,
            },
            output,
        )
        console.print(f"[green]Results written to {output}[/green]")

    console.print(f"\n[bold]Updated:[/bold] {updated}, [red]failed: {failed}[/red]")
    if failed:
        raise typer.Exit(1)


def _apply_topic_change(
    client: GitHubClient,
    change: dict[str, Any],
    include_archived: bool,
) -> bool:
    owner = change["owner"]
    repo = change["repo"]
    full_name = change["full_name"]
    topics = change.get("final_topics")
    if not isinstance(topics, list) or not topics:
        console.print(f"[red]✗ {full_name}: no final topics[/red]")
        return False

    archived = bool(change.get("archived"))
    if archived:
        if not include_archived:
            console.print(f"[dim]Skipped archived repository: {full_name}[/dim]")
            return False
        if not client.set_repo_archived(owner, repo, False):
            console.print(f"[red]✗ {full_name}: could not unarchive[/red]")
            return False

    try:
        try:
            return client.set_repo_topics(
                owner, repo, [str(topic) for topic in cast(list[object], topics)]
            )
        except GitHubAPIError as e:
            console.print(f"[red]✗ {full_name}: {e.message}[/red]")
            return False
    finally:
        if archived and not client.set_repo_archived(owner, repo, True):
            console.print(f"[red]⚠ Could not rearchive {full_name}[/red]")


def _display_tag_changes(changes: list[dict[str, Any]]) -> None:
    table = Table(title=f"Proposed tags ({len(changes)} repositories)")
    table.add_column("Repository", style="cyan")
    table.add_column("Standard", style="green", max_width=40)
    table.add_column("Free", style="yellow", max_width=30)
    table.add_column("Review", style="dim", max_width=30)

    for change in changes:
        standard = ", ".join(change.get("selected_standard") or [])
        free = ", ".join(change.get("free_tags") or [])
        review_scores = cast(dict[str, float], change.get("review_standard") or {})
        review = ", ".join(
            f"{name} ({score:.1f})" for name, score in review_scores.items()
        )
        table.add_row(
            change.get("full_name", ""),
            standard or "-",
            free or "-",
            review or "-",
        )

    console.print(table)


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
                user_repos = client.get_repos_for_owner(owner)
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
