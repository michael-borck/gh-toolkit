"""Unit tests for LicenseManager."""

import base64
import json
from datetime import datetime

import responses

from gh_toolkit.core.github_client import GitHubClient
from gh_toolkit.core.license_manager import (
    COMMON_LICENSES,
    DEFAULT_LICENSE,
    LicenseManager,
)

MIT_TEMPLATE_BODY = (
    "MIT License\n"
    "\n"
    "Copyright (c) [year] [fullname]\n"
    "\n"
    "Permission is hereby granted, free of charge, to any person obtaining a "
    "copy of this software and associated documentation files (the "
    '"Software"), to deal in the Software without restriction.\n'
)

MIT_TEMPLATE = {
    "key": "mit",
    "name": "MIT License",
    "spdx_id": "MIT",
    "body": MIT_TEMPLATE_BODY,
}


def make_manager(token: str, rate_limit: float = 0.5) -> LicenseManager:
    """Create a LicenseManager with a real GitHubClient."""
    return LicenseManager(GitHubClient(token), rate_limit=rate_limit)


def add_repo_response(license_info: dict | None) -> None:
    """Register a GET /repos/testuser/test-repo response."""
    responses.add(
        responses.GET,
        "https://api.github.com/repos/testuser/test-repo",
        json={
            "name": "test-repo",
            "full_name": "testuser/test-repo",
            "license": license_info,
        },
        status=200,
    )


class TestLicenseManagerInit:
    """Test LicenseManager initialization."""

    def test_init_defaults(self, mock_github_token):
        client = GitHubClient(mock_github_token)
        manager = LicenseManager(client)

        assert manager.client is client
        assert manager.rate_limit == 0.5
        assert manager._license_cache == {}

    def test_init_custom_rate_limit(self, mock_github_token):
        manager = make_manager(mock_github_token, rate_limit=1.5)
        assert manager.rate_limit == 1.5

    def test_common_licenses_constants(self):
        assert DEFAULT_LICENSE == "mit"
        assert DEFAULT_LICENSE in COMMON_LICENSES
        assert "apache-2.0" in COMMON_LICENSES
        assert "gpl-3.0" in COMMON_LICENSES


class TestGetAvailableLicenses:
    """Test fetching the list of available licenses."""

    @responses.activate
    def test_success(self, mock_github_token):
        licenses = [
            {"key": "mit", "name": "MIT License", "spdx_id": "MIT"},
            {
                "key": "apache-2.0",
                "name": "Apache License 2.0",
                "spdx_id": "Apache-2.0",
            },
        ]
        responses.add(
            responses.GET,
            "https://api.github.com/licenses",
            json=licenses,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.get_available_licenses()

        assert result == licenses

    @responses.activate
    def test_api_failure_returns_empty_list(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/licenses",
            json={"message": "Server Error"},
            status=500,
        )

        manager = make_manager(mock_github_token)
        result = manager.get_available_licenses()

        assert result == []


class TestGetLicenseTemplate:
    """Test fetching a single license template."""

    @responses.activate
    def test_success(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.get_license_template("mit")

        assert result == MIT_TEMPLATE

    @responses.activate
    def test_key_is_lowercased_in_endpoint(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.get_license_template("MIT")

        assert result == MIT_TEMPLATE
        assert responses.calls[0].request.url == "https://api.github.com/licenses/mit"

    @responses.activate
    def test_caches_template(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        first = manager.get_license_template("mit")
        second = manager.get_license_template("mit")

        assert first == second == MIT_TEMPLATE
        assert len(responses.calls) == 1  # Second call served from cache
        assert manager._license_cache["mit"] == MIT_TEMPLATE

    @responses.activate
    def test_not_found_returns_none(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/bogus-license",
            json={"message": "Not Found"},
            status=404,
        )

        manager = make_manager(mock_github_token)
        result = manager.get_license_template("bogus-license")

        assert result is None
        assert "bogus-license" not in manager._license_cache

    @responses.activate
    def test_not_found_is_not_cached(self, mock_github_token):
        """A failed lookup is retried on the next call."""
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json={"message": "Server Error"},
            status=500,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        assert manager.get_license_template("mit") is None
        assert manager.get_license_template("mit") == MIT_TEMPLATE


class TestCheckRepoLicense:
    """Test checking a repository's existing license."""

    @responses.activate
    def test_repo_with_license(self, mock_github_token):
        add_repo_response({"key": "mit", "spdx_id": "MIT", "name": "MIT License"})

        manager = make_manager(mock_github_token)
        result = manager.check_repo_license("testuser", "test-repo")

        assert result == {"key": "mit", "spdx_id": "MIT", "name": "MIT License"}

    @responses.activate
    def test_repo_without_license(self, mock_github_token):
        add_repo_response(None)

        manager = make_manager(mock_github_token)
        result = manager.check_repo_license("testuser", "test-repo")

        assert result is None

    @responses.activate
    def test_repo_not_found(self, mock_github_token):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/missing-repo",
            json={"message": "Not Found"},
            status=404,
        )

        manager = make_manager(mock_github_token)
        result = manager.check_repo_license("testuser", "missing-repo")

        assert result is None


class TestFormatLicenseBody:
    """Test license template placeholder substitution."""

    def test_replaces_year_and_fullname(self, mock_github_token):
        manager = make_manager(mock_github_token)
        result = manager.format_license_body(
            "Copyright (c) [year] [fullname]", full_name="Jane Doe", year=2024
        )
        assert result == "Copyright (c) 2024 Jane Doe"

    def test_default_year_is_current_year(self, mock_github_token):
        manager = make_manager(mock_github_token)
        result = manager.format_license_body("Copyright [yyyy]", full_name="Jane")
        assert result == f"Copyright {datetime.now().year}"

    def test_all_year_placeholder_variants(self, mock_github_token):
        manager = make_manager(mock_github_token)
        result = manager.format_license_body("[year] [yyyy] <year>", year=2025)
        assert result == "2025 2025 2025"

    def test_all_name_placeholder_variants(self, mock_github_token):
        manager = make_manager(mock_github_token)
        template = (
            "[fullname] / [name of copyright owner] / <name of author> / "
            "[name] / <copyright holders> / [copyright holders]"
        )
        result = manager.format_license_body(template, full_name="Jane", year=2025)
        assert result == "Jane / Jane / Jane / Jane / Jane / Jane"

    def test_no_fullname_leaves_name_placeholders(self, mock_github_token):
        manager = make_manager(mock_github_token)
        result = manager.format_license_body(
            "Copyright (c) [year] [fullname]", year=2024
        )
        assert result == "Copyright (c) 2024 [fullname]"


class TestAddLicense:
    """Test adding a license file to a repository."""

    @responses.activate
    def test_skipped_when_license_exists(self, mock_github_token):
        add_repo_response({"key": "apache-2.0", "spdx_id": "Apache-2.0"})

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit")

        assert result["status"] == "skipped"
        assert "Apache-2.0" in result["reason"]
        # Only the repo check should have been made
        assert len(responses.calls) == 1

    @responses.activate
    def test_error_when_template_not_found(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/bogus",
            json={"message": "Not Found"},
            status=404,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "bogus")

        assert result["status"] == "error"
        assert result["reason"] == "License template not found: bogus"

    @responses.activate
    def test_error_when_template_has_no_body(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json={"key": "mit", "spdx_id": "MIT", "body": ""},
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit")

        assert result["status"] == "error"
        assert result["reason"] == "License template has no body"

    @responses.activate
    def test_dry_run_create(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license(
            "testuser", "test-repo", "mit", full_name="Jane Doe", dry_run=True
        )

        assert result["status"] == "dry_run"
        assert result["action"] == "create"
        assert "Jane Doe" in result["content_preview"]
        # No write requests were made
        assert all(call.request.method == "GET" for call in responses.calls)

    @responses.activate
    def test_dry_run_force_replace(self, mock_github_token):
        add_repo_response({"key": "apache-2.0", "spdx_id": "Apache-2.0"})
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license(
            "testuser", "test-repo", "mit", dry_run=True, force=True
        )

        assert result["status"] == "dry_run"
        assert result["action"] == "replace"

    @responses.activate
    def test_content_preview_truncated_to_200_chars(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit", dry_run=True)

        assert result["content_preview"].endswith("...")
        assert len(result["content_preview"]) == 203

    @responses.activate
    def test_create_license_file(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )
        # No existing LICENSE file
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"message": "Not Found"},
            status=404,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"content": {"name": "LICENSE"}},
            status=201,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit")

        assert result["status"] == "created"
        assert result["action"] == "create"

        put_request = responses.calls[-1].request
        assert put_request.method == "PUT"
        payload = json.loads(put_request.body)
        assert "sha" not in payload
        assert payload["message"].startswith("Add MIT license")

        decoded = base64.b64decode(payload["content"]).decode("utf-8")
        # full_name defaults to owner, year defaults to current year
        assert "testuser" in decoded
        assert str(datetime.now().year) in decoded
        assert "[fullname]" not in decoded
        assert "[year]" not in decoded

    @responses.activate
    def test_update_existing_license_file_with_force(self, mock_github_token):
        add_repo_response({"key": "apache-2.0", "spdx_id": "Apache-2.0"})
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"sha": "abc123", "name": "LICENSE"},
            status=200,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"content": {"name": "LICENSE"}},
            status=200,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit", force=True)

        assert result["status"] == "updated"
        assert result["action"] == "replace"

        payload = json.loads(responses.calls[-1].request.body)
        assert payload["sha"] == "abc123"

    @responses.activate
    def test_put_failure_returns_error(self, mock_github_token):
        add_repo_response(None)
        responses.add(
            responses.GET,
            "https://api.github.com/licenses/mit",
            json=MIT_TEMPLATE,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"message": "Not Found"},
            status=404,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/testuser/test-repo/contents/LICENSE",
            json={"message": "Validation Failed"},
            status=422,
        )

        manager = make_manager(mock_github_token)
        result = manager.add_license("testuser", "test-repo", "mit")

        assert result["status"] == "error"
        assert "422" in result["reason"]


class TestProcessRepository:
    """Test single-repository processing with rate limiting."""

    def test_returns_result_and_sleeps(self, mock_github_token, mocker):
        mock_add = mocker.patch.object(
            LicenseManager,
            "add_license",
            return_value={"status": "created", "owner": "u", "repo": "r"},
        )
        mock_sleep = mocker.patch("time.sleep")

        manager = make_manager(mock_github_token)
        result = manager.process_repository("u", "r", "mit", "Jane", False, True)

        assert result["status"] == "created"
        mock_add.assert_called_once_with("u", "r", "mit", "Jane", False, True)
        mock_sleep.assert_called_once_with(0.5)

    def test_custom_rate_limit(self, mock_github_token, mocker):
        mocker.patch.object(
            LicenseManager, "add_license", return_value={"status": "skipped"}
        )
        mock_sleep = mocker.patch("time.sleep")

        manager = make_manager(mock_github_token, rate_limit=2.0)
        manager.process_repository("u", "r")

        mock_sleep.assert_called_once_with(2.0)


class TestProcessMultipleRepositories:
    """Test batch repository processing."""

    def test_processes_all_repos(self, mock_github_token, mocker):
        mock_process = mocker.patch.object(LicenseManager, "process_repository")
        mock_process.side_effect = [
            {"owner": "u", "repo": "repo1", "status": "created"},
            {"owner": "u", "repo": "repo2", "status": "skipped", "reason": "has one"},
            {"owner": "u", "repo": "repo3", "status": "updated"},
            {"owner": "u", "repo": "repo4", "status": "dry_run", "action": "create"},
            {"owner": "u", "repo": "repo5", "status": "error", "reason": "boom"},
        ]

        manager = make_manager(mock_github_token)
        repos = [("u", f"repo{i}") for i in range(1, 6)]
        results = manager.process_multiple_repositories(repos, "mit")

        assert len(results) == 5
        assert [r["status"] for r in results] == [
            "created",
            "skipped",
            "updated",
            "dry_run",
            "error",
        ]
        assert mock_process.call_count == 5

    def test_exception_recorded_as_error_result(self, mock_github_token, mocker):
        mock_process = mocker.patch.object(LicenseManager, "process_repository")
        mock_process.side_effect = [
            {"owner": "u", "repo": "repo1", "status": "created"},
            RuntimeError("network down"),
            {"owner": "u", "repo": "repo3", "status": "created"},
        ]

        manager = make_manager(mock_github_token)
        repos = [("u", "repo1"), ("u", "repo2"), ("u", "repo3")]
        results = manager.process_multiple_repositories(repos)

        assert len(results) == 3
        assert results[1] == {
            "owner": "u",
            "repo": "repo2",
            "status": "error",
            "reason": "network down",
        }
        # Processing continues after the failure
        assert results[2]["status"] == "created"

    def test_empty_repo_list(self, mock_github_token, mocker):
        mock_process = mocker.patch.object(LicenseManager, "process_repository")

        manager = make_manager(mock_github_token)
        results = manager.process_multiple_repositories([])

        assert results == []
        mock_process.assert_not_called()

    def test_passes_arguments_through(self, mock_github_token, mocker):
        mock_process = mocker.patch.object(
            LicenseManager, "process_repository", return_value={"status": "dry_run"}
        )

        manager = make_manager(mock_github_token)
        manager.process_multiple_repositories(
            [("owner1", "repo1")],
            license_key="apache-2.0",
            full_name="Jane Doe",
            dry_run=True,
            force=True,
        )

        mock_process.assert_called_once_with(
            "owner1", "repo1", "apache-2.0", "Jane Doe", True, True
        )
