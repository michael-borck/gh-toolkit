"""Integration tests for repo restore."""

import json

import responses
from typer.testing import CliRunner

from gh_toolkit.cli import app


def _write_backup(
    tmp_path, *, description="Old description", topics=None, archived=False
):
    path = tmp_path / "backup.json"
    path.write_text(
        json.dumps(
            {
                "format": "gh-toolkit-backup",
                "version": 1,
                "repos": [
                    {
                        "full_name": "user/repo",
                        "description": description,
                        "topics": topics if topics is not None else ["python"],
                        "archived": archived,
                    }
                ],
            }
        )
    )
    return path


class TestRepoRestore:
    @responses.activate
    def test_restores_description_and_topics(self, mock_github_token, tmp_path):
        backup = _write_backup(tmp_path)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "New description",
                "topics": ["python", "cli"],
                "archived": False,
            },
            status=200,
        )
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/user/repo",
            json={},
            status=200,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/user/repo/topics",
            json={"names": ["python"]},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "restore",
                str(backup),
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        patch_calls = [
            call for call in responses.calls if call.request.method == "PATCH"
        ]
        put_calls = [call for call in responses.calls if call.request.method == "PUT"]
        assert json.loads(patch_calls[0].request.body) == {
            "description": "Old description"
        }
        assert json.loads(put_calls[0].request.body) == {"names": ["python"]}

    @responses.activate
    def test_dry_run_makes_no_writes(self, mock_github_token, tmp_path):
        backup = _write_backup(tmp_path)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "New description",
                "topics": ["python", "cli"],
                "archived": False,
            },
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "restore",
                str(backup),
                "--dry-run",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert not any(
            call.request.method in ("PATCH", "PUT") for call in responses.calls
        )

    @responses.activate
    def test_skips_archived_by_default(self, mock_github_token, tmp_path):
        backup = _write_backup(tmp_path)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "New description",
                "topics": ["python", "cli"],
                "archived": True,
            },
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "restore",
                str(backup),
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert "Skipped archived" in result.stdout
        assert not any(
            call.request.method in ("PATCH", "PUT") for call in responses.calls
        )

    @responses.activate
    def test_only_topics(self, mock_github_token, tmp_path):
        backup = _write_backup(tmp_path)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/user/repo",
            json={
                "name": "repo",
                "full_name": "user/repo",
                "description": "New description",
                "topics": ["python", "cli"],
                "archived": False,
            },
            status=200,
        )
        responses.add(
            responses.PUT,
            "https://api.github.com/repos/user/repo/topics",
            json={"names": ["python"]},
            status=200,
        )

        result = CliRunner().invoke(
            app,
            [
                "repo",
                "restore",
                str(backup),
                "--only",
                "topics",
                "--yes",
                "--token",
                mock_github_token,
            ],
        )

        assert result.exit_code == 0
        assert not any(call.request.method == "PATCH" for call in responses.calls)
        assert any(call.request.method == "PUT" for call in responses.calls)

    def test_rejects_invalid_backup(self, mock_github_token, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"format": "not-a-backup"}))

        result = CliRunner().invoke(
            app,
            ["repo", "restore", str(path), "--token", mock_github_token],
        )

        assert result.exit_code == 1
        assert "Not a gh-toolkit backup" in result.stdout
