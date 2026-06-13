"""Organization management commands."""

import os
from pathlib import Path

import typer
from rich.console import Console

from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient
from gh_toolkit.core.readme_generator import OrgReadmeGenerator

console = Console()


def readme(
    org_name: str = typer.Argument(help="GitHub organization name"),
    output: str = typer.Option(
        "README.md",
        "--output",
        "-o",
        help="Output file path (ignored if --apply is used)",
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
        help="Anthropic API key for LLM-powered descriptions",
    ),
    template: str = typer.Option(
        "default",
        "--template",
        help="Template style: default, minimal, detailed",
    ),
    group_by: str = typer.Option(
        "category",
        "--group-by",
        help="Group repos by: category, language, topic",
    ),
    stats: bool = typer.Option(
        True,
        "--stats/--no-stats",
        help="Include repository statistics",
    ),
    max_repos: int | None = typer.Option(
        None,
        "--max-repos",
        help="Maximum repositories to include",
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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview without writing to file",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        "-a",
        help="Push README directly to organization's .github repo profile",
    ),
) -> None:
    """Generate a profile README for a GitHub organization.

    Creates a comprehensive README with repository listings, statistics,
    and an LLM-generated organization description.

    Use --apply to push directly to the organization's .github/profile/README.md
    which displays on the organization's GitHub profile page.

    Examples:
        gh-toolkit org readme my-org
        gh-toolkit org readme my-org --template detailed --output profile/README.md
        gh-toolkit org readme my-org --group-by language --max-repos 20
        gh-toolkit org readme my-org --apply  # Push to GitHub directly
    """
    try:
        # Get tokens
        github_token = token or os.environ.get("GITHUB_TOKEN")
        if not github_token:
            console.print(
                "[red]Error: GitHub token required. Set GITHUB_TOKEN or use --token[/red]"
            )
            raise typer.Exit(1)

        anthropic_api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")

        # Validate template
        valid_templates = ["default", "minimal", "detailed"]
        if template not in valid_templates:
            console.print(
                f"[red]Error: Invalid template '{template}'. Choose from: {', '.join(valid_templates)}[/red]"
            )
            raise typer.Exit(1)

        # Validate group_by
        valid_group_by = ["category", "language", "topic"]
        if group_by not in valid_group_by:
            console.print(
                f"[red]Error: Invalid group-by '{group_by}'. Choose from: {', '.join(valid_group_by)}[/red]"
            )
            raise typer.Exit(1)

        # Initialize client and generator
        client = GitHubClient(github_token)
        generator = OrgReadmeGenerator(client, anthropic_api_key)

        console.print(f"[blue]Generating README for organization: {org_name}[/blue]")

        # Generate README
        readme_content = generator.generate_readme(
            org_name=org_name,
            template=template,
            group_by=group_by,
            include_stats=stats,
            exclude_forks=exclude_forks,
            max_repos=max_repos,
            min_stars=min_stars,
        )

        if dry_run:
            console.print(
                "\n[yellow]--- DRY RUN: Preview of generated README ---[/yellow]\n"
            )
            # markup=False: markdown links like [name](url) would otherwise be
            # eaten as rich markup, hiding repo names from the preview
            console.print(readme_content, markup=False)
            console.print("\n[yellow]--- End of preview ---[/yellow]")
        elif apply:
            # Push to organization's .github repo
            _apply_org_readme(client, org_name, readme_content)
        else:
            generator.save_readme(readme_content, output)
            console.print("\n[green]README generated successfully![/green]")
            console.print(f"[blue]Location: {Path(output).absolute()}[/blue]")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API error: {e.message}[/red]")
        raise typer.Exit(1) from e
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


def _apply_org_readme(client: GitHubClient, org_name: str, readme_content: str) -> bool:
    """Apply README to organization's .github repository profile.

    GitHub organizations display their profile from .github/profile/README.md.
    This function creates/updates that file, creating the .github repo if needed.

    Args:
        client: GitHub API client
        org_name: Organization name
        readme_content: README content to push

    Returns:
        True if successful, False otherwise
    """
    import base64

    github_repo = ".github"
    readme_path = "profile/README.md"

    # Check if .github repo exists
    if not client.repo_exists(org_name, github_repo):
        console.print(f"[yellow]Creating .github repository for {org_name}...[/yellow]")
        result = client.create_org_repo(
            org_name=org_name,
            repo_name=github_repo,
            description=f"Organization profile for {org_name}",
            private=False,
        )
        if not result:
            console.print("[red]Failed to create .github repository[/red]")
            console.print(
                "[dim]Make sure you have admin permissions for this organization[/dim]"
            )
            return False
        console.print(f"[green]Created {org_name}/.github repository[/green]")

    # Check if profile/README.md already exists
    existing_file = client.get_file_contents(org_name, github_repo, readme_path)

    if existing_file:
        # File exists - check if we should merge or replace
        try:
            existing_content = base64.b64decode(existing_file["content"]).decode(
                "utf-8"
            )
            sha = existing_file["sha"]

            # Check if content is different
            if existing_content.strip() == readme_content.strip():
                console.print("[dim]README is already up to date[/dim]")
                return True

            # Show what exists and ask about merge
            console.print("[yellow]Existing README found. Updating...[/yellow]")

            # Preserve any custom sections marked with comments
            merged_content = _merge_readme_content(existing_content, readme_content)

            # Update the file
            result = client.update_file_contents(
                owner=org_name,
                repo=github_repo,
                path=readme_path,
                content=merged_content,
                message="Update organization profile README\n\nAuto-generated by gh-toolkit",
                sha=sha,
            )
        except Exception as e:
            console.print(f"[red]Error processing existing README: {e}[/red]")
            return False
    else:
        # Create new file
        console.print(f"[blue]Creating {readme_path}...[/blue]")
        result = client.create_file_contents(
            owner=org_name,
            repo=github_repo,
            path=readme_path,
            content=readme_content,
            message="Add organization profile README\n\nAuto-generated by gh-toolkit",
        )

    if result:
        console.print(
            f"[green]Successfully updated {org_name}/.github/{readme_path}[/green]"
        )
        console.print(f"[blue]View at: https://github.com/{org_name}[/blue]")
        return True
    else:
        console.print("[red]Failed to update README[/red]")
        return False


def _merge_readme_content(existing: str, new: str) -> str:
    """Merge existing README with new content, preserving custom sections.

    Sections marked with <!-- CUSTOM:START --> and <!-- CUSTOM:END -->
    will be preserved from the existing README.

    Args:
        existing: Existing README content
        new: New generated README content

    Returns:
        Merged content
    """
    import re

    # Look for custom sections to preserve
    custom_pattern = re.compile(
        r"(<!-- CUSTOM:START -->.*?<!-- CUSTOM:END -->)", re.DOTALL
    )
    custom_sections = custom_pattern.findall(existing)

    if not custom_sections:
        # No custom sections to preserve, use new content entirely
        return new

    # Append preserved custom sections to new content
    merged = new.rstrip() + "\n\n"
    merged += "<!-- Preserved custom sections -->\n"
    for section in custom_sections:
        merged += section + "\n\n"

    return merged
