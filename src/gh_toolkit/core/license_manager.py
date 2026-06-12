"""Manage licenses for GitHub repositories."""

import time
from datetime import datetime
from typing import Any

from rich.console import Console

from gh_toolkit.core.github_client import GitHubClient

console = Console()

# Common licenses with their SPDX identifiers
COMMON_LICENSES = {
    "mit": "MIT License - Simple and permissive",
    "apache-2.0": "Apache 2.0 - Permissive with patent protection",
    "gpl-3.0": "GPL 3.0 - Copyleft, requires source disclosure",
    "bsd-3-clause": "BSD 3-Clause - Permissive with attribution",
    "bsd-2-clause": "BSD 2-Clause - Simplified BSD",
    "unlicense": "Unlicense - Public domain dedication",
    "mpl-2.0": "Mozilla Public License 2.0",
    "lgpl-3.0": "LGPL 3.0 - Lesser GPL for libraries",
    "agpl-3.0": "AGPL 3.0 - Network copyleft",
    "cc0-1.0": "CC0 1.0 - Public domain",
}

DEFAULT_LICENSE = "mit"


class LicenseManager:
    """Manage licenses for GitHub repositories."""

    def __init__(
        self,
        client: GitHubClient,
        rate_limit: float = 0.5,
    ):
        """Initialize the license manager.

        Args:
            client: GitHub API client
            rate_limit: Seconds between API requests
        """
        self.client = client
        self.rate_limit = rate_limit
        self._license_cache: dict[str, dict[str, Any]] = {}

    def get_available_licenses(self) -> list[dict[str, Any]]:
        """Get list of available licenses from GitHub.

        Returns:
            List of license info dictionaries
        """
        try:
            response = self.client.request("GET", "/licenses")
            return response.json()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch licenses: {e}[/yellow]")
            return []

    def get_license_template(self, license_key: str) -> dict[str, Any] | None:
        """Get license template by key.

        Args:
            license_key: License SPDX identifier (e.g., 'mit', 'apache-2.0')

        Returns:
            License template data or None if not found
        """
        if license_key in self._license_cache:
            return self._license_cache[license_key]

        try:
            response = self.client.request("GET", f"/licenses/{license_key.lower()}")
            data = response.json()
            self._license_cache[license_key] = data
            return data
        except Exception as e:
            console.print(f"[red]Could not fetch license template: {e}[/red]")
            return None

    def check_repo_license(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Check if repository has a license.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            License info if exists, None otherwise
        """
        try:
            repo_data = self.client.get_repo(owner, repo)
            if repo_data:
                return repo_data.get("license")
            return None
        except Exception:
            return None

    def format_license_body(
        self,
        template_body: str,
        full_name: str | None = None,
        year: int | None = None,
    ) -> str:
        """Format license template with placeholders filled in.

        Args:
            template_body: License template text
            full_name: Name for copyright (defaults to repo owner)
            year: Copyright year (defaults to current year)

        Returns:
            Formatted license text
        """
        if year is None:
            year = datetime.now().year

        # Replace common placeholders
        body = template_body
        body = body.replace("[year]", str(year))
        body = body.replace("[yyyy]", str(year))
        body = body.replace("<year>", str(year))

        if full_name:
            body = body.replace("[fullname]", full_name)
            body = body.replace("[name of copyright owner]", full_name)
            body = body.replace("<name of author>", full_name)
            body = body.replace("[name]", full_name)
            body = body.replace("<copyright holders>", full_name)
            body = body.replace("[copyright holders]", full_name)

        return body

    def add_license(
        self,
        owner: str,
        repo: str,
        license_key: str = DEFAULT_LICENSE,
        full_name: str | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Add a license to a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            license_key: License SPDX identifier
            full_name: Name for copyright holder
            dry_run: If True, don't make changes
            force: If True, replace existing license

        Returns:
            Result dictionary with status and details
        """
        result: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "license": license_key,
            "status": "pending",
        }

        # Check existing license
        existing = self.check_repo_license(owner, repo)
        if existing and not force:
            result["status"] = "skipped"
            result["reason"] = (
                f"Already has license: {existing.get('spdx_id', 'unknown')}"
            )
            return result

        # Get license template
        template = self.get_license_template(license_key)
        if not template:
            result["status"] = "error"
            result["reason"] = f"License template not found: {license_key}"
            return result

        # Format the license body
        template_body = template.get("body", "")
        if not template_body:
            result["status"] = "error"
            result["reason"] = "License template has no body"
            return result

        # Use owner as default name if not provided
        if not full_name:
            full_name = owner

        license_content = self.format_license_body(template_body, full_name)
        result["content_preview"] = (
            license_content[:200] + "..."
            if len(license_content) > 200
            else license_content
        )

        if dry_run:
            result["status"] = "dry_run"
            result["action"] = "replace" if existing else "create"
            return result

        # Create or update the LICENSE file
        try:
            import base64

            encoded_content = base64.b64encode(license_content.encode("utf-8")).decode(
                "utf-8"
            )

            # Check if LICENSE file exists
            license_sha = None
            try:
                response = self.client.request(
                    "GET",
                    f"/repos/{owner}/{repo}/contents/LICENSE",
                )
                if response.ok:
                    license_sha = response.json().get("sha")
            except Exception:
                pass

            # Prepare request data
            data: dict[str, Any] = {
                "message": f"Add {template.get('spdx_id', license_key)} license\n\nAuto-generated by gh-toolkit",
                "content": encoded_content,
            }

            if license_sha:
                data["sha"] = license_sha

            # Create/update the file
            response = self.client.request(
                "PUT",
                f"/repos/{owner}/{repo}/contents/LICENSE",
                json_data=data,
            )

            if response.ok:
                result["status"] = "updated" if license_sha else "created"
                result["action"] = "replace" if license_sha else "create"
            else:
                result["status"] = "error"
                result["reason"] = f"API error: {response.status_code}"

        except Exception as e:
            result["status"] = "error"
            result["reason"] = str(e)

        return result

    def process_repository(
        self,
        owner: str,
        repo: str,
        license_key: str = DEFAULT_LICENSE,
        full_name: str | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Process a single repository for license addition.

        Args:
            owner: Repository owner
            repo: Repository name
            license_key: License SPDX identifier
            full_name: Name for copyright holder
            dry_run: If True, don't make changes
            force: If True, replace existing license

        Returns:
            Result dictionary
        """
        result = self.add_license(owner, repo, license_key, full_name, dry_run, force)
        time.sleep(self.rate_limit)
        return result

    def process_multiple_repositories(
        self,
        repos: list[tuple[str, str]],
        license_key: str = DEFAULT_LICENSE,
        full_name: str | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Process multiple repositories.

        Args:
            repos: List of (owner, repo) tuples
            license_key: License SPDX identifier
            full_name: Name for copyright holder
            dry_run: If True, don't make changes
            force: If True, replace existing license

        Returns:
            List of result dictionaries
        """
        results: list[dict[str, Any]] = []

        for i, (owner, repo) in enumerate(repos, 1):
            console.print(f"\n[blue]Processing {i}/{len(repos)}: {owner}/{repo}[/blue]")

            try:
                result = self.process_repository(
                    owner, repo, license_key, full_name, dry_run, force
                )
                results.append(result)

                # Print status
                status = result["status"]
                if status == "created":
                    console.print(
                        f"[green]  ✓ Added {license_key.upper()} license[/green]"
                    )
                elif status == "updated":
                    console.print(
                        f"[green]  ✓ Replaced with {license_key.upper()} license[/green]"
                    )
                elif status == "dry_run":
                    action = result.get("action", "add")
                    console.print(
                        f"[yellow]  Would {action} {license_key.upper()} license[/yellow]"
                    )
                elif status == "skipped":
                    console.print(
                        f"[dim]  Skipped: {result.get('reason', 'unknown')}[/dim]"
                    )
                elif status == "error":
                    console.print(
                        f"[red]  ✗ Error: {result.get('reason', 'unknown')}[/red]"
                    )

            except Exception as e:
                console.print(f"[red]  ✗ Error: {e}[/red]")
                results.append(
                    {
                        "owner": owner,
                        "repo": repo,
                        "status": "error",
                        "reason": str(e),
                    }
                )

        return results
