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

- **Papers** — ranked list, search box (filters by title / authors / abstract), MD + JSON download buttons. Per paper: rank, title, authors, subjects, section, summary, arXiv link, score badge, a **Save to Zotero** button, expandable score breakdown, expandable full abstract.
- **Score a paper** — paste an arXiv link or ID to see how it would score under your current config, why it did (or didn't) appear in the digest, and save it to Zotero.
- **Keywords** — spreadsheet-style editor for `core_keywords`. Each match adds the *Per-keyword bonus* (default +6).
- **Authors** — same pattern for `named_authors`. Default +6 per match. Case-insensitive substring match.
- **Low priority** — penalty list. If *any* term matches, the paper takes the *Low-priority penalty* (default −5) — once, not per hit.
- **Feeds** — `name → URL` editor. Add custom arXiv lists (e.g. `hep-th=https://arxiv.org/list/hep-th/new`). The `/new` / `/pastweek` suffix is rewritten by the timeframe selector.
- **Scoring** — number inputs for each weight: per-keyword bonus, per-author bonus, the three subject bonuses, low-priority penalty, long-abstract bonus, abstract-length threshold. **Per-feed bonuses**: every extra feed you add in the Feeds tab gets its own bonus field here (raise or lower how much a paper from that feed scores). Set to 0 to disable.
- **Profiles** — save / load / export / import named configs. Files live in `~/.arxiv_scraper/profiles/<name>.json` and persist across project clones. **Write project config** dumps the current config to `arxiv_config.json` in the project root, which is what the CLI picks up on the next run — use this to push GUI tweaks into your daily CLI digest.

## Highlighting

Matched terms are hover-highlighted in the Papers tab so you can see *why* a
paper ranked at a glance:

- **Authors** in your Authors list — bold, colored.
- **Core keywords** — light highlight; **low-priority terms** — light highlight.
  Shown in the title and the full abstract.
- **Subjects** — feed names that carry a subject bonus are highlighted on the
  paper's **Subjects** line.

Hover any highlight for a tooltip with its score weight (e.g. `core keyword
(+6)`, `low-priority term (−5)`, `subject bonus (+4)`).

Three checkboxes in the sidebar **Display** section toggle each surface
independently — author highlight, keywords in titles, keywords in abstracts.
They are part of the config, so profiles and the project config remember them.

### Highlight colors

Each aspect has its own color, chosen with a **color picker** in the sidebar
**Display** section:

- **Keywords** (default blue `#388bfd`)
- **Low priority** (default red `#f85149`)
- **Authors** (default green `#3fb950`)
- **Subjects** (default purple `#a371f7`)

By default the highlight is a light background tint. For each aspect you can
also tick **"Font: …"** to tint the matched text's font with the aspect color
too (authors are font-tinted by default, matching the original behavior).

Colors apply live in the current session and persist when you save a profile or
write the project config.

## Zotero bridge

The GUI can save papers straight into your **local Zotero library** — the same
mechanism the official Zotero Connector uses. No API key setup is needed.

- **Save to Zotero** popover next to each paper's score, and in the **Score a
  paper** tab. It fetches the paper from the arXiv export API and writes a
  `preprint` item with the same fields, category tags, and PDF/Snapshot
  attachments the Zotero Connector would produce, plus an `arxiv-digest` source
  tag.
- **Choose a collection**: the popover lists your Zotero collections (plus
  **My Library**); pick one and the paper is saved there.
- **Confirmation**: a toast shows *"Saved to Zotero: …"* and auto-dismisses
  after 10 seconds. Each paper saves at most once per session (the button shows
  **Saved ✓** afterwards) to avoid accidental duplicates.

### Enabling saving to Zotero

Saving uses Zotero's **local HTTP API**, which must be switched on:

1. **Install/run Zotero 10 or newer** — older versions expose a read-only local
   API and cannot save (the button explains this).
2. Open Zotero → **Settings** (macOS: *Preferences*) → **Advanced** tab.
3. Tick **"Allow other applications on this computer to communicate with
   Zotero"**.
4. Restart Zotero if prompted. The GUI sidebar should now show **Zotero:
   connected**.
5. On the **first save**, Zotero pops an *"Allow this application to modify your
   library?"* dialog — click **Allow** (or **Always Allow**) once, then save
   again.

The sidebar shows a **Zotero: connected / not running** status pill so you can
tell at a glance whether saving is available.

## Score a paper

Paste an arXiv link or ID (full URL, bare ID, or `arXiv:xxxx`) into the
**Score a paper** tab and click **Score this paper**. It shows:

- The paper's title, authors, subjects, and **total score** under your current
  config.
- A full **breakdown** of which keywords / authors / subjects / penalties
  contributed.
- **Why it did (or didn't) appear in the digest**: if the paper is in the
  current fetch it shows its rank; otherwise it runs a **deterministic check** —
  it fetches the paper's actual submission date and categories, compares them
  against the days present in the fetched feed and your subscribed feeds, and
  tells you precisely whether it was fetched but ranked below `top_n`, submitted
  on a day the fetch didn't cover, or in a category you don't subscribe to.
- A **Save to Zotero** button to save it directly.

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
