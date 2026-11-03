"""Environment and credential diagnostics."""

from __future__ import annotations

import os
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version

import typer
from rich.console import Console
from rich.table import Table

from gh_toolkit import __version__
from gh_toolkit.core.config import config_file, resolve_token, token_source
from gh_toolkit.core.github_client import GitHubAPIError, GitHubClient

console = Console()

_OPTIONAL_TOOLS = ("gh", "gita", "git-reclaim", "gx")


def doctor() -> None:
    """Check credentials, optional tools, and configuration.

    This command is read-only. It prints a table and exits 1 when the GitHub
    token is missing or invalid. Missing optional tools do not fail the check.
    """
    rows: list[tuple[str, str, str]] = [
        ("Python", "ok", sys.version.split()[0]),
        ("gh-toolkit", "ok", __version__),
    ]

    source = token_source()
    token = resolve_token()
    token_ok = False

    if not token:
        rows.append(
            (
                "GitHub token",
                "missing",
                "set GITHUB_TOKEN, use --token, or run gh auth login",
            )
        )
    else:
        client = GitHubClient(token)
        try:
            response = client.request("GET", "/user")
            data = response.json()
            login = data.get("login", "unknown")
            scopes = response.headers.get("X-OAuth-Scopes", "")
            detail = f"{login} via {source}"
            if scopes:
                detail += f"; scopes: {scopes}"
            else:
                detail += "; scopes not reported"
            rows.append(("GitHub token", "ok", detail))
            token_ok = True
        except GitHubAPIError as e:
            rows.append(("GitHub token", "invalid", f"{source}: {e.message}"))

    if os.environ.get("ANTHROPIC_API_KEY"):
        rows.append(("Anthropic key", "ok", "ANTHROPIC_API_KEY"))
    else:
        rows.append(
            (
                "Anthropic key",
                "optional",
                "not set; LLM features fall back to rules",
            )
        )

    try:
        rows.append(("anthropic", "ok", version("anthropic")))
    except PackageNotFoundError:
        rows.append(("anthropic", "missing", "pip install anthropic"))

    config_path = config_file()
    rows.append(
        (
            "config",
            "ok" if config_path else "none",
            str(config_path) if config_path else "no config file",
        )
    )

    for tool in _OPTIONAL_TOOLS:
        path = shutil.which(tool)
        rows.append((tool, "ok" if path else "missing", path or "not on PATH"))

    table = Table(title="gh-toolkit doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", style="white")

    styles = {
        "ok": "green",
        "missing": "red",
        "invalid": "red",
        "optional": "yellow",
        "none": "dim",
    }
    for check, status, detail in rows:
        style = styles.get(status, "white")
        table.add_row(check, f"[{style}]{status}[/]", detail)

    console.print(table)

    if not token_ok:
        raise typer.Exit(1)
