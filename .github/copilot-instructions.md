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
uv sync                                      # install dependencies
uv run python arxiv_digest.py --top 15       # run with defaults
uv run python arxiv_digest.py --today --top 10
uv run python arxiv_digest.py --pastweek --feed cond-mat --feed quant-ph
uv run python arxiv_digest.py --list-config  # inspect current config
```

No test suite currently exists. Manual testing via the above commands.

## Architecture

Single-file tool (`arxiv_digest.py`). Data flow:

1. **Config** (`Config` dataclass) — loaded from `arxiv_config.json` (if present), then mutated by CLI flags via `apply_cli_modifications`. Persisted back with `--save-config`.
2. **Fetch** — `fetch_feeds` → `fetch_feed` scrapes arXiv HTML list pages (BeautifulSoup). Missing abstracts are back-filled in parallel via `ThreadPoolExecutor` calling `fetch_abstract` on individual paper pages.
3. **Score** (`score_paper`) — heuristic integer score: +6 per core keyword/author match, +4/+2 subject boosts, −5 low-priority penalty.
4. **Rank & format** — `build_ranked_entries` sorts and slices to `top_n`; `format_digest` / `format_markdown` produce output strings.
5. **Output** — stdout (always) + optional JSON/Markdown files under `reports/`.

Feed URLs encode the timeframe: `/new` = today, `/pastweek` = last ~5 days. `determine_feed` rewrites the suffix based on `--timeframe` / `--today` / `--pastweek`.

Config file (`arxiv_config.json`) is gitignored; defaults live in the `_default_*` functions at the top of the script.
