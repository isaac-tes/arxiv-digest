# Beads Issue Tracking

This project uses [Beads (bd)](https://github.com/steveyegge/beads) for issue tracking.

## Core Rules

- Track ALL work in bd (never use markdown TODOs or comment-based task lists)
- Use `bd ready` to find available work
- Use `bd create` to track new issues/tasks/bugs
- Use `bd dolt push` at end of session to sync with remote
- Run `bd prime` for complete workflow context (SSOT for operational commands)

## Quick Reference

```bash
bd prime                              # Load complete workflow context (SSOT)
bd ready                              # Show issues ready to work (no blockers)
bd list --status=open                 # List all open issues
bd create "title" -t task -p 2        # Create new issue
bd update <id> --claim                # Claim work atomically
bd close <id>                         # Mark complete
bd dep add <issue> <depends-on>       # Add dependency
bd dolt push                          # Sync with remote
```

## Workflow

1. Check for ready work: `bd ready`
2. Claim an issue atomically: `bd update <id> --claim`
3. Do the work
4. Mark complete: `bd close <id>`
5. Push changes: `bd dolt push`

## Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

## Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

## Context Loading

Run `bd prime` to get complete workflow documentation in AI-optimized format.
`bd prime` is the single source of truth for operational commands and session workflow.

For detailed docs: see AGENTS.md, QUICKSTART.md, or run `bd --help`

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
