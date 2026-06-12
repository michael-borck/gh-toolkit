"""Generate README files for individual GitHub repositories."""

import base64
import re
import time
from typing import Any

from rich.console import Console

from gh_toolkit.core.github_client import GitHubClient

console = Console()


class RepoReadmeGenerator:
    """Generate README files for GitHub repositories using LLM."""

    def __init__(
        self,
        client: GitHubClient,
        anthropic_key: str | None = None,
        rate_limit: float = 0.5,
        model: str = "claude-3-haiku-20240307",
    ):
        """Initialize the README generator.

        Args:
            client: GitHub API client
            anthropic_key: Anthropic API key for LLM generation
            rate_limit: Seconds between API requests
            model: Anthropic model to use
        """
        self.client = client
        self.anthropic_key = anthropic_key
        self.rate_limit = rate_limit
        self.model = model
        self._anthropic_client: Any = None

    def _get_anthropic_client(self) -> Any:
        """Get or create Anthropic client."""
        if self._anthropic_client is None and self.anthropic_key:
            try:
                import anthropic

                self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_key)
            except ImportError:
                console.print(
                    "[yellow]Warning: anthropic package not installed[/yellow]"
                )
                return None
        return self._anthropic_client

    def get_readme_content(self, owner: str, repo: str) -> str | None:
        """Get README content from a repository.

        Returns:
            README content as string, or None if not found.
        """
        try:
            readme_data = self.client.get_repo_readme(owner, repo)
            if readme_data:
                # The API returns base64-encoded content
                try:
                    return base64.b64decode(readme_data).decode("utf-8")
                except Exception:
                    return readme_data
            return None
        except Exception:
            return None

    def assess_readme_quality(
        self, readme_content: str | None
    ) -> tuple[float, list[str]]:
        """Assess README quality and identify issues.

        Args:
            readme_content: README content to assess

        Returns:
            Tuple of (quality_score 0-1, list of issues)
        """
        if not readme_content:
            return 0.0, ["No README found"]

        issues: list[str] = []
        score = 0.0
        max_score = 8.0

        # Check for title
        if re.search(r"^#\s+.+", readme_content, re.MULTILINE):
            score += 1.0
        else:
            issues.append("Missing title")

        # Check for description/introduction (content after title)
        paragraphs = readme_content.split("\n\n")
        if len(paragraphs) >= 2 and len(paragraphs[1].strip()) > 50:
            score += 1.0
        else:
            issues.append("Missing or short description")

        # Check for installation section
        if re.search(
            r"##?\s*(install|setup|getting started)", readme_content, re.IGNORECASE
        ):
            score += 1.0
        else:
            issues.append("Missing installation section")

        # Check for usage section
        if re.search(
            r"##?\s*(usage|examples?|how to use)", readme_content, re.IGNORECASE
        ):
            score += 1.0
        else:
            issues.append("Missing usage section")

        # Check for code examples
        if re.search(r"```[\s\S]*?```", readme_content):
            score += 1.0
        else:
            issues.append("Missing code examples")

        # Check reasonable length (not a placeholder)
        if len(readme_content) > 500:
            score += 1.0
        else:
            issues.append("Content too short (likely placeholder)")

        # Check for multiple sections
        section_count = len(re.findall(r"^##?\s+", readme_content, re.MULTILINE))
        if section_count >= 3:
            score += 1.0
        else:
            issues.append("Few sections (needs more structure)")

        # Check it's not just auto-generated boilerplate
        boilerplate_patterns = [
            r"^# \w+\s*$",  # Just a title and nothing else
            r"TODO",
            r"Add description here",
            r"This is a placeholder",
            r"^# \w+\n\n?$",  # Title with maybe one newline
        ]
        is_boilerplate = False
        for pattern in boilerplate_patterns:
            if re.search(pattern, readme_content, re.IGNORECASE):
                is_boilerplate = True
                break

        if not is_boilerplate:
            score += 1.0
        else:
            issues.append("Appears to be placeholder/boilerplate")

        return score / max_score, issues

    def get_repo_context(self, owner: str, repo: str) -> dict[str, Any]:
        """Gather context about a repository for README generation.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary with repo context
        """
        context: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "description": "",
            "languages": [],
            "topics": [],
            "has_license": False,
            "license_name": None,
            "default_branch": "main",
            "is_fork": False,
            "homepage": None,
        }

        try:
            # Get repo metadata
            repo_data = self.client.get_repo(owner, repo)
            if repo_data:
                context["description"] = repo_data.get("description") or ""
                context["default_branch"] = repo_data.get("default_branch", "main")
                context["is_fork"] = repo_data.get("fork", False)
                context["homepage"] = repo_data.get("homepage")

                license_info = repo_data.get("license")
                if license_info:
                    context["has_license"] = True
                    context["license_name"] = license_info.get("name")

            # Get languages
            languages = self.client.get_repo_languages(owner, repo)
            if languages:
                context["languages"] = list(languages.keys())

            # Get topics
            topics = self.client.get_repo_topics(owner, repo)
            if topics:
                context["topics"] = topics

            # Try to get file tree for structure understanding
            try:
                tree = self.client.get_repo_tree(owner, repo)
                if tree:
                    # Extract key files/directories
                    files = [item["path"] for item in tree if item["type"] == "blob"]
                    dirs = [item["path"] for item in tree if item["type"] == "tree"]
                    context["key_files"] = files[:20]  # Limit to 20
                    context["key_dirs"] = dirs[:10]  # Limit to 10
            except Exception:
                context["key_files"] = []
                context["key_dirs"] = []

        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not fetch full context: {e}[/yellow]"
            )

        return context

    def generate_readme_with_llm(self, context: dict[str, Any]) -> str | None:
        """Generate README content using LLM.

        Args:
            context: Repository context dictionary

        Returns:
            Generated README content, or None if failed
        """
        client = self._get_anthropic_client()
        if not client:
            return None

        # Build prompt
        prompt = self._build_generation_prompt(context)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            if response.content and len(response.content) > 0:
                content = response.content[0].text
                # Clean up any markdown code blocks wrapper
                if content.startswith("```markdown"):
                    content = content[11:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                return content.strip()

        except Exception as e:
            console.print(f"[red]LLM generation failed: {e}[/red]")

        return None

    def _build_generation_prompt(self, context: dict[str, Any]) -> str:
        """Build the prompt for README generation."""
        parts = [
            "Generate a professional README.md file for the following GitHub repository.",
            "The README should be well-structured, informative, and follow best practices.",
            "",
            "Repository Information:",
            f"- Name: {context['repo']}",
            f"- Owner: {context['owner']}",
        ]

        if context.get("description"):
            parts.append(f"- Description: {context['description']}")

        if context.get("languages"):
            parts.append(f"- Languages: {', '.join(context['languages'])}")

        if context.get("topics"):
            parts.append(f"- Topics: {', '.join(context['topics'])}")

        if context.get("license_name"):
            parts.append(f"- License: {context['license_name']}")

        if context.get("homepage"):
            parts.append(f"- Homepage: {context['homepage']}")

        if context.get("key_files"):
            parts.append(f"- Key files: {', '.join(context['key_files'][:10])}")

        if context.get("key_dirs"):
            parts.append(f"- Key directories: {', '.join(context['key_dirs'])}")

        parts.extend(
            [
                "",
                "Requirements for the README:",
                "1. Start with a clear title (# Repository Name)",
                "2. Add a concise but informative description/introduction",
                "3. Include an Installation section with code examples",
                "4. Include a Usage section with practical examples",
                "5. Add any relevant sections based on the project type (API docs, configuration, etc.)",
                "6. Include a License section if applicable",
                "7. Keep it professional and well-formatted",
                "8. Use appropriate markdown formatting",
                "9. Do NOT include badges - those will be added separately",
                "10. Do NOT use emojis in section headers",
                "",
                "Generate ONLY the README content, no explanations or commentary.",
            ]
        )

        return "\n".join(parts)

    def generate_readme_fallback(self, context: dict[str, Any]) -> str:
        """Generate a basic README without LLM.

        Args:
            context: Repository context dictionary

        Returns:
            Basic README content
        """
        parts = [f"# {context['repo']}", ""]

        if context.get("description"):
            parts.extend([context["description"], ""])

        # Languages
        if context.get("languages"):
            primary_lang = context["languages"][0]
            parts.extend(
                [
                    "## Technologies",
                    "",
                    f"- Primary language: {primary_lang}",
                ]
            )
            if len(context["languages"]) > 1:
                parts.append(f"- Also uses: {', '.join(context['languages'][1:])}")
            parts.append("")

        # Installation
        parts.extend(
            [
                "## Installation",
                "",
                "```bash",
                f"git clone https://github.com/{context['owner']}/{context['repo']}.git",
                f"cd {context['repo']}",
                "```",
                "",
            ]
        )

        # Usage
        parts.extend(
            [
                "## Usage",
                "",
                "See the documentation for usage instructions.",
                "",
            ]
        )

        # License
        if context.get("license_name"):
            parts.extend(
                [
                    "## License",
                    "",
                    f"This project is licensed under the {context['license_name']}.",
                    "",
                ]
            )

        return "\n".join(parts)

    def update_readme(
        self,
        owner: str,
        repo: str,
        content: str,
        branch: str | None = None,
    ) -> bool:
        """Update README in the repository.

        Args:
            owner: Repository owner
            repo: Repository name
            content: New README content
            branch: Branch to update (default: repo's default branch)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current README to get its SHA (needed for update)
            readme_path = "README.md"
            current_sha = None

            try:
                response = self.client.request(
                    "GET",
                    f"/repos/{owner}/{repo}/contents/{readme_path}",
                )
                if response.ok:
                    current_sha = response.json().get("sha")
            except Exception:
                pass  # README doesn't exist, we'll create it

            # Prepare the update/create request
            import base64 as b64

            encoded_content = b64.b64encode(content.encode("utf-8")).decode("utf-8")

            data: dict[str, Any] = {
                "message": "Update README.md\n\nAuto-generated by gh-toolkit",
                "content": encoded_content,
            }

            if current_sha:
                data["sha"] = current_sha

            if branch:
                data["branch"] = branch

            response = self.client.request(
                "PUT",
                f"/repos/{owner}/{repo}/contents/{readme_path}",
                json_data=data,
            )

            return response.ok

        except Exception as e:
            console.print(f"[red]Failed to update README: {e}[/red]")
            return False

    def process_repository(
        self,
        owner: str,
        repo: str,
        dry_run: bool = False,
        force: bool = False,
        min_quality: float = 0.5,
    ) -> dict[str, Any]:
        """Process a single repository for README generation/update.

        Args:
            owner: Repository owner
            repo: Repository name
            dry_run: If True, don't make changes
            force: If True, update even good READMEs
            min_quality: Quality threshold below which to update (0-1)

        Returns:
            Result dictionary with status and details
        """
        result: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "status": "skipped",
            "quality_before": None,
            "quality_after": None,
            "issues": [],
            "action": None,
        }

        # Get current README
        current_readme = self.get_readme_content(owner, repo)
        quality, issues = self.assess_readme_quality(current_readme)
        result["quality_before"] = quality
        result["issues"] = issues

        # Decide if we should update
        if current_readme is None:
            result["action"] = "create"
        elif force:
            result["action"] = "force_update"
        elif quality < min_quality:
            result["action"] = "quality_update"
        else:
            result["status"] = "skipped"
            result["action"] = "quality_ok"
            return result

        # Get context and generate README
        context = self.get_repo_context(owner, repo)

        # Try LLM generation first
        new_readme = self.generate_readme_with_llm(context)
        if not new_readme:
            # Fall back to template
            new_readme = self.generate_readme_fallback(context)
            result["generation_method"] = "fallback"
        else:
            result["generation_method"] = "llm"

        result["generated_content"] = new_readme

        # Assess new quality
        new_quality, _ = self.assess_readme_quality(new_readme)
        result["quality_after"] = new_quality

        if dry_run:
            result["status"] = "dry_run"
            return result

        # Apply the update
        if self.update_readme(owner, repo, new_readme):
            result["status"] = "updated"
        else:
            result["status"] = "failed"

        # Rate limiting
        time.sleep(self.rate_limit)

        return result

    def process_multiple_repositories(
        self,
        repos: list[tuple[str, str]],
        dry_run: bool = False,
        force: bool = False,
        min_quality: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Process multiple repositories.

        Args:
            repos: List of (owner, repo) tuples
            dry_run: If True, don't make changes
            force: If True, update even good READMEs
            min_quality: Quality threshold below which to update (0-1)

        Returns:
            List of result dictionaries
        """
        results: list[dict[str, Any]] = []

        for i, (owner, repo) in enumerate(repos, 1):
            console.print(f"\n[blue]Processing {i}/{len(repos)}: {owner}/{repo}[/blue]")

            try:
                result = self.process_repository(
                    owner, repo, dry_run, force, min_quality
                )
                results.append(result)

                # Print status
                status = result["status"]
                if status == "updated":
                    console.print(
                        f"[green]  ✓ Updated README "
                        f"(quality: {result['quality_before']:.0%} → {result['quality_after']:.0%})[/green]"
                    )
                elif status == "dry_run":
                    console.print(
                        f"[yellow]  Would update README "
                        f"(quality: {result['quality_before']:.0%} → {result['quality_after']:.0%})[/yellow]"
                    )
                elif status == "skipped":
                    console.print(
                        f"[dim]  Skipped (quality: {result['quality_before']:.0%})[/dim]"
                    )
                elif status == "failed":
                    console.print("[red]  ✗ Failed to update README[/red]")

                if result.get("issues") and result["status"] != "skipped":
                    for issue in result["issues"][:3]:
                        console.print(f"[dim]    - {issue}[/dim]")

            except Exception as e:
                console.print(f"[red]  ✗ Error: {e}[/red]")
                results.append(
                    {
                        "owner": owner,
                        "repo": repo,
                        "status": "error",
                        "error": str(e),
                    }
                )

        return results
