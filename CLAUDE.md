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
uv run streamlit run arxiv_gui.py                                    # Streamlit GUI
uv run pytest                                                        # 74-test suite, ~1s, no network
```

CLI uses `--timeframe {today,pastweek}`. There are no `--today` / `--pastweek` / `--days` flags despite older docs — confirm with `--help`.

## Architecture

`arxiv_digest.py` is the single-file CLI; `arxiv_gui.py` is a Streamlit GUI that imports from it. Data flow:

1. **Config** (`Config` dataclass + `ScoringWeights` dataclass) — loaded from `arxiv_config.json` if present, then mutated by CLI flags via `apply_cli_modifications`. Persisted with `--save-config`. The GUI reads/writes the same file.
2. **Fetch** — `fetch_feeds` → `fetch_feed` scrapes arXiv HTML list pages (BeautifulSoup). Missing abstracts are back-filled in parallel via `ThreadPoolExecutor` calling `fetch_abstract` on individual paper pages.
3. **Score** (`score_paper`) — delegates to `explain_score(paper, cfg)` which returns a per-rule breakdown; weights live in `cfg.weights` (`ScoringWeights` dataclass). Defaults: +6 per keyword/author, +4/+2 subject boosts, −5 once if any low-priority hit, +1 long-abstract bonus.
4. **Rank & format** — `build_ranked_entries` sorts and slices to `top_n`; `format_digest` / `format_markdown` produce output strings.
5. **Output** — stdout (always) + optional JSON/Markdown under `reports/`. GUI download buttons reuse the same formatters.

Feed URLs encode the timeframe: `/new` = today, `/pastweek` = last ~5 days. `determine_feed` rewrites the suffix based on `--timeframe` (or `cfg.timeframe`).

`arxiv_config.json` is gitignored; defaults live in `_default_*` helpers and `ScoringWeights()` at the top of the script. GUI profiles live in `~/.arxiv_scraper/profiles/<name>.json`.

Tests live in `tests/`; run with `uv run pytest`. `requests.get` is monkey-patched, so no network calls hit arXiv during the suite.
