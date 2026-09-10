# CLI guide

The CLI (`arxiv_digest.py`) is single-file by design: it's pasteable into ChatGPT Code Interpreter, scriptable for cron, and deterministic. After `uv tool install '.[gui]'` it's also available as the `arxiv-digest` command on your PATH; or run it on the fly with `uvx --from '.[gui]' arxiv-digest ...` without installing anything.

## Basic invocations

```bash
# Default run: pastweek, top 20, all four configured feeds
uv run python arxiv_digest.py

# Today's papers, top 10
uv run python arxiv_digest.py --timeframe today --top 10

# Pastweek with specific feeds
uv run python arxiv_digest.py --timeframe pastweek --feed cond-mat --feed quant-ph

# Write reports to ./reports/digest-YYYY-MM-DD.{md,json}
uv run python arxiv_digest.py --output-markdown --output-json

# Add a keyword and persist the change to arxiv_config.json
uv run python arxiv_digest.py --add-core "rydberg" --save-config

# Inspect the resolved config without fetching anything
uv run python arxiv_digest.py --list-config --no-config
```

## All flags

| Flag | Purpose |
|------|---------|
| `--feed NAME` | Select feed (repeatable). Either a name from `feeds` config or a full URL. |
| `--top N` | Override number of entries to print (default: 20). |
| `--timeframe {today,pastweek}` | Override which arXiv listing window to scrape. |
| `--include-replacements` | Keep arXiv *Replacement submissions* (hidden by default; only present in the `today` feed). |
| `--score ID_OR_URL` | Score a single arXiv paper (by id or URL) against the current config and print its per-aspect breakdown, without fetching the whole digest. |
| `--sections NAME ...` | Limit to specific date-section titles (e.g. `"Thu, 4 Dec 2025"`). |
| `--output-json [PATH]` | Write JSON. Bare flag → `reports/digest-YYYY-MM-DD.json`. |
| `--output-markdown [PATH]` | Write Markdown. Bare flag → `reports/digest-YYYY-MM-DD.md`. |
| `--config PATH` | Use a non-default config JSON path. |
| `--no-config` | Ignore the config file even if present. |
| `--preset NAME` | Start from a built-in [starter preset](./#starter-presets) (replaces the config's content). |
| `--add-preset NAME` | Union a starter preset's keywords/authors/feeds onto the current config (repeatable). |
| `--list-presets` | List the built-in starter presets and exit. |
| `--save-config` | Persist current (modified) config back to `--config` path. |
| `--list-config` | Print the resolved config as JSON and exit. |
| `--verbose` | Log fetch progress to stderr. |
| `--add-core W` / `--remove-core W` / `--rename-core OLD:NEW` | Mutate `core_keywords`. |
| `--add-author N` / `--remove-author N` / `--rename-author OLD:NEW` | Mutate `named_authors`. |
| `--add-low-priority W` / `--remove-low-priority W` / `--rename-low-priority OLD:NEW` | Mutate `low_priority_kw`. |
| `--add-url NAME=URL` / `--rename-url OLD:NEW` / `--delete-url NAME` | Mutate the feeds map. |
| `--set-default-feed NAME` | Set which feed(s) are used when `--feed` is omitted (repeatable). |

The `--add-* / --remove-* / --rename-*` flags only stick if combined with `--save-config`; otherwise they apply for that run only.

## Configuration file

`arxiv_config.json` lives next to `arxiv_digest.py` (gitignored). See [Scoring](scoring.md) for the `weights` block.

The CLI never exposes flags for `weights`. To tune scoring weights, use the GUI's Scoring tab and click *Write project config*, or hand-edit the JSON.

## Output formats

- **Console** (default): copy-paste friendly digest, ranked.
- **JSON** (`--output-json`): structured data with `generated_at`, `feed_urls`, `top_n`, `total_papers`, and the ranked `entries`.
- **Markdown** (`--output-markdown`): formatted for Notion / Obsidian / Slack.
- **Plain text**: redirect stdout: `... > digest.txt`.

## ChatGPT / Code Interpreter

```
Save this as arxiv_digest.py and run:
python arxiv_digest.py --feed cond-mat --top 12 --timeframe today --output-json
Show me the output.
```

Requires Code Interpreter / Advanced Data Analysis mode for network access.
