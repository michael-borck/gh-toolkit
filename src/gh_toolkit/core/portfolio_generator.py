"""Portfolio generation for cross-organization repository aggregation."""

from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.readme_generator import OrgReadmeGenerator

console = Console()


class PortfolioGenerator:
    """Generate cross-organization portfolio index with README and HTML output."""

    def __init__(
        self, github_client: GitHubClient, anthropic_api_key: str | None = None
    ):
        """Initialize with GitHub client and optional Anthropic API key.

        Args:
            github_client: GitHub API client
            anthropic_api_key: Anthropic API key for LLM-powered descriptions
        """
        self.client = github_client
        self.anthropic_api_key = anthropic_api_key
        self._readme_generator = OrgReadmeGenerator(github_client, anthropic_api_key)

    def discover_organizations(self) -> list[dict[str, Any]]:
        """Discover organizations the authenticated user belongs to.

        Returns:
            List of organization data
        """
        console.print("[blue]Discovering organizations...[/blue]")
        orgs = self.client.get_user_organizations()
        console.print(f"[green]Found {len(orgs)} organizations[/green]")
        return orgs

    def aggregate_repos(
        self,
        org_names: list[str],
        exclude_forks: bool = True,
        include_private: bool = False,
        min_stars: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch and aggregate repositories from multiple organizations.

        Args:
            org_names: List of organization names
            exclude_forks: Whether to exclude forked repositories
            include_private: Whether to include private repositories
            min_stars: Minimum stars required

        Returns:
            List of repositories with source organization tracking
        """
        all_repos: list[dict[str, Any]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching repositories...", total=len(org_names))

            for org_name in org_names:
                progress.update(task, description=f"Fetching repos from {org_name}...")

                try:
                    repos = self.client.get_org_repos(org_name)

                    for repo in repos:
                        # Apply filters
                        if exclude_forks and repo.get("fork", False):
                            continue
                        if not include_private and repo.get("private", False):
                            continue
                        if repo.get("stargazers_count", 0) < min_stars:
                            continue
                        if repo.get("archived", False):
                            continue

                        # Add source organization tracking
                        repo["source_org"] = org_name

                        # Infer category
                        repo["category"] = self._infer_category(repo)

                        all_repos.append(repo)

                except GitHubAPIError as e:
                    console.print(
                        f"[yellow]Warning: Failed to fetch repos from {org_name}: {e.message}[/yellow]"
                    )

                progress.advance(task)

        # Sort by stars
        all_repos.sort(key=lambda x: x.get("stargazers_count", 0), reverse=True)

        console.print(
            f"[green]Aggregated {len(all_repos)} repositories from {len(org_names)} organizations[/green]"
        )
        return all_repos

    def _infer_category(self, repo: dict[str, Any]) -> str:
        """Infer a category for a repository."""
        return self._readme_generator.infer_category(repo)

    def audit_repos(self, repos: list[dict[str, Any]]) -> dict[str, Any]:
        """Audit repositories for missing descriptions, README, topics, or license.

        Args:
            repos: List of repository data

        Returns:
            Audit report dictionary
        """
        console.print("[blue]Auditing repositories...[/blue]")

        issues: list[dict[str, Any]] = []
        issue_counts: dict[str, int] = {
            "missing_description": 0,
            "missing_topics": 0,
            "missing_license": 0,
        }

        for repo in repos:
            repo_name = repo.get("full_name", repo.get("name", "Unknown"))
            source_org = repo.get("source_org", "Unknown")

            # Check for missing description
            if not repo.get("description"):
                issues.append(
                    {
                        "repo": repo_name,
                        "org": source_org,
                        "issue_type": "missing_description",
                        "severity": "error",
                        "suggestion": "Add a clear, concise description explaining what this repository does",
                    }
                )
                issue_counts["missing_description"] += 1

            # Check for missing topics
            if not repo.get("topics"):
                issues.append(
                    {
                        "repo": repo_name,
                        "org": source_org,
                        "issue_type": "missing_topics",
                        "severity": "warning",
                        "suggestion": "Add relevant topic tags to improve discoverability",
                    }
                )
                issue_counts["missing_topics"] += 1

            # Check for missing license
            if not repo.get("license"):
                issues.append(
                    {
                        "repo": repo_name,
                        "org": source_org,
                        "issue_type": "missing_license",
                        "severity": "warning",
                        "suggestion": "Add a license to clarify usage terms",
                    }
                )
                issue_counts["missing_license"] += 1

        repos_with_issues = len({issue["repo"] for issue in issues})

        report = {
            "total_repos": len(repos),
            "repos_with_issues": repos_with_issues,
            "issues": issues,
            "summary": issue_counts,
        }

        console.print(
            f"[yellow]Found {len(issues)} issues in {repos_with_issues} repositories[/yellow]"
        )
        return report

    def generate_readme(
        self,
        repos: list[dict[str, Any]],
        org_infos: dict[str, dict[str, Any]],
        group_by: str = "org",
        title: str | None = None,
    ) -> str:
        """Generate portfolio README markdown.

        Args:
            repos: List of repository data
            org_infos: Dictionary mapping org names to org info
            group_by: Grouping method (org, category, language)
            title: Custom title for the portfolio

        Returns:
            Generated README markdown content
        """
        lines: list[str] = []

        # Get user info for title
        try:
            user_info = self.client.get_user_info()
            username = user_info.get("name") or user_info.get("login", "")
        except GitHubAPIError:
            username = "My"

        portfolio_title = title or f"{username}'s Project Portfolio"

        # Header
        lines.append(f"# {portfolio_title}")
        lines.append("")

        # Organizations summary
        if org_infos:
            lines.append("## Organizations")
            lines.append("")
            for org_name, org_info in org_infos.items():
                org_desc = org_info.get("description") or "No description"
                org_url = f"https://github.com/{org_name}"
                lines.append(f"- [{org_name}]({org_url}) - {org_desc}")
            lines.append("")

        # Group repositories
        grouped_repos = self._group_repos(repos, group_by)

        # Projects section
        lines.append("## Projects")
        lines.append("")

        for group_name, group_repos in grouped_repos.items():
            lines.append(f"### {group_name}")
            lines.append("")
            lines.append("| Project | Description | Category | Stars |")
            lines.append("|---------|-------------|----------|-------|")

            for repo in group_repos:
                name = repo.get("name", "")
                desc = (repo.get("description") or "No description").replace(
                    "|", "\\|"
                )[:50]
                if len(repo.get("description") or "") > 50:
                    desc += "..."
                category = repo.get("category", "Other")
                stars = repo.get("stargazers_count", 0)
                url = repo.get("html_url", "")

                lines.append(f"| [{name}]({url}) | {desc} | {category} | {stars} |")

            lines.append("")

        # Summary statistics
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Projects | {len(repos)} |")
        lines.append(f"| Organizations | {len(org_infos)} |")

        total_stars = sum(r.get("stargazers_count", 0) for r in repos)
        lines.append(f"| Total Stars | {total_stars} |")

        # Language count
        languages: set[str] = set()
        for repo in repos:
            if repo.get("language"):
                languages.add(repo["language"])
        lines.append(f"| Languages | {len(languages)} |")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            f"*Generated with [gh-toolkit](https://github.com/michael-borck/gh-toolkit) on {datetime.now().strftime('%Y-%m-%d')}*"
        )

        return "\n".join(lines)

    def _group_repos(
        self, repos: list[dict[str, Any]], group_by: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Group repositories by the specified criteria.

        Args:
            repos: List of repository data
            group_by: Grouping method (org, category, language)

        Returns:
            Dictionary of grouped repositories
        """
        grouped: dict[str, list[dict[str, Any]]] = {}

        for repo in repos:
            if group_by == "org":
                key = repo.get("source_org", "Unknown")
            elif group_by == "language":
                key = repo.get("language") or "Other"
            else:  # category
                key = repo.get("category", "Other")

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(repo)

        return grouped

    def generate_html(
        self,
        repos: list[dict[str, Any]],
        org_infos: dict[str, dict[str, Any]],
        theme: str = "portfolio",
        title: str | None = None,
    ) -> str:
        """Generate portfolio HTML using existing SiteGenerator.

        Args:
            repos: List of repository data
            org_infos: Dictionary mapping org names to org info
            theme: HTML theme (educational, resume, research, portfolio)
            title: Custom title

        Returns:
            Generated HTML content
        """
        from gh_toolkit.core.site_generator import SiteGenerator

        # Transform repos to match SiteGenerator expected format
        transformed_repos: list[dict[str, Any]] = []
        for repo in repos:
            transformed_repos.append(
                {
                    "name": repo.get("name", ""),
                    "full_name": repo.get("full_name", ""),
                    "description": repo.get("description"),
                    "url": repo.get("html_url", ""),
                    "homepage": repo.get("homepage"),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "watchers": repo.get("watchers_count", 0),
                    "language": repo.get("language"),
                    "languages": [repo.get("language")] if repo.get("language") else [],
                    "topics": repo.get("topics", []),
                    "license": repo["license"].get("spdx_id")
                    if repo.get("license")
                    else None,
                    "private": repo.get("private", False),
                    "archived": repo.get("archived", False),
                    "fork": repo.get("fork", False),
                    "category": repo.get("category", "Other"),
                    "category_confidence": 0.8,
                    "category_reason": "Inferred from repository characteristics",
                    "has_pages": repo.get("has_pages", False),
                    "pages_url": None,
                    "download_links": {},
                    "latest_version": None,
                }
            )

        # Use SiteGenerator
        generator = SiteGenerator()

        # Get user info for title
        if not title:
            try:
                user_info = self.client.get_user_info()
                username = user_info.get("name") or user_info.get("login", "")
                title = f"{username}'s Project Portfolio"
            except GitHubAPIError:
                title = "Project Portfolio"

        # Generate HTML content directly using SiteGenerator internals
        # (reusing existing HTML generation logic as per design)
        theme_config = generator.themes.get(theme, generator.themes["portfolio"])
        categories = generator._group_by_category(transformed_repos, theme_config)  # type: ignore[reportPrivateUsage]

        html = generator._generate_html(  # type: ignore[reportPrivateUsage]
            categories=categories,
            theme_config=theme_config,
            metadata={},
            title=title,
            description=f"A portfolio of {len(repos)} projects across {len(org_infos)} organizations",
        )

        return html

    def save_readme(self, content: str, output_path: str) -> None:
        """Save README content to file.

        Args:
            content: README markdown content
            output_path: Output file path
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]README saved to {path.absolute()}[/green]")

    def save_html(self, content: str, output_path: str) -> None:
        """Save HTML content to file.

        Args:
            content: HTML content
            output_path: Output file path
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]HTML portfolio saved to {path.absolute()}[/green]")

    def print_audit_report(self, report: dict[str, Any]) -> None:
        """Print a formatted audit report to console.

        Args:
            report: Audit report dictionary
        """
        console.print("\n[bold]Portfolio Audit Report[/bold]")
        console.print("=" * 50)
        console.print(f"Total repositories: {report['total_repos']}")
        console.print(f"Repositories with issues: {report['repos_with_issues']}")
        console.print("")

        # Summary
        console.print("[bold]Issue Summary:[/bold]")
        for issue_type, count in report["summary"].items():
            if count > 0:
                icon = "[red]!" if "description" in issue_type else "[yellow]*"
                console.print(
                    f"  {icon}[/] {issue_type.replace('_', ' ').title()}: {count}"
                )
        console.print("")

        # Details by severity
        errors = [i for i in report["issues"] if i["severity"] == "error"]
        warnings = [i for i in report["issues"] if i["severity"] == "warning"]

        if errors:
            console.print("[bold red]Errors (should fix):[/bold red]")
            for issue in errors[:10]:  # Limit output
                console.print(
                    f"  [red]![/red] {issue['repo']}: {issue['issue_type'].replace('_', ' ')}"
                )
            if len(errors) > 10:
                console.print(f"  ... and {len(errors) - 10} more errors")
            console.print("")

        if warnings:
            console.print("[bold yellow]Warnings (recommended fixes):[/bold yellow]")
            for issue in warnings[:10]:  # Limit output
                console.print(
                    f"  [yellow]*[/yellow] {issue['repo']}: {issue['issue_type'].replace('_', ' ')}"
                )
            if len(warnings) > 10:
                console.print(f"  ... and {len(warnings) - 10} more warnings")

        console.print("")
