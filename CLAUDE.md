# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
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

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
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
