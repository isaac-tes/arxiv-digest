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
