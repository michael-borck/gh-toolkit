# repo audit

Read-only audit of repository descriptions, Australian spelling, and topic
hygiene. It also writes a restore-ready backup of the current descriptions and
topics so later bulk edits have a rollback point.

`repo audit` never changes a repository.

## Usage

```bash
# Audit your public repositories
gh-toolkit repo audit --user

# Include private repositories
gh-toolkit repo audit --user --include-private

# Audit one or more organizations
gh-toolkit repo audit --org my-org
gh-toolkit repo audit --org org-one --org org-two

# Machine-readable report
gh-toolkit repo audit --user --include-private --json

# Write the report and a backup
gh-toolkit repo audit --user --include-private \
  --output audit.json \
  --backup gh-toolkit-backup.json
```

## Options

| Option | Meaning |
|---|---|
| `--user`, `-u` | Audit the authenticated user's repositories |
| `--org`, `-o` | Audit an organization. Repeat for more than one |
| `--include-private` | Include private repositories |
| `--json` | Write the report as JSON to stdout |
| `--output FILE` | Write the report as JSON to a file |
| `--backup FILE` | Write a restore-ready backup of descriptions and topics |
| `--only-issues` | Show only repositories with issues |
| `--token`, `-t` | GitHub token. Prefer `GITHUB_TOKEN` |

At least one of `--user` or `--org` is required.

## What it checks

Descriptions:

- missing or blank
- ends with an ellipsis, likely truncated
- at the 250-character GitHub limit
- close to the limit, at 230 characters or more
- ends with an incomplete token such as a colon, slash, or open bracket

Spelling:

- American spellings in the description, using a curated mapping
- case is preserved in the suggestion
- URLs, emails, and inline code are ignored
- context-dependent words such as `license`, `catalog`, `dialog`, and
  `artifact` are deliberately not flagged

Topics:

- no topics
- more than 20 topics
- invalid topics: uppercase, spaces, other invalid characters, or longer than
  50 characters
- duplicate topics

## Report format

```json
{
  "format": "gh-toolkit-audit",
  "version": 1,
  "created_at": "2026-11-03T10:00:00+00:00",
  "sources": {"user": true, "orgs": []},
  "summary": {
    "total": 290,
    "missing_description": 12,
    "truncated_description": 8,
    "near_limit_description": 5,
    "with_spelling": 30,
    "with_topic_issues": 40,
    "clean": 200
  },
  "repos": [
    {
      "full_name": "owner/repo",
      "description": "An organization tool for color analysis",
      "description_status": "ok",
      "description_issues": [],
      "spelling": [
        {"word": "organization", "suggestion": "organisation"},
        {"word": "color", "suggestion": "colour"}
      ],
      "topics": ["python", "cli-tool"],
      "topic_issues": [],
      "private": false,
      "archived": false,
      "fork": false,
      "html_url": "https://github.com/owner/repo"
    }
  ]
}
```

## Backup format

```json
{
  "format": "gh-toolkit-backup",
  "version": 1,
  "created_at": "2026-11-03T10:00:00+00:00",
  "sources": {"user": true, "orgs": []},
  "repos": [
    {
      "full_name": "owner/repo",
      "name": "repo",
      "description": "Current description",
      "topics": ["python", "cli-tool"],
      "private": false,
      "archived": false,
      "fork": false,
      "html_url": "https://github.com/owner/repo",
      "default_branch": "main",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

The backup is written atomically. It contains only the fields needed to restore
descriptions and topics. Keep the file until the bulk edits are verified.

## Recommended workflow

1. Audit and back up before changing anything.
2. Review the JSON or table output.
3. Generate proposed descriptions and tags in a separate step.
4. Apply in batches.
5. Re-audit and compare against the backup.

## Exit codes

- `0` audit completed, even when issues were found
- `1` missing token, invalid source selection, or API failure
