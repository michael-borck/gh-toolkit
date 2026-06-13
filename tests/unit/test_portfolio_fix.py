"""Unit tests for portfolio audit --fix orchestration (_apply_audit_fixes)."""

import pytest

from gh_toolkit.commands.portfolio import _apply_audit_fixes


def _report(*issue_pairs):
    """Build an audit report from (repo, issue_type) pairs."""
    return {
        "issues": [
            {"repo": repo, "issue_type": kind, "org": "o"} for repo, kind in issue_pairs
        ]
    }


@pytest.fixture
def fixers(mocker):
    """Patch the three fixer classes; return their instance mocks."""
    desc = mocker.patch(
        "gh_toolkit.core.description_generator.DescriptionGenerator"
    ).return_value
    tag = mocker.patch("gh_toolkit.core.topic_tagger.TopicTagger").return_value
    lic = mocker.patch("gh_toolkit.core.license_manager.LicenseManager").return_value
    return desc, tag, lic


class TestApplyAuditFixes:
    def test_fixes_description_and_topics(self, mocker, fixers):
        desc, tag, lic = fixers
        report = _report(
            ("org/repo", "missing_description"), ("org/repo", "missing_topics")
        )

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=True,
        )

        desc.process_repository.assert_called_once_with("org", "repo", dry_run=False)
        tag.process_repository.assert_called_once_with("org", "repo", dry_run=False)
        lic.add_license.assert_not_called()  # no --license

    def test_license_skipped_without_key(self, mocker, fixers):
        desc, tag, lic = fixers
        report = _report(("org/repo", "missing_license"))

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=True,
        )

        lic.add_license.assert_not_called()
        desc.process_repository.assert_not_called()

    def test_license_applied_with_key(self, mocker, fixers):
        desc, tag, lic = fixers
        report = _report(("org/repo", "missing_license"))

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key="mit",
            dry_run=False,
            assume_yes=True,
        )

        lic.add_license.assert_called_once_with("org", "repo", "mit", dry_run=False)

    def test_dry_run_passes_through_and_skips_confirm(self, mocker, fixers):
        desc, tag, lic = fixers
        confirm = mocker.patch("gh_toolkit.commands.portfolio.typer.confirm")
        report = _report(("org/repo", "missing_description"))

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=True,
            assume_yes=False,
        )

        desc.process_repository.assert_called_once_with("org", "repo", dry_run=True)
        confirm.assert_not_called()  # dry-run never prompts

    def test_declined_confirmation_makes_no_changes(self, mocker, fixers):
        desc, tag, lic = fixers
        mocker.patch("gh_toolkit.commands.portfolio.typer.confirm", return_value=False)
        report = _report(("org/repo", "missing_description"))

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=False,
        )

        desc.process_repository.assert_not_called()

    def test_repo_without_owner_skipped(self, mocker, fixers):
        desc, tag, lic = fixers
        report = _report(("bareword", "missing_description"))

        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=True,
        )

        desc.process_repository.assert_not_called()

    def test_nothing_to_fix(self, mocker, fixers):
        desc, tag, lic = fixers
        _apply_audit_fixes(
            mocker.Mock(),
            {"issues": []},
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=True,
        )
        desc.process_repository.assert_not_called()

    def test_api_error_isolated_per_repo(self, mocker, fixers):
        from gh_toolkit.core.github_client import GitHubAPIError

        desc, tag, lic = fixers
        desc.process_repository.side_effect = GitHubAPIError("nope", 403)
        report = _report(
            ("org/a", "missing_description"), ("org/b", "missing_description")
        )

        # Should not raise despite one repo failing
        _apply_audit_fixes(
            mocker.Mock(),
            report,
            anthropic_api_key=None,
            license_key=None,
            dry_run=False,
            assume_yes=True,
        )

        assert desc.process_repository.call_count == 2
