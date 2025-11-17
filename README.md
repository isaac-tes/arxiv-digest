# cond-mat arXiv digest

Single-script workflow that fetches the latest `cond-mat` listings from arXiv, ranks
papers using heuristics (keywords, authors, channel penalties), and prints a tidy
digest that is easy to paste anywhere—including straight into ChatGPT / o1.

## Quick start

```bash
cd /Users/isaac/tubCloud/Dokumente/PhD_Masterarbeit/PhD_Projects/Misc/arxiv-scraper-gpt_cp
uv sync
uv run python condmat_digest.py --top 15
```

That command will fetch the live feed, score every paper, and print the top 15.
The UV-managed `.venv` isolates dependencies (`requests`, `beautifulsoup4`).

## Configuration workflow

`condmat_digest.py` ships with embedded defaults, so you can copy/paste the file
into ChatGPT Code Interpreter and run it without any side files.

When running locally you can persist tweaks in `condmat_config.json` (auto-created
next to the script). Every config operation can be performed via CLI flags:

| Action | Flag(s) |
| --- | --- |
| Add/remove/rename core keywords | `--add-core tebd` `--remove-core mpo` `--rename-core "anyon:anyons"` |
| Manage favorite authors | `--add-author surname` `--remove-author` `--rename-author "old:new"` |
| Adjust low-priority penalties | `--add-low-priority film` `--remove-low-priority` `--rename-low-priority` |
| Manage feed URLs | `--add-url other=https://arxiv.org/list/quant-ph/new` `--rename-url "cond-mat:cm"` `--delete-url cm` |
| Pick / change default feed | `--set-default-feed cond-mat` or `--feed https://...` |

Changes apply immediately; append `--save-config` to persist them. Example:

```bash
uv run python condmat_digest.py \
  --add-core "rydberg" --add-author "bloch" --save-config
```

Inspect the current configuration at any time:

```bash
uv run python condmat_digest.py --list-config
```

## ChatGPT / Code Interpreter usage

1. Copy the entire contents of `condmat_digest.py` and paste it into ChatGPT.
2. Tell ChatGPT to execute the script (the default config is embedded, so no
   sibling files are required).
3. Optionally pass CLI-like instructions inside the same message, e.g.:
   ````
   Please run the script with:
   python condmat_digest.py --top 10 --add-core "rydberg" --feed https://arxiv.org/list/quant-ph/new
   ````
4. You will receive the same digest table that you see locally.

Because the script performs live HTTP requests, ChatGPT must be in a mode that
allows outbound network calls (Code Interpreter / o1 / Advanced Data Analysis).

## Handy examples

Show only cross listings and export the updated config:

```bash
uv run python condmat_digest.py --sections "Cross" --save-config
```

Try a one-off alternative feed without touching config:

```bash
uv run python condmat_digest.py --feed https://arxiv.org/list/quant-ph/new
```

Raise/lower the number of entries:

```bash
uv run python condmat_digest.py --top 5
```

Copy/paste the resulting digest directly into notes, Slack, or ChatGPT. Each
entry includes title, authors, section, link, and a two-sentence summary.
