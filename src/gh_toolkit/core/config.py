"""Configuration loading and credential resolution.

Centralizes where a GitHub token comes from and reads an optional TOML config
file so users don't have to repeat the same flags on every command.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


def _config_paths() -> list[Path]:
    """Config file search path, highest precedence first.

    A project-local ``gh-toolkit.toml`` overrides the user-level config so a
    repo can pin its own defaults.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    user_base = Path(xdg) if xdg else Path.home() / ".config"
    return [
        Path.cwd() / "gh-toolkit.toml",
        user_base / "gh-toolkit" / "config.toml",
    ]


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Load the first config file found, or an empty dict if none/invalid.

    Cached for the process lifetime. A malformed file is treated as absent
    rather than crashing every command.
    """
    for path in _config_paths():
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    return tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                return {}
    return {}


def get_setting(key: str, default: Any = None) -> Any:
    """Read a top-level setting from the config file."""
    return load_config().get(key, default)


def _gh_cli_token() -> str | None:
    """Return the token from the `gh` CLI if it is installed and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def resolve_token(cli_token: str | None = None) -> str | None:
    """Resolve a GitHub token from the first available source.

    Precedence: explicit ``--token`` flag, then ``GITHUB_TOKEN`` env var, then
    a ``token`` key in the config file, then the ``gh`` CLI's stored token.
    Returns None when no source provides one.
    """
    if cli_token:
        return cli_token
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token
    config_token = get_setting("token")
    if config_token:
        return str(config_token)
    return _gh_cli_token()
