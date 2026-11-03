# gh-toolkit Documentation

This directory contains detailed documentation for each command and subcommand in gh-toolkit.

## Command Documentation

### Repository Management
- [repo list](repo-list.md) - List repositories with filters
- [repo extract](repo-extract.md) - Extract comprehensive repository data with LLM categorization
- [repo describe](repo-describe.md) - Generate and update repository descriptions with LLM
- [repo tag](repo-tag.md) - Add intelligent topic tags to repositories
- [repo badges](repo-badges.md) - Generate topic badge markdown for READMEs
- [repo health](repo-health.md) - Check repository health and best practices compliance
- [repo audit](repo-audit.md) - Audit descriptions, spelling, and topics, and write a backup
- [repo restore](repo-restore.md) - Restore descriptions and topics from a backup
- [repo clone](repo-clone.md) - Clone repositories with smart organization and parallel processing

### Invitation Management
- [invite accept](invite-accept.md) - Accept repository invitations in bulk
- [invite leave](invite-leave.md) - Leave repositories where you're a collaborator

### Organization Management
- [org readme](org-readme.md) - Generate profile README for a GitHub organization

### Portfolio Generation
- [portfolio generate](portfolio-generate.md) - Generate cross-organization portfolio index
- [portfolio audit](portfolio-audit.md) - Audit repos for missing descriptions, topics, licenses

### Site Generation
- [site generate](site-generate.md) - Generate beautiful portfolio websites from repository data
- [page generate](page-generate.md) - Generate landing pages from README.md files

## Quick Reference

| Command | Purpose | Key Features |
|---------|---------|--------------|
| `repo list` | List repositories | Filtering, JSON output |
| `repo extract` | Extract repo data | LLM categorization, detailed analysis |
| `repo describe` | Generate descriptions | AI-powered, bulk operations |
| `repo tag` | Add topic tags | AI-powered, preferred tags, model selection |
| `repo badges` | Generate topic badges | Auto-apply to READMEs, multiple styles |
| `repo health` | Check repo quality | Best practices audit, grading system |
| `repo audit` | Audit metadata | Descriptions, spelling, topics, backup |
| `repo restore` | Restore metadata | Descriptions, topics, dry-run |
| `repo clone` | Clone repositories | Parallel processing, smart organization |
| `invite accept` | Accept invitations | Dry-run mode, bulk processing |
| `invite leave` | Leave repositories | Confirmation prompts, safety checks |
| `org readme` | Generate org README | LLM descriptions, 3 templates, direct push |
| `portfolio generate` | Cross-org portfolio | Auto-discover orgs, README + HTML |
| `portfolio audit` | Audit repositories | Find missing metadata, personal repos, JSON reports |
| `site generate` | Create portfolio sites | 4 themes, responsive design |
| `page generate` | Create landing pages | HTML/Jekyll output, README conversion |

## Diagnostics

- [doctor](doctor.md) - Check credentials, config, and optional tools

## Comparison & Reference

- [gh-toolkit vs GitHub CLI](gh-cli-comparison.md) - When to use `gh-toolkit` vs the official `gh` CLI

## Design Documentation

- [Design Documents](design/) - Architectural plans and future enhancement proposals
  - [GUI Interface Plan](design/gui-interface-plan.md) - Cross-platform GUI implementation roadmap

## Configuration

See the main [README](../README.md) for environment variables and GitHub token setup.