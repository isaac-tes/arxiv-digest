# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->


## Build & Run

```bash
uv sync                                                              # CLI deps only
uv sync --group dev                                                  # CLI + GUI + tests
uv run python arxiv_digest.py --top 15                               # CLI, defaults to pastweek
uv run python arxiv_digest.py --timeframe today --top 10
uv run python arxiv_digest.py --timeframe pastweek --feed cond-mat --feed quant-ph
uv run python arxiv_digest.py --list-config --no-config              # inspect built-in defaults
uv run python arxiv_digest.py --timeframe today --include-replacements      # keep 'Replacement submissions'
uv run streamlit run arxiv_gui.py                                    # Streamlit GUI
uv run pytest                                                        # 102-test suite, ~1s, no network
```

CLI uses `--timeframe {today,pastweek}`. There are no `--today` / `--pastweek` / `--days` flags despite older docs — confirm with `--help`. `--include-replacements` keeps arXiv "Replacement submissions" (hidden by default; only present in the `today`/`/new` feed).

## Architecture

`arxiv_digest.py` is the single-file CLI; `arxiv_gui.py` is a Streamlit GUI that imports from it. Data flow:

1. **Config** (`Config` dataclass + `ScoringWeights` dataclass) — loaded from `arxiv_config.json` if present, then mutated by CLI flags via `apply_cli_modifications`. Persisted with `--save-config`. The GUI reads/writes the same file. Also persists: `include_replacements`, `feed_weights`, and the three GUI display toggles (`highlight_authors` / `highlight_terms_title` / `highlight_terms_abstract`).
2. **Fetch** — `fetch_feeds` → `fetch_feed` scrapes arXiv HTML list pages (BeautifulSoup). Each paper keeps its section header in `paper["section"]` (e.g. `New submissions…` / `Cross submissions…` / `Replacement submissions…` on `/new`, or a date like `Fri, 19 Jun 2026` on `/pastweek`). Missing abstracts are back-filled in parallel via `ThreadPoolExecutor` calling `fetch_abstract`.
3. **Filter** — `filter_papers(papers, include_replacements, days)` drops `Replacement submissions` by default (cross-lists kept) and optionally restricts to specific day labels. Helpers: `section_category`, `section_day_label`, `available_day_labels`. Applied post-fetch so the GUI re-filters without re-fetching.
4. **Score** (`score_paper`) — delegates to `explain_score(paper, cfg)` which returns a per-rule breakdown. Scalar weights live in `cfg.weights`; **subject scoring is `cfg.feed_weights`** (a bonus per feed name found in a paper's subjects — defaults quant-gas 4 / mes-hall 4 / quant-ph 2 via `_default_feed_weights`). Named-author matches the author field **only**, not title/abstract. Defaults: +6 per keyword/author, per-feed subject bonus, −5 once if any low-priority hit, +1 long-abstract bonus.
5. **Rank & format** — `build_ranked_entries` sorts and slices to `top_n`; `format_digest` / `format_markdown` produce output strings.
6. **Output** — stdout (always) + optional JSON/Markdown under `reports/`. GUI download buttons reuse the same formatters.

Feed URLs encode the timeframe: `/new` = today, `/pastweek` = last ~5 days. `determine_feed` rewrites the suffix based on `--timeframe` (or `cfg.timeframe`). arXiv has no arbitrary-day URL, so the GUI day-picker is limited to the days `/pastweek` returns.

`arxiv_config.json` is gitignored; defaults live in `_default_*` helpers (incl. `_default_feed_weights`) and `ScoringWeights()` near the top. Legacy configs (old `weights.*_subject` keys) auto-migrate into `feed_weights` via `_hydrate_feed_weights`. GUI profiles live in `~/.arxiv_scraper/profiles/<name>.json`; both profiles and the project config persist the full `Config`.

GUI display: `arxiv_gui.py` hover-highlights authors (in the author list), and matched keywords/low-priority terms in the title + abstract via `_highlight_terms`; toggled by the three `highlight_*` config flags. Streamlit strips the `title` attribute, so tooltips use CSS (`.tip`/`.hl-tip`), not `title=`.

Tests live in `tests/`; run with `uv run pytest` (102 tests). `requests.get` is monkey-patched, so no network calls hit arXiv during the suite. GUI tests use `streamlit.testing.v1.AppTest` (headless).
