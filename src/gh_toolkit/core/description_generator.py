"""Description generation functionality for GitHub repositories."""

import time
from typing import Any

from rich.console import Console

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient

console = Console()


class DescriptionGenerator:
    """Generate and update GitHub repository descriptions using LLM analysis."""

    DEFAULT_MODEL = "claude-3-haiku-20240307"

    def __init__(
        self,
        github_client: GitHubClient,
        anthropic_api_key: str | None = None,
        rate_limit: float = 0.5,
        model: str | None = None,
    ):
        """Initialize with GitHub client and optional Anthropic API key.

        Args:
            github_client: Authenticated GitHub client
            anthropic_api_key: Optional Anthropic API key for LLM features
            rate_limit: Seconds to wait between API requests (default: 0.5)
            model: Anthropic model to use (default: claude-3-haiku-20240307)
        """
        self.client = github_client
        self.anthropic_api_key = anthropic_api_key
        self.rate_limit = rate_limit
        self.model = model or self.DEFAULT_MODEL

        if anthropic_api_key:
            try:
                from anthropic import Anthropic

                self._anthropic_client = Anthropic(api_key=anthropic_api_key)
            except ImportError:
                console.print(
                    "[yellow]Anthropic package not available. Install with: pip install anthropic[/yellow]"
                )
                self._anthropic_client = None
        else:
            self._anthropic_client = None

    def generate_description(
        self, owner: str, repo: str, repo_data: dict[str, Any] | None = None
    ) -> str | None:
        """Generate a description for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            repo_data: Optional pre-fetched repository data

        Returns:
            Generated description or None if generation failed
        """
        try:
            # Fetch repo data if not provided
            if repo_data is None:
                repo_data = self.client.get_repo_info(owner, repo)

            # Get README content
            readme = self.client.get_repo_readme(owner, repo)

            # Try LLM generation first, fall back to rule-based
            if self._anthropic_client:
                description = self._generate_with_llm(repo_data, readme)
                if description:
                    return description

            # Fallback to rule-based generation
            return self._generate_fallback(repo_data)

        except GitHubAPIError as e:
            console.print(
                f"[red]Error fetching repo data for {owner}/{repo}: {e.message}[/red]"
            )
            return None
        except Exception as e:
            console.print(
                f"[red]Unexpected error generating description for {owner}/{repo}: {e}[/red]"
            )
            return None

    def _generate_with_llm(
        self, repo_data: dict[str, Any], readme: str
    ) -> str | None:
        """Generate description using Claude LLM.

        Args:
            repo_data: Repository metadata
            readme: README content

        Returns:
            Generated description or None if LLM call failed
        """
        if not self._anthropic_client:
            return None

        name = repo_data.get("name", "")
        language = repo_data.get("language", "Unknown")
        topics = repo_data.get("topics", [])

        context = f"Repository name: {name}\n"
        context += f"Primary language: {language}\n"
        if topics:
            context += f"Topics: {', '.join(topics)}\n"
        if readme:
            context += f"\nREADME excerpt:\n{readme[:1500]}\n"

        prompt = f"""Generate a concise one-line description (max 250 chars) for this GitHub repository.
The description should explain what the project does, not use marketing language.
Do not start with "A" or "This". Use active voice.
Only output the description, nothing else.

{context}"""

        try:
            response = self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            response_content = response.content[0]
            description = (
                getattr(response_content, "text", "").strip()
                if hasattr(response_content, "text")
                else ""
            )

            # Ensure description fits GitHub's limit and is clean
            if description:
                # Remove surrounding quotes if present
                description = description.strip('"\'')
                return description[:250]

            return None

        except Exception as e:
            console.print(f"[yellow]LLM generation failed: {e}[/yellow]")
            return None

    def _generate_fallback(self, repo_data: dict[str, Any]) -> str:
        """Generate a basic description using rule-based approach.

        Args:
            repo_data: Repository metadata

        Returns:
            Generated description string
        """
        lang = repo_data.get("language", "")
        name = repo_data.get("name", "").replace("-", " ").replace("_", " ")
        topics = repo_data.get("topics", [])

        # Try to construct something meaningful
        if topics and lang:
            topic_str = ", ".join(topics[:3])
            return f"{lang} project for {topic_str}"[:250]
        elif lang:
            return f"{lang} project: {name}"[:250]
        elif topics:
            topic_str = ", ".join(topics[:3])
            return f"Project for {topic_str}"[:250]
        else:
            return f"Project: {name}"[:250]

    def update_description(
        self, owner: str, repo: str, description: str, dry_run: bool = False
    ) -> bool:
        """Update repository description on GitHub.

        Args:
            owner: Repository owner
            repo: Repository name
            description: New description to set
            dry_run: If True, don't actually update

        Returns:
            True if successful (or dry_run), False otherwise
        """
        if dry_run:
            return True

        return self.client.update_repo_description(owner, repo, description)

    def process_repository(
        self,
        owner: str,
        repo: str,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Process a single repository for description generation.

        Args:
            owner: Repository owner
            repo: Repository name
            dry_run: If True, show what would be done without making changes
            force: If True, update even if description already exists

        Returns:
            Result dictionary with status and details
        """
        repo_string = f"{owner}/{repo}"

        try:
            # Get repo info
            repo_data = self.client.get_repo_info(owner, repo)
            old_description = repo_data.get("description")

            # Check if description already exists
            if old_description and not force:
                return {
                    "repo": repo_string,
                    "status": "skipped",
                    "old_description": old_description,
                    "new_description": None,
                    "message": "Repository already has a description",
                }

            # Generate new description
            new_description = self.generate_description(owner, repo, repo_data)

            if not new_description:
                return {
                    "repo": repo_string,
                    "status": "error",
                    "old_description": old_description,
                    "new_description": None,
                    "message": "Failed to generate description",
                }

            # Prepare result
            result: dict[str, Any] = {
                "repo": repo_string,
                "old_description": old_description,
                "new_description": new_description,
            }

            # Update description if not dry run
            if dry_run:
                result.update({
                    "status": "dry_run",
                    "message": f"Would update description to: {new_description}",
                })
            else:
                if self.update_description(owner, repo, new_description):
                    result.update({
                        "status": "success",
                        "message": f"Updated description to: {new_description}",
                    })
                else:
                    result.update({
                        "status": "error",
                        "message": "Failed to update description via API",
                    })

            return result

        except GitHubAPIError as e:
            return {
                "repo": repo_string,
                "status": "error",
                "old_description": None,
                "new_description": None,
                "message": f"GitHub API error: {e.message}",
            }
        except Exception as e:
            return {
                "repo": repo_string,
                "status": "error",
                "old_description": None,
                "new_description": None,
                "message": f"Unexpected error: {str(e)}",
            }

    def process_multiple_repositories(
        self,
        repo_list: list[tuple[str, str]],
        dry_run: bool = False,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Process multiple repositories with rate limiting.

        Args:
            repo_list: List of (owner, repo) tuples
            dry_run: If True, show what would be done without making changes
            force: If True, update even if descriptions already exist

        Returns:
            List of result dictionaries
        """
        results: list[dict[str, Any]] = []

        for i, (owner, repo) in enumerate(repo_list, 1):
            console.print(
                f"\n[blue]Processing {i}/{len(repo_list)}: {owner}/{repo}[/blue]"
            )

            result = self.process_repository(owner, repo, dry_run, force)
            results.append(result)

            # Show result
            status = result["status"]
            message = result.get("message", "")

            if status == "success":
                console.print(f"[green]{message}[/green]")
            elif status == "skipped":
                console.print(f"[yellow]{message}[/yellow]")
                if result.get("old_description"):
                    console.print(
                        f"[dim]Current: {result['old_description']}[/dim]"
                    )
            elif status == "dry_run":
                console.print(f"[cyan]{message}[/cyan]")
            else:  # error
                console.print(f"[red]{message}[/red]")

            # Rate limiting
            if i < len(repo_list) and self.rate_limit > 0:
                time.sleep(self.rate_limit)

        return results
