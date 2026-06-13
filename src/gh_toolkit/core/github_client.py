"""Shared GitHub API client with rate limiting and error handling."""

import os
import time
from typing import Any

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.status_code:
            return f"GitHub API Error ({self.status_code}): {self.message}"
        return f"GitHub API Error: {self.message}"


class GitHubClient:
    """GitHub API client with rate limiting and error handling."""

    def __init__(self, token: str | None = None):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If None, will try to get from
                   GITHUB_TOKEN environment variable.
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")

        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gh-toolkit/0.1.0",
        }

        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._authenticated_user: str | None = None

    def get_authenticated_user(self) -> str | None:
        """Get the username of the authenticated user.

        Returns:
            Username of authenticated user, or None if not authenticated.
        """
        if self._authenticated_user is not None:
            return self._authenticated_user

        if not self.token:
            return None

        try:
            response = self._make_request("GET", "/user")
            data = response.json()
            self._authenticated_user = data.get("login")
            return self._authenticated_user
        except GitHubAPIError:
            return None

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Make a request to GitHub API with error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/user/repos")
            params: Query parameters
            json_data: JSON data for POST/PUT requests
            timeout: Request timeout in seconds

        Returns:
            Response object

        Raises:
            GitHubAPIError: If the request fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method=method, url=url, params=params, json=json_data, timeout=timeout
            )

            # Check rate limiting
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_time = max(0, reset_time - current_time)

                if wait_time > 0:
                    console.print(
                        f"[yellow]Rate limit reached. Waiting {wait_time} seconds...[/yellow]"
                    )
                    time.sleep(wait_time + 1)
                    # Retry the request
                    return self._make_request(
                        method, endpoint, params, json_data, timeout
                    )

            # Check for other errors
            if not response.ok:
                error_msg = f"GitHub API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                raise GitHubAPIError(error_msg, response.status_code)

            return response

        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}") from e

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Make a raw request to a GitHub API endpoint.

        Public entry point for callers that need endpoints without a
        dedicated helper method. See _make_request for details.

        Raises:
            GitHubAPIError: If the request fails
        """
        return self._make_request(method, endpoint, params, json_data, timeout)

    def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        per_page: int = 100,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all pages from a paginated GitHub API endpoint.

        Args:
            endpoint: API endpoint
            params: Query parameters
            per_page: Items per page (max 100)
            max_pages: Maximum pages to fetch (None for all)

        Returns:
            List of all items from all pages
        """
        items: list[dict[str, Any]] = []
        page = 1
        params = params or {}
        params["per_page"] = min(per_page, 100)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching data...", total=None)

            while True:
                if max_pages and page > max_pages:
                    break

                params["page"] = page
                progress.update(task, description=f"Fetching page {page}...")

                response = self._make_request("GET", endpoint, params)
                page_items: list[dict[str, Any]] = response.json()

                if not page_items:
                    break

                items.extend(page_items)
                page += 1

                # Small delay to be nice to the API
                time.sleep(0.1)

        return items

    def get_user_repos(
        self,
        username: str | None = None,
        repo_type: str = "all",
        visibility: str = "all",
        affiliation: str = "owner,collaborator,organization_member",
    ) -> list[dict[str, Any]]:
        """Get repositories for a user.

        Args:
            username: GitHub username (None for authenticated user)
            repo_type: Repository type (all, owner, public, private, member)
            visibility: Repository visibility (all, public, private)
            affiliation: Affiliation (owner, collaborator, organization_member)

        Returns:
            List of repository data
        """
        if username:
            # Get repos for specific user
            endpoint = f"/users/{username}/repos"
            params = {"type": repo_type}
        else:
            # Get repos for authenticated user
            endpoint = "/user/repos"
            params = {}

            # Only add type if visibility/affiliation are default
            if (
                visibility == "all"
                and affiliation == "owner,collaborator,organization_member"
            ):
                params["type"] = repo_type
            else:
                # Use visibility and affiliation (cannot combine with type)
                params["visibility"] = visibility
                params["affiliation"] = affiliation

        return self.get_paginated(endpoint, params)

    def get_org_repos(
        self, org_name: str, repo_type: str = "all"
    ) -> list[dict[str, Any]]:
        """Get repositories for an organization.

        Args:
            org_name: Organization name
            repo_type: Repository type (all, public, private, forks, sources, member)

        Returns:
            List of repository data
        """
        endpoint = f"/orgs/{org_name}/repos"
        params = {"type": repo_type}
        return self.get_paginated(endpoint, params)

    def get_user_info(self, username: str | None = None) -> dict[str, Any]:
        """Get user information.

        Args:
            username: GitHub username (None for authenticated user)

        Returns:
            User information
        """
        if username:
            endpoint = f"/users/{username}"
        else:
            endpoint = "/user"

        response = self._make_request("GET", endpoint)
        return response.json()

    def get_repo_info(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository information
        """
        endpoint = f"/repos/{owner}/{repo}"
        response = self._make_request("GET", endpoint)
        return response.json()

    # Invitation management methods

    def get_repository_invitations(self) -> list[dict[str, Any]]:
        """Get pending repository invitations for the authenticated user.

        Returns:
            List of repository invitation data
        """
        endpoint = "/user/repository_invitations"
        response = self._make_request("GET", endpoint)
        return response.json()

    def accept_repository_invitation(self, invitation_id: int) -> bool:
        """Accept a repository invitation.

        Args:
            invitation_id: ID of the invitation to accept

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/user/repository_invitations/{invitation_id}"
        try:
            response = self._make_request("PATCH", endpoint)
            if response.status_code != 204:
                console.print(
                    f"[yellow]Warning: Expected status 204 but got {response.status_code} for repo invitation {invitation_id}[/yellow]"
                )
            return response.status_code == 204
        except GitHubAPIError as e:
            console.print(
                f"[yellow]API error while accepting repo invitation {invitation_id}: {e.message}[/yellow]"
            )
            return False

    def get_organization_invitations(self) -> list[dict[str, Any]]:
        """Get pending organization invitations for the authenticated user.

        Returns:
            List of organization invitation data
        """
        endpoint = "/user/organization_invitations"
        try:
            response = self._make_request("GET", endpoint)
            return response.json()
        except GitHubAPIError as e:
            # 404 means no pending invitations
            if e.status_code == 404:
                return []
            raise

    def accept_organization_invitation(self, invitation_id: int) -> bool:
        """Accept an organization invitation.

        Args:
            invitation_id: ID of the invitation to accept

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/user/organization_invitations/{invitation_id}"
        try:
            response = self._make_request("PATCH", endpoint)
            return response.status_code == 204
        except GitHubAPIError:
            return False

    def leave_repository(self, owner: str, repo: str, username: str) -> bool:
        """Leave a repository (remove user as collaborator).

        Args:
            owner: Repository owner
            repo: Repository name
            username: Username to remove (usually authenticated user)

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/repos/{owner}/{repo}/collaborators/{username}"
        try:
            response = self._make_request("DELETE", endpoint)
            return response.status_code in [
                204,
                404,
            ]  # 404 means already not a collaborator
        except GitHubAPIError:
            return False

    # Repository data extraction methods

    def get_repo_readme(self, owner: str, repo: str) -> str:
        """Get README content from repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            README content as string
        """
        endpoint = f"/repos/{owner}/{repo}/readme"
        try:
            response = self._make_request("GET", endpoint)
            content_data = response.json()

            # Decode base64 content
            import base64

            readme_text = base64.b64decode(content_data["content"]).decode("utf-8")
            return readme_text[:5000]  # Limit to 5000 chars to avoid token limits
        except Exception:
            return ""

    def get_repo_releases(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """Get releases for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of release data
        """
        endpoint = f"/repos/{owner}/{repo}/releases"
        try:
            response = self._make_request("GET", endpoint)
            return response.json()
        except Exception:
            return []

    def get_repo_topics(self, owner: str, repo: str) -> list[str]:
        """Get topics for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of topic strings
        """
        endpoint = f"/repos/{owner}/{repo}/topics"
        try:
            response = self._make_request("GET", endpoint)
            return response.json().get("names", [])
        except Exception:
            return []

    def get_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Get programming languages used in repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary of language names to byte counts
        """
        endpoint = f"/repos/{owner}/{repo}/languages"
        try:
            response = self._make_request("GET", endpoint)
            return response.json()
        except Exception:
            return {}

    def get_repo(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get repository metadata.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository data or None if not found
        """
        endpoint = f"/repos/{owner}/{repo}"
        try:
            response = self._make_request("GET", endpoint)
            return response.json()
        except Exception:
            return None

    def get_repo_tree(
        self, owner: str, repo: str, branch: str | None = None
    ) -> list[dict[str, Any]]:
        """Get repository file tree.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name (default: repo's default branch)

        Returns:
            List of tree items (files and directories)
        """
        # First get default branch if not specified
        if not branch:
            repo_data = self.get_repo(owner, repo)
            if repo_data:
                branch = repo_data.get("default_branch", "main")
            else:
                branch = "main"

        endpoint = f"/repos/{owner}/{repo}/git/trees/{branch}"
        try:
            response = self._make_request("GET", endpoint, params={"recursive": "1"})
            data = response.json()
            return data.get("tree", [])
        except Exception:
            return []

    def get_repo_pages_info(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get GitHub Pages information for repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Pages information or None if not available
        """
        endpoint = f"/repos/{owner}/{repo}/pages"
        try:
            response = self._make_request("GET", endpoint)
            return response.json()
        except Exception:
            return None

    # Repository transfer methods

    def transfer_repository(
        self, owner: str, repo: str, new_owner: str, new_name: str | None = None
    ) -> dict[str, Any]:
        """Transfer repository ownership to another user or organization.

        Args:
            owner: Current repository owner
            repo: Repository name
            new_owner: Username or organization name to transfer to
            new_name: Optional new repository name (defaults to current name)

        Returns:
            Transfer response data

        Raises:
            GitHubAPIError: If the transfer fails
        """
        endpoint = f"/repos/{owner}/{repo}/transfer"

        json_data: dict[str, str] = {"new_owner": new_owner}
        if new_name:
            json_data["new_name"] = new_name

        response = self._make_request("POST", endpoint, json_data=json_data)
        return response.json()

    def get_repository_transfers(self) -> list[dict[str, Any]]:
        """Get pending repository transfer invitations for the authenticated user.

        Note: This uses the repository invitations endpoint as GitHub doesn't
        have a separate transfers endpoint for listing pending transfers.

        Returns:
            List of pending repository invitations/transfers
        """
        # Repository invitations are effectively transfer invitations
        return self.get_repository_invitations()

    def get_organization_transfers(self, org_name: str) -> list[dict[str, Any]]:
        """Get pending organization membership invitations (NOT repository transfers).

        Note: This method actually gets organization membership invitations,
        not repository transfers. GitHub's API doesn't provide a direct way
        to list repository transfers by destination organization.

        Args:
            org_name: Organization name

        Returns:
            List of pending organization membership invitations
        """
        endpoint = f"/orgs/{org_name}/invitations"
        try:
            return self.get_paginated(endpoint)
        except GitHubAPIError:
            # Fallback to empty list if we don't have access
            return []

    # Organization methods

    def get_user_organizations(self) -> list[dict[str, Any]]:
        """Get organizations the authenticated user belongs to.

        Returns:
            List of organization data
        """
        return self.get_paginated("/user/orgs")

    def update_repo_description(self, owner: str, repo: str, description: str) -> bool:
        """Update repository description via GitHub API.

        Uses PATCH /repos/{owner}/{repo} endpoint.
        Description limited to 250 characters by GitHub.

        Args:
            owner: Repository owner
            repo: Repository name
            description: New description (will be truncated to 250 chars)

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/repos/{owner}/{repo}"
        try:
            self._make_request(
                "PATCH", endpoint, json_data={"description": description[:250]}
            )
            return True
        except GitHubAPIError:
            return False

    def get_repo_issues(
        self, owner: str, repo: str, state: str = "open"
    ) -> list[dict[str, Any]]:
        """List a repository's issues (excluding pull requests).

        The issues endpoint returns PRs too; they carry a ``pull_request`` key,
        which we filter out so callers only see real issues.
        """
        items = self.get_paginated(
            f"/repos/{owner}/{repo}/issues", params={"state": state}
        )
        return [item for item in items if "pull_request" not in item]

    def create_issue(
        self, owner: str, repo: str, title: str, body: str
    ) -> dict[str, Any]:
        """Create an issue on a repository.

        Raises:
            GitHubAPIError: e.g. 410 if issues are disabled, 403/404 if the
                token lacks write access.
        """
        response = self._make_request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json_data={"title": title, "body": body},
        )
        return response.json()

    def update_issue(
        self, owner: str, repo: str, number: int, title: str, body: str
    ) -> dict[str, Any]:
        """Update an existing issue's title and body."""
        response = self._make_request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{number}",
            json_data={"title": title, "body": body},
        )
        return response.json()

    def get_file_contents(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict[str, Any] | None:
        """Get file contents from repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file in repository
            ref: Branch, tag, or commit SHA (defaults to default branch)

        Returns:
            File contents dict with 'content', 'sha', 'encoding', etc. or None if not found
        """
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": ref} if ref else {}
        try:
            response = self._make_request("GET", endpoint, params=params)
            return response.json()
        except GitHubAPIError:
            return None

    def update_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        sha: str,
        branch: str | None = None,
    ) -> dict[str, Any] | None:
        """Update file contents in repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file in repository
            content: New file content (will be base64 encoded)
            message: Commit message
            sha: SHA of the file being replaced (from get_file_contents)
            branch: Branch to update (defaults to default branch)

        Returns:
            Commit response or None if failed
        """
        import base64

        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        data: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "sha": sha,
        }
        if branch:
            data["branch"] = branch

        try:
            response = self._make_request("PUT", endpoint, json_data=data)
            return response.json()
        except GitHubAPIError:
            return None

    def get_org_info(self, org_name: str) -> dict[str, Any]:
        """Get detailed information about an organization.

        Args:
            org_name: Organization name

        Returns:
            Organization information
        """
        endpoint = f"/orgs/{org_name}"
        response = self._make_request("GET", endpoint)
        return response.json()

    def create_org_repo(
        self,
        org_name: str,
        repo_name: str,
        description: str = "",
        private: bool = False,
    ) -> dict[str, Any] | None:
        """Create a new repository in an organization.

        Args:
            org_name: Organization name
            repo_name: Repository name
            description: Repository description
            private: Whether the repository should be private

        Returns:
            Repository data or None if failed
        """
        endpoint = f"/orgs/{org_name}/repos"
        data = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": False,  # We'll add files ourselves
        }
        try:
            response = self._make_request("POST", endpoint, json_data=data)
            return response.json()
        except GitHubAPIError:
            return None

    def create_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a new file in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path for the new file
            content: File content (will be base64 encoded)
            message: Commit message
            branch: Branch to create file on (defaults to default branch)

        Returns:
            Commit response or None if failed
        """
        import base64

        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        data: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
        }
        if branch:
            data["branch"] = branch

        try:
            response = self._make_request("PUT", endpoint, json_data=data)
            return response.json()
        except GitHubAPIError:
            return None

    def repo_exists(self, owner: str, repo: str) -> bool:
        """Check if a repository exists.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            True if repository exists, False otherwise
        """
        try:
            self.get_repo_info(owner, repo)
            return True
        except GitHubAPIError:
            return False
