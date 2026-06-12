"""Repository data extraction and categorization."""

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.llm import DEFAULT_LLM_MODEL

console = Console()


class RepositoryExtractor:
    """Extract comprehensive data from GitHub repositories."""

    def __init__(self, client: GitHubClient, anthropic_api_key: str | None = None):
        """Initialize extractor.

        Args:
            client: GitHub API client
            anthropic_api_key: Anthropic API key for LLM categorization (optional)
        """
        self.client = client
        self.anthropic_api_key = anthropic_api_key

        # Initialize Anthropic client if key provided
        self._anthropic_client = None
        if anthropic_api_key:
            try:
                from anthropic import Anthropic

                self._anthropic_client = Anthropic(api_key=anthropic_api_key)
            except ImportError:
                console.print(
                    "[yellow]Warning: anthropic package not installed. LLM categorization disabled.[/yellow]"
                )
                console.print("Install with: pip install anthropic")

    def extract_repository_data(self, owner: str, repo_name: str) -> dict[str, Any]:
        """Extract comprehensive data from a single repository.

        Args:
            owner: Repository owner
            repo_name: Repository name

        Returns:
            Dictionary with comprehensive repository data
        """
        console.print(f"[blue]Extracting data from {owner}/{repo_name}...[/blue]")

        # Get basic repo info
        repo_data = self.client.get_repo_info(owner, repo_name)

        # Get additional data
        readme_content = self.client.get_repo_readme(owner, repo_name)
        releases = self.client.get_repo_releases(owner, repo_name)
        topics = self.client.get_repo_topics(owner, repo_name)
        languages = self.client.get_repo_languages(owner, repo_name)
        pages_info = self.client.get_repo_pages_info(owner, repo_name)

        # Extract download links from latest release
        download_links = self._extract_download_links(releases)

        # Get GitHub Pages URL
        pages_url = self._get_pages_url(repo_data, pages_info, owner, repo_name)

        # Get latest version info
        latest_version = self._get_latest_version_info(releases)

        # Categorize the repository
        category, category_details = self._categorize_repository(
            repo_data, readme_content, topics, languages
        )

        # Build comprehensive data structure
        extracted_data = {
            # Basic info
            "name": repo_data["name"],
            "full_name": repo_data["full_name"],
            "description": repo_data.get("description"),
            "url": repo_data["html_url"],
            "homepage": repo_data.get("homepage", ""),
            # Metadata
            "topics": topics,
            "languages": list(languages.keys()),
            "primary_language": repo_data.get("language"),
            "license": repo_data.get("license", {}).get("spdx_id")
            if repo_data.get("license")
            else None,
            # Statistics
            "stars": repo_data["stargazers_count"],
            "forks": repo_data["forks_count"],
            "watchers": repo_data["watchers_count"],
            "open_issues": repo_data["open_issues_count"],
            # Dates
            "created_at": repo_data["created_at"],
            "updated_at": repo_data["updated_at"],
            "last_updated": repo_data["updated_at"],
            # Categorization
            "category": category,
            "category_confidence": category_details["confidence"],
            "category_reason": category_details["reason"],
            # Features
            "pages_url": pages_url,
            "download_links": download_links,
            "latest_version": latest_version,
            # Flags
            "is_fork": repo_data.get("fork", False),
            "is_archived": repo_data.get("archived", False),
            "is_private": repo_data.get("private", False),
            "is_template": repo_data.get("is_template", False),
            "is_website": bool(repo_data.get("homepage") or pages_url),
            "has_downloads": bool(download_links),
            "has_pages": repo_data.get("has_pages", False),
            # Content
            "readme_excerpt": readme_content[:500] + "..."
            if len(readme_content) > 500
            else readme_content,
            "readme_length": len(readme_content),
        }

        return extracted_data

    def extract_multiple_repositories(
        self, repo_list: list[str], show_progress: bool = True
    ) -> list[dict[str, Any]]:
        """Extract data from multiple repositories.

        Args:
            repo_list: List of 'owner/repo' strings
            show_progress: Whether to show progress bar

        Returns:
            List of repository data dictionaries
        """
        extracted_repos: list[dict[str, Any]] = []

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Extracting repositories...", total=len(repo_list)
                )

                for repo_string in repo_list:
                    try:
                        if "/" not in repo_string:
                            console.print(
                                f"[red]✗ Invalid format: {repo_string}. Use 'owner/repo'[/red]"
                            )
                            continue

                        owner, repo_name = repo_string.split("/", 1)
                        progress.update(
                            task, description=f"Extracting {repo_string}..."
                        )

                        repo_data = self.extract_repository_data(owner, repo_name)
                        extracted_repos.append(repo_data)

                        console.print(f"[green]✓ Extracted: {repo_string}[/green]")

                    except Exception as e:
                        console.print(
                            f"[red]✗ Failed to extract {repo_string}: {str(e)}[/red]"
                        )

                    progress.advance(task)
        else:
            for repo_string in repo_list:
                try:
                    if "/" not in repo_string:
                        console.print(
                            f"[red]✗ Invalid format: {repo_string}. Use 'owner/repo'[/red]"
                        )
                        continue

                    owner, repo_name = repo_string.split("/", 1)
                    repo_data = self.extract_repository_data(owner, repo_name)
                    extracted_repos.append(repo_data)

                    console.print(f"[green]✓ Extracted: {repo_string}[/green]")

                except Exception as e:
                    console.print(
                        f"[red]✗ Failed to extract {repo_string}: {str(e)}[/red]"
                    )

        return extracted_repos

    def save_to_json(self, repos_data: list[dict[str, Any]], output_file: str) -> None:
        """Save extracted data to JSON file.

        Args:
            repos_data: List of repository data
            output_file: Output file path
        """
        output_path = Path(output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(repos_data, f, indent=2, ensure_ascii=False)

        console.print(f"[green]✓ Data saved to {output_path}[/green]")

    def _extract_download_links(self, releases: list[dict[str, Any]]) -> dict[str, str]:
        """Extract download links from releases."""
        download_links: dict[str, str] = {}

        if not releases:
            return download_links

        latest_release = releases[0]
        for asset in latest_release.get("assets", []):
            name = asset["name"].lower()
            download_url = asset["browser_download_url"]

            if any(x in name for x in ["windows", ".exe", ".msi"]):
                download_links["windows"] = download_url
            elif any(x in name for x in ["mac", "macos", ".dmg", ".pkg"]):
                download_links["mac"] = download_url
            elif any(
                x in name for x in ["linux", ".deb", ".rpm", ".appimage", ".tar.gz"]
            ):
                download_links["linux"] = download_url

        return download_links

    def _get_pages_url(
        self,
        repo_data: dict[str, Any],
        pages_info: dict[str, Any] | None,
        owner: str,
        repo_name: str,
    ) -> str | None:
        """Get GitHub Pages URL."""
        if not repo_data.get("has_pages"):
            return None

        if pages_info and pages_info.get("html_url"):
            return pages_info["html_url"]

        # Fallback to standard patterns
        if owner.lower() + ".github.io" == repo_name.lower():
            return f"https://{owner}.github.io/"
        else:
            return f"https://{owner}.github.io/{repo_name}/"

    def _get_latest_version_info(
        self, releases: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Get latest version information."""
        if not releases:
            return None

        latest_release = releases[0]
        return {
            "tag": latest_release.get("tag_name"),
            "name": latest_release.get("name"),
            "published": latest_release.get("published_at"),
            "prerelease": latest_release.get("prerelease", False),
            "draft": latest_release.get("draft", False),
        }

    def _categorize_repository(
        self,
        repo_data: dict[str, Any],
        readme: str,
        topics: list[str],
        languages: dict[str, int],
    ) -> tuple[str, dict[str, Any]]:
        """Categorize repository using rule-based system and optionally LLM.

        Returns:
            Tuple of (category, details_dict)
        """
        # First try LLM categorization if available
        if self._anthropic_client:
            try:
                llm_result = self._categorize_with_llm(
                    repo_data, readme, topics, languages
                )
                if llm_result:
                    return llm_result
            except Exception as e:
                console.print(
                    f"[yellow]Warning: LLM categorization failed: {e}[/yellow]"
                )

        # Fallback to rule-based categorization
        return self._categorize_with_rules(repo_data, readme, topics, languages)

    def _categorize_with_rules(
        self,
        repo_data: dict[str, Any],
        readme: str,
        topics: list[str],
        languages: dict[str, int],
    ) -> tuple[str, dict[str, Any]]:
        """Rule-based repository categorization."""
        name_lower = repo_data["name"].lower()
        desc_lower = (repo_data.get("description", "") or "").lower()
        # readme_lower = readme.lower()  # Could be used for content-based categorization
        topics_str = " ".join(topics).lower()
        languages_list = list(languages.keys())

        # Check for manual override via topic tag
        for topic in topics:
            if topic.startswith("cat-"):
                category = topic[4:].replace("-", " ").title()
                return category, {
                    "confidence": 1.0,
                    "reason": f"Manual override via topic: {topic}",
                }

        # Desktop Application
        desktop_indicators = ["electron", "tauri", "desktop-app", "desktop-application"]
        if any(indicator in topics_str for indicator in desktop_indicators):
            return "Desktop Application", {
                "confidence": 0.95,
                "reason": "Desktop framework detected in topics",
            }

        # Check for desktop downloads
        if repo_data.get("has_downloads") and languages_list:
            primary_lang = languages_list[0] if languages_list else ""
            if primary_lang in ["C++", "C#", "Java", "Rust", "Go"]:
                return "Desktop Application", {
                    "confidence": 0.8,
                    "reason": "Native language with downloadable releases",
                }

        # Infrastructure/Templates
        infra_indicators = [
            "docker",
            "docker-compose",
            "template",
            "boilerplate",
            "starter",
            "cookiecutter",
        ]
        if any(indicator in topics_str for indicator in infra_indicators):
            return "Infrastructure Tool", {
                "confidence": 0.9,
                "reason": "Infrastructure/template indicators in topics",
            }

        template_patterns = [
            "template",
            "boilerplate",
            "starter",
            "scaffold",
            "skeleton",
        ]
        if any(pattern in name_lower for pattern in template_patterns):
            return "Infrastructure Tool", {
                "confidence": 0.9,
                "reason": "Template naming pattern detected",
            }

        if repo_data.get("is_template"):
            return "Infrastructure Tool", {
                "confidence": 0.95,
                "reason": "GitHub template repository",
            }

        # Learning Resource
        if "TeX" in languages_list and ("book" in name_lower or "book" in topics_str):
            return "Learning Resource", {
                "confidence": 0.95,
                "reason": "TeX-based book project",
            }

        learning_indicators = [
            "book",
            "guide",
            "tutorial",
            "course",
            "curriculum",
            "documentation",
        ]
        if any(indicator in topics_str for indicator in learning_indicators):
            return "Learning Resource", {
                "confidence": 0.85,
                "reason": "Educational content indicators in topics",
            }

        # Python Package
        if "Python" in languages_list:
            pkg_indicators = ["pip install", "pypi", "python package", "python library"]
            if any(pkg in desc_lower for pkg in pkg_indicators):
                return "Python Package", {
                    "confidence": 0.95,
                    "reason": "Explicit package installation mentioned",
                }

            # Check if it's NOT a web app
            web_frameworks = ["flask", "fastapi", "django", "streamlit", "fasthtml"]
            is_web_framework = any(
                fw in topics_str or fw in desc_lower for fw in web_frameworks
            )

            if not is_web_framework:
                cli_indicators = ["cli-tool", "library", "package", "api"]
                if any(indicator in topics_str for indicator in cli_indicators):
                    return "Python Package", {
                        "confidence": 0.85,
                        "reason": "Python CLI/library without web framework",
                    }

        # Web Application
        web_frameworks = [
            "flask",
            "fastapi",
            "django",
            "react",
            "vue",
            "angular",
            "svelte",
            "nextjs",
        ]
        if any(fw in topics_str or fw in desc_lower for fw in web_frameworks):
            return "Web Application", {
                "confidence": 0.85,
                "reason": "Web framework detected",
            }

        if repo_data.get("homepage") or repo_data.get("has_pages"):
            if not any(x in desc_lower for x in ["documentation", "docs"]):
                return "Web Application", {
                    "confidence": 0.8,
                    "reason": "Has live website",
                }

        web_indicators = ["web-app", "web-application", "website"]
        if any(indicator in topics_str for indicator in web_indicators):
            return "Web Application", {
                "confidence": 0.8,
                "reason": "Web application indicators in topics",
            }

        # Notebook/Analysis
        if "Jupyter Notebook" in languages_list:
            return "Notebook/Analysis", {
                "confidence": 0.9,
                "reason": "Jupyter Notebook detected",
            }

        # Default fallbacks based on primary language
        if languages_list:
            primary_lang = languages_list[0]
            if primary_lang == "Python":
                return "Python Package", {
                    "confidence": 0.6,
                    "reason": "Primary language: Python",
                }
            elif primary_lang in ["JavaScript", "TypeScript"]:
                return "Web Application", {
                    "confidence": 0.6,
                    "reason": f"Primary language: {primary_lang}",
                }
            elif primary_lang in ["Java", "C++", "C#", "Go", "Rust"]:
                return "Desktop Application", {
                    "confidence": 0.6,
                    "reason": f"Primary language: {primary_lang}",
                }

        # Final fallback
        return "Other Tool", {
            "confidence": 0.5,
            "reason": "Default categorization - unable to determine specific type",
        }

    def _categorize_with_llm(
        self,
        repo_data: dict[str, Any],
        readme: str,
        topics: list[str],
        languages: dict[str, int],
    ) -> tuple[str, dict[str, Any]] | None:
        """LLM-powered repository categorization using Anthropic Claude."""
        if not self._anthropic_client:
            return None

        # Prepare context for LLM
        context = f"""Repository: {repo_data.get("name", "")}
Description: {repo_data.get("description", "No description")}
Main Language: {repo_data.get("language", "Unknown")}
All Languages: {", ".join(languages.keys()) if languages else "Unknown"}
Topics: {", ".join(topics) if topics else "None"}
Stars: {repo_data.get("stargazers_count", 0)}
Is Fork: {repo_data.get("fork", False)}
Has Downloads: {repo_data.get("has_downloads", False)}
Has Pages: {repo_data.get("has_pages", False)}
Homepage: {repo_data.get("homepage", "None")}

README excerpt:
{readme[:2000] if readme else "No README available"}"""

        prompt = f"""Based on the GitHub repository information below, categorize this repository into ONE of these categories:

1. Desktop Application - Standalone applications for desktop/mobile platforms
2. Web Application - Web apps, websites, web services, APIs
3. Python Package - Python libraries/packages for pip install
4. Learning Resource - Educational content, books, tutorials, courses
5. Infrastructure Tool - Templates, boilerplates, Docker configs, dev tools
6. Notebook/Analysis - Jupyter notebooks, data analysis, research
7. Other Tool - Everything else

{context}

Respond with ONLY the category name from the list above. Choose the most specific and accurate category."""

        try:
            response = self._anthropic_client.messages.create(
                model=DEFAULT_LLM_MODEL,
                max_tokens=50,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            response_content = response.content[0] if response.content else None
            category = getattr(response_content, "text", "").strip()

            # Validate category
            valid_categories = [
                "Desktop Application",
                "Web Application",
                "Python Package",
                "Learning Resource",
                "Infrastructure Tool",
                "Notebook/Analysis",
                "Other Tool",
            ]

            if category in valid_categories:
                return category, {
                    "confidence": 0.9,
                    "reason": "LLM categorization with Claude",
                }

        except Exception as e:
            console.print(f"[yellow]LLM categorization failed: {e}[/yellow]")

        return None
