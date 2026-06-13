"""Repository management commands."""

import os
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit.core.config import resolve_token
from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.health_checker import HealthReport, RepositoryHealthChecker
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL
from gh_toolkit.core.repo_cloner import CloneResult, CloneStats, RepoCloner
from gh_toolkit.core.repo_extractor import RepositoryExtractor

console = Console()
err_console = Console(stderr=True)


def _load_rubric(path: str | None):
    """Load a rubric from ``path`` or return None; exit cleanly on a bad file."""
    if not path:
        return None
    from gh_toolkit.core.rubric import load_rubric

    try:
        return load_rubric(path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error loading rubric: {e}[/red]")
        raise typer.Exit(1) from e


def list_repos(
    owner: str = typer.Argument(help="GitHub username or organization name"),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    public: bool = typer.Option(
        False, "--public", help="Show only public repositories"
    ),
    private: bool = typer.Option(
        False, "--private", help="Show only private repositories"
    ),
    forks: bool = typer.Option(False, "--forks", help="Show only forked repositories"),
    sources: bool = typer.Option(
        False, "--sources", help="Show only source repositories"
    ),
    archived: bool = typer.Option(
        False, "--archived", help="Show only archived repositories"
    ),
    language: str | None = typer.Option(
        None, "--language", help="Filter by programming language"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
    raw: bool = typer.Option(False, "--raw", "-r", help="Output only repository names"),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON to stdout (for piping)"
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Limit number of results"
    ),
) -> None:
    """List GitHub repositories with filtering options."""

    # In --json mode, status/warnings go to stderr so stdout stays clean JSON
    status = err_console if json_output else console

    try:
        # Use provided token or fallback to environment
        github_token = resolve_token(token)
        if not github_token:
            status.print("[yellow]Warning: No GitHub token provided[/yellow]")
            status.print("Rate limits will be much lower without authentication")
            status.print("Set GITHUB_TOKEN environment variable or use --token option")
            status.print("Get a token at: https://github.com/settings/tokens")
            status.print()

        client = GitHubClient(github_token)

        # Determine if this is the authenticated user
        try:
            auth_user = client.get_user_info()
            is_own_repos = auth_user["login"].lower() == owner.lower()
        except GitHubAPIError:
            is_own_repos = False

        # Determine repository type for API call
        repo_type = "all"
        if forks:
            repo_type = "forks"
        elif sources:
            repo_type = "sources"

        # Get repositories
        status.print(f"[blue]Fetching repositories for '{owner}'...[/blue]")

        # Note: GitHub API client returns list[dict[str, Any]] which we treat as GitHubRepository
        repos: list[dict[str, Any]]
        if is_own_repos:
            repos = client.get_user_repos(repo_type=repo_type)
        else:
            # Check if it's an organization
            try:
                user_info = client.get_user_info(owner)
                if user_info.get("type") == "Organization":
                    repos = client.get_org_repos(owner, repo_type)
                else:
                    repos = client.get_user_repos(owner, repo_type)
            except GitHubAPIError as e:
                console.print(
                    f"[red]Error: Could not find user/organization '{owner}'[/red]"
                )
                raise typer.Exit(1) from e

        if not repos:
            if json_output:
                print("[]")
            else:
                console.print("[yellow]No repositories found[/yellow]")
            return

        # Apply filters
        filtered_repos: list[dict[str, Any]] = repos

        # Visibility filter
        if public:
            filtered_repos = [r for r in filtered_repos if not r.get("private", False)]
        elif private:
            filtered_repos = [r for r in filtered_repos if r.get("private", False)]

        # Type filters
        if archived:
            filtered_repos = [r for r in filtered_repos if r.get("archived", False)]
        elif forks and repo_type == "all":  # Additional filtering if not done by API
            filtered_repos = [r for r in filtered_repos if r.get("fork", False)]
        elif sources and repo_type == "all":
            filtered_repos = [r for r in filtered_repos if not r.get("fork", False)]

        # Language filter
        if language:
            filtered_repos = [
                r
                for r in filtered_repos
                if r.get("language")
                and r["language"]
                and r["language"].lower() == language.lower()
            ]

        # Apply limit
        if limit:
            filtered_repos = filtered_repos[:limit]

        if not filtered_repos:
            if json_output:
                print("[]")
            else:
                console.print(
                    "[yellow]No repositories found matching the criteria[/yellow]"
                )
            return

        # Display results
        if json_output:
            import json

            print(json.dumps([_repo_summary(r) for r in filtered_repos], indent=2))
        elif raw:
            # Raw mode: just print repository names
            for repo in filtered_repos:
                console.print(repo["name"])
        elif verbose:
            # Verbose mode: detailed information
            _display_verbose_repos(filtered_repos)
        else:
            # Default mode: table format
            _display_repos_table(filtered_repos)

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def _display_repos_table(repos: list[dict[str, Any]]) -> None:
    """Display repositories in a beautiful table format."""
    table = Table(title=f"Found {len(repos)} repositories")

    table.add_column("Repository", style="cyan", min_width=20)
    table.add_column("Description", style="white", max_width=50)
    table.add_column("Language", style="green")
    table.add_column("Stars", justify="right", style="yellow")
    table.add_column("Forks", justify="right", style="blue")
    table.add_column("Updated", style="magenta")

    for repo in repos:
        # Repository name with indicators
        repo_name = repo["full_name"]
        if repo.get("private", False):
            repo_name = f"🔒 {repo_name}"
        if repo.get("fork", False):
            repo_name = f"{repo_name} (fork)"
        if repo.get("archived", False):
            repo_name = f"{repo_name} [ARCHIVED]"

        # Description (truncated)
        description = repo.get("description") or ""
        if len(description) > 45:
            description = description[:42] + "..."

        # Language
        language = repo.get("language") or ""

        # Stars and forks
        stars = str(repo.get("stargazers_count", 0))
        forks = str(repo.get("forks_count", 0))

        # Last updated (just the date)
        updated = repo.get("updated_at", "")
        if updated:
            updated = updated.split("T")[0]  # Just the date part

        table.add_row(repo_name, description, language, stars, forks, updated)

    console.print(table)


def _display_verbose_repos(repos: list[dict[str, Any]]) -> None:
    """Display repositories in verbose format."""
    for i, repo in enumerate(repos, 1):
        console.print(f"\n[bold cyan]{i}. {repo['full_name']}[/bold cyan]")
        console.print(f"   URL: [link]{repo['html_url']}[/link]")

        if repo.get("description"):
            console.print(f"   Description: {repo['description']}")

        # Status indicators
        status_parts: list[str] = []
        if repo.get("private", False):
            status_parts.append("[red]Private[/red]")
        else:
            status_parts.append("[green]Public[/green]")

        if repo.get("fork", False):
            status_parts.append("[blue]Fork[/blue]")

        if repo.get("archived", False):
            status_parts.append("[yellow]Archived[/yellow]")

        console.print(f"   Status: {' | '.join(status_parts)}")

        # Stats
        console.print(
            f"   Stats: ⭐ {repo.get('stargazers_count', 0)} stars, "
            f"🍴 {repo.get('forks_count', 0)} forks, "
            f"👁️ {repo.get('watchers_count', 0)} watchers"
        )

        # Language and dates
        if repo.get("language"):
            console.print(f"   Language: [green]{repo['language']}[/green]")

        console.print(f"   Created: {repo.get('created_at', 'N/A')}")
        console.print(f"   Updated: {repo.get('updated_at', 'N/A')}")

        if repo.get("homepage"):
            console.print(f"   Homepage: [link]{repo['homepage']}[/link]")


def extract_repos(
    repos_input: str = typer.Argument(
        help="File with repo list (owner/repo per line) or single owner/repo"
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
        help="Anthropic API key for LLM categorization (or set ANTHROPIC_API_KEY env var)",
    ),
    output: str = typer.Option(
        "repos_data.json", "--output", "-o", help="Output JSON file"
    ),
    parallel: int = typer.Option(
        4, "--parallel", "-p", help="Number of concurrent extractions"
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Skip repos already present in the output file and append the rest",
    ),
    show_confidence: bool = typer.Option(
        False, "--show-confidence", help="Show categorization confidence details"
    ),
) -> None:
    """Extract comprehensive data from GitHub repositories with LLM categorization."""

    try:
        # Use provided token or fallback to environment
        github_token = resolve_token(token)
        if not github_token:
            console.print("[yellow]Warning: No GitHub token provided[/yellow]")
            console.print("Rate limits will be much lower without authentication")
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print()

        # Get Anthropic key for LLM categorization
        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            console.print("[yellow]Info: No Anthropic API key provided[/yellow]")
            console.print("Will use rule-based categorization instead of LLM")
            console.print(
                "For LLM categorization, set ANTHROPIC_API_KEY or use --anthropic-key"
            )
            console.print()

        # Initialize client and extractor
        client = GitHubClient(github_token)
        extractor = RepositoryExtractor(client, anthropic_api_key)

        # Determine if input is a file or single repo
        repo_list: list[str] = []
        input_path = Path(repos_input)

        if input_path.exists() and input_path.is_file():
            # Read repo list from file
            console.print(f"[blue]Reading repository list from {input_path}[/blue]")
            try:
                with open(input_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            repo_list.append(line)
            except Exception as e:
                console.print(f"[red]Error reading file {input_path}: {e}[/red]")
                raise typer.Exit(1) from e
        else:
            # Single repository
            if "/" not in repos_input:
                console.print(
                    "[red]Error: Repository must be in 'owner/repo' format[/red]"
                )
                raise typer.Exit(1)
            repo_list = [repos_input]

        if not repo_list:
            console.print("[red]Error: No repositories to process[/red]")
            raise typer.Exit(1)

        console.print(
            f"[green]Found {len(repo_list)} repository(ies) to extract[/green]"
        )

        # Resume: load existing results and skip repos already extracted
        import json as _json

        combined: list[dict[str, Any]] = []
        skip: set[str] = set()
        if resume and Path(output).exists():
            try:
                with open(output, encoding="utf-8") as f:
                    combined = _json.load(f)
                skip = {r["full_name"] for r in combined if r.get("full_name")}
                console.print(
                    f"[blue]Resuming: {len(skip)} already in {output}, will skip those[/blue]"
                )
            except (OSError, ValueError, KeyError) as e:
                console.print(
                    f"[yellow]Could not read {output} for resume ({e}); starting fresh[/yellow]"
                )
                combined = []
                skip = set()

        # Persist incrementally so a crash mid-run keeps progress
        def _save_progress(result: dict[str, Any]) -> None:
            combined.append(result)
            extractor.save_to_json(combined, output)

        # Extract data
        console.print(
            f"\n[bold]Starting repository data extraction "
            f"({parallel} concurrent)...[/bold]"
        )
        extracted_data = extractor.extract_multiple_repositories(
            repo_list,
            parallel=parallel,
            skip=skip,
            result_callback=_save_progress,
        )

        if not combined:
            console.print("[red]No repositories were successfully extracted[/red]")
            raise typer.Exit(1)

        # Final save (covers the resume-only case where nothing new was extracted)
        extractor.save_to_json(combined, output)

        # Show summary
        attempted = len(repo_list) - len(skip)
        console.print(
            f"\n[bold green]✓ Extracted {len(extracted_data)} repositories "
            f"({len(combined)} total in {output})[/bold green]"
        )
        if attempted - len(extracted_data) > 0:
            console.print(
                f"[red]✗ Failed to extract {attempted - len(extracted_data)} "
                "repositories[/red]"
            )

        # Category summary over everything in the output file
        extracted_data = combined
        categories: dict[str, int] = {}
        for repo in extracted_data:
            cat = repo["category"]
            categories[cat] = categories.get(cat, 0) + 1

        if categories:
            console.print("\n[bold]Categories found:[/bold]")
            for cat, count in sorted(categories.items()):
                console.print(f"  • [cyan]{cat}[/cyan]: {count} repos")

        # Show confidence details if requested
        if show_confidence and extracted_data:
            console.print("\n[bold]Category Detection Details:[/bold]")
            table = Table()
            table.add_column("Repository", style="cyan")
            table.add_column("Category", style="green")
            table.add_column("Confidence", justify="center", style="yellow")
            table.add_column("Reason", style="white", max_width=40)

            for repo in sorted(extracted_data, key=lambda x: x["category_confidence"]):
                confidence = f"{repo['category_confidence']:.1%}"
                reason = repo["category_reason"]
                if len(reason) > 37:
                    reason = reason[:34] + "..."

                table.add_row(repo["name"], repo["category"], confidence, reason)

            console.print(table)

        console.print(f"\n[bold]Data saved to: [link]{output}[/link][/bold]")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def health_check(
    repos_input: str = typer.Argument(
        help="File with repo list (owner/repo per line) or single owner/repo"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    rules: str = typer.Option(
        "general", "--rules", "-r", help="Rule set: general, academic, professional"
    ),
    rubric: str | None = typer.Option(
        None,
        "--rubric",
        help="Custom rubric YAML (overrides check weights, grade thresholds, required checks)",
    ),
    min_score: int = typer.Option(
        70, "--min-score", help="Minimum health score threshold (0-100)"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output JSON report file"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output reports as JSON to stdout (for piping)"
    ),
    show_details: bool = typer.Option(
        True, "--details/--no-details", help="Show detailed check results"
    ),
    show_fixes: bool = typer.Option(
        True, "--fixes/--no-fixes", help="Show fix suggestions"
    ),
    only_failed: bool = typer.Option(
        False, "--only-failed", help="Show only repositories that failed health checks"
    ),
    post_issue: bool = typer.Option(
        False,
        "--post-issue",
        help="Post the health report as an issue on each repo (idempotent; "
        "updates an existing gh-toolkit issue rather than duplicating)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt for --post-issue"
    ),
) -> None:
    """Check repository health and best practices compliance."""

    # In --json mode, status/progress go to stderr so stdout stays clean JSON
    status = err_console if json_output else console

    try:
        # Use provided token or fallback to environment
        github_token = resolve_token(token)
        if not github_token:
            console.print("[red]Error: GitHub token required for health checks[/red]")
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            console.print("Get a token at: https://github.com/settings/tokens")
            raise typer.Exit(1)

        # Initialize client and health checker
        client = GitHubClient(github_token)
        checker = RepositoryHealthChecker(client, rules, rubric=_load_rubric(rubric))

        # Determine if input is a file, wildcard pattern, or single repo
        repo_list: list[str] = []
        input_path = Path(repos_input)

        if input_path.exists() and input_path.is_file():
            # Read repo list from file
            console.print(f"[blue]Reading repository list from {input_path}[/blue]")
            try:
                with open(input_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            repo_list.append(line)
            except Exception as e:
                console.print(f"[red]Error reading file {input_path}: {e}[/red]")
                raise typer.Exit(1) from e
        elif repos_input.endswith("/*"):
            # Wildcard pattern: fetch all repos for user/org
            owner = repos_input[:-2]
            console.print(
                f"[blue]🔍 Fetching all repositories for user/org: {owner}[/blue]"
            )

            # Check if this is the authenticated user (to include private repos)
            authenticated_user = client.get_authenticated_user()
            if authenticated_user and authenticated_user.lower() == owner.lower():
                console.print("[dim]Including private repositories[/dim]")
                user_repos = client.get_user_repos(
                    None, visibility="all", affiliation="owner"
                )
            else:
                user_repos = client.get_user_repos(owner)

            repo_list = [f"{owner}/{r['name']}" for r in user_repos]
            console.print(
                f"[green]✓ Found {len(repo_list)} repositories for {owner}[/green]\n"
            )
        else:
            # Single repository
            if "/" not in repos_input:
                console.print(
                    "[red]Error: Repository must be in 'owner/repo' format[/red]"
                )
                raise typer.Exit(1)
            repo_list = [repos_input]

        if not repo_list:
            console.print("[red]Error: No repositories to check[/red]")
            raise typer.Exit(1)

        status.print(
            f"[green]Checking health of {len(repo_list)} repository(ies)[/green]"
        )
        status.print(f"[blue]Rule set: {rules}[/blue]")
        status.print(f"[blue]Minimum score threshold: {min_score}%[/blue]\n")

        # Check each repository
        reports: list[HealthReport] = []
        failed_repos: list[str] = []

        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=status,
        ) as progress:
            task = progress.add_task("Checking repositories...", total=len(repo_list))

            for repo_name in repo_list:
                progress.update(task, description=f"Checking {repo_name}")

                try:
                    report = checker.check_repository_health(repo_name)
                    reports.append(report)

                    if report.percentage < min_score:
                        failed_repos.append(repo_name)

                except Exception as e:
                    console.print(f"[red]✗ Failed to check {repo_name}: {str(e)}[/red]")
                    failed_repos.append(repo_name)

                progress.advance(task)

        # Post feedback as issues (its own outward-facing action)
        if post_issue:
            _post_health_feedback(checker.client, reports, assume_yes=yes)
            return

        # Filter reports if only showing failed
        display_reports = (
            [r for r in reports if r.percentage < min_score] if only_failed else reports
        )

        if not display_reports:
            if json_output:
                print("[]")
            elif only_failed:
                console.print(
                    "[green]🎉 All repositories passed the health checks![/green]"
                )
            else:
                console.print("[yellow]No health reports to display[/yellow]")
            return

        # Save JSON report to file if requested (independent of --json stdout)
        if output:
            _save_health_reports(reports, output)
            status.print(
                f"\n[bold]Health reports saved to: [link]{output}[/link][/bold]"
            )

        # Display results
        if json_output:
            print(_health_reports_to_json(display_reports))
            return

        console.print(
            f"\n[bold]Health Check Results ({len(display_reports)} repositories)[/bold]\n"
        )

        for report in display_reports:
            _display_health_report(report, show_details, show_fixes)

        # Summary statistics
        if len(reports) > 1:
            _display_health_summary(reports, min_score, failed_repos)

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def roster_report(
    roster_path: str = typer.Argument(
        help="Roster CSV with a GitHub username column (and optional name/id/repo)"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    org: str | None = typer.Option(
        None,
        "--org",
        help="Organization that owns the repos (used with --repo-pattern or a bare username)",
    ),
    repo_pattern: str | None = typer.Option(
        None,
        "--repo-pattern",
        help="Repo name template, e.g. 'assignment1-{github}' (fields: github, username, id, name)",
    ),
    rules: str = typer.Option(
        "academic", "--rules", "-r", help="Rule set: general, academic, professional"
    ),
    rubric: str | None = typer.Option(
        None,
        "--rubric",
        help="Custom rubric YAML (overrides check weights, grade thresholds, required checks)",
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Write the full report to a CSV file"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output report as JSON to stdout (for piping)"
    ),
) -> None:
    """Submission/hygiene report for a class roster.

    Joins repository health results to a roster of students. For each student it
    resolves a repo (from an explicit roster column, a --repo-pattern, or
    org/<username>), runs the health checks, and reports whether the repo exists
    plus its hygiene score and which checks fail. This tracks *whether the repo
    was set up properly* — it does not mark the work itself.

    Examples:
        gh-toolkit repo roster students.csv --org myclass --repo-pattern "lab1-{github}"
        gh-toolkit repo roster students.csv --org myclass --output report.csv
    """
    import json as _json

    from gh_toolkit.core.roster import (
        parse_roster,
        report_row,
        resolve_repo,
        rows_to_csv,
    )

    status = err_console if json_output else console

    try:
        github_token = resolve_token(token)
        if not github_token:
            console.print("[red]Error: GitHub token required for roster reports[/red]")
            console.print("Set GITHUB_TOKEN environment variable or use --token option")
            raise typer.Exit(1)

        try:
            students = parse_roster(roster_path)
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1) from e

        client = GitHubClient(github_token)
        checker = RepositoryHealthChecker(client, rules, rubric=_load_rubric(rubric))

        status.print(
            f"[green]Checking {len(students)} student repositories"
            f" (rule set: {rules})[/green]\n"
        )

        rows: list[dict[str, Any]] = []
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=status,
        ) as progress:
            task = progress.add_task("Checking submissions...", total=len(students))
            for student in students:
                repo = resolve_repo(student, org, repo_pattern)
                progress.update(
                    task, description=f"Checking {repo or student.github_username}"
                )

                if repo is None:
                    rows.append(
                        report_row(
                            student,
                            None,
                            "unresolved",
                            None,
                            error="Could not resolve a repo (pass --org or --repo-pattern)",
                        )
                    )
                else:
                    try:
                        report = checker.check_repository_health(repo)
                        rows.append(report_row(student, repo, "found", report))
                    except GitHubAPIError as e:
                        row_status = "not_found" if e.status_code == 404 else "error"
                        rows.append(
                            report_row(student, repo, row_status, None, error=e.message)
                        )
                    except Exception as e:  # noqa: BLE001 - per-student isolation
                        rows.append(
                            report_row(student, repo, "error", None, error=str(e))
                        )
                progress.advance(task)

        if output:
            rows_to_csv(rows, output)
            status.print(f"\n[bold]Report written to: [link]{output}[/link][/bold]")

        if json_output:
            print(_json.dumps(rows, indent=2))
            return

        _display_roster_summary(rows)

    except typer.Exit:
        raise
    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def _display_roster_summary(rows: list[dict[str, Any]]) -> None:
    """Display the per-student roster report as a table plus a summary."""
    table = Table(title=f"Roster Submission Report ({len(rows)} students)")
    table.add_column("Student", style="cyan")
    table.add_column("Username", style="blue")
    table.add_column("Repository", style="white")
    table.add_column("Status", style="white")
    table.add_column("Score", justify="right", style="yellow")
    table.add_column("Grade", justify="center")
    table.add_column("Failing checks", style="red", max_width=40)

    status_style = {
        "found": "green",
        "not_found": "red",
        "unresolved": "yellow",
        "error": "red",
    }
    for row in rows:
        st = row["status"]
        status_label = {
            "found": "✓ submitted",
            "not_found": "✗ missing",
            "unresolved": "? unresolved",
            "error": "! error",
        }.get(st, st)
        score = f"{row['score_percent']}%" if row["score_percent"] is not None else "-"
        table.add_row(
            row["student_name"] or "-",
            row["github_username"],
            row["repository"] or "-",
            f"[{status_style.get(st, 'white')}]{status_label}[/]",
            score,
            row["grade"] or "-",
            row["failed_checks"] or ("" if st == "found" else "-"),
        )

    console.print(table)

    found = [r for r in rows if r["status"] == "found"]
    missing = sum(1 for r in rows if r["status"] == "not_found")
    other = len(rows) - len(found) - missing
    console.print(
        f"\n[bold]Submitted:[/bold] {len(found)}/{len(rows)}"
        f"   [bold]Missing:[/bold] {missing}"
        f"   [bold]Unresolved/errors:[/bold] {other}"
    )
    if found:
        avg = sum(r["score_percent"] for r in found) / len(found)
        console.print(f"[bold]Average hygiene score (submitted):[/bold] {avg:.1f}%")


def _display_health_report(
    report: HealthReport, show_details: bool, show_fixes: bool
) -> None:
    """Display a single repository health report."""
    from rich.panel import Panel
    # Unused imports removed for type checking

    # Header with score
    grade_color = {"A": "green", "B": "blue", "C": "yellow", "D": "orange1", "F": "red"}

    header = f"[bold cyan]{report.repository}[/bold cyan] - Grade: [{grade_color.get(report.grade, 'white')}]{report.grade}[/{grade_color.get(report.grade, 'white')}] ({report.percentage:.1f}%)"

    content = []

    # Score breakdown by category
    content: list[str] = []
    if show_details:
        content.append("[bold]Category Breakdown:[/bold]")
        for category, data in report.summary["by_category"].items():
            percentage = data["percentage"]
            passed = data["passed"]
            total = data["total"]

            bar_color = (
                "green" if percentage >= 80 else "yellow" if percentage >= 60 else "red"
            )
            content.append(
                f"  {category}: [{bar_color}]{percentage:.0f}%[/{bar_color}] ({passed}/{total} checks passed)"
            )

        content.append("")

    # Failed checks with fix suggestions
    if show_fixes and report.summary["top_issues"]:
        content.append("[bold]Top Issues to Fix:[/bold]")
        for i, issue in enumerate(report.summary["top_issues"][:3], 1):
            content.append(f"  {i}. [red]{issue.name}[/red]: {issue.message}")
            if issue.fix_suggestion:
                content.append(f"     💡 [dim]{issue.fix_suggestion}[/dim]")
        content.append("")

    # Repository stats
    repo_info = report.summary["repository_info"]
    stats_parts: list[str] = []
    if repo_info["language"]:
        stats_parts.append(f"Language: {repo_info['language']}")
    if repo_info["stars"] and repo_info["stars"] > 0:
        stats_parts.append(f"⭐ {repo_info['stars']}")
    if repo_info["size_kb"] and repo_info["size_kb"] > 0:
        stats_parts.append(f"Size: {repo_info['size_kb']}KB")

    if stats_parts:
        content.append(f"[dim]{' | '.join(stats_parts)}[/dim]")

    # Highlight required checks (from a rubric) that failed
    required_failures = report.summary.get("required_failures")
    if required_failures:
        content.append("")
        content.append(
            f"[bold red]✗ Required checks failed:[/bold red] "
            f"{', '.join(required_failures)}"
        )

    panel_content = (
        "\n".join(content)
        if content
        else f"Score: {report.total_score}/{report.max_score}"
    )

    # Color the panel border based on grade
    border_style = grade_color.get(report.grade, "white")

    console.print(Panel(panel_content, title=header, border_style=border_style))
    console.print()


def _post_health_feedback(
    client: GitHubClient, reports: list[HealthReport], assume_yes: bool
) -> None:
    """Post each health report as an issue on its repo (create or update).

    Idempotent: an existing issue carrying the gh-toolkit marker is updated
    rather than duplicated. Confirms before posting unless assume_yes.
    """
    from gh_toolkit.core.feedback import (
        feedback_body,
        feedback_title,
        find_marker_issue,
    )

    if not reports:
        console.print("[yellow]No repositories were checked; nothing to post.[/yellow]")
        return

    # Preview
    table = Table(title=f"Feedback to post ({len(reports)} repositories)")
    table.add_column("Repository", style="cyan")
    table.add_column("Grade", justify="center")
    table.add_column("Issue title", style="white")
    for report in reports:
        table.add_row(
            report.repository,
            report.grade,
            feedback_title(report),
        )
    console.print(table)
    console.print(
        "[dim]Existing gh-toolkit health issues are updated; others are created. "
        "Repo owners are notified by GitHub per their settings.[/dim]"
    )

    if not assume_yes:
        if not typer.confirm(f"\nPost feedback to {len(reports)} repository(ies)?"):
            console.print("[yellow]Aborted; no issues posted.[/yellow]")
            return

    created = updated = failed = 0
    for report in reports:
        owner, _, repo = report.repository.partition("/")
        title = feedback_title(report)
        body = feedback_body(report)
        try:
            existing = find_marker_issue(client.get_repo_issues(owner, repo))
            if existing:
                client.update_issue(owner, repo, existing["number"], title, body)
                console.print(
                    f"  [blue]↻[/blue] {report.repository}: updated #{existing['number']}"
                )
                updated += 1
            else:
                issue = client.create_issue(owner, repo, title, body)
                console.print(
                    f"  [green]✓[/green] {report.repository}: created #{issue['number']}"
                )
                created += 1
        except GitHubAPIError as e:
            console.print(f"  [red]✗[/red] {report.repository}: {e.message}")
            failed += 1

    console.print(
        f"\n[bold]Posted:[/bold] {created} created, {updated} updated, "
        f"[red]{failed} failed[/red]"
    )


def _display_health_summary(
    reports: list[HealthReport], min_score: int, failed_repos: list[str]
) -> None:
    """Display summary statistics for multiple repositories."""
    from rich.panel import Panel

    total_repos = len(reports)
    passed_repos = len([r for r in reports if r.percentage >= min_score])
    failed_count = len(failed_repos)

    avg_score = sum(r.percentage for r in reports) / total_repos if reports else 0

    # Grade distribution
    grades: dict[str, int] = {}
    for report in reports:
        grades[report.grade] = grades.get(report.grade, 0) + 1

    summary_lines: list[str] = [
        f"[bold]Total Repositories:[/bold] {total_repos}",
        f"[bold]Passed ({min_score}%+):[/bold] [green]{passed_repos}[/green]",
        f"[bold]Failed:[/bold] [red]{failed_count}[/red]",
        f"[bold]Average Score:[/bold] {avg_score:.1f}%",
        "",
        "[bold]Grade Distribution:[/bold]",
    ]

    for grade in ["A", "B", "C", "D", "F"]:
        count = grades.get(grade, 0)
        if count > 0:
            percentage = count / total_repos * 100
            summary_lines.append(f"  Grade {grade}: {count} ({percentage:.0f}%)")

    console.print(
        Panel(
            "\n".join(summary_lines), title="[bold]Summary[/bold]", border_style="blue"
        )
    )


def _health_reports_to_json(reports: list[HealthReport]) -> str:
    """Serialize health reports to a JSON string."""
    import json
    from dataclasses import asdict

    return json.dumps([asdict(r) for r in reports], indent=2, default=str)


def _save_health_reports(reports: list[HealthReport], output_file: str) -> None:
    """Save health reports to JSON file."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(_health_reports_to_json(reports))


def _repo_summary(repo: dict[str, Any]) -> dict[str, Any]:
    """Curated, stable subset of repo fields for --json output."""
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "private": repo.get("private", False),
        "archived": repo.get("archived", False),
        "fork": repo.get("fork", False),
        "url": repo.get("html_url"),
        "topics": repo.get("topics", []),
        "updated_at": repo.get("updated_at"),
    }


def clone_repos(
    repos_input: str = typer.Argument(
        help="File with repo list (owner/repo per line) or single owner/repo"
    ),
    target_dir: str = typer.Option(
        "./repos", "--target-dir", "-d", help="Target directory for cloned repositories"
    ),
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Specific branch to clone"
    ),
    depth: int | None = typer.Option(
        None, "--depth", help="Clone depth for shallow clones"
    ),
    ssh: bool = typer.Option(
        None, "--ssh/--https", help="Force SSH or HTTPS (auto-detect by default)"
    ),
    parallel: int = typer.Option(
        4, "--parallel", "-p", help="Number of concurrent clone operations"
    ),
    continue_on_error: bool = typer.Option(
        True, "--continue/--fail-fast", help="Continue cloning on failures"
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--overwrite",
        help="Skip repositories that already exist locally",
    ),
    before: str | None = typer.Option(
        None,
        "--before",
        help="Check out the last commit before this date (e.g. '2026-06-12 23:59'); "
        "snapshots submissions at a deadline. Forces a full clone.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be cloned without doing it"
    ),
    cleanup: bool = typer.Option(
        True, "--cleanup/--no-cleanup", help="Clean up failed clone directories"
    ),
) -> None:
    """Clone GitHub repositories with smart organization and parallel processing."""

    try:
        # A deadline snapshot needs full history; shallow clones can't reach an
        # older commit. Drop --depth with a warning rather than silently failing.
        if before is not None and depth is not None:
            console.print(
                "[yellow]Note: --depth is ignored with --before (full history "
                "is needed to find the deadline commit)[/yellow]"
            )
            depth = None

        # Initialize cloner
        cloner = RepoCloner(target_dir=target_dir, parallel=parallel)

        # Check if git is available
        if not cloner.validate_git_available():
            console.print("[red]Error: Git is not available on this system[/red]")
            console.print("Please install Git and ensure it's in your PATH")
            raise typer.Exit(1)

        # Determine if input is a file or single repo
        repo_list: list[str] = []
        input_path = Path(repos_input)

        if input_path.exists() and input_path.is_file():
            # Read repo list from file
            console.print(f"[blue]Reading repository list from {input_path}[/blue]")
            try:
                repo_list = cloner.read_repo_list(input_path)
            except Exception as e:
                console.print(f"[red]Error reading file {input_path}: {e}[/red]")
                raise typer.Exit(1) from e
        else:
            # Single repository
            try:
                # Validate format by parsing
                cloner.parse_repo_input(repos_input)
                repo_list = [repos_input]
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1) from e

        if not repo_list:
            console.print("[red]Error: No repositories to clone[/red]")
            raise typer.Exit(1)

        # Show summary
        console.print(f"[green]Found {len(repo_list)} repository(ies) to clone[/green]")
        console.print(f"[blue]Target directory: {target_dir}[/blue]")
        console.print(f"[blue]Parallel operations: {parallel}[/blue]")

        if branch:
            console.print(f"[blue]Branch: {branch}[/blue]")
        if depth:
            console.print(f"[blue]Clone depth: {depth}[/blue]")
        if before:
            console.print(
                f"[blue]Deadline snapshot: last commit before {before}[/blue]"
            )

        # Estimate disk space
        space_estimate = cloner.estimate_disk_space(repo_list)
        console.print(f"[blue]Estimated disk space: {space_estimate}[/blue]")

        # Show organization strategy
        console.print("[blue]Organization: owner/repository directory structure[/blue]")

        if dry_run:
            console.print(
                "\n[yellow]🔍 Dry run mode - no repositories will be cloned[/yellow]"
            )
            _show_clone_preview(cloner, repo_list, branch, depth, ssh)
            return

        console.print()

        # Set up progress tracking
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Cloning repositories...", total=len(repo_list))

            def progress_callback(result: CloneResult, completed: int, total: int):
                if result.success:
                    status = "[green]✓[/green]"
                elif result.skipped:
                    status = "[yellow]⏭[/yellow]"
                else:
                    status = "[red]✗[/red]"

                progress.update(
                    task,
                    description=f"Cloning repositories... {status} {result.repo_name}",
                )
                progress.advance(task)

            # Clone repositories
            results, stats = cloner.clone_repositories(
                repo_list,
                branch=branch,
                depth=depth,
                use_ssh=ssh,
                skip_existing=skip_existing,
                progress_callback=progress_callback,
                before=before,
            )

        # Clean up failed clones if requested
        cleaned_up = 0
        if cleanup and stats.failed > 0:
            console.print("\n[blue]Cleaning up failed clone directories...[/blue]")
            cleaned_up = cloner.cleanup_failed_clones(results)

        # Show results
        _display_clone_results(results, stats, cleaned_up)

        # Exit with error code if there were failures and not continuing on error
        if stats.failed > 0 and not continue_on_error:
            raise typer.Exit(1)

    except KeyboardInterrupt as e:
        console.print("\n[yellow]Clone operation interrupted by user[/yellow]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def _show_clone_preview(
    cloner: RepoCloner,
    repo_list: list[str],
    branch: str | None,
    depth: int | None,
    use_ssh: bool | None,
) -> None:
    """Show preview of what would be cloned in dry-run mode."""
    from rich.table import Table

    table = Table(title="Clone Preview")
    table.add_column("Repository", style="cyan")
    table.add_column("Target Path", style="green")
    table.add_column("Clone URL", style="blue")
    table.add_column("Status", style="white")

    for repo_input in repo_list[:20]:  # Limit to first 20 for display
        try:
            owner, repo = cloner.parse_repo_input(repo_input)
            target_path = cloner.get_target_path(owner, repo)
            clone_url = cloner.build_clone_url(owner, repo, use_ssh)

            if target_path.exists():
                status = "[yellow]Would skip (exists)[/yellow]"
            else:
                status = "[green]Would clone[/green]"

            table.add_row(
                f"{owner}/{repo}",
                str(target_path.relative_to(cloner.target_dir)),
                clone_url,
                status,
            )
        except ValueError as e:
            table.add_row(
                repo_input,
                "[red]Invalid[/red]",
                "[red]Invalid[/red]",
                f"[red]{e}[/red]",
            )

    if len(repo_list) > 20:
        table.add_row("...", f"... and {len(repo_list) - 20} more", "...", "...")

    console.print(table)

    # Show additional options
    if branch:
        console.print(f"[blue]Branch:[/blue] {branch}")
    if depth:
        console.print(f"[blue]Depth:[/blue] {depth}")


def _display_clone_results(
    results: list[CloneResult], stats: CloneStats, cleaned_up: int
) -> None:
    """Display clone operation results."""
    from rich.panel import Panel

    # Summary panel
    summary_lines = [
        f"[bold]Total Repositories:[/bold] {stats.total_repos}",
        f"[bold]Successfully Cloned:[/bold] [green]{stats.successful}[/green]",
        f"[bold]Skipped (Already Exist):[/bold] [yellow]{stats.skipped}[/yellow]",
        f"[bold]Failed:[/bold] [red]{stats.failed}[/red]",
    ]

    if cleaned_up > 0:
        summary_lines.append(f"[bold]Cleaned Up Failed:[/bold] {cleaned_up}")

    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold]Clone Results[/bold]",
            border_style="blue",
        )
    )

    # Show successful clones
    if stats.successful > 0:
        console.print("\n[bold green]✓ Successfully Cloned:[/bold green]")
        successful_repos = [r for r in results if r.success]
        for result in successful_repos[:10]:  # Show first 10
            console.print(
                f"  [green]✓[/green] {result.repo_name} → {result.target_path}"
            )
            if result.note:
                console.print(f"      [dim]{result.note}[/dim]")

        if len(successful_repos) > 10:
            console.print(f"  ... and {len(successful_repos) - 10} more")

        # Flag repos with no commit before the deadline (no submission in time)
        no_commit = [
            r
            for r in successful_repos
            if r.note and r.note.startswith("No commit before")
        ]
        if no_commit:
            console.print(
                f"\n[yellow]⚠️  {len(no_commit)} repo(s) had no commit before "
                "the deadline (left at default HEAD)[/yellow]"
            )

    # Show skipped repositories
    if stats.skipped > 0:
        console.print("\n[bold yellow]⏭ Skipped (Already Exist):[/bold yellow]")
        skipped_repos = [r for r in results if r.skipped]
        for result in skipped_repos[:5]:  # Show first 5
            console.print(
                f"  [yellow]⏭[/yellow] {result.repo_name} → {result.target_path}"
            )

        if len(skipped_repos) > 5:
            console.print(f"  ... and {len(skipped_repos) - 5} more")

    # Show errors
    if stats.failed > 0:
        console.print("\n[bold red]✗ Failed to Clone:[/bold red]")
        for error in stats.errors[:10]:  # Show first 10 errors
            console.print(f"  [red]✗[/red] {error.repo_name}: {error.error}")

        if len(stats.errors) > 10:
            console.print(f"  ... and {len(stats.errors) - 10} more errors")

    # Overall status
    if stats.failed == 0:
        console.print(
            "\n[bold green]🎉 All clone operations completed successfully![/bold green]"
        )
    elif stats.successful > 0:
        console.print(
            f"\n[bold yellow]⚠️ Clone completed with {stats.failed} failures[/bold yellow]"
        )
    else:
        console.print("\n[bold red]❌ All clone operations failed[/bold red]")


def describe_repos(
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
        help="Anthropic API key for LLM generation (or set ANTHROPIC_API_KEY env var)",
    ),
    model: str = typer.Option(
        DEFAULT_LLM_MODEL,
        "--model",
        "-m",
        help="Anthropic model to use (e.g., claude-sonnet-4-6, claude-haiku-4-5)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what descriptions would be added without making changes",
    ),
    force: bool = typer.Option(
        False, "--force", help="Update description even if repository already has one"
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
    """Generate and update repository descriptions using LLM analysis.

    Automatically generates descriptions for repositories based on their
    content, README, and programming languages used.

    Examples:
        gh-toolkit repo describe user/repo --dry-run
        gh-toolkit repo describe repos.txt --force
        gh-toolkit repo describe michael-borck/* --anthropic-key=sk-...
    """
    try:
        from gh_toolkit.core.description_generator import DescriptionGenerator

        # Get tokens
        github_token = resolve_token(token)
        if not github_token:
            console.print(
                "[red]GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]"
            )
            console.print("[dim]Required scopes: repo[/dim]")
            raise typer.Exit(1)

        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            console.print(
                "[yellow]No Anthropic API key provided. Will use rule-based generation.[/yellow]"
            )
            console.print(
                "[dim]For better results, set ANTHROPIC_API_KEY env var or use --anthropic-key[/dim]"
            )

        # Initialize clients
        client = GitHubClient(github_token)
        generator = DescriptionGenerator(client, anthropic_api_key, rate_limit, model)

        # Parse repository input
        repo_list = _parse_describe_repos_input(repos_input, client)

        if not repo_list:
            console.print("[red]No repositories found to process[/red]")
            raise typer.Exit(1)

        # Show what we're about to do
        console.print(f"\n[blue]Found {len(repo_list)} repositories to process[/blue]")
        console.print(f"[blue]Using model: {model}[/blue]")
        if dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        if force:
            console.print(
                "[yellow]FORCE MODE - Will update repositories that already have descriptions[/yellow]"
            )

        # Process repositories
        results = generator.process_multiple_repositories(repo_list, dry_run, force)

        # Show summary
        _show_describe_summary(results, dry_run)

        # Save results if requested
        if output:
            _save_describe_results(results, output, dry_run, force)

    except KeyboardInterrupt as e:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _parse_describe_repos_input(
    repos_input: str, client: GitHubClient
) -> list[tuple[str, str]]:
    """Parse repository input and return list of (owner, repo) tuples."""
    repos: list[tuple[str, str]] = []

    # Check if it's a file
    if Path(repos_input).exists():
        console.print(f"[blue]Loading repositories from file: {repos_input}[/blue]")
        with open(repos_input, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        owner, repo = _parse_describe_repo_string(line)
                        repos.append((owner, repo))
                    except ValueError as e:
                        console.print(f"[yellow]Line {line_num}: {e}[/yellow]")
        return repos

    # Check if it's a wildcard pattern (user/*)
    if repos_input.endswith("/*"):
        owner = repos_input[:-2]
        console.print(f"[blue]Fetching all repositories for user/org: {owner}[/blue]")
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
            console.print(f"[green]Found {len(repos)} repositories for {owner}[/green]")
            return repos
        except Exception as e:
            console.print(f"[red]Error fetching repositories for {owner}: {e}[/red]")
            return []

    # Single repository
    try:
        owner, repo = _parse_describe_repo_string(repos_input)
        return [(owner, repo)]
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return []


def _parse_describe_repo_string(repo_string: str) -> tuple[str, str]:
    """Parse 'owner/repo' format into owner and repo name."""
    parts = repo_string.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format: {repo_string}. Expected 'owner/repo'")
    return parts[0], parts[1]


def _show_describe_summary(results: list[dict[str, Any]], dry_run: bool) -> None:
    """Display summary of description generation results."""
    console.print("\n[bold]SUMMARY[/bold]")

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
            "Success",
            str(status_counts.get("success", 0)),
            "Descriptions successfully updated",
        )
        table.add_row(
            "Skipped",
            str(status_counts.get("skipped", 0)),
            "Already has description (use --force to update)",
        )
    else:
        dry_run_count = status_counts.get("dry_run", 0)
        table.add_row(
            "Would Update", str(dry_run_count), "Descriptions would be added/updated"
        )

    table.add_row("Errors", str(status_counts.get("error", 0)), "Failed to process")
    table.add_row("Total", str(len(results)), "Repositories processed")

    console.print(table)

    # Show error details if any
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        console.print("\n[red]Error Details:[/red]")
        for error in errors:
            console.print(
                f"  [red]-[/red] {error['repo']}: {error.get('message', 'Unknown error')}"
            )


def _save_describe_results(
    results: list[dict[str, Any]], output_path: str, dry_run: bool, force: bool
) -> None:
    """Save results to JSON file."""
    import json
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

    console.print(f"\n[green]Results saved to: {output_file.absolute()}[/green]")


# Badge color mapping for common topic categories
BADGE_COLORS: dict[str, str] = {
    # Languages
    "python": "3776ab",
    "javascript": "f7df1e",
    "typescript": "3178c6",
    "rust": "000000",
    "go": "00add8",
    "java": "007396",
    "ruby": "cc342d",
    "html": "e34f26",
    "css": "1572b6",
    # Categories
    "edtech": "4caf50",
    "curtin": "f57c00",
    "presentation": "9c27b0",
    "exec-ed": "673ab7",
    "cybersecurity": "f44336",
    "book": "795548",
    "tool": "607d8b",
    "resume": "00bcd4",
    "research": "3f51b5",
    "website": "2196f3",
    # Frameworks/Tools
    "react": "61dafb",
    "docker": "2496ed",
    "flask": "000000",
    "django": "092e20",
    "fastapi": "009688",
    "electron": "47848f",
    "tauri": "ffc131",
    # AI/ML
    "ai": "ff6f00",
    "machine-learning": "ff6f00",
    "llm": "ff6f00",
    "openai": "412991",
    # Default
    "default": "blue",
}


def get_badge_color(topic: str) -> str:
    """Get the color for a topic badge."""
    return BADGE_COLORS.get(topic, BADGE_COLORS["default"])


def escape_shields_io(text: str) -> str:
    """Escape text for shields.io badge URLs.

    Shields.io has special character handling:
    - Hyphens must be doubled: - → --
    - Underscores must be doubled: _ → __
    - Spaces can be represented by _ or %20
    """
    # Order matters: escape hyphens and underscores
    escaped = text.replace("-", "--").replace("_", "__")
    return escaped


def generate_badge_markdown(
    topic: str, style: str = "flat-square", link: bool = True
) -> str:
    """Generate markdown for a single topic badge.

    Args:
        topic: The topic name
        style: Badge style (flat, flat-square, plastic, for-the-badge)
        link: Whether to link to GitHub topic search

    Returns:
        Markdown string for the badge
    """
    color = get_badge_color(topic)
    # Escape the topic for shields.io URL format
    escaped_topic = escape_shields_io(topic)
    badge_url = f"https://img.shields.io/badge/-{escaped_topic}-{color}?style={style}"

    if link:
        topic_url = f"https://github.com/topics/{topic}"
        return f"[![{topic}]({badge_url})]({topic_url})"
    else:
        return f"![{topic}]({badge_url})"


def generate_badges(
    repos_input: str = typer.Argument(
        help="Repository (owner/repo) or 'username/*' for all user repos"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    style: str = typer.Option(
        "flat-square",
        "--style",
        "-s",
        help="Badge style: flat, flat-square, plastic, for-the-badge",
    ),
    max_badges: int = typer.Option(
        10, "--max", "-n", help="Maximum number of badges to generate"
    ),
    no_link: bool = typer.Option(
        False, "--no-link", help="Don't link badges to GitHub topic search"
    ),
    apply: bool = typer.Option(
        False, "--apply", "-a", help="Apply badges to README files in repositories"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Save badge markdown to file"
    ),
    clipboard: bool = typer.Option(
        False, "--clipboard", "-c", help="Copy badge markdown to clipboard"
    ),
) -> None:
    """Generate topic badge markdown for repository READMEs.

    Creates shields.io badge markdown based on repository topics.
    Badges are colored by category and link to GitHub topic search.

    Examples:
        gh-toolkit repo badges user/repo
        gh-toolkit repo badges user/repo --style for-the-badge
        gh-toolkit repo badges user/repo --clipboard
        gh-toolkit repo badges user/repo --apply
        gh-toolkit repo badges "michael-borck/*" --output badges.md
    """
    try:
        # Get token
        github_token = resolve_token(token)
        if not github_token:
            console.print(
                "[red]GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]"
            )
            raise typer.Exit(1)

        client = GitHubClient(github_token)

        # Parse input
        if repos_input.endswith("/*"):
            # Multiple repos
            owner = repos_input[:-2]
            console.print(f"[blue]Fetching repositories for: {owner}[/blue]")
            # Check if owner is the authenticated user - if so, include private repos
            authenticated_user = client.get_authenticated_user()
            if authenticated_user and authenticated_user.lower() == owner.lower():
                console.print("[dim]Including private repositories[/dim]")
                repos = client.get_user_repos(
                    None, visibility="all", affiliation="owner"
                )
            else:
                repos = client.get_user_repos(owner)
            repo_list = [(owner, repo["name"]) for repo in repos]
        elif "/" in repos_input:
            # Single repo
            parts = repos_input.split("/")
            repo_list = [(parts[0], parts[1])]
        else:
            console.print("[red]Invalid input. Use owner/repo or owner/*[/red]")
            raise typer.Exit(1)

        all_badges_output: list[str] = []

        for owner, repo in repo_list:
            console.print(f"\n[blue]Processing: {owner}/{repo}[/blue]")

            try:
                # Get repo topics (returns list of strings)
                topics = client.get_repo_topics(owner, repo)

                if not topics:
                    console.print(
                        f"[yellow]  No topics found for {owner}/{repo}[/yellow]"
                    )
                    continue

                # Limit topics
                topics = topics[:max_badges]

                # Generate badges
                badges = [
                    generate_badge_markdown(topic, style, not no_link)
                    for topic in topics
                ]
                badge_line = " ".join(badges)

                # Display
                console.print(f"[green]  Topics: {', '.join(topics)}[/green]")

                # Apply to README if requested
                if apply:
                    _apply_badges_to_readme(client, owner, repo, badge_line)
                else:
                    console.print("\n[dim]Markdown:[/dim]")
                    # Use markup=False to avoid rich interpreting markdown brackets
                    console.print(badge_line, markup=False)

                # Collect for output
                all_badges_output.append(f"## {owner}/{repo}\n\n{badge_line}\n")

            except GitHubAPIError as e:
                console.print(f"[red]  Error: {e.message}[/red]")

        # Handle output options
        combined_output = "\n".join(all_badges_output)

        if output:
            output_path = Path(output)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(combined_output)
            console.print(f"\n[green]Saved to: {output_path.absolute()}[/green]")

        if clipboard:
            try:
                import subprocess

                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
                process.communicate(input=combined_output)
                console.print("\n[green]Copied to clipboard![/green]")
            except Exception as e:
                console.print(f"\n[yellow]Could not copy to clipboard: {e}[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


def _apply_badges_to_readme(
    client: GitHubClient, owner: str, repo: str, badge_line: str
) -> bool:
    """Apply badge markdown to a repository's README file.

    Inserts or updates a badge section after the main title in the README.
    The badge section is marked with HTML comments for easy identification.

    Args:
        client: GitHub API client
        owner: Repository owner
        repo: Repository name
        badge_line: Badge markdown to insert

    Returns:
        True if successful, False otherwise
    """
    import base64
    import re

    # Badge section markers
    badge_start = "<!-- BADGES:START -->"
    badge_end = "<!-- BADGES:END -->"

    # Try common README filenames
    readme_files = ["README.md", "readme.md", "README.MD", "Readme.md"]

    readme_data = None
    readme_path = None

    for filename in readme_files:
        readme_data = client.get_file_contents(owner, repo, filename)
        if readme_data:
            readme_path = filename
            break

    if not readme_data or not readme_path:
        console.print(f"[yellow]  No README found for {owner}/{repo}[/yellow]")
        return False

    # Decode current content
    try:
        current_content = base64.b64decode(readme_data["content"]).decode("utf-8")
        sha = readme_data["sha"]
    except Exception as e:
        console.print(f"[red]  Error decoding README: {e}[/red]")
        return False

    # Build the new badge section
    new_badge_section = f"{badge_start}\n{badge_line}\n{badge_end}"

    # Check if badge section already exists
    badge_pattern = re.compile(
        rf"{re.escape(badge_start)}.*?{re.escape(badge_end)}", re.DOTALL
    )

    if badge_pattern.search(current_content):
        # Replace existing badge section
        new_content = badge_pattern.sub(new_badge_section, current_content)
        action = "Updated"
    else:
        # Insert after the first heading (# Title)
        heading_match = re.match(r"^(#\s+[^\n]+\n)", current_content)
        if heading_match:
            # Insert after the heading
            heading_end = heading_match.end()
            new_content = (
                current_content[:heading_end]
                + "\n"
                + new_badge_section
                + "\n"
                + current_content[heading_end:]
            )
        else:
            # No heading found, insert at the beginning
            new_content = new_badge_section + "\n\n" + current_content
        action = "Added"

    # Check if content actually changed
    if new_content == current_content:
        console.print("[dim]  README already up to date[/dim]")
        return True

    # Update the file
    result = client.update_file_contents(
        owner=owner,
        repo=repo,
        path=readme_path,
        content=new_content,
        message="Update README badges\n\nAuto-generated by gh-toolkit",
        sha=sha,
    )

    if result:
        console.print(f"[green]  ✓ {action} badges in {readme_path}[/green]")
        return True
    else:
        console.print(f"[red]  ✗ Failed to update {readme_path}[/red]")
        return False


def readme_repos(
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
        help="Anthropic API key for LLM generation (or set ANTHROPIC_API_KEY env var)",
    ),
    model: str = typer.Option(
        DEFAULT_LLM_MODEL,
        "--model",
        "-m",
        help="Anthropic model to use (e.g., claude-sonnet-4-6)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without updating repositories",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Update READMEs even if they pass quality checks",
    ),
    min_quality: float = typer.Option(
        0.5,
        "--min-quality",
        "-q",
        help="Quality threshold (0-1). READMEs below this will be updated (default: 0.5)",
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
    update_tags: bool = typer.Option(
        False,
        "--update-tags",
        help="After updating READMEs, run tag update on modified repos",
    ),
) -> None:
    """Generate or update README files for GitHub repositories.

    Analyzes repositories and generates professional README files using LLM.
    Can create missing READMEs or update low-quality/placeholder ones.

    Quality is assessed based on:
    - Has proper title and description
    - Has installation and usage sections
    - Contains code examples
    - Reasonable length (not just a placeholder)
    - Multiple structured sections

    Examples:
        gh-toolkit repo readme user/repo --dry-run
        gh-toolkit repo readme "user/*" --min-quality 0.6
        gh-toolkit repo readme repos.txt --force --model claude-sonnet-4-6
        gh-toolkit repo readme "user/*" --update-tags
    """
    from gh_toolkit.core.repo_readme_generator import RepoReadmeGenerator

    try:
        # Get tokens
        github_token = resolve_token(token)
        if not github_token:
            console.print(
                "[red]GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]"
            )
            raise typer.Exit(1)

        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            console.print(
                "[yellow]Warning: No Anthropic API key. Will use template-based generation.[/yellow]"
            )

        client = GitHubClient(github_token)
        generator = RepoReadmeGenerator(client, anthropic_api_key, rate_limit, model)

        # Parse repository input
        repo_list = _parse_readme_repos_input(repos_input, client)

        if not repo_list:
            console.print("[red]No repositories found to process[/red]")
            raise typer.Exit(1)

        console.print(f"\n[blue]Found {len(repo_list)} repositories to process[/blue]")
        console.print(f"[blue]Using model: {model}[/blue]")
        console.print(f"[blue]Quality threshold: {min_quality:.0%}[/blue]")

        if dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        if force:
            console.print("[yellow]FORCE MODE - Will update all READMEs[/yellow]")

        # Process repositories
        results = generator.process_multiple_repositories(
            repo_list, dry_run, force, min_quality
        )

        # Show summary
        _show_readme_summary(results, dry_run)

        # Get list of updated repos for tag update
        updated_repos = [
            (r["owner"], r["repo"])
            for r in results
            if r["status"] in ("updated", "dry_run")
        ]

        # Save results if requested
        if output:
            _save_readme_results(results, output)

        # Update tags for modified repos if requested
        if update_tags and updated_repos and not dry_run:
            console.print(
                f"\n[blue]Updating tags for {len(updated_repos)} modified repositories...[/blue]"
            )
            _update_tags_for_repos(
                updated_repos, client, anthropic_api_key, model, rate_limit
            )

        # Return the list of updated repos (useful for chaining)
        return updated_repos  # type: ignore[return-value]

    except KeyboardInterrupt as e:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _parse_readme_repos_input(
    repos_input: str, client: GitHubClient
) -> list[tuple[str, str]]:
    """Parse repository input and return list of (owner, repo) tuples."""
    repos: list[tuple[str, str]] = []

    # Check if it's a file
    if Path(repos_input).exists():
        console.print(f"[blue]Loading repositories from file: {repos_input}[/blue]")
        with open(repos_input, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        parts = line.split("/")
                        if len(parts) == 2:
                            repos.append((parts[0], parts[1]))
                        else:
                            console.print(
                                f"[yellow]Line {line_num}: Invalid format[/yellow]"
                            )
                    except Exception as e:
                        console.print(f"[yellow]Line {line_num}: {e}[/yellow]")
        return repos

    # Check if it's a wildcard pattern (user/*)
    if repos_input.endswith("/*"):
        owner = repos_input[:-2]
        console.print(f"[blue]Fetching all repositories for user/org: {owner}[/blue]")
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
            console.print(f"[green]Found {len(repos)} repositories for {owner}[/green]")
            return repos
        except Exception as e:
            console.print(f"[red]Error fetching repositories for {owner}: {e}[/red]")
            return []

    # Single repository
    if "/" in repos_input:
        parts = repos_input.split("/")
        if len(parts) == 2:
            return [(parts[0], parts[1])]

    console.print(f"[red]Invalid input format: {repos_input}[/red]")
    return []


def _show_readme_summary(results: list[dict[str, Any]], dry_run: bool) -> None:
    """Display summary of README processing results."""
    updated = sum(1 for r in results if r["status"] == "updated")
    would_update = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] in ("failed", "error"))

    console.print("\n[bold]SUMMARY[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status")
    table.add_column("Count")
    table.add_column("Description")

    if dry_run:
        table.add_row(
            "Would Update", str(would_update), "READMEs that would be updated"
        )
    else:
        table.add_row("Updated", str(updated), "READMEs successfully updated")

    table.add_row("Skipped", str(skipped), "READMEs already good quality")
    table.add_row("Failed", str(failed), "Failed to process")
    table.add_row("Total", str(len(results)), "Repositories processed")

    console.print(table)

    # Show failed repos
    failed_repos = [r for r in results if r["status"] in ("failed", "error")]
    if failed_repos:
        console.print("\n[red]Failed repositories:[/red]")
        for r in failed_repos:
            error = r.get("error", "Unknown error")
            console.print(f"  - {r['owner']}/{r['repo']}: {error}")


def _save_readme_results(results: list[dict[str, Any]], output_path: str) -> None:
    """Save README processing results to JSON file."""
    import json

    # Remove generated content from saved results (too large)
    save_results: list[dict[str, Any]] = []
    for r in results:
        save_r = {k: v for k, v in r.items() if k != "generated_content"}
        save_results.append(save_r)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(save_results, f, indent=2)

    console.print(f"\n[green]Results saved to {output_path}[/green]")


def _update_tags_for_repos(
    repos: list[tuple[str, str]],
    client: GitHubClient,
    anthropic_key: str | None,
    model: str,
    rate_limit: float,
) -> None:
    """Update tags for a list of repositories."""
    from gh_toolkit.core.topic_tagger import TopicTagger

    tagger = TopicTagger(client, anthropic_key, rate_limit, model)

    console.print("")
    for i, (owner, repo) in enumerate(repos, 1):
        console.print(f"[blue]Tagging {i}/{len(repos)}: {owner}/{repo}[/blue]")
        try:
            result = tagger.process_repository(owner, repo, dry_run=False, force=True)
            if result.get("status") == "updated":
                topics = result.get("new_topics", [])
                console.print(
                    f"[green]  ✓ Updated topics: {', '.join(topics[:5])}[/green]"
                )
            elif result.get("status") == "skipped":
                console.print("[dim]  Skipped (already has topics)[/dim]")
            else:
                console.print(f"[yellow]  {result.get('status', 'unknown')}[/yellow]")
        except Exception as e:
            console.print(f"[red]  ✗ Failed: {e}[/red]")


def license_repos(
    repos_input: str | None = typer.Argument(
        None,
        help="Repository (owner/repo), file with repo list, or 'username/*' for all user repos",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (prefer GITHUB_TOKEN env var; CLI args are visible in shell history and process lists)",
    ),
    license_type: str = typer.Option(
        "mit",
        "--license",
        "-l",
        help="License type (mit, apache-2.0, gpl-3.0, bsd-3-clause, unlicense, etc.)",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Copyright holder name (defaults to repository owner)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without adding licenses",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace existing license files",
    ),
    list_licenses: bool = typer.Option(
        False,
        "--list",
        help="List available license types and exit",
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
    """Add license files to GitHub repositories.

    Adds a LICENSE file to repositories that don't have one. Supports all
    standard licenses available on GitHub including MIT, Apache 2.0, GPL, etc.

    Common license types:
        mit          - MIT License (simple, permissive) [DEFAULT]
        apache-2.0   - Apache 2.0 (permissive with patent protection)
        gpl-3.0      - GPL 3.0 (copyleft, requires source disclosure)
        bsd-3-clause - BSD 3-Clause (permissive with attribution)
        unlicense    - Public domain dedication

    Examples:
        gh-toolkit repo license user/repo --dry-run
        gh-toolkit repo license "user/*" --license mit --name "John Doe"
        gh-toolkit repo license repos.txt --license apache-2.0 --force
        gh-toolkit repo license --list
    """
    from gh_toolkit.core.license_manager import COMMON_LICENSES, LicenseManager

    # Handle --list option
    if list_licenses:
        console.print("\n[bold]Available Licenses:[/bold]\n")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Key")
        table.add_column("Description")

        for key, desc in COMMON_LICENSES.items():
            if key == "mit":
                table.add_row(f"[green]{key}[/green]", f"{desc} [dim](default)[/dim]")
            else:
                table.add_row(key, desc)

        console.print(table)
        console.print(
            "\n[dim]Use any GitHub license key (see: https://choosealicense.com)[/dim]"
        )
        return

    # Require repos_input if not listing
    if not repos_input:
        console.print(
            "[red]Error: REPOS_INPUT is required (use --list to see available licenses)[/red]"
        )
        raise typer.Exit(1)

    try:
        # Get token
        github_token = resolve_token(token)
        if not github_token:
            console.print(
                "[red]GitHub token required. Set GITHUB_TOKEN env var or use --token[/red]"
            )
            raise typer.Exit(1)

        client = GitHubClient(github_token)
        manager = LicenseManager(client, rate_limit)

        # Parse repository input
        repo_list = _parse_license_repos_input(repos_input, client)

        if not repo_list:
            console.print("[red]No repositories found to process[/red]")
            raise typer.Exit(1)

        console.print(f"\n[blue]Found {len(repo_list)} repositories to process[/blue]")
        console.print(f"[blue]License: {license_type.upper()}[/blue]")
        if name:
            console.print(f"[blue]Copyright holder: {name}[/blue]")

        if dry_run:
            console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        if force:
            console.print(
                "[yellow]FORCE MODE - Will replace existing licenses[/yellow]"
            )

        # Process repositories
        results = manager.process_multiple_repositories(
            repo_list, license_type, name, dry_run, force
        )

        # Show summary
        _show_license_summary(results, dry_run)

        # Save results if requested
        if output:
            _save_license_results(results, output)

    except KeyboardInterrupt as e:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _parse_license_repos_input(
    repos_input: str, client: GitHubClient
) -> list[tuple[str, str]]:
    """Parse repository input and return list of (owner, repo) tuples."""
    repos: list[tuple[str, str]] = []

    # Check if it's a file
    if Path(repos_input).exists():
        console.print(f"[blue]Loading repositories from file: {repos_input}[/blue]")
        with open(repos_input, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        parts = line.split("/")
                        if len(parts) == 2:
                            repos.append((parts[0], parts[1]))
                        else:
                            console.print(
                                f"[yellow]Line {line_num}: Invalid format[/yellow]"
                            )
                    except Exception as e:
                        console.print(f"[yellow]Line {line_num}: {e}[/yellow]")
        return repos

    # Check if it's a wildcard pattern (user/*)
    if repos_input.endswith("/*"):
        owner = repos_input[:-2]
        console.print(f"[blue]Fetching all repositories for user/org: {owner}[/blue]")
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
            console.print(f"[green]Found {len(repos)} repositories for {owner}[/green]")
            return repos
        except Exception as e:
            console.print(f"[red]Error fetching repositories for {owner}: {e}[/red]")
            return []

    # Single repository
    if "/" in repos_input:
        parts = repos_input.split("/")
        if len(parts) == 2:
            return [(parts[0], parts[1])]

    console.print(f"[red]Invalid input format: {repos_input}[/red]")
    return []


def _show_license_summary(results: list[dict[str, Any]], dry_run: bool) -> None:
    """Display summary of license processing results."""
    created = sum(1 for r in results if r["status"] == "created")
    updated = sum(1 for r in results if r["status"] == "updated")
    would_add = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "error")

    console.print("\n[bold]SUMMARY[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status")
    table.add_column("Count")
    table.add_column("Description")

    if dry_run:
        table.add_row("Would Add", str(would_add), "Licenses that would be added")
    else:
        table.add_row("Created", str(created), "New licenses added")
        table.add_row("Updated", str(updated), "Existing licenses replaced")

    table.add_row("Skipped", str(skipped), "Already has license")
    table.add_row("Failed", str(failed), "Failed to process")
    table.add_row("Total", str(len(results)), "Repositories processed")

    console.print(table)

    # Show failed repos
    failed_repos = [r for r in results if r["status"] == "error"]
    if failed_repos:
        console.print("\n[red]Failed repositories:[/red]")
        for r in failed_repos:
            reason = r.get("reason", "Unknown error")
            console.print(f"  - {r['owner']}/{r['repo']}: {reason}")


def _save_license_results(results: list[dict[str, Any]], output_path: str) -> None:
    """Save license processing results to JSON file."""
    import json

    # Remove content preview from saved results
    save_results: list[dict[str, Any]] = []
    for r in results:
        save_r = {k: v for k, v in r.items() if k != "content_preview"}
        save_results.append(save_r)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(save_results, f, indent=2)

    console.print(f"\n[green]Results saved to {output_path}[/green]")
