"""Unit tests for RepoCloner."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gh_toolkit.core.repo_cloner import CloneResult, CloneStats, RepoCloner


class TestRepoCloner:
    """Test RepoCloner functionality."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for testing."""
        return tmp_path / "repos"

    @pytest.fixture
    def repo_cloner(self, temp_dir):
        """Create RepoCloner instance for testing."""
        return RepoCloner(target_dir=temp_dir, parallel=2)

    def test_init(self, temp_dir):
        """Test RepoCloner initialization."""
        cloner = RepoCloner(target_dir=temp_dir, parallel=3)
        assert cloner.target_dir == temp_dir
        assert cloner.parallel == 3

    def test_init_defaults(self):
        """Test RepoCloner initialization with defaults."""
        cloner = RepoCloner()
        assert cloner.target_dir == Path("./repos")
        assert cloner.parallel == 4

    def test_parse_repo_input_owner_repo_format(self, repo_cloner):
        """Test parsing owner/repo format."""
        owner, repo = repo_cloner.parse_repo_input("microsoft/vscode")
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_owner_repo_with_git_suffix(self, repo_cloner):
        """Test parsing owner/repo format with .git suffix."""
        owner, repo = repo_cloner.parse_repo_input("microsoft/vscode.git")
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_https_url(self, repo_cloner):
        """Test parsing HTTPS GitHub URL."""
        owner, repo = repo_cloner.parse_repo_input(
            "https://github.com/microsoft/vscode"
        )
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_https_url_with_git(self, repo_cloner):
        """Test parsing HTTPS GitHub URL with .git suffix."""
        owner, repo = repo_cloner.parse_repo_input(
            "https://github.com/microsoft/vscode.git"
        )
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_ssh_url(self, repo_cloner):
        """Test parsing SSH GitHub URL."""
        owner, repo = repo_cloner.parse_repo_input(
            "git@github.com:microsoft/vscode.git"
        )
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_ssh_url_without_git(self, repo_cloner):
        """Test parsing SSH GitHub URL without .git suffix."""
        owner, repo = repo_cloner.parse_repo_input("git@github.com:microsoft/vscode")
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_input_invalid_format(self, repo_cloner):
        """Test parsing invalid repository format."""
        with pytest.raises(ValueError, match="Invalid repository format"):
            repo_cloner.parse_repo_input("invalid-format")

    def test_parse_repo_input_too_many_parts(self, repo_cloner):
        """Test parsing with too many parts."""
        with pytest.raises(ValueError, match="Invalid repository format"):
            repo_cloner.parse_repo_input("owner/repo/extra/parts")

    def test_parse_repo_input_empty(self, repo_cloner):
        """Test parsing empty input."""
        with pytest.raises(ValueError, match="Invalid repository format"):
            repo_cloner.parse_repo_input("")

    def test_parse_github_url_invalid_https(self, repo_cloner):
        """Test parsing invalid HTTPS URL."""
        with pytest.raises(ValueError, match="Invalid GitHub URL format"):
            repo_cloner._parse_github_url("https://gitlab.com/user/repo")

    def test_parse_github_url_invalid_ssh(self, repo_cloner):
        """Test parsing invalid SSH URL."""
        with pytest.raises(ValueError, match="Invalid GitHub URL format"):
            repo_cloner._parse_github_url("git@gitlab.com:user/repo.git")

    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_build_clone_url_auto_detect_ssh(self, mock_has_ssh, repo_cloner):
        """Test clone URL building with auto-detection (SSH available)."""
        mock_has_ssh.return_value = True
        url = repo_cloner.build_clone_url("owner", "repo")
        assert url == "git@github.com:owner/repo.git"

    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_build_clone_url_auto_detect_https(self, mock_has_ssh, repo_cloner):
        """Test clone URL building with auto-detection (SSH not available)."""
        mock_has_ssh.return_value = False
        url = repo_cloner.build_clone_url("owner", "repo")
        assert url == "https://github.com/owner/repo.git"

    def test_build_clone_url_force_ssh(self, repo_cloner):
        """Test clone URL building with forced SSH."""
        url = repo_cloner.build_clone_url("owner", "repo", use_ssh=True)
        assert url == "git@github.com:owner/repo.git"

    def test_build_clone_url_force_https(self, repo_cloner):
        """Test clone URL building with forced HTTPS."""
        url = repo_cloner.build_clone_url("owner", "repo", use_ssh=False)
        assert url == "https://github.com/owner/repo.git"

    @patch("subprocess.run")
    def test_has_ssh_key_ssh_agent_available(self, mock_run, repo_cloner):
        """Test SSH key detection with ssh-agent."""
        mock_run.return_value = Mock(returncode=0, stdout="ssh-rsa AAAAB3...")
        assert repo_cloner._has_ssh_key() is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    def test_has_ssh_key_file_available(self, mock_exists, mock_run, repo_cloner):
        """Test SSH key detection with key files."""
        mock_run.return_value = Mock(returncode=1, stdout="")
        mock_exists.return_value = True
        assert repo_cloner._has_ssh_key() is True

    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    def test_has_ssh_key_not_available(self, mock_exists, mock_run, repo_cloner):
        """Test SSH key detection when no keys available."""
        mock_run.return_value = Mock(returncode=1, stdout="")
        mock_exists.return_value = False
        assert repo_cloner._has_ssh_key() is False

    @patch("subprocess.run")
    def test_has_ssh_key_timeout(self, mock_run, repo_cloner):
        """Test SSH key detection with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("ssh-add", 5)
        assert repo_cloner._has_ssh_key() is False

    def test_get_target_path(self, repo_cloner):
        """Test target path generation."""
        path = repo_cloner.get_target_path("owner", "repo")
        expected = repo_cloner.target_dir / "owner" / "repo"
        assert path == expected

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_success(self, mock_has_ssh, mock_run, repo_cloner):
        """Test successful repository cloning."""
        mock_has_ssh.return_value = False  # Use HTTPS to avoid SSH key check
        mock_run.return_value = Mock(returncode=0, stderr="")

        result = repo_cloner.clone_repository("owner/repo")

        assert result.success is True
        assert result.repo_name == "owner/repo"
        assert result.error is None
        assert result.skipped is False
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_failure(self, mock_has_ssh, mock_run, repo_cloner):
        """Test failed repository cloning."""
        mock_has_ssh.return_value = False
        mock_run.return_value = Mock(returncode=1, stderr="Permission denied")

        result = repo_cloner.clone_repository("owner/repo")

        assert result.success is False
        assert result.repo_name == "owner/repo"
        assert result.error == "Permission denied"
        assert result.skipped is False

    def test_clone_repository_skip_existing(self, repo_cloner):
        """Test skipping existing repository."""
        # Create the target directory to simulate existing repo
        target_path = repo_cloner.get_target_path("owner", "repo")
        target_path.mkdir(parents=True, exist_ok=True)

        result = repo_cloner.clone_repository("owner/repo", skip_existing=True)

        assert result.success is False
        assert result.skipped is True
        assert result.skip_reason == "Repository already exists locally"

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_overwrite_existing(
        self, mock_has_ssh, mock_run, repo_cloner
    ):
        """Test overwriting existing repository."""
        mock_has_ssh.return_value = False
        # Create the target directory to simulate existing repo
        target_path = repo_cloner.get_target_path("owner", "repo")
        target_path.mkdir(parents=True, exist_ok=True)

        mock_run.return_value = Mock(returncode=0, stderr="")

        result = repo_cloner.clone_repository("owner/repo", skip_existing=False)

        assert result.success is True
        assert result.skipped is False

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_with_branch(self, mock_has_ssh, mock_run, repo_cloner):
        """Test cloning with specific branch."""
        mock_has_ssh.return_value = False
        mock_run.return_value = Mock(returncode=0, stderr="")

        repo_cloner.clone_repository("owner/repo", branch="develop")

        # Check that the command includes branch option
        args = mock_run.call_args[0][0]
        assert "--branch" in args
        assert "develop" in args

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_with_depth(self, mock_has_ssh, mock_run, repo_cloner):
        """Test cloning with specific depth."""
        mock_has_ssh.return_value = False
        mock_run.return_value = Mock(returncode=0, stderr="")

        repo_cloner.clone_repository("owner/repo", depth=1)

        # Check that the command includes depth option
        args = mock_run.call_args[0][0]
        assert "--depth" in args
        assert "1" in args

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repository_timeout(self, mock_has_ssh, mock_run, repo_cloner):
        """Test clone operation timeout."""
        mock_has_ssh.return_value = False
        mock_run.side_effect = subprocess.TimeoutExpired("git", 300)

        result = repo_cloner.clone_repository("owner/repo")

        assert result.success is False
        assert "timed out" in result.error

    def test_clone_repository_invalid_input(self, repo_cloner):
        """Test cloning with invalid repository input."""
        result = repo_cloner.clone_repository("invalid-input")

        assert result.success is False
        assert "Invalid repository format" in result.error

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repositories_parallel(self, mock_has_ssh, mock_run, repo_cloner):
        """Test parallel cloning of multiple repositories."""
        mock_has_ssh.return_value = False
        mock_run.return_value = Mock(returncode=0, stderr="")

        repos = ["owner1/repo1", "owner2/repo2", "owner3/repo3"]
        results, stats = repo_cloner.clone_repositories(repos)

        assert len(results) == 3
        assert stats.total_repos == 3
        assert stats.successful == 3
        assert stats.failed == 0
        assert stats.skipped == 0

    @patch("subprocess.run")
    @patch("gh_toolkit.core.repo_cloner.RepoCloner._has_ssh_key")
    def test_clone_repositories_with_callback(
        self, mock_has_ssh, mock_run, repo_cloner
    ):
        """Test parallel cloning with progress callback."""
        mock_has_ssh.return_value = False
        mock_run.return_value = Mock(returncode=0, stderr="")

        callback_calls = []

        def progress_callback(result, completed, total):
            callback_calls.append((result.repo_name, completed, total))

        repos = ["owner1/repo1", "owner2/repo2"]
        results, stats = repo_cloner.clone_repositories(
            repos, progress_callback=progress_callback
        )

        assert len(callback_calls) == 2
        assert all(call[2] == 2 for call in callback_calls)  # Total should be 2

    def test_generate_stats(self, repo_cloner):
        """Test statistics generation."""
        results = [
            CloneResult("repo1", "url1", Path("path1"), True),
            CloneResult("repo2", "url2", Path("path2"), False, error="Failed"),
            CloneResult(
                "repo3",
                "url3",
                Path("path3"),
                False,
                skipped=True,
                skip_reason="Exists",
            ),
        ]

        stats = repo_cloner._generate_stats(results)

        assert stats.total_repos == 3
        assert stats.successful == 1
        assert stats.failed == 1
        assert stats.skipped == 1
        assert len(stats.errors) == 1

    def test_read_repo_list_valid_file(self, repo_cloner, tmp_path):
        """Test reading repository list from valid file."""
        repo_file = tmp_path / "repos.txt"
        repo_file.write_text("owner1/repo1\nowner2/repo2\n# Comment\n\nowner3/repo3\n")

        repos = repo_cloner.read_repo_list(repo_file)

        assert repos == ["owner1/repo1", "owner2/repo2", "owner3/repo3"]

    def test_read_repo_list_nonexistent_file(self, repo_cloner):
        """Test reading from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            repo_cloner.read_repo_list("nonexistent.txt")

    def test_read_repo_list_empty_file(self, repo_cloner, tmp_path):
        """Test reading from empty file."""
        repo_file = tmp_path / "empty.txt"
        repo_file.write_text("# Only comments\n\n")

        with pytest.raises(ValueError, match="No repositories found"):
            repo_cloner.read_repo_list(repo_file)

    @patch("subprocess.run")
    def test_validate_git_available(self, mock_run, repo_cloner):
        """Test git availability validation."""
        mock_run.return_value = Mock(returncode=0)
        assert repo_cloner.validate_git_available() is True

    @patch("subprocess.run")
    def test_validate_git_not_available(self, mock_run, repo_cloner):
        """Test git not available."""
        mock_run.side_effect = FileNotFoundError()
        assert repo_cloner.validate_git_available() is False

    @patch("subprocess.run")
    def test_validate_git_timeout(self, mock_run, repo_cloner):
        """Test git validation timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 10)
        assert repo_cloner.validate_git_available() is False

    def test_estimate_disk_space_small(self, repo_cloner):
        """Test disk space estimation for small number of repos."""
        repos = ["repo1", "repo2"]
        estimate = repo_cloner.estimate_disk_space(repos)
        assert "MB" in estimate
        assert "20" in estimate

    def test_estimate_disk_space_large(self, repo_cloner):
        """Test disk space estimation for large number of repos."""
        repos = [f"repo{i}" for i in range(200)]  # 200 repos = ~2GB
        estimate = repo_cloner.estimate_disk_space(repos)
        assert "GB" in estimate

    def test_concurrent_clone_same_repo_only_clones_once(self, tmp_path):
        """Parallel workers must not race to clone the same target path."""
        import threading

        cloner = RepoCloner(target_dir=tmp_path, parallel=4)
        barrier = threading.Barrier(4)
        clone_calls: list[list[str]] = []
        call_lock = threading.Lock()

        def fake_run(cmd, **kwargs):
            # All threads that got past the claim would land here together
            with call_lock:
                clone_calls.append(cmd)
            return Mock(returncode=0, stdout="", stderr="")

        def attempt():
            barrier.wait()
            return cloner.clone_repository(
                "user/repo", use_ssh=False, skip_existing=True
            )

        with patch("subprocess.run", side_effect=fake_run):
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                results = list(ex.map(lambda _: attempt(), range(4)))

        # Exactly one thread performs the clone; the rest are skipped
        git_clones = [c for c in clone_calls if c[:2] == ["git", "clone"]]
        assert len(git_clones) == 1
        assert sum(1 for r in results if r.success) == 1
        assert sum(1 for r in results if r.skipped) == 3

    def test_parse_repo_input_rejects_traversal(self, repo_cloner):
        """Owner/repo names that could escape the target dir are rejected."""
        for bad in ["../etc/passwd", "owner/..", "owner/re po"]:
            with pytest.raises(ValueError):
                repo_cloner.parse_repo_input(bad)

    @patch("shutil.rmtree")
    def test_cleanup_failed_clones(self, mock_rmtree, repo_cloner, tmp_path):
        """Test cleanup of failed clone directories."""
        # Create some test directories
        failed_path1 = tmp_path / "failed1"
        failed_path2 = tmp_path / "failed2"
        success_path = tmp_path / "success"

        failed_path1.mkdir()
        failed_path2.mkdir()
        success_path.mkdir()

        results = [
            CloneResult("failed1", "url1", failed_path1, False, error="Failed"),
            CloneResult("failed2", "url2", failed_path2, False, error="Failed"),
            CloneResult("success", "url3", success_path, True),
            CloneResult("skipped", "url4", Path("nonexistent"), False, skipped=True),
        ]

        cleaned = repo_cloner.cleanup_failed_clones(results)

        assert cleaned == 2
        assert mock_rmtree.call_count == 2

    @patch("shutil.rmtree")
    def test_cleanup_failed_clones_ignore_errors(
        self, mock_rmtree, repo_cloner, tmp_path
    ):
        """Test cleanup ignores errors during removal."""
        mock_rmtree.side_effect = OSError("Permission denied")

        failed_path = tmp_path / "failed"
        failed_path.mkdir()

        results = [
            CloneResult("failed", "url", failed_path, False, error="Failed"),
        ]

        # Should not raise exception
        cleaned = repo_cloner.cleanup_failed_clones(results)
        assert cleaned == 0  # No successful cleanups due to error


class TestDeadlineSnapshot:
    """Test --before deadline-snapshot checkout."""

    @pytest.fixture
    def repo_cloner(self, tmp_path):
        return RepoCloner(target_dir=tmp_path / "repos", parallel=1)

    def test_checkout_before_finds_commit(self, repo_cloner, tmp_path):
        def fake_run(cmd, **kwargs):
            if "rev-list" in cmd:
                return Mock(returncode=0, stdout="abc123def456789\n", stderr="")
            if "checkout" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            note = repo_cloner._checkout_before(tmp_path, "2020-01-01 00:00")

        assert "abc123de" in note
        assert "Snapshot" in note

    def test_checkout_before_no_commit(self, repo_cloner, tmp_path):
        def fake_run(cmd, **kwargs):
            if "rev-list" in cmd:
                return Mock(returncode=0, stdout="\n", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            note = repo_cloner._checkout_before(tmp_path, "2000-01-01")

        assert note.startswith("No commit before")

    def test_checkout_before_rev_list_error(self, repo_cloner, tmp_path):
        def fake_run(cmd, **kwargs):
            if "rev-list" in cmd:
                return Mock(returncode=128, stdout="", stderr="bad revision")
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            note = repo_cloner._checkout_before(tmp_path, "nonsense")

        assert "Could not resolve" in note

    def test_clone_with_before_forces_full_clone_and_checks_out(
        self, repo_cloner, tmp_path
    ):
        clone_cmds = []

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "clone"]:
                clone_cmds.append(cmd)
                return Mock(returncode=0, stdout="", stderr="")
            if "rev-list" in cmd:
                return Mock(returncode=0, stdout="deadbeef1234\n", stderr="")
            if "checkout" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = repo_cloner.clone_repository(
                "user/repo",
                use_ssh=False,
                depth=1,  # should be dropped because --before needs full history
                before="2026-06-12 23:59",
            )

        assert result.success
        assert result.note is not None
        assert "deadbeef" in result.note
        # --depth must NOT appear in the clone command when --before is used
        assert "--depth" not in clone_cmds[0]


class TestCloneResult:
    """Test CloneResult dataclass."""

    def test_clone_result_success(self):
        """Test successful clone result."""
        result = CloneResult(
            "owner/repo", "https://github.com/owner/repo.git", Path("/path"), True
        )
        assert result.success is True
        assert result.skipped is False
        assert result.error is None

    def test_clone_result_failure(self):
        """Test failed clone result."""
        result = CloneResult("owner/repo", "url", Path("/path"), False, error="Failed")
        assert result.success is False
        assert result.error == "Failed"

    def test_clone_result_skipped(self):
        """Test skipped clone result."""
        result = CloneResult(
            "owner/repo",
            "url",
            Path("/path"),
            False,
            skipped=True,
            skip_reason="Exists",
        )
        assert result.skipped is True
        assert result.skip_reason == "Exists"


class TestCloneStats:
    """Test CloneStats dataclass."""

    def test_clone_stats(self):
        """Test clone statistics."""
        error_result = CloneResult("repo", "url", Path("/path"), False, error="Failed")
        stats = CloneStats(
            total_repos=10, successful=7, failed=2, skipped=1, errors=[error_result]
        )

        assert stats.total_repos == 10
        assert stats.successful == 7
        assert stats.failed == 2
        assert stats.skipped == 1
        assert len(stats.errors) == 1
