# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:full hash:f65d5d33 -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Quality
- Use `--acceptance` and `--design` fields when creating issues
- Use `--validate` to check description completeness

### Lifecycle
- `bd defer <id>` / `bd supersede <id>` for issue management
- `bd stale` / `bd orphans` / `bd lint` for hygiene
- `bd human <id>` to flag for human decisions
- `bd formula list` / `bd mol pour <name>` for structured workflows

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

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
