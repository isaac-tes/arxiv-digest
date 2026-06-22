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

## Filtering: replacements & single past days

- **Include replacement submissions** (sidebar checkbox) — arXiv's `today` feed
  splits entries into *New submissions*, *Cross submissions*, and *Replacement
  submissions* (papers re-uploaded with a new version). Replacements are
  **hidden by default** so you don't keep seeing the same paper; tick the box to
  keep them. Cross-lists are always kept. The `pastweek` feed contains no
  replacements.
- **Day picker** (Papers tab) — when a fetch returns several days (i.e.
  `pastweek`), a **Day** selector lets you view just one past day's ranking —
  useful if you skipped yesterday and want its dedicated list today.
  - **Limitation:** only the days arXiv's `pastweek` feed still lists (roughly
    the last 5 days) are reachable. arXiv exposes **no URL for an arbitrary
    older day**, so days beyond that window cannot be retrieved this way. The
    picker only ever offers days actually present in the current fetch.

Both filters are applied at display time, so toggling them re-ranks instantly
with **no re-fetch**.

## Tabs

- **Papers** — ranked list, search box (filters by title / authors / abstract), MD + JSON download buttons. Per paper: rank, title, authors, section, summary, arXiv link, score badge, expandable score breakdown, expandable full abstract.
- **Keywords** — spreadsheet-style editor for `core_keywords`. Each match adds the *Per-keyword bonus* (default +6).
- **Authors** — same pattern for `named_authors`. Default +6 per match. Case-insensitive substring match.
- **Low priority** — penalty list. If *any* term matches, the paper takes the *Low-priority penalty* (default −5) — once, not per hit.
- **Feeds** — `name → URL` editor. Add custom arXiv lists (e.g. `hep-th=https://arxiv.org/list/hep-th/new`). The `/new` / `/pastweek` suffix is rewritten by the timeframe selector.
- **Scoring** — number inputs for each weight: per-keyword bonus, per-author bonus, the three subject bonuses, low-priority penalty, long-abstract bonus, abstract-length threshold. **Per-feed bonuses**: every extra feed you add in the Feeds tab gets its own bonus field here (raise or lower how much a paper from that feed scores). Set to 0 to disable.
- **Profiles** — save / load / export / import named configs. Files live in `~/.arxiv_scraper/profiles/<name>.json` and persist across project clones. **Write project config** dumps the current config to `arxiv_config.json` in the project root, which is what the CLI picks up on the next run — use this to push GUI tweaks into your daily CLI digest.

## Profiles vs project config

Both save the **complete** configuration — every feed, the keyword / author /
low-priority lists, `top_n`, timeframe, the replacement filter, scoring weights,
and per-feed bonuses. They differ only in *where* the file lives and *who reads
it*:

| | **Profile** | **Project config** |
|---|---|---|
| File | `~/.arxiv_scraper/profiles/<name>.json` | `arxiv_config.json` next to `arxiv_digest.py` |
| How many | Many, named — switch between them | Exactly one |
| Saved via | Profiles tab → **Save** (or sidebar **Load profile**) | Profiles tab → **Write project config** |
| Who reads it | The GUI only | The **CLI** on every run (and the GUI on startup) |
| Use it for | Experimenting, separate "modes" (e.g. `topology-mode`, `cold-atoms`) | Your day-to-day default that the CLI digest uses |

In short: **profiles are personal presets you swap inside the GUI; the project
config is the single file your CLI command picks up.** Push a profile into your
CLI workflow by loading it, then clicking **Write project config**.

!!! warning "Save/Apply before saving"
    Edits in the **Keywords / Authors / Low priority** tabs only enter the live
    config when you click that tab's **Save** button; **Feeds** edits need
    **Save feeds**; scoring/per-feed changes need **Apply weights**. A profile or
    project-config save captures the *current* live config — so apply your tab
    edits first, otherwise they won't be included.

## Tips

- The score breakdown is the fastest way to figure out why a low-priority hit overshadowed a keyword match — open it before re-tweaking weights blindly.
- Profiles are pure JSON; you can hand-edit them outside the GUI or check them into a separate dotfiles repo.
- The GUI never writes back to `arxiv_config.json` automatically — you must press **Write project config** in the Profiles tab. That keeps surprises out of your CLI workflow.
