"""Repository cloning functionality with parallel processing and organization."""

import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class CloneProgressCallback(Protocol):
    """Callback protocol for clone progress reporting."""

    def __call__(self, result: "CloneResult", completed: int, total: int) -> None:
        """Report clone progress."""
        ...


@dataclass
class CloneResult:
    """Result of a repository clone operation."""

    repo_name: str
    repo_url: str
    target_path: Path
    success: bool
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    note: str | None = None  # e.g. deadline-snapshot checkout outcome
    # Path this operation is allowed to remove if the clone failed. None means
    # "do not clean anything up" (e.g. the target existed before we started).
    cleanup_path: Path | None = None


@dataclass
class CloneStats:
    """Statistics for a clone operation."""

    total_repos: int
    successful: int
    failed: int
    skipped: int
    errors: list[CloneResult]


class RepoCloner:
    """Repository cloner with parallel processing and smart organization."""

    def __init__(self, target_dir: str | Path = "./repos", parallel: int = 4):
        """Initialize the repository cloner.

        Args:
            target_dir: Base directory for cloned repositories
            parallel: Number of parallel clone operations
        """
        self.target_dir = Path(target_dir)
        self.parallel = parallel
        self._lock = threading.Lock()
        self._in_progress: set[Path] = set()

    def parse_repo_input(self, repo_input: str) -> tuple[str, str]:
        """Parse repository input into owner and repo name.

        Args:
            repo_input: Repository identifier (owner/repo, URL, etc.)

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            ValueError: If input format is invalid
        """
        repo_input = repo_input.strip()

        # Handle GitHub URLs
        if repo_input.startswith(("https://github.com/", "git@github.com:")):
            return self._parse_github_url(repo_input)

        # Handle owner/repo format
        if "/" in repo_input:
            parts = repo_input.split("/")
            if len(parts) == 2:
                owner, repo = parts
                # Clean up repo name (remove .git suffix if present)
                if repo.endswith(".git"):
                    repo = repo[:-4]
                if not (self._is_valid_name(owner) and self._is_valid_name(repo)):
                    raise ValueError(f"Invalid repository format: {repo_input}")
                return owner, repo
            else:
                raise ValueError(f"Invalid repository format: {repo_input}")

        raise ValueError(
            f"Invalid repository format: {repo_input}. Use 'owner/repo' or GitHub URL"
        )

    @staticmethod
    def _is_valid_name(name: str) -> bool:
        """Validate a GitHub owner/repo name segment.

        Names become filesystem path components, so reject anything that
        could traverse outside the target directory ('..', separators).
        """
        return bool(re.match(r"^[A-Za-z0-9._-]+$", name)) and name not in (".", "..")

    def _parse_github_url(self, url: str) -> tuple[str, str]:
        """Parse GitHub URL into owner and repo name.

        Args:
            url: GitHub URL (HTTPS or SSH)

        Returns:
            Tuple of (owner, repo_name)
        """
        if url.startswith("git@github.com:"):
            # SSH format: git@github.com:owner/repo.git
            match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
            if match:
                owner, repo = match.group(1), match.group(2)
                if self._is_valid_name(owner) and self._is_valid_name(repo):
                    return owner, repo
        else:
            # HTTPS format: https://github.com/owner/repo
            parsed = urlparse(url)
            if parsed.netloc == "github.com":
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    owner, repo = path_parts[0], path_parts[1]
                    # Remove .git suffix if present
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    if self._is_valid_name(owner) and self._is_valid_name(repo):
                        return owner, repo

        raise ValueError(f"Invalid GitHub URL format: {url}")

    def build_clone_url(
        self, owner: str, repo: str, use_ssh: bool | None = None
    ) -> str:
        """Build clone URL for repository.

        Args:
            owner: Repository owner
            repo: Repository name
            use_ssh: Force SSH (True) or HTTPS (False). Auto-detect if None.

        Returns:
            Clone URL
        """
        if use_ssh is None:
            # Auto-detect: use SSH if SSH key is available
            use_ssh = self._has_ssh_key()

        if use_ssh:
            return f"git@github.com:{owner}/{repo}.git"
        else:
            return f"https://github.com/{owner}/{repo}.git"

    def _has_ssh_key(self) -> bool:
        """Check if SSH key is available for GitHub."""
        try:
            # Check if ssh-agent has keys
            result = subprocess.run(
                ["ssh-add", "-l"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return True

            # Check for default SSH key files
            ssh_dir = Path.home() / ".ssh"
            for key_file in ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]:
                if (ssh_dir / key_file).exists():
                    return True

            return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_target_path(self, owner: str, repo: str) -> Path:
        """Get target path for cloned repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Target path for repository

        Raises:
            ValueError: if the path would escape the target directory.
        """
        target_root = self.target_dir.resolve()
        target_path = self.target_dir / owner / repo
        resolved = target_path.resolve()
        if resolved == target_root or not resolved.is_relative_to(target_root):
            raise ValueError(
                f"Repository path escapes target directory: {owner}/{repo}"
            )
        return target_path

    def clone_repository(
        self,
        repo_input: str,
        branch: str | None = None,
        depth: int | None = None,
        use_ssh: bool | None = None,
        skip_existing: bool = True,
        before: str | None = None,
    ) -> CloneResult:
        """Clone a single repository.

        Args:
            repo_input: Repository identifier
            branch: Specific branch to clone
            depth: Clone depth for shallow clones
            use_ssh: Force SSH or HTTPS
            skip_existing: Skip if repository already exists locally
            before: If set, after cloning check out the last commit before this
                date (any git-parseable timestamp). Forces a full clone since
                history is needed to find the commit.

        Returns:
            CloneResult with operation details
        """
        # A deadline snapshot needs full history; a shallow clone may not
        # contain the commit before the deadline.
        if before is not None:
            depth = None

        temp_root: Path | None = None
        cleanup_path: Path | None = None
        target_path: Path | None = None
        try:
            # Parse repository input
            owner, repo = self.parse_repo_input(repo_input)
            clone_url = self.build_clone_url(owner, repo, use_ssh)
            target_path = self.get_target_path(owner, repo)

            # Claim the target path atomically: the existence check, the
            # in-progress check, and the parent mkdir must happen under the
            # same lock or two parallel workers can both clone the same path
            with self._lock:
                if target_path.exists() and skip_existing:
                    return CloneResult(
                        repo_name=f"{owner}/{repo}",
                        repo_url=clone_url,
                        target_path=target_path,
                        success=False,
                        skipped=True,
                        skip_reason="Repository already exists locally",
                    )

                if target_path in self._in_progress:
                    return CloneResult(
                        repo_name=f"{owner}/{repo}",
                        repo_url=clone_url,
                        target_path=target_path,
                        success=False,
                        skipped=True,
                        skip_reason="Clone already in progress",
                    )

                self._in_progress.add(target_path)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                existed_before = target_path.exists()

                if existed_before:
                    # --overwrite: clone beside the existing directory and swap
                    # it in only after the clone succeeds. A failed clone must
                    # never remove the user's existing checkout.
                    temp_root = Path(
                        tempfile.mkdtemp(
                            prefix=".gh-toolkit-clone-", dir=target_path.parent
                        )
                    )
                    clone_target = temp_root / repo
                else:
                    clone_target = target_path
                    cleanup_path = target_path

            try:
                # Build git clone command
                cmd = ["git", "clone"]

                if depth is not None:
                    cmd.extend(["--depth", str(depth)])

                if branch is not None:
                    cmd.extend(["--branch", branch])

                cmd.extend([clone_url, str(clone_target)])

                # Execute clone
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

                if result.returncode == 0:
                    if existed_before:
                        self._replace_directory(clone_target, target_path)
                        temp_root = None
                        cleanup_path = None
                    note = None
                    if before is not None:
                        note = self._checkout_before(target_path, before)
                    return CloneResult(
                        repo_name=f"{owner}/{repo}",
                        repo_url=clone_url,
                        target_path=target_path,
                        success=True,
                        note=note,
                    )
                else:
                    if existed_before:
                        self._remove_path(temp_root)
                        temp_root = None
                        cleanup_path = None
                    return CloneResult(
                        repo_name=f"{owner}/{repo}",
                        repo_url=clone_url,
                        target_path=target_path,
                        success=False,
                        error=result.stderr.strip() or "Clone failed",
                        cleanup_path=cleanup_path,
                    )
            finally:
                with self._lock:
                    self._in_progress.discard(target_path)

        except ValueError as e:
            if temp_root is not None:
                self._remove_path(temp_root)
            return CloneResult(
                repo_name=repo_input,
                repo_url="",
                target_path=Path(),
                success=False,
                error=str(e),
            )
        except subprocess.TimeoutExpired:
            if temp_root is not None:
                self._remove_path(temp_root)
            return CloneResult(
                repo_name=repo_input,
                repo_url="",
                target_path=target_path or Path(),
                success=False,
                error="Clone operation timed out",
                cleanup_path=cleanup_path,
            )
        except Exception as e:
            if temp_root is not None:
                self._remove_path(temp_root)
            return CloneResult(
                repo_name=repo_input,
                repo_url="",
                target_path=target_path or Path(),
                success=False,
                error=f"Unexpected error: {str(e)}",
                cleanup_path=cleanup_path,
            )

    def _checkout_before(self, target_path: Path, before: str) -> str:
        """Detach-checkout the last commit before ``before`` in a cloned repo.

        Best-effort: the clone itself already succeeded, so a failure here is
        reported as a note rather than failing the whole operation.

        Returns a human-readable note describing the outcome.
        """
        try:
            rev = subprocess.run(
                [
                    "git",
                    "-C",
                    str(target_path),
                    "rev-list",
                    "-n",
                    "1",
                    f"--before={before}",
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.SubprocessError as e:
            return f"Could not resolve deadline commit: {e}"

        if rev.returncode != 0:
            return f"Could not resolve deadline commit: {rev.stderr.strip()}"

        sha = rev.stdout.strip()
        if not sha:
            return f"No commit before {before}; left at default branch HEAD"

        checkout = subprocess.run(
            ["git", "-C", str(target_path), "checkout", "--quiet", sha],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if checkout.returncode != 0:
            return f"Failed to check out {sha[:8]}: {checkout.stderr.strip()}"

        return f"Snapshot at {sha[:8]} (last commit before {before})"

    @staticmethod
    def _remove_path(path: Path | None) -> None:
        """Remove a file or directory, ignoring errors and None."""
        if path is None or not path.exists():
            return
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            pass

    def _replace_directory(self, new_path: Path, target_path: Path) -> None:
        """Replace ``target_path`` with ``new_path``, keeping a rollback copy."""
        backup = target_path.with_name(target_path.name + ".gh-toolkit-old")
        self._remove_path(backup)
        target_path.rename(backup)
        try:
            new_path.rename(target_path)
        except OSError:
            backup.rename(target_path)
            raise
        finally:
            self._remove_path(backup)
            if new_path.parent != target_path.parent:
                self._remove_path(new_path.parent)

    def clone_repositories(
        self,
        repo_inputs: list[str],
        branch: str | None = None,
        depth: int | None = None,
        use_ssh: bool | None = None,
        skip_existing: bool = True,
        progress_callback: CloneProgressCallback | None = None,
        before: str | None = None,
    ) -> tuple[list[CloneResult], CloneStats]:
        """Clone multiple repositories in parallel.

        Args:
            repo_inputs: List of repository identifiers
            branch: Specific branch to clone
            depth: Clone depth for shallow clones
            use_ssh: Force SSH or HTTPS
            skip_existing: Skip if repository already exists locally
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (results, stats)
        """
        results: list[CloneResult] = []

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            # Submit all clone tasks
            future_to_repo = {
                executor.submit(
                    self.clone_repository,
                    repo_input,
                    branch,
                    depth,
                    use_ssh,
                    skip_existing,
                    before,
                ): repo_input
                for repo_input in repo_inputs
            }

            # Collect results as they complete
            for future in as_completed(future_to_repo):
                result = future.result()
                results.append(result)

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(result, len(results), len(repo_inputs))

        # Generate statistics
        stats = self._generate_stats(results)

        return results, stats

    def _generate_stats(self, results: list[CloneResult]) -> CloneStats:
        """Generate statistics from clone results.

        Args:
            results: List of clone results

        Returns:
            CloneStats with summary information
        """
        successful = sum(1 for r in results if r.success)
        skipped = sum(1 for r in results if r.skipped)
        failed = len(results) - successful - skipped
        errors = [r for r in results if not r.success and not r.skipped]

        return CloneStats(
            total_repos=len(results),
            successful=successful,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def read_repo_list(self, file_path: str | Path) -> list[str]:
        """Read repository list from file.

        Args:
            file_path: Path to file containing repository list

        Returns:
            List of repository identifiers

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty or invalid
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Repository list file not found: {file_path}")

        repos: list[str] = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                repos.append(line)

        if not repos:
            raise ValueError(f"No repositories found in file: {file_path}")

        return repos

    def validate_git_available(self) -> bool:
        """Check if git is available in the system.

        Returns:
            True if git is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "--version"], capture_output=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def estimate_disk_space(self, repo_inputs: list[str]) -> str:
        """Estimate disk space requirements for cloning repositories.

        Args:
            repo_inputs: List of repository identifiers

        Returns:
            Estimated disk space as human-readable string
        """
        # Rough estimate: average repository is ~10MB
        # This is very approximate - actual sizes vary wildly
        avg_size_mb = 10
        total_mb = len(repo_inputs) * avg_size_mb

        if total_mb < 1024:
            return f"~{total_mb}MB"
        else:
            return f"~{total_mb / 1024:.1f}GB"

    def cleanup_failed_clones(self, results: list[CloneResult]) -> int:
        """Clean up partially cloned repositories that failed.

        Args:
            results: List of clone results

        Returns:
            Number of directories cleaned up
        """
        cleaned = 0
        target_root = self.target_dir.resolve()

        for result in results:
            if result.success or result.skipped or result.cleanup_path is None:
                continue

            path = result.cleanup_path
            try:
                resolved = path.resolve()
            except OSError:
                continue

            # Only ever remove a path we created inside the target directory.
            # This blocks Path(".") and paths that escaped via traversal.
            if resolved == target_root or not resolved.is_relative_to(target_root):
                continue

            if not resolved.exists():
                continue

            try:
                if resolved.is_dir() and not resolved.is_symlink():
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink()
                cleaned += 1
            except OSError:
                # Ignore cleanup errors
                pass

        return cleaned
