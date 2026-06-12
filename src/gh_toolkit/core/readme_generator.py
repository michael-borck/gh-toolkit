"""README generation for GitHub organizations."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL

console = Console()


class OrgReadmeGenerator:
    """Generate profile README for a GitHub organization."""

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
        self._anthropic_client = None

        if anthropic_api_key:
            try:
                from anthropic import Anthropic

                self._anthropic_client = Anthropic(api_key=anthropic_api_key)
            except ImportError:
                console.print(
                    "[yellow]Anthropic package not available. Install with: pip install anthropic[/yellow]"
                )

    def fetch_org_repos(
        self,
        org_name: str,
        exclude_forks: bool = True,
        max_repos: int | None = None,
        min_stars: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch repositories for an organization with filtering.

        Args:
            org_name: Organization name
            exclude_forks: Whether to exclude forked repositories
            max_repos: Maximum number of repositories to include
            min_stars: Minimum stars required to include

        Returns:
            List of filtered repository data
        """
        repos = self.client.get_org_repos(org_name)

        # Apply filters
        filtered_repos: list[dict[str, Any]] = []
        for repo in repos:
            if exclude_forks and repo.get("fork", False):
                continue
            if repo.get("stargazers_count", 0) < min_stars:
                continue
            if repo.get("archived", False):
                continue
            filtered_repos.append(repo)

        # Sort by stars
        filtered_repos.sort(key=lambda x: x.get("stargazers_count", 0), reverse=True)

        # Apply max_repos limit
        if max_repos:
            filtered_repos = filtered_repos[:max_repos]

        return filtered_repos

    def categorize_repos(
        self, repos: list[dict[str, Any]], group_by: str = "category"
    ) -> dict[str, list[dict[str, Any]]]:
        """Group repositories by category, language, or topic.

        Args:
            repos: List of repository data
            group_by: Grouping method (category, language, topic)

        Returns:
            Dictionary of grouped repositories
        """
        grouped: dict[str, list[dict[str, Any]]] = {}

        for repo in repos:
            if group_by == "language":
                key = repo.get("language") or "Other"
            elif group_by == "topic":
                topics = repo.get("topics", [])
                key = topics[0] if topics else "Uncategorized"
            else:  # category
                key = self.infer_category(repo)

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(repo)

        return grouped

    def infer_category(self, repo: dict[str, Any]) -> str:
        """Infer a category for a repository based on its characteristics.

        Args:
            repo: Repository data

        Returns:
            Category string
        """
        name_lower = repo.get("name", "").lower()
        desc_lower = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", [])]
        language = (repo.get("language") or "").lower()

        # Check topics first for explicit categories
        topic_categories = {
            "library": "Libraries",
            "cli": "CLI Tools",
            "web-app": "Web Applications",
            "api": "APIs",
            "tutorial": "Learning Resources",
            "education": "Learning Resources",
            "documentation": "Documentation",
            "template": "Templates",
        }
        for topic, category in topic_categories.items():
            if topic in topics:
                return category

        # Check name and description patterns
        if any(x in name_lower for x in ["template", "boilerplate", "starter"]):
            return "Templates"
        if any(x in name_lower for x in ["api", "service"]):
            return "APIs"
        if any(x in desc_lower for x in ["cli", "command-line", "terminal"]):
            return "CLI Tools"
        if any(x in desc_lower for x in ["library", "package", "module"]):
            return "Libraries"
        if any(x in desc_lower for x in ["web app", "webapp", "website"]):
            return "Web Applications"
        if any(x in desc_lower for x in ["tutorial", "learn", "course"]):
            return "Learning Resources"

        # Fallback to language-based categories
        language_categories = {
            "python": "Python Projects",
            "javascript": "JavaScript Projects",
            "typescript": "TypeScript Projects",
            "rust": "Rust Projects",
            "go": "Go Projects",
        }
        return language_categories.get(language, "Other Projects")

    def generate_org_description(
        self, org_info: dict[str, Any], repos: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate organization description using LLM or fallback.

        Args:
            org_info: Organization information
            repos: List of organization repositories

        Returns:
            Dictionary with title, tagline, focus_areas, and mission
        """
        if self._anthropic_client:
            try:
                return self._generate_description_with_llm(org_info, repos)
            except Exception as e:
                console.print(f"[yellow]LLM description failed: {e}[/yellow]")

        return self._generate_fallback_description(org_info, repos)

    def _generate_description_with_llm(
        self, org_info: dict[str, Any], repos: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate description using Claude."""
        if not self._anthropic_client:
            return self._generate_fallback_description(org_info, repos)

        # Prepare repository summary
        repo_summary: list[str] = []
        for repo in repos[:20]:  # Limit to top 20 repos
            repo_summary.append(
                f"- {repo.get('name')}: {repo.get('description') or 'No description'} "
                f"[{repo.get('language') or 'Unknown'}] ({repo.get('stargazers_count', 0)} stars)"
            )

        context = f"""
Organization: {org_info.get("login", "")}
Description: {org_info.get("description") or "No description"}
Blog: {org_info.get("blog") or "None"}
Location: {org_info.get("location") or "Unknown"}
Public Repositories: {org_info.get("public_repos", 0)}

Top Repositories:
{chr(10).join(repo_summary)}
"""

        prompt = f"""Based on the following GitHub organization information, generate a compelling profile description.

{context}

Respond with valid JSON containing:
- "title": A short, catchy title for the org (2-5 words)
- "tagline": A one-sentence description of what the org does
- "focus_areas": Array of 3-5 key focus areas/technologies
- "mission": A 1-2 sentence mission statement

JSON only, no markdown code blocks:"""

        response = self._anthropic_client.messages.create(
            model=DEFAULT_LLM_MODEL,
            max_tokens=500,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )

        response_content = response.content[0] if response.content else None
        response_text = getattr(response_content, "text", "").strip()

        # Parse JSON response
        try:
            result = json.loads(response_text)
            return {
                "title": result.get("title", org_info.get("login", "")),
                "tagline": result.get("tagline", org_info.get("description", "")),
                "focus_areas": result.get("focus_areas", []),
                "mission": result.get("mission", ""),
            }
        except json.JSONDecodeError:
            return self._generate_fallback_description(org_info, repos)

    def _generate_fallback_description(
        self, org_info: dict[str, Any], repos: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate description using rule-based approach."""
        org_name = org_info.get("login", "Organization")
        org_desc = org_info.get("description") or ""

        # Collect languages and topics
        languages: dict[str, int] = {}
        topics: dict[str, int] = {}

        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            for topic in repo.get("topics", []):
                topics[topic] = topics.get(topic, 0) + 1

        # Get top languages and topics
        top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
        top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]

        focus_areas = [lang for lang, _ in top_languages]
        if top_topics:
            focus_areas.extend(
                [topic.replace("-", " ").title() for topic, _ in top_topics[:3]]
            )

        return {
            "title": org_name,
            "tagline": org_desc or f"A collection of {len(repos)} repositories",
            "focus_areas": focus_areas[:5],
            "mission": f"Building and maintaining open source projects focused on {', '.join(focus_areas[:3])}."
            if focus_areas
            else "Building and maintaining open source projects.",
        }

    def generate_readme(
        self,
        org_name: str,
        template: str = "default",
        group_by: str = "category",
        include_stats: bool = True,
        exclude_forks: bool = True,
        max_repos: int | None = None,
        min_stars: int = 0,
    ) -> str:
        """Generate a complete README for an organization.

        Args:
            org_name: Organization name
            template: Template style (default, minimal, detailed)
            group_by: How to group repos (category, language, topic)
            include_stats: Whether to include statistics
            exclude_forks: Whether to exclude forked repositories
            max_repos: Maximum repositories to include
            min_stars: Minimum stars required

        Returns:
            Generated README markdown content
        """
        console.print(f"[blue]Fetching organization info for {org_name}...[/blue]")
        try:
            org_info = self.client.get_org_info(org_name)
        except GitHubAPIError as e:
            raise ValueError(f"Failed to get organization info: {e.message}") from e

        console.print(f"[blue]Fetching repositories for {org_name}...[/blue]")
        repos = self.fetch_org_repos(
            org_name,
            exclude_forks=exclude_forks,
            max_repos=max_repos,
            min_stars=min_stars,
        )

        if not repos:
            raise ValueError(f"No repositories found for organization {org_name}")

        console.print(f"[green]Found {len(repos)} repositories[/green]")

        # Generate description
        console.print("[blue]Generating organization description...[/blue]")
        description = self.generate_org_description(org_info, repos)

        # Group repositories
        grouped_repos = self.categorize_repos(repos, group_by)

        # Generate markdown based on template
        if template == "minimal":
            return self._generate_minimal_readme(
                org_info, description, grouped_repos, include_stats
            )
        elif template == "detailed":
            return self._generate_detailed_readme(
                org_info, description, grouped_repos, repos, include_stats
            )
        else:
            return self._generate_default_readme(
                org_info, description, grouped_repos, include_stats
            )

    def _generate_default_readme(
        self,
        org_info: dict[str, Any],
        description: dict[str, Any],
        grouped_repos: dict[str, list[dict[str, Any]]],
        include_stats: bool,
    ) -> str:
        """Generate default template README."""
        lines: list[str] = []

        # Header
        lines.append(f"# {description['title']}")
        lines.append("")
        lines.append(description["tagline"])
        lines.append("")

        if description.get("mission"):
            lines.append(description["mission"])
            lines.append("")

        # Focus areas
        if description.get("focus_areas"):
            lines.append("## Focus Areas")
            for area in description["focus_areas"]:
                lines.append(f"- {area}")
            lines.append("")

        # Repositories
        lines.append("## Repositories")
        lines.append("")

        for category, repos in grouped_repos.items():
            lines.append(f"### {category}")
            lines.append("")
            lines.append("| Repository | Description | Language | Stars |")
            lines.append("|------------|-------------|----------|-------|")

            for repo in repos:
                name = repo.get("name", "")
                desc = (repo.get("description") or "").replace("|", "\\|")[:60]
                if len(repo.get("description") or "") > 60:
                    desc += "..."
                lang = repo.get("language") or "-"
                stars = repo.get("stargazers_count", 0)
                url = repo.get("html_url", "")

                lines.append(f"| [{name}]({url}) | {desc} | {lang} | {stars} |")

            lines.append("")

        # Statistics
        if include_stats:
            lines.append("## Stats")
            total_stars = sum(
                r.get("stargazers_count", 0)
                for repos in grouped_repos.values()
                for r in repos
            )
            total_repos = sum(len(repos) for repos in grouped_repos.values())

            # Collect all languages
            all_languages: set[str] = set()
            for repos in grouped_repos.values():
                for repo in repos:
                    if repo.get("language"):
                        all_languages.add(repo["language"])

            lines.append(f"- **Repositories**: {total_repos}")
            lines.append(f"- **Total Stars**: {total_stars}")
            lines.append(f"- **Languages**: {', '.join(sorted(all_languages)[:10])}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            f"*Generated with [gh-toolkit](https://github.com/michael-borck/gh-toolkit) on {datetime.now().strftime('%Y-%m-%d')}*"
        )

        return "\n".join(lines)

    def _generate_minimal_readme(
        self,
        org_info: dict[str, Any],
        description: dict[str, Any],
        grouped_repos: dict[str, list[dict[str, Any]]],
        include_stats: bool,
    ) -> str:
        """Generate minimal template README."""
        lines: list[str] = []

        # Header
        lines.append(f"# {description['title']}")
        lines.append("")
        lines.append(description["tagline"])
        lines.append("")

        # Simple repository list
        lines.append("## Projects")
        lines.append("")

        for repos in grouped_repos.values():
            for repo in repos:
                name = repo.get("name", "")
                desc = repo.get("description") or "No description"
                url = repo.get("html_url", "")
                lines.append(f"- [{name}]({url}) - {desc}")

        lines.append("")
        lines.append("---")
        lines.append(
            "*Generated with [gh-toolkit](https://github.com/michael-borck/gh-toolkit)*"
        )

        return "\n".join(lines)

    def _generate_detailed_readme(
        self,
        org_info: dict[str, Any],
        description: dict[str, Any],
        grouped_repos: dict[str, list[dict[str, Any]]],
        all_repos: list[dict[str, Any]],
        include_stats: bool,
    ) -> str:
        """Generate detailed template README with extended information."""
        lines: list[str] = []

        # Header with avatar
        avatar_url = org_info.get("avatar_url", "")
        if avatar_url:
            lines.append('<p align="center">')
            lines.append(
                f'  <img src="{avatar_url}" alt="{description["title"]}" width="200" />'
            )
            lines.append("</p>")
            lines.append("")

        lines.append(f"# {description['title']}")
        lines.append("")
        lines.append(f"**{description['tagline']}**")
        lines.append("")

        if description.get("mission"):
            lines.append(f"> {description['mission']}")
            lines.append("")

        # Organization info
        lines.append("## About")
        lines.append("")
        if org_info.get("location"):
            lines.append(f"- **Location**: {org_info['location']}")
        if org_info.get("blog"):
            lines.append(f"- **Website**: [{org_info['blog']}]({org_info['blog']})")
        lines.append(
            f"- **GitHub**: [@{org_info.get('login', '')}](https://github.com/{org_info.get('login', '')})"
        )
        lines.append("")

        # Focus areas
        if description.get("focus_areas"):
            lines.append("## Focus Areas")
            lines.append("")
            lines.append(
                " | ".join([f"**{area}**" for area in description["focus_areas"]])
            )
            lines.append("")

        # Repositories with detailed info
        lines.append("## Repositories")
        lines.append("")

        for category, repos in grouped_repos.items():
            lines.append(f"### {category}")
            lines.append("")

            for repo in repos:
                name = repo.get("name", "")
                desc = repo.get("description") or "No description"
                url = repo.get("html_url", "")
                lang = repo.get("language") or "Unknown"
                topics = repo.get("topics", [])

                lines.append(f"#### [{name}]({url})")
                lines.append("")
                lines.append(desc)
                lines.append("")
                lines.append(
                    f"![Language](https://img.shields.io/badge/language-{lang.replace(' ', '%20')}-blue) "
                )
                lines.append(
                    f"![Stars](https://img.shields.io/github/stars/{repo.get('full_name', '')}?style=social) "
                )
                lines.append(
                    f"![Forks](https://img.shields.io/github/forks/{repo.get('full_name', '')}?style=social)"
                )
                lines.append("")

                if topics:
                    lines.append(f"**Topics**: {', '.join(topics)}")
                    lines.append("")

        # Comprehensive statistics
        if include_stats:
            lines.append("## Statistics")
            lines.append("")

            total_stars = sum(r.get("stargazers_count", 0) for r in all_repos)
            total_forks = sum(r.get("forks_count", 0) for r in all_repos)
            total_repos = len(all_repos)

            # Language breakdown
            lang_counts: dict[str, int] = {}
            for repo in all_repos:
                lang = repo.get("language")
                if lang:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1

            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Repositories | {total_repos} |")
            lines.append(f"| Total Stars | {total_stars} |")
            lines.append(f"| Total Forks | {total_forks} |")
            lines.append(f"| Languages | {len(lang_counts)} |")
            lines.append("")

            if lang_counts:
                lines.append("### Language Distribution")
                lines.append("")
                lines.append("| Language | Repositories |")
                lines.append("|----------|--------------|")
                for lang, count in sorted(
                    lang_counts.items(), key=lambda x: x[1], reverse=True
                )[:10]:
                    lines.append(f"| {lang} | {count} |")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(
            f"*Generated with [gh-toolkit](https://github.com/michael-borck/gh-toolkit) on {datetime.now().strftime('%Y-%m-%d')}*"
        )

        return "\n".join(lines)

    def save_readme(self, content: str, output_path: str) -> None:
        """Save README content to file.

        Args:
            content: README markdown content
            output_path: Output file path
        """
        path = Path(output_path)
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]README saved to {path.absolute()}[/green]")
