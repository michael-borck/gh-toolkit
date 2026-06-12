"""Portfolio generation and audit commands."""

import os
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.portfolio_generator import PortfolioGenerator

console = Console()


def generate(
    org: Annotated[
        list[str] | None,
        typer.Option("--org", "-o", help="Organization names to include (repeatable)"),
    ] = None,
    discover: bool = typer.Option(
        False,
        "--discover",
        "-d",
        help="Auto-discover organizations from user memberships",
    ),
    readme_path: str = typer.Option(
        "README.md",
        "--readme",
        help="Output README.md path",
    ),
    html_path: str | None = typer.Option(
        None,
        "--html",
        help="Output HTML portfolio path (optional)",
    ),
    theme: str = typer.Option(
        "portfolio",
        "--theme",
        help="HTML theme: educational, resume, research, portfolio",
    ),
    group_by: str = typer.Option(
        "org",
        "--group-by",
        help="Group repos by: org, category, language",
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Custom portfolio title",
    ),
    include_private: bool = typer.Option(
        False,
        "--include-private",
        help="Include private repositories",
    ),
    exclude_forks: bool = typer.Option(
        True,
        "--exclude-forks/--include-forks",
        help="Exclude forked repositories",
    ),
    min_stars: int = typer.Option(
        0,
        "--min-stars",
        help="Minimum stars required to include a repo",
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
        help="Anthropic API key for LLM features",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview without writing files",
    ),
) -> None:
    """Generate a cross-organization portfolio index.

    Creates a README and optional HTML portfolio page aggregating
    repositories from multiple GitHub organizations.

    Examples:
        gh-toolkit portfolio generate --discover
        gh-toolkit portfolio generate --org my-org --org other-org
        gh-toolkit portfolio generate --discover --html portfolio.html --theme resume
    """
    try:
        # Validate inputs
        if not org and not discover:
            console.print(
                "[red]Error: Specify --org names or use --discover flag[/red]"
            )
            raise typer.Exit(1)

        # Get tokens
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required. Set GITHUB_TOKEN or use --token[/red]"
            )
            raise typer.Exit(1)

        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")

        # Validate theme
        valid_themes = ["educational", "resume", "research", "portfolio"]
        if theme not in valid_themes:
            console.print(
                f"[red]Error: Invalid theme '{theme}'. Choose from: {', '.join(valid_themes)}[/red]"
            )
            raise typer.Exit(1)

        # Validate group_by
        valid_group_by = ["org", "category", "language"]
        if group_by not in valid_group_by:
            console.print(
                f"[red]Error: Invalid group-by '{group_by}'. Choose from: {', '.join(valid_group_by)}[/red]"
            )
            raise typer.Exit(1)

        # Initialize client and generator
        client = GitHubClient(github_token)
        generator = PortfolioGenerator(client, anthropic_api_key)

        # Determine organizations
        org_names: list[str] = list(org) if org else []

        if discover:
            discovered_orgs = generator.discover_organizations()
            for org_data in discovered_orgs:
                org_login = org_data.get("login", "")
                if org_login and org_login not in org_names:
                    org_names.append(org_login)

        if not org_names:
            console.print("[yellow]No organizations found[/yellow]")
            raise typer.Exit(0)

        console.print(
            f"[blue]Generating portfolio for {len(org_names)} organizations:[/blue]"
        )
        for name in org_names:
            console.print(f"  - {name}")

        # Fetch organization info
        org_infos: dict[str, dict[str, Any]] = {}
        for org_name in org_names:
            try:
                org_info = client.get_org_info(org_name)
                org_infos[org_name] = org_info
            except GitHubAPIError as e:
                console.print(
                    f"[yellow]Warning: Could not fetch info for {org_name}: {e.message}[/yellow]"
                )
                org_infos[org_name] = {"login": org_name, "description": None}

        # Aggregate repositories
        repos = generator.aggregate_repos(
            org_names=org_names,
            exclude_forks=exclude_forks,
            include_private=include_private,
            min_stars=min_stars,
        )

        if not repos:
            console.print("[yellow]No repositories found matching criteria[/yellow]")
            raise typer.Exit(0)

        # Generate README
        readme_content = generator.generate_readme(
            repos=repos,
            org_infos=org_infos,
            group_by=group_by,
            title=title,
        )

        if dry_run:
            console.print(
                "\n[yellow]--- DRY RUN: Preview of generated README ---[/yellow]\n"
            )
            console.print(readme_content)
            console.print("\n[yellow]--- End of preview ---[/yellow]")
        else:
            generator.save_readme(readme_content, readme_path)

        # Generate HTML if requested
        if html_path:
            html_content = generator.generate_html(
                repos=repos,
                org_infos=org_infos,
                theme=theme,
                title=title,
            )

            if dry_run:
                console.print(
                    f"\n[yellow]Would generate HTML portfolio at: {html_path}[/yellow]"
                )
            else:
                generator.save_html(html_content, html_path)

        if not dry_run:
            console.print("\n[green]Portfolio generated successfully![/green]")
            console.print(f"[blue]README: {Path(readme_path).absolute()}[/blue]")
            if html_path:
                console.print(f"[blue]HTML: {Path(html_path).absolute()}[/blue]")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def audit(
    org: Annotated[
        list[str] | None,
        typer.Option("--org", "-o", help="Organization names to audit (repeatable)"),
    ] = None,
    discover: bool = typer.Option(
        False,
        "--discover",
        "-d",
        help="Auto-discover organizations from user memberships",
    ),
    user: bool = typer.Option(
        False,
        "--user",
        "-u",
        help="Include authenticated user's personal repositories",
    ),
    include_private: bool = typer.Option(
        False,
        "--include-private",
        help="Include private repositories",
    ),
    exclude_forks: bool = typer.Option(
        True,
        "--exclude-forks/--include-forks",
        help="Exclude forked repositories",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Output audit report to JSON file",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
) -> None:
    """Audit repositories for missing descriptions, topics, and licenses.

    Scans repositories across organizations and flags those with
    missing metadata that should be improved.

    Examples:
        gh-toolkit portfolio audit --discover
        gh-toolkit portfolio audit --org my-org --output audit-report.json
    """
    try:
        # Validate inputs
        if not org and not discover and not user:
            console.print(
                "[red]Error: Specify --org names, use --discover flag, or use --user flag[/red]"
            )
            raise typer.Exit(1)

        # Get token
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required. Set GITHUB_TOKEN or use --token[/red]"
            )
            raise typer.Exit(1)

        # Initialize client and generator
        client = GitHubClient(github_token)
        generator = PortfolioGenerator(client)

        # Determine organizations
        org_names: list[str] = list(org) if org else []

        if discover:
            discovered_orgs = generator.discover_organizations()
            for org_data in discovered_orgs:
                org_login = org_data.get("login", "")
                if org_login and org_login not in org_names:
                    org_names.append(org_login)

        # Show what we're auditing
        sources: list[str] = []
        if org_names:
            sources.append(f"{len(org_names)} organizations")
        if user:
            sources.append("personal repositories")

        if not org_names and not user:
            console.print("[yellow]No organizations found[/yellow]")
            raise typer.Exit(0)

        console.print(f"[blue]Auditing: {', '.join(sources)}[/blue]")
        for name in org_names:
            console.print(f"  - {name}")

        # Aggregate repositories from organizations
        repos: list[dict[str, Any]] = []
        if org_names:
            repos = generator.aggregate_repos(
                org_names=org_names,
                exclude_forks=exclude_forks,
                include_private=include_private,
                min_stars=0,
            )

        # Include personal repositories if requested
        if user:
            console.print("[blue]Including personal repositories...[/blue]")
            visibility = "all" if include_private else "public"
            user_repos = client.get_user_repos(
                visibility=visibility, affiliation="owner"
            )
            for repo in user_repos:
                if exclude_forks and repo.get("fork"):
                    continue
                repo["source_org"] = "personal"
                repos.append(repo)

        if not repos:
            console.print("[yellow]No repositories found[/yellow]")
            raise typer.Exit(0)

        # Run audit
        report = generator.audit_repos(repos)

        # Print report
        generator.print_audit_report(report)

        # Save to file if requested
        if output:
            import json

            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            console.print(
                f"\n[green]Audit report saved to {output_path.absolute()}[/green]"
            )

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e
