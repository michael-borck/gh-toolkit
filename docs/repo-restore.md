# repo restore

Restore repository descriptions and topics from a backup created by
`gh-toolkit repo audit --backup FILE`.

## Usage

```bash
gh-toolkit repo restore <BACKUP> [OPTIONS]
```

## Options

| Option | Meaning |
|---|---|
| `--token`, `-t` | GitHub token. Prefer `GITHUB_TOKEN` |
| `--only descriptions` | Restore descriptions only |
| `--only topics` | Restore topics only |
| `--include-archived` | Temporarily unarchive, restore, then rearchive |
| `--dry-run` | Show changes without writing |
| `--yes`, `-y` | Skip the confirmation prompt |
| `--output`, `-O` | Write the restore report as JSON |

By default both descriptions and topics are restored. Only fields that differ
from the current repository state are written.

## Examples

```bash
# Preview a restore
gh-toolkit repo restore backup.json --dry-run

# Restore descriptions and topics
gh-toolkit repo restore backup.json --yes

# Restore topics only
gh-toolkit repo restore backup.json --only topics --yes

# Restore an archived repository
gh-toolkit repo restore backup.json --include-archived --yes
```

## Safety

- The backup format is validated before any write.
- Archived repositories are skipped unless `--include-archived` is passed.
- `--dry-run` shows the old and new values.
- The restore report records updated, failed, and skipped repositories.
