# gh-toolkit repo describe

Generate and update repository descriptions using LLM-powered analysis.

## Usage

```bash
gh-toolkit repo describe <REPOS_INPUT> [OPTIONS]
```

## Arguments

- `REPOS_INPUT` - Repository (owner/repo), file with repo list, or 'username/*' for all user repos

## Options

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `--token`, `-t` | TEXT | GitHub personal access token | `$GITHUB_TOKEN` |
| `--anthropic-key` | TEXT | Anthropic API key for LLM generation | `$ANTHROPIC_API_KEY` |
| `--model`, `-m` | TEXT | Anthropic model to use | `claude-haiku-4-5` |
| `--dry-run` | FLAG | Preview descriptions without making changes | Execute changes |
| `--force` | FLAG | Update description even if one already exists | Skip existing |
| `--rate-limit`, `-r` | FLOAT | Seconds between API requests | `0.5` |
| `--output`, `-o` | PATH | Save results to JSON file | |
| `--help` | FLAG | Show help message | |

## Examples

### Basic Usage

```bash
# Generate description for a single repository
gh-toolkit repo describe user/repo

# Preview without making changes
gh-toolkit repo describe user/repo --dry-run

# Process all repositories for a user
gh-toolkit repo describe "user/*"
```

### Using Different Models

```bash
# Use Haiku (fastest, default)
gh-toolkit repo describe user/repo --model claude-haiku-4-5

# Use Sonnet (balanced)
gh-toolkit repo describe user/repo --model claude-sonnet-4-6

# Use Opus (highest quality)
gh-toolkit repo describe user/repo --model claude-opus-4-8
```

### Bulk Operations

```bash
# Process all user repositories
gh-toolkit repo describe "myuser/*" --dry-run

# Process repositories from a file
gh-toolkit repo describe repos.txt --output results.json

# Force update existing descriptions
gh-toolkit repo describe "myorg/*" --force --rate-limit 1.0
```

### From File

Create a file `repos.txt` with one repository per line:

```text
owner/repo1
owner/repo2
# Comments are ignored
owner/repo3
```

Then process them:

```bash
gh-toolkit repo describe repos.txt --anthropic-key sk-ant-...
```

## Description Generation

### LLM-Powered Analysis

When an Anthropic API key is provided, descriptions are generated using intelligent analysis:

1. **README Analysis** - Reads and summarizes the repository's README
2. **Language Detection** - Identifies primary programming languages
3. **Content Analysis** - Examines repository structure and files
4. **Concise Output** - Generates a clear, informative one-liner

### Example Output

```
Repository: myorg/data-pipeline
Current description: (empty)
Generated description: A Python ETL framework for processing and transforming data from multiple sources with scheduling support.
Action: Updated description
```

### Fallback Mode

When no API key is provided, descriptions are generated using rule-based analysis:

- Combines repository name, language, and topics
- Extracts key phrases from README
- Produces a basic but informative description

## Output Formats

### Console Output

```
Generating descriptions...

✓ user/web-app
  New: A React-based dashboard for real-time data visualization

⏭ user/cli-tool
  Skipped: Already has description (use --force to update)

✓ user/api-server
  New: RESTful API service built with FastAPI for user management

Summary: 2 updated, 1 skipped, 0 errors
```

### JSON Output

When using `--output`, results are saved in JSON format:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "dry_run": false,
  "force_update": false,
  "total_processed": 3,
  "summary": {
    "success": 2,
    "skipped": 1,
    "errors": 0,
    "dry_run": 0
  },
  "results": [
    {
      "repo": "user/web-app",
      "status": "success",
      "old_description": "",
      "new_description": "A React-based dashboard for real-time data visualization"
    }
  ]
}
```

## Authentication

Requires a GitHub personal access token with `repo` scope:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Optional Anthropic API key for intelligent analysis:

```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
```

## Permissions

### Required GitHub Scopes
- `repo` - Full repository access for updating descriptions
- `public_repo` - For public repositories only

### Repository Access
- Must have **admin** or **maintain** access to update descriptions
- Read access sufficient for dry-run mode

## Rate Limiting

### GitHub API Limits
- 5000 requests/hour (authenticated)
- Description updates count as write operations
- Built-in retry logic for rate limit handling

### Anthropic API Limits
- Varies by subscription plan
- Use `--rate-limit` to control request frequency
- Graceful fallback to rule-based generation

## Common Use Cases

### Portfolio Cleanup

Ensure all your repositories have descriptions:

```bash
# Preview what would be generated
gh-toolkit repo describe "myuser/*" --dry-run

# Apply descriptions to repos without one
gh-toolkit repo describe "myuser/*"

# Force refresh all descriptions
gh-toolkit repo describe "myuser/*" --force
```

### Organization Standardization

```bash
# Generate descriptions for org repos
gh-toolkit repo describe "myorg/*" --output org-descriptions.json

# Review the JSON output before applying
cat org-descriptions.json | jq '.results[] | {repo, new_description}'
```

### CI/CD Integration

```bash
#!/bin/bash
# Check for repos missing descriptions
gh-toolkit repo describe "myorg/*" --dry-run --output audit.json

MISSING=$(jq '[.results[] | select(.status == "dry_run")] | length' audit.json)
if [ "$MISSING" -gt 0 ]; then
  echo "Found $MISSING repos needing descriptions"
fi
```

## Error Handling

Common errors and solutions:

- **403 Forbidden**: Need admin/maintain access to repository
- **404 Not Found**: Repository doesn't exist or no access
- **401 Unauthorized**: Check your GitHub token
- **Rate limit exceeded**: Increase `--rate-limit` value
- **LLM API error**: Will fallback to rule-based generation

## Best Practices

1. **Test first**: Always use `--dry-run` before bulk operations
2. **Review output**: LLM suggestions may need manual review
3. **Respect rate limits**: Use `--rate-limit` for large operations
4. **Use quality models**: Consider Sonnet for better descriptions
5. **Save results**: Use `--output` to track what was changed

## Integration

Works well with other gh-toolkit commands:

```bash
# Complete repository cleanup workflow
gh-toolkit repo describe "myorg/*"     # Add descriptions
gh-toolkit repo tag "myorg/*"          # Add topic tags
gh-toolkit repo badges "myorg/*"       # Generate badges
gh-toolkit org readme myorg --apply    # Update org README
```

## See Also

- [repo tag](repo-tag.md) - Add intelligent topic tags to repositories
- [repo badges](repo-badges.md) - Generate topic badge markdown
- [org readme](org-readme.md) - Generate organization profile README
- [portfolio audit](portfolio-audit.md) - Find repos with missing metadata
