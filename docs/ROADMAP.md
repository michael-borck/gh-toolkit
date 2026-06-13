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

- **`gh auth token` fallback** — when `GITHUB_TOKEN` is unset, fall back to the
  `gh` CLI's stored token so the tool works with zero setup and the `--token`
  flag becomes unnecessary in practice. _(in progress)_
- **`--json` output** for `repo list` and `repo health` — machine-readable
  output for piping to `jq`, spreadsheets, and gradebooks. _(in progress)_
- **Replace the deprecated Tailwind 2 CDN** in `site_generator.py`
  (`tailwindcss@2.2.19` on jsdelivr, EOL since 2022) — a latent breakage in
  every published portfolio. _(in progress)_
- **Config file support** — `~/.config/gh-toolkit/config.toml` (and a
  per-project `gh-toolkit.toml`) for the options people repeat: default org,
  theme, model, rate limit, preferred tags. Precedence: CLI flag > env var >
  config file > built-in default. Touches token/model/theme/rate-limit
  resolution across all commands, so worth a deliberate settings layer rather
  than scattering reads — recommended as a focused next piece.

## Classroom use case (gh-toolkit's stated focus)

- **Roster-aware submission reports** _(highest value)_ — join `repo health`
  results to a roster CSV (name, ID, GitHub username) and emit a tracking sheet:
  who set up their repo, who's missing a README/CI, who's still empty. The
  health checker already produces the per-repo signals; this wires them to
  student identity. Framed as submission/hygiene tracking, not marking.
- **Custom health rubrics** — let educators define check weights and required
  checks in YAML (`repo health --rules assignment2.yaml`) instead of the three
  hardcoded sets. A hygiene-linter config, distinct from an assessment rubric.
- **Deadline snapshots for cloning** — `repo clone --before "2026-06-12 23:59"`
  checks out the last commit before a deadline
  (`git rev-list -n1 --before=…`). Clones "what the student had at the due
  date." Also produces the exact `submissions/<id>/` layout the lens family's
  `assess` consumes.
- **Push feedback to students** — `repo health --post-issue` files the health
  report (with its existing fix suggestions) as an issue on each repo, closing
  the loop from grading back to learning.

## Performance & robustness at scale

- **Parallel + resumable extraction** — `repo extract` is serial (5–6 API calls
  per repo) and loses everything on a mid-run failure. Use a worker pool (the
  cloner already has the pattern) and write results incrementally so `--resume`
  can pick up.
- **ETag-based response caching** — GitHub 304s don't count against the rate
  limit; a small local ETag cache makes re-runs nearly free.
- **Anthropic Batches API for bulk LLM work** — tagging/describing hundreds of
  repos is the batch use case: ~50% cheaper, latency-insensitive.

## Smaller polish

- `portfolio audit --fix` — the audit finds missing descriptions/topics and
  `repo describe`/`repo tag` already fix them; connect them.
- `site deploy` — emit a GitHub Pages Actions workflow so the portfolio
  republishes on push.
- `transfer list` / `transfer accept` currently exit 0 on API failure — should
  surface a non-zero exit code.
- Document `gh-toolkit --install-completion` (exists via typer, undocumented).
- **Footgun:** `portfolio generate` and `org readme` default their output to
  `README.md` in the *current directory* — running either in a project root
  silently overwrites the project's own README. Consider a safer default
  (e.g. refuse to overwrite an existing non-generated README, or default to a
  distinct filename like `PORTFOLIO.md`).
