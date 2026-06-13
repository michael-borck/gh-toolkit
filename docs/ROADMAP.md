# gh-toolkit Roadmap

Backlog of proposed features and improvements, captured 2026-06-13. Grouped by
theme; ordering within a group is rough priority. Nothing here is committed —
it's a menu, not a plan.

## Scope boundary (read this first)

gh-toolkit is the **GitHub operations + repository-hygiene** layer. It fetches
repos, audits repository-level metadata (README / license / CI / activity),
maps GitHub usernames to people (rosters), generates portfolios, and pushes
feedback back to GitHub.

It deliberately does **not** assess the *content* of student work. That belongs
to the separate `lens` family (`code-analyser`, `assessment-lens`, …), which
maps content signals to a rubric as *observations, not grades*, with a human in
the loop. The two layers meet at a **data contract** — gh-toolkit produces a
`submissions/<student-id>/` folder layout that `assessment-lens assess`
consumes — not a code dependency. Keep that seam clean: gh-toolkit must not grow
a marking engine for student work.

Practical consequence for the classroom features below: roster reports and
hygiene rubrics are about *"did the repo get set up / submitted properly,"* not
*"how good is the work."*

## Quick wins

- **`gh auth token` fallback** _(done)_ — when `GITHUB_TOKEN` is unset, falls
  back to the `gh` CLI's stored token so the tool works with zero setup.
- **`--json` output** _(done)_ for `repo list` and `repo health` —
  machine-readable output for piping to `jq`, spreadsheets, and gradebooks.
- **Replace the deprecated Tailwind 2 CDN** _(done)_ in `site_generator.py` —
  now uses the maintained Play CDN.
- **Config file support** _(partially done)_ — `gh-toolkit.toml` (project-local)
  and `~/.config/gh-toolkit/config.toml` are read today, but only the `token`
  key is wired in. Still to do: per-option defaults (default org, theme, model,
  rate limit, preferred tags) with precedence CLI flag > env var > config file >
  built-in default. The remaining work touches model/theme/rate-limit resolution
  across all commands and is fiddly because typer evaluates option defaults at
  import time — worth a deliberate settings layer rather than scattering reads.

## Classroom use case (gh-toolkit's stated focus)

- **Roster-aware submission reports** _(done — `gh-toolkit repo roster`)_ — joins
  `repo health` results to a roster CSV (name, ID, GitHub username) and emits a
  tracking sheet: who set up their repo, who's missing a README/CI, who's still
  empty. Resolves repos via an explicit roster column, a `--repo-pattern`, or
  `org/<username>`. Output as a rich table, `--output` CSV, or `--json`. Framed
  as submission/hygiene tracking, not marking.
- **Custom health rubrics** _(done — `--rubric`)_ — `repo health --rubric
  my.yaml` (and `repo roster --rubric`) override check weights, grade
  thresholds, and mark checks as required, layered on top of the named rule
  set. Required-check failures are flagged in the report. A hygiene-linter
  config, distinct from an assessment rubric. See `example_rubric.yaml`.
- **Deadline snapshots for cloning** _(done — `repo clone --before`)_ —
  `repo clone --before "2026-06-12 23:59"` checks out the last commit before a
  deadline (`git rev-list -n1 --before=…`), snapshotting "what the student had
  at the due date." Forces a full clone, flags repos with no commit before the
  deadline, and produces the `owner/repo` folder layout content-assessment tools
  consume.
- **Push feedback to students** _(done — `repo health --post-issue`)_ — files
  the health report (score, failing checks, fix suggestions) as an issue on each
  repo; GitHub notifies the owner per their settings. Idempotent: re-runs update
  the existing gh-toolkit issue (found via a hidden marker) instead of
  duplicating. Dry-run preview + confirmation by default; `--yes` to skip.
  There is no GitHub DM/email API, so an issue (which triggers GitHub's own
  notifications) is the delivery mechanism.

## Performance & robustness at scale

- **Parallel + resumable extraction** _(done)_ — `repo extract --parallel N`
  runs extractions through a worker pool, and results are saved incrementally
  after each repo so a mid-run crash keeps progress; `--resume` reloads the
  output file, skips repos already in it, and appends the rest.
- **ETag-based response caching** — GitHub 304s don't count against the rate
  limit; a small local ETag cache makes re-runs nearly free.
- **Anthropic Batches API for bulk LLM work** — tagging/describing hundreds of
  repos is the batch use case: ~50% cheaper, latency-insensitive.

## Smaller polish

- `portfolio audit --fix` _(done)_ — generates missing descriptions and topics
  in place using the existing describe/tag fixers (and adds a license when
  `--license KEY` is given). `--dry-run` to preview, confirmation prompt unless
  `--yes`. License is opt-in since it's a deliberate choice, not auto-derivable.
- `site deploy` — emit a GitHub Pages Actions workflow so the portfolio
  republishes on push.
- `transfer list` / `transfer accept` currently exit 0 on API failure — should
  surface a non-zero exit code.
- Document `gh-toolkit --install-completion` (exists via typer, undocumented).
- **TUI test coverage** — the `tui/` package (~2,500 lines) has no tests and is
  excluded from strict type checking. Would need textual's pilot test harness
  and `textual` added to the dev dependency group.
- **Footgun:** `portfolio generate` and `org readme` default their output to
  `README.md` in the *current directory* — running either in a project root
  silently overwrites the project's own README. Consider a safer default
  (e.g. refuse to overwrite an existing non-generated README, or default to a
  distinct filename like `PORTFOLIO.md`).
