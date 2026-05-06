# arXiv digest (cond-mat + quant-ph)

Single-file tool that fetches arXiv feeds, scores papers by heuristics (keywords, authors, subject boosts/penalties), and prints a compact digest for terminal, notes, or ChatGPT.

## Defaults

- **Feeds**: `cond-mat`, `cond-mat.mes-hall`, `cond-mat.quant-gas`, `quant-ph`
- **Output**: printed to stdout
- **Config**: persists to `arxiv_config.json` with `--save-config`

## Quick start

```bash
cd .../arxiv_scraper_cli
uv sync
uv run python arxiv_digest.py --top 15
```

Fetches all default feeds, scores papers, prints top 15.

## Common flags

| Flag | Purpose |
|------|---------|
| `--feed NAME` | Select feed (repeatable); use name or full URL |
| `--top N` | Show top N entries (default: 20) |
| `--days N` | Limit to papers from last N days |
| `--today` | Fetch only today's papers (equivalent to `--days 1`) |
| `--pastweek` | Fetch last 7 days of papers (equivalent to `--days 7`) |
| `--output-json [PATH]` | Write JSON (default: `reports/digest-YYYY-MM-DD.json`) |
| `--output-markdown [PATH]` | Write Markdown (default: `reports/digest-YYYY-MM-DD.md`) |
| `--save-config` | Persist config modifications |
| `--list-config` | Show current configuration |

## Quick examples

```bash
# Today's papers only, top 10
uv run python arxiv_digest.py --today --top 10

# Past week with specific feeds
uv run python arxiv_digest.py --pastweek --feed cond-mat --feed quant-ph

# Last 3 days, top 10
uv run python arxiv_digest.py --days 3 --top 10

# Specific feeds with JSON output
uv run python arxiv_digest.py --feed cond-mat --feed quant-ph --output-json

# Add keyword and save config
uv run python arxiv_digest.py --add-core "rydberg" --save-config
```

## Configuration

Modify via CLI flags (persists with `--save-config`):

- Keywords: `--add-core WORD`, `--remove-core WORD`
- Authors: `--add-author NAME`, `--remove-author NAME`
- Feeds: `--add-url name=URL`, `--set-default-feed NAME`
- Low-priority: `--add-low-priority WORD`, `--remove-low-priority WORD`

Example:
```bash
uv run python arxiv_digest.py --add-core "tebd" --add-author "bloch" --save-config
```

## Scoring

- **+6** per core keyword match
- **+6** per highlighted author match
- **+4** for `cond-mat.quant-gas` or `cond-mat.mes-hall`
- **+2** for `quant-ph`
- **−5** for low-priority keyword matches
- **+1** if abstract > 200 chars

## ChatGPT / Code Interpreter

Copy `arxiv_digest.py` content and paste into ChatGPT with:

```
Save this as arxiv_digest.py and run:
python arxiv_digest.py --feed cond-mat --top 12 --days 2 --output-json
Show me the output.
```

All CLI flags work identically in ChatGPT's sandbox. Requires Code Interpreter/Advanced Data Analysis mode for network access.

## Output formats

- **Console**: copy-paste friendly digest (default)
- **JSON**: structured data with metadata, scores, entries
- **Markdown**: formatted for Notion/Obsidian/Slack
- **Plain text**: redirect stdout with `> file.txt`
