"""Repository metadata audit and backup commands."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit.core.audit import (
    RepoAudit,
    audit_repository,
    build_backup,
    build_report,
    write_json_atomic,
)
from gh_toolkit.core.config import resolve_token
from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.tag_vocabulary import load_vocabulary

console = Console()
err_console = Console(stderr=True)


def audit_repos(
    user: bool = typer.Option(
        False,
        "--user",
        "-u",
        help="Audit the authenticated user's repositories",
    ),
    org: Annotated[
        list[str] | None,
        typer.Option("--org", "-o", help="Organization to audit (repeatable)"),
    ] = None,
    include_private: bool = typer.Option(
        False,
        "--include-private",
        help="Include private repositories",
    ),
    vocabulary: str | None = typer.Option(
        None,
        "--vocabulary",
        help="YAML tag vocabulary to check for standard tags",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output the audit report as JSON to stdout",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-O",
        help="Write the JSON audit report to a file",
    ),
    backup: str | None = typer.Option(
        None,
        "--backup",
        "-b",
        help="Write a restore-ready backup of descriptions and topics to a file",
    ),
    only_issues: bool = typer.Option(
        False,
        "--only-issues",
        help="Show only repositories with issues",
    ),
) -> None:
    """Audit descriptions, spelling, and topics, and optionally back them up.

    This command is read-only. It never changes a repository. Use it before
    bulk description or topic edits so you know the size of the job and have a
    restore-ready snapshot of the current values.

    Examples:
        gh-toolkit repo audit --user --include-private --json
        gh-toolkit repo audit --user --backup gh-toolkit-backup.json
        gh-toolkit repo audit --org my-org --output audit.json
    """
    status = err_console if json_output else console

    try:
        if not user and not org:
            console.print("[red]Error: specify --user, --org, or both[/red]")
            raise typer.Exit(1)

        github_token = resolve_token(token)
        if not github_token:
            console.print("[red]Error: GitHub token required for audits[/red]")
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            raise typer.Exit(1)

        vocab = None
        if vocabulary:
            try:
                vocab = load_vocabulary(vocabulary)
            except (FileNotFoundError, ValueError) as e:
                console.print(f"[red]Error loading vocabulary: {e}[/red]")
                raise typer.Exit(1) from e

        client = GitHubClient(github_token)
        repos = _fetch_repos(client, user, org or [], include_private, status)

        if not repos:
            status.print("[yellow]No repositories found[/yellow]")
            raise typer.Exit(0)

        sources = {"user": user, "orgs": org or []}
        audits = [audit_repository(repo, vocab) for repo in repos]
        report = build_report(audits, sources, vocab)

        if backup:
            write_json_atomic(build_backup(repos, sources), backup)
            status.print(f"[green]Backup written to {backup}[/green]")

        if output:
            write_json_atomic(report, output)
            status.print(f"[green]Audit report written to {output}[/green]")

        if json_output:
            print(json.dumps(report, indent=2, default=str))
            return

        display = [audit for audit in audits if audit.has_issues]
        if only_issues:
            audits_to_show = display
        else:
            audits_to_show = audits

        _display_audit(audits_to_show, report["summary"])

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _fetch_repos(
    client: GitHubClient,
    user: bool,
    orgs: list[str],
    include_private: bool,
    status: Console,
) -> list[dict[str, Any]]:
    """Fetch and deduplicate repositories from the requested sources."""
    repos: list[dict[str, Any]] = []

    if user:
        visibility = "all" if include_private else "public"
        status.print(f"[blue]Fetching your {visibility} repositories...[/blue]")
        repos.extend(
            client.get_user_repos(None, visibility=visibility, affiliation="owner")
        )

    for org_name in orgs:
        status.print(f"[blue]Fetching repositories for {org_name}...[/blue]")
        org_repos = client.get_org_repos(org_name)
        if not include_private:
            org_repos = [repo for repo in org_repos if not repo.get("private", False)]
        repos.extend(org_repos)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for repo in repos:
        full_name = repo.get("full_name")
        if full_name:
            if full_name in seen:
                continue
            seen.add(full_name)
        unique.append(repo)

    # The list endpoint normally includes topics. If it does not, fetch them
    # per repo so the audit does not report false missing-topic issues.
    for repo in unique:
        if repo.get("topics") is None:
            owner, _, name = str(repo.get("full_name") or "").partition("/")
            if owner and name:
                repo["topics"] = client.get_repo_topics(owner, name)

    return unique


def _display_audit(audits: list[RepoAudit], summary: dict[str, int]) -> None:
    """Display the audit as a table plus summary counts."""
    if not audits:
        console.print("[green]No issues found.[/green]")
        return

    status_style = {
        "missing": "red",
        "truncated": "yellow",
        "near_limit": "yellow",
        "ok": "green",
    }

    table = Table(title=f"Repository audit ({summary['total']} repositories)")
    table.add_column("Repository", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Spelling", style="yellow", max_width=40)
    table.add_column("Standard tags", style="green", max_width=30)
    table.add_column("Topic issues", style="magenta", max_width=40)

    for audit in audits:
        style = status_style.get(audit.description_status, "white")
        spelling = ", ".join(
            f"{issue.word}->{issue.suggestion}" for issue in audit.spelling
        )
        table.add_row(
            audit.full_name,
            f"[{style}]{audit.description_status}[/]",
            spelling or "-",
            ", ".join(audit.standard_topics) or "-",
            "; ".join(audit.topic_issues) or "-",
        )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {summary['total']} repos, "
        f"[red]{summary['missing_description']} missing[/red], "
        f"[yellow]{summary['truncated_description']} truncated[/yellow], "
        f"[yellow]{summary['near_limit_description']} near limit[/yellow], "
        f"[yellow]{summary['with_spelling']} with US spelling[/yellow], "
        f"[magenta]{summary['with_topic_issues']} with topic issues[/magenta], "
        f"[green]{summary['clean']} clean[/green]"
    )
    if "without_standard_tag" in summary:
        console.print(
            f"[yellow]{summary['without_standard_tag']} without a standard tag[/yellow]"
        )
