# doctor

Check credentials, configuration, and optional tools.

## Usage

```bash
gh-toolkit doctor
```

The command is read-only. It prints a table and exits 1 when the GitHub token is
missing or invalid. Missing optional tools do not fail the check.

## Checks

- Python version
- gh-toolkit version
- GitHub token source and validity
- Token scopes when GitHub reports them
- Anthropic key presence and SDK version
- Config file location
- Optional tools: `gh`, `gita`, `git-reclaim`, `gx`

## Examples

```bash
gh-toolkit doctor
gh-toolkit doctor | grep -E "GitHub token|Anthropic|gx"
```
