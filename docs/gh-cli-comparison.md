# gh-toolkit vs GitHub CLI (gh)

This document compares `gh-toolkit` with the official [GitHub CLI (`gh`)](https://cli.github.com/) to help you understand when to use each tool.

## Quick Summary

| Aspect | `gh` | `gh-toolkit` |
|--------|------|--------------|
| **Focus** | Day-to-day GitHub operations | Portfolio management & presentation |
| **Scope** | All GitHub features | Repository aggregation & showcase |
| **AI Integration** | None | Claude for categorization & tagging |
| **Target Users** | All developers | Educators, portfolio builders, academics |
| **Bulk Operations** | Limited | Primary use case |
| **Output** | Text/JSON | HTML sites, themed portfolios |

## Complementary Tools

**These tools complement each other.** Use `gh` for daily GitHub work (PRs, issues, actions) and `gh-toolkit` for portfolio management, bulk operations, and presentation. To use `gh`, `gh-toolkit`, `gita`, and `git-reclaim` through one verb set, see [gx](https://github.com/michael-borck/gx).

```bash
# Daily workflow with gh
gh pr create --title "Fix bug" --body "Description"
gh issue list --assignee @me
gh run watch

# Portfolio workflow with gh-toolkit
gh-toolkit repo extract my-repos.txt --output data.json
gh-toolkit site generate data.json --theme resume
gh-toolkit portfolio generate --discover --html portfolio.html
```

---

## Where They Overlap

Both tools can perform these operations, but with different approaches:

| Feature | `gh` | `gh-toolkit` |
|---------|------|--------------|
| **List repositories** | `gh repo list` | `gh-toolkit repo list` |
| **Clone repositories** | `gh repo clone owner/repo` | `gh-toolkit repo clone repos.txt` (bulk) |
| **View repo info** | `gh repo view` | Part of `repo extract` |
| **Accept invitations** | `gh api` (manual REST calls) | `gh-toolkit invite accept` (automated) |
| **Transfer repos** | `gh api` (manual REST calls) | `gh-toolkit transfer initiate/accept` |

### Key Differences in Overlapping Features

**Repository Listing:**
- `gh repo list` - Lists repos for a user/org with basic filtering
- `gh-toolkit repo list` - Similar, but optimized for portfolio workflows with rich output

**Cloning:**
- `gh repo clone` - Clones a single repository
- `gh-toolkit repo clone` - Bulk clones from a file, parallel processing, organized directory structure

**Invitations:**
- `gh` requires manual API calls: `gh api /user/repository_invitations`
- `gh-toolkit invite accept` - One command accepts all pending invitations

---

## What `gh` Does That `gh-toolkit` Doesn't

The official GitHub CLI is a general-purpose tool covering the full GitHub feature set:

### Issues & Pull Requests
```bash
gh issue create --title "Bug" --body "Description"
gh issue list --assignee @me --state open
gh pr create --fill
gh pr review --approve
gh pr merge --squash
gh pr checkout 123
```

### GitHub Actions
```bash
gh run list
gh run watch
gh run view 12345
gh workflow run deploy.yml
gh workflow list
```

### Releases & Assets
```bash
gh release create v1.0.0 --generate-notes
gh release download v1.0.0
gh release list
```

### Gists
```bash
gh gist create file.txt
gh gist list
gh gist view abc123
```

### Codespaces
```bash
gh codespace create
gh codespace list
gh codespace ssh
gh codespace code  # Opens in VS Code
```

### Projects (v2)
```bash
gh project list
gh project view 1
gh project item-add 1 --url <issue-url>
```

### Secrets & Variables
```bash
gh secret set API_KEY
gh secret list
gh variable set ENV_NAME
```

### Authentication & Configuration
```bash
gh auth login
gh auth status
gh config set editor vim
```

### SSH & GPG Keys
```bash
gh ssh-key add ~/.ssh/id_rsa.pub
gh gpg-key list
```

### Raw API Access
```bash
gh api /repos/owner/repo
gh api graphql -f query='{ viewer { login }}'
```

### Extensions
```bash
gh extension install owner/gh-extension
gh extension list
```

### Browser Integration
```bash
gh browse           # Open repo in browser
gh browse issues    # Open issues page
gh pr view --web    # Open PR in browser
```

---

## What `gh-toolkit` Does That `gh` Doesn't

`gh-toolkit` specializes in portfolio management, bulk operations, and presentation:

### LLM-Powered Intelligence

**Repository Categorization:**
```bash
# AI analyzes repos and categorizes them
gh-toolkit repo extract repos.txt --output data.json
# Categories: Web Development, Desktop Apps, Python Libraries, Infrastructure, Learning Resources
```

**Smart Topic Tagging:**
```bash
# AI generates relevant GitHub topics from content analysis
gh-toolkit repo tag username/* --dry-run
gh-toolkit repo tag repos.txt --force
```

**Organization Descriptions:**
```bash
# AI-powered summaries for org README generation
gh-toolkit org readme my-org --output README.md
```

### Portfolio & Site Generation

**HTML Portfolio Sites:**
```bash
# Generate beautiful, responsive portfolio sites
gh-toolkit site generate repos.json --theme educational
gh-toolkit site generate repos.json --theme resume
gh-toolkit site generate repos.json --theme research
gh-toolkit site generate repos.json --theme portfolio
```

**Cross-Organization Portfolios:**
```bash
# Aggregate repos from multiple orgs
gh-toolkit portfolio generate --discover --html portfolio.html
gh-toolkit portfolio generate --org org1 --org org2 --theme resume
```

**Landing Page Generation:**
```bash
# Convert README to HTML or Jekyll pages
gh-toolkit page generate README.md --output index.html
gh-toolkit page generate README.md --jekyll --output index.md
```

### Bulk Operations

**Bulk Cloning:**
```bash
# Clone many repos in parallel with organized structure
gh-toolkit repo clone repos.txt --parallel 8 --depth 1
```

**Bulk Invitation Management:**
```bash
# Accept all pending invitations at once
gh-toolkit invite accept
gh-toolkit invite leave --dry-run
```

**Bulk Transfers:**
```bash
# Transfer multiple repos via CSV
gh-toolkit transfer initiate --file transfers.csv
gh-toolkit transfer accept --org destination-org --all
```

### Repository Quality & Auditing

**Health Checking:**
```bash
# Score repos on quality, documentation, setup, community
gh-toolkit repo health username/repo --rules academic
gh-toolkit repo health repos.txt --min-score 80 --output report.json
```

**Portfolio Audit:**
```bash
# Find repos missing descriptions, topics, licenses
gh-toolkit portfolio audit --discover --output audit.json
```

### Organization Management

**Organization README Generation:**
```bash
gh-toolkit org readme my-org --template detailed --group-by language
gh-toolkit org readme my-org --max-repos 20 --min-stars 5
```

### Academic Workflows

Perfect for educators as a GitHub Classroom alternative:

```bash
# Students accept invitations
gh-toolkit invite accept

# Teacher extracts all student repos
gh-toolkit repo extract student_repos.txt --output class_data.json

# Generate class portfolio
gh-toolkit site generate class_data.json \
  --theme educational \
  --title "CS 101 Projects"

# Audit student repos for completeness
gh-toolkit portfolio audit --org class-org --output audit.json
```

---

## Decision Guide: When to Use Which

### Use `gh` when you need to:
- Create or review pull requests
- Manage issues
- Monitor GitHub Actions workflows
- Create releases
- Work with Codespaces
- Manage secrets and variables
- Perform any single-repository operation
- Access GitHub API directly

### Use `gh-toolkit` when you need to:
- Generate portfolio websites
- Bulk clone or process repositories
- Categorize repositories with AI
- Auto-tag repositories with topics
- Accept/manage bulk invitations
- Audit repository metadata
- Create organization READMEs
- Generate cross-org portfolios
- Check repository health/quality
- Educational/academic workflows

### Use both together:
```bash
# Use gh for daily work
gh pr create --fill
gh issue close 42

# Use gh-toolkit for portfolio presentation
gh-toolkit repo extract my-projects.txt --output data.json
gh-toolkit site generate data.json --theme resume --output portfolio.html
```

---

## Feature Comparison Table

| Feature | `gh` | `gh-toolkit` |
|---------|:----:|:------------:|
| **Repository Operations** | | |
| List repositories | Yes | Yes |
| Clone single repo | Yes | Yes |
| Bulk clone repos | No | Yes |
| Create repository | Yes | No |
| Delete repository | Yes | No |
| Fork repository | Yes | No |
| **Pull Requests** | | |
| Create PR | Yes | No |
| Review PR | Yes | No |
| Merge PR | Yes | No |
| List PRs | Yes | No |
| **Issues** | | |
| Create issue | Yes | No |
| List issues | Yes | No |
| Close issue | Yes | No |
| **GitHub Actions** | | |
| View runs | Yes | No |
| Trigger workflow | Yes | No |
| Watch run | Yes | No |
| **Releases** | | |
| Create release | Yes | No |
| Download assets | Yes | No |
| **Portfolio & Presentation** | | |
| HTML site generation | No | Yes |
| Multiple themes | No | Yes |
| Landing page generation | No | Yes |
| Cross-org portfolios | No | Yes |
| **AI/LLM Features** | | |
| Repository categorization | No | Yes |
| Smart topic tagging | No | Yes |
| AI-generated descriptions | No | Yes |
| **Bulk Operations** | | |
| Bulk clone | No | Yes |
| Bulk invitation accept | No | Yes |
| Bulk transfers | No | Yes |
| **Quality & Auditing** | | |
| Health checking | No | Yes |
| Metadata auditing | No | Yes |
| **Organization** | | |
| Org README generation | No | Yes |
| **Authentication** | | |
| Login/logout | Yes | No (uses env var) |
| Token management | Yes | No |
| **Other** | | |
| Gists | Yes | No |
| Codespaces | Yes | No |
| Projects | Yes | No |
| Secrets/Variables | Yes | No |
| SSH/GPG keys | Yes | No |
| Extensions | Yes | No |
| Raw API access | Yes | No |

---

## Installation Side-by-Side

```bash
# Install GitHub CLI
brew install gh        # macOS
winget install gh      # Windows
sudo apt install gh    # Debian/Ubuntu

# Install gh-toolkit
pip install gh-toolkit
# or
uv pip install gh-toolkit
```

## Authentication

```bash
# GitHub CLI - interactive login
gh auth login

# gh-toolkit - environment variable
export GITHUB_TOKEN=ghp_...
export ANTHROPIC_API_KEY=sk-ant-...  # Optional, for AI features
```
