# cond-mat + quant-ph arXiv digest

Single-script workflow (`arxiv_digest.py`) that fetches multiple arXiv feeds
(`cond-mat`, `cond-mat.mes-hall`, `cond-mat.quant-gas`, `quant-ph`, plus any you
add), ranks papers using heuristics (keywords, authors, subject boosts, and
penalties), and prints a tidy digest you can paste anywhere—including straight
into ChatGPT / o1.

## Quick start

```bash
cd /Users/isaac/tubCloud/Dokumente/PhD_Masterarbeit/PhD_Projects/Misc/arxiv-scraper-gpt_cp
uv sync
uv run python arxiv_digest.py --feed cond-mat --top 15
```

That command fetches the default `cond-mat` feed, scores every paper, and prints
the top 15. Add more feeds by repeating `--feed NAME` (e.g. `--feed cond-mat --feed quant-ph`).
The UV-managed `.venv` isolates dependencies (`requests`, `beautifulsoup4`).

Optional shell completion (bash/zsh) is available via `argcomplete`:

```bash
uv run pip install argcomplete
eval "$(register-python-argcomplete arxiv_digest.py)"
```

Add the `eval` line to your shell rc file to keep completion enabled.

## Configuration workflow

`arxiv_digest.py` ships with embedded defaults, so you can copy/paste the file
into ChatGPT Code Interpreter and run it without any side files.

When running locally you can persist tweaks in `arxiv_config.json` (auto-created
next to the script whenever you pass `--save-config`). Every config operation can
be performed via CLI flags, so you rarely need to hand-edit JSON:

| Action | Flag(s) |
| --- | --- |
| Add/remove/rename core keywords | `--add-core tebd` `--remove-core mpo` `--rename-core "anyon:anyons"` |
| Manage favorite authors | `--add-author surname` `--remove-author` `--rename-author "old:new"` |
| Adjust low-priority penalties | `--add-low-priority film` `--remove-low-priority` `--rename-low-priority` |
| Manage feed URLs | `--add-url other=https://arxiv.org/list/quant-ph/new` `--rename-url "cond-mat:cm"` `--delete-url cm` |
| Pick / change default feed | `--set-default-feed cond-mat` or supply explicit `--feed NAME` |
| Show combined config | `--list-config` |

Changes apply immediately in-memory; append `--save-config` to write the new
state back to `arxiv_config.json`. Example:

```bash
uv run python arxiv_digest.py \
  --add-core "rydberg" --add-author "bloch" --save-config
```

Inspect the current configuration at any time:

```bash
uv run python arxiv_digest.py --list-config

### Feed selection cheatsheet

- Use a named feed: `uv run python arxiv_digest.py --feed cond-mat`
- Combine feeds: `uv run python arxiv_digest.py --feed cond-mat --feed cond-mat.quant-gas --top 25`
- Use a URL directly: `uv run python arxiv_digest.py --feed https://arxiv.org/list/quant-ph/new`
- Persist a new feed name: `uv run python arxiv_digest.py --add-url qp=https://arxiv.org/list/quant-ph/new --save-config`
- Make a feed the default: `uv run python arxiv_digest.py --set-default-feed qp --save-config`
```

## Saving results

By default the digest is printed to stdout—great for copy/pasting or terminal
review. To capture the ranked entries as structured data, add
`--output-json path/to/digest.json`:

```bash
uv run python arxiv_digest.py --top 20 --output-json reports/condmat-2025-11-17.json
```

The JSON file includes metadata (timestamp, list of feed URLs, section filters) plus the
top-N entries with scores, titles, authors, sections, links, and summaries. You
can still redirect stdout to a text file if you prefer the plain digest:

```bash
uv run python arxiv_digest.py --top 5 > notes/today.txt
```

## ChatGPT / Code Interpreter usage

1. Copy the entire contents of `arxiv_digest.py` (no other files needed).
2. In ChatGPT (Code Interpreter / Advanced Data Analysis / o1), paste the script
   followed by a prompt such as:

   ```
   Please save that script as arxiv_digest.py and run:
   python arxiv_digest.py --feed cond-mat --feed quant-ph --top 12 --output-json digest.json
   Then show me the console output.
   ```

3. ChatGPT will install dependencies in its sandbox, execute the script, and
   return the digest (and the JSON file if requested). Any CLI flag that works
   locally works the same way in ChatGPT.

Because the script performs live HTTP requests, make sure you are in a mode
that allows outbound network calls; the default “chat” model cannot run Python.

### Suggested GUI prompt

```
You are ChatGPT with Code Interpreter enabled. I will paste a Python script that
fetches and ranks arXiv papers. After pasting, please:
1. Save it as arxiv_digest.py
2. Run: python arxiv_digest.py --feed cond-mat --feed cond-mat.quant-gas --top 15
3. Show me the printed digest

If the script needs any packages, install them first.
```

## Handy examples

Show only cross listings and export the updated config:

```bash
uv run python arxiv_digest.py --sections "Cross" --save-config
```

Try a one-off alternative feed without touching config:

```bash
uv run python arxiv_digest.py --feed https://arxiv.org/list/quant-ph/new
```

Raise/lower the number of entries:

```bash
uv run python arxiv_digest.py --top 5
```

## Ranking overview

The score per paper is computed in `score_paper`:

- +6 per core keyword match (`core_keywords`)
- +6 per highlighted author match (`named_authors`)
- +4 if subjects include `cond-mat.quant-gas`
- +4 if subjects include `cond-mat.mes-hall`
- +2 if subjects include `quant-ph`
- −5 if any low-priority keyword matches (`low_priority_kw`)
- +1 if abstract length exceeds 200 characters

Modify the weighting by editing `score_paper` or adjust the keyword lists via
CLI flags / config. Order of keywords in each list does not impact scoring.

Copy/paste the resulting digest directly into notes, Slack, or ChatGPT. Each
entry includes title, authors, section, link, summary, and the associated score.
