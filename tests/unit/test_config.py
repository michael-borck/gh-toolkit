"""Unit tests for config loading and token resolution."""

from gh_toolkit.core import config


class TestResolveToken:
    """Token resolution precedence: CLI > env > config > gh CLI."""

    def test_cli_token_wins(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        monkeypatch.setattr(config, "load_config", lambda: {"token": "cfg-token"})
        monkeypatch.setattr(config, "_gh_cli_token", lambda: "gh-token")

        assert config.resolve_token("cli-token") == "cli-token"

    def test_env_token_used_when_no_cli(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        monkeypatch.setattr(config, "load_config", lambda: {"token": "cfg-token"})
        monkeypatch.setattr(config, "_gh_cli_token", lambda: "gh-token")

        assert config.resolve_token(None) == "env-token"

    def test_config_token_used_when_no_cli_or_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(config, "load_config", lambda: {"token": "cfg-token"})
        monkeypatch.setattr(config, "_gh_cli_token", lambda: "gh-token")

        assert config.resolve_token(None) == "cfg-token"

    def test_gh_cli_token_is_last_resort(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(config, "load_config", lambda: {})
        monkeypatch.setattr(config, "_gh_cli_token", lambda: "gh-token")

        assert config.resolve_token(None) == "gh-token"

    def test_returns_none_when_nothing_available(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(config, "load_config", lambda: {})
        monkeypatch.setattr(config, "_gh_cli_token", lambda: None)

        assert config.resolve_token(None) is None


class TestGhCliToken:
    """The `gh auth token` shell-out fallback."""

    def test_returns_token_on_success(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "gho_fromcli\n"

        monkeypatch.setattr(config.subprocess, "run", lambda *a, **k: _Result())
        assert config._gh_cli_token() == "gho_fromcli"

    def test_returns_none_when_gh_not_installed(self, monkeypatch):
        def _raise(*a, **k):
            raise FileNotFoundError

        monkeypatch.setattr(config.subprocess, "run", _raise)
        assert config._gh_cli_token() is None

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        class _Result:
            returncode = 1
            stdout = ""

        monkeypatch.setattr(config.subprocess, "run", lambda *a, **k: _Result())
        assert config._gh_cli_token() is None

    def test_returns_none_on_empty_output(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "   \n"

        monkeypatch.setattr(config.subprocess, "run", lambda *a, **k: _Result())
        assert config._gh_cli_token() is None


class TestLoadConfig:
    """Config file discovery and parsing."""

    def test_loads_project_local_config(self, monkeypatch, tmp_path):
        config.load_config.cache_clear()
        (tmp_path / "gh-toolkit.toml").write_text(
            'token = "from-file"\ntheme = "resume"\n'
        )
        monkeypatch.chdir(tmp_path)

        cfg = config.load_config()
        assert cfg["token"] == "from-file"
        assert cfg["theme"] == "resume"
        config.load_config.cache_clear()

    def test_missing_config_returns_empty(self, monkeypatch, tmp_path):
        config.load_config.cache_clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))

        assert config.load_config() == {}
        config.load_config.cache_clear()

    def test_malformed_config_returns_empty(self, monkeypatch, tmp_path):
        config.load_config.cache_clear()
        (tmp_path / "gh-toolkit.toml").write_text("this is = = not valid toml")
        monkeypatch.chdir(tmp_path)

        assert config.load_config() == {}
        config.load_config.cache_clear()
