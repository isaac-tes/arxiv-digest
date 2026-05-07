# GUI guide

The GUI is a [Streamlit](https://streamlit.io/) app that imports `arxiv_digest` directly, so every fetch / score / format function used by the CLI is also what the GUI runs. No duplication; tweaks in one show up in the other.

## Launching

```bash
uv sync --group gui                       # one-time
uv run streamlit run arxiv_gui.py         # canonical
./launch_gui.sh                           # optional one-shot wrapper
arxiv-gui                                 # if installed via `uv tool install '.[gui]'`
```

Default URL: `http://localhost:8501`. The bundled `.streamlit/config.toml` opts out of Streamlit telemetry and runs headless (no auto-opened browser tab — handy when launching from a script).

## The daily flow

1. **Sidebar** — pick **Timeframe** (`today` / `pastweek`), **Top N**, and which **Feeds** to fetch from. Click **Fetch papers**. Cached for 1 hour per `(timeframe, feeds)` combo; click **Clear fetch cache** to force a refresh.
2. **Papers tab** — papers appear ranked. Open *Why this score?* to see exactly which keywords / authors / subjects contributed. Open *Full abstract* without leaving the page.
3. **Tweak preferences** in the **Keywords**, **Authors**, **Low priority**, **Scoring** tabs. The Papers tab re-ranks live on the cached fetch — no re-fetch needed.
4. **Download** the current ranked list as Markdown or JSON. Output is byte-identical to `--output-markdown` / `--output-json`, so existing pipelines keep working.

## Tabs

- **Papers** — ranked list, search box (filters by title / authors / abstract), MD + JSON download buttons. Per paper: rank, title, authors, section, summary, arXiv link, score badge, expandable score breakdown, expandable full abstract.
- **Keywords** — spreadsheet-style editor for `core_keywords`. Each match adds the *Per-keyword bonus* (default +6).
- **Authors** — same pattern for `named_authors`. Default +6 per match. Case-insensitive substring match.
- **Low priority** — penalty list. If *any* term matches, the paper takes the *Low-priority penalty* (default −5) — once, not per hit.
- **Feeds** — `name → URL` editor. Add custom arXiv lists (e.g. `hep-th=https://arxiv.org/list/hep-th/new`). The `/new` / `/pastweek` suffix is rewritten by the timeframe selector.
- **Scoring** — number inputs for each weight: per-keyword bonus, per-author bonus, the three subject bonuses, low-priority penalty, long-abstract bonus, abstract-length threshold.
- **Profiles** — save / load / export / import named configs. Files live in `~/.arxiv_scraper/profiles/<name>.json` and persist across project clones. **Write project config** dumps the current config to `arxiv_config.json` in the project root, which is what the CLI picks up on the next run — use this to push GUI tweaks into your daily CLI digest.

## Tips

- The score breakdown is the fastest way to figure out why a low-priority hit overshadowed a keyword match — open it before re-tweaking weights blindly.
- Profiles are pure JSON; you can hand-edit them outside the GUI or check them into a separate dotfiles repo.
- The GUI never writes back to `arxiv_config.json` automatically — you must press **Write project config** in the Profiles tab. That keeps surprises out of your CLI workflow.
