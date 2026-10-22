# GUI guide

<video src="../assets/showcase.mp4" autoplay loop muted playsinline controls width="100%"
       aria-label="A tour of the web app: fetching the past week, hovering highlighted keywords and authors to see their bonus, Why this score?, picking a day, searching, Markdown export, saving to a Zotero collection, the PDF, following an author with the unsaved-changes bar, removing and restoring a paper, scoring an arXiv link, the Keywords, Scoring and Profiles tabs, config as JSON, server sync and highlight colors"></video>

The GUI is a [Streamlit](https://streamlit.io/) app that imports `arxiv_digest` directly, so every fetch / score / format function used by the CLI is also what the GUI runs. No duplication; tweaks in one show up in the other.

## Launching

```bash
uv sync --group gui                       # one-time
uv run streamlit run arxiv_gui.py         # canonical
./launch_gui.sh                           # optional one-shot wrapper
arxiv-gui                                 # if installed via `uv tool install '.[gui]'`
uvx --from '.[gui]' arxiv-gui             # run on the fly, no install
```

Default URL: `http://localhost:8501`. The GUI **opens your browser
automatically**: the `arxiv-gui` launcher passes `--server.headless false` so
you don't have to copy-paste the localhost URL. (The bundled
`.streamlit/config.toml` opts out of Streamlit telemetry; pass
`--server.headless true` to suppress the auto-opened tab, e.g. when launching
from a script.)

## The daily flow

1. **Sidebar**: pick **Timeframe** (`today` / `pastweek`), **Top N**, and which **Feeds** to fetch from. Click **Fetch papers**. Results are cached per `(timeframe, feeds)` and reused automatically — even across app restarts — until the next UTC day (see [Caching](#caching)); click **Clear fetch cache** to force a fresh fetch.
2. **Papers tab**: papers appear ranked. Open *Why this score?* to see exactly which keywords / authors / subjects contributed. Open *Full abstract* without leaving the page.
3. **Tweak preferences** in the **Keywords**, **Authors**, **Low priority**, **Scoring** tabs. The Papers tab re-ranks live on the cached fetch, with no re-fetch needed.
4. **Download** the current ranked list as Markdown or JSON. The Markdown is `--output-markdown`'s format; the JSON holds the same ranked `entries` as `--output-json` (it omits the CLI-only `feed_urls`/`sections` header fields).

## Filtering: replacements & single past days

- **Include replacement submissions** (sidebar checkbox): arXiv's `today` feed
  splits entries into *New submissions*, *Cross submissions*, and *Replacement
  submissions* (papers re-uploaded with a new version). Replacements are
  **hidden by default** so you don't keep seeing the same paper; tick the box to
  keep them. Cross-lists are always kept. The `pastweek` feed contains no
  replacements.
- **Day picker** (Papers tab): when a fetch returns several days (i.e.
  `pastweek`), a **Day** selector lets you view just one past day's ranking,
  useful if you skipped yesterday and want its dedicated list today. The
  newest day comes first.
  - **Limitation:** the fetch covers seven days of submissions, while the day
    labels follow the announcement sections currently shown by arXiv. Weekends
    and holidays may therefore be folded into the next announcement day. arXiv
    exposes **no URL for an arbitrary older day**, so the picker only offers
    sections present in the current fetch.

Both filters are applied at display time, so toggling them re-ranks instantly
with **no re-fetch**.

## Caching

Fetching from arXiv is the slow, rate-limited step (the `pastweek` export API
will temporarily **block your IP** if hit too often — see
[Troubleshooting](troubleshooting.md#arxiv-is-rate-limiting-or-blocking-you)).
To avoid needless refetches the GUI caches results in **two layers**, both keyed
on the `(timeframe, feeds)` you selected:

| Layer | Where | Survives restart? | Expires |
|---|---|---|---|
| In-memory (`st.cache_data`) | RAM, current app process | No | 1 hour, or on **Clear fetch cache** |
| Persistent (disk) | `~/.arxiv_scraper/cache/*.json` | **Yes** | Next **UTC day**, or on **Clear fetch cache** |

On a fetch the GUI checks the in-memory layer, then the disk layer, and only
hits arXiv on a miss. Because arXiv announces once per day, the disk key
includes the **UTC date**: re-selecting the same feeds later the same day (or
after restarting the app) is served instantly from disk with **no network
call**, so a routine re-open never re-triggers the rate limiter. A new UTC day
misses naturally and refetches the fresh announcements.

The disk cache is intentionally small: results are stored as JSON on disk (not
held in memory), files older than **3 days** are pruned on each save, and an
empty/failed fetch is **never** cached (so a fetch that got rate-limited retries
next time instead of pinning zero papers for the day).

### How this differs from the previous cache

Before, the GUI had **only** the in-memory `st.cache_data` layer: it was lost
whenever the Streamlit process restarted and expired after one hour, so a
restart (or an hour later) forced a full refetch — exactly the burst that trips
arXiv's rate limiter. The **persistent disk layer is new**: it makes the cache
survive restarts, key on the UTC day instead of a rolling hour, and prune
itself. The in-memory layer is unchanged and still sits on top for zero-latency
re-ranking within a session.

### Clearing the cache

- **GUI:** click **Clear fetch cache** in the sidebar. This now clears **both**
  layers (in-memory *and* the disk files), then the next **Fetch papers** does a
  fresh fetch.
- **Manually / scripts:** delete the disk cache directory, e.g.
  `rm -rf ~/.arxiv_scraper/cache`, or from Python call
  `arxiv_digest.clear_fetch_cache()`.

## Tabs

The GUI has eight tabs across the top, in this order: **Papers**, **Score a
paper**, **Keywords**, **Authors**, **Low priority**, **Feeds**, **Scoring**,
**Profiles** (plus the sidebar with Timeframe / Top N / Feeds / fetch controls
and the Display + Zotero status sections).

- **Papers**: ranked list, search box (filters by title / authors / abstract), MD + JSON download buttons. Per paper: rank, title, authors, subjects, section, summary, arXiv link, score badge, **Save to Zotero**, **Add author**, **Open PDF** and **Remove** buttons (Remove takes it off the list; the papers below move up and the next one fills the top N; removals are remembered per profile across reloads and later fetches, and can be restored from *Removed papers*), expandable score breakdown, expandable full abstract.
- **Score a paper**: paste an arXiv link or ID to see how it would score under your current config, why it did (or didn't) appear in the digest, and save it to Zotero.
- **Keywords**: spreadsheet-style editor for `core_keywords`. Each match adds the *Per-keyword bonus* (default +6).
- **Authors**: same pattern for `named_authors`. Default +6 per match. Whole-word match by default (configurable in Scoring, like keywords).
- **Low priority**: penalty list. If *any* term matches, the paper takes the *Low-priority penalty* (default −5), once, not per hit.
- **Feeds**: `name → URL` editor. Add custom arXiv lists (e.g. `hep-th=https://arxiv.org/list/hep-th/new`). The `/new` / `/pastweek` suffix is rewritten by the timeframe selector.
- **Scoring**: a **Whole-word matching** toggle (default on; untick for legacy substring matching), then number inputs for each weight: per-keyword bonus, per-author bonus, per-feed subject bonuses, low-priority penalty, long-abstract bonus, abstract-length threshold. **Per-feed bonuses**: every extra feed you add in the Feeds tab gets its own bonus field here (raise or lower how much a paper from that feed scores). Set to 0 to disable.
- **Profiles**: save / load / export / import named configs. Each profile keeps its own list of removed papers (under `~/.arxiv_scraper/removed/`). Files live in `~/.arxiv_scraper/profiles/<name>.json` and persist across project clones. **Write project config** dumps the current config to `arxiv_config.json` in the project root, which is what the CLI picks up on the next run. Use this to push GUI tweaks into your daily CLI digest.

## Highlighting

Matched terms are hover-highlighted in the Papers tab so you can see *why* a
paper ranked at a glance:

- **Authors** in your Authors list: bold, colored.
- **Core keywords**: light highlight; **low-priority terms**: light highlight.
  Shown in the title and the full abstract.
- **Subjects**: feed names that carry a subject bonus are highlighted on the
  paper's **Subjects** line.

Hover any highlight for a tooltip with its score weight (e.g. `core keyword
(+6)`, `low-priority term (−5)`, `subject bonus (+4)`).

Four checkboxes in the sidebar **Display** section toggle each surface
independently: author highlight, keywords in titles, keywords in abstracts, and
keywords in the truncated **summaries** on the paper cards (off by default).
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

The GUI saves papers into your **personal My Library** through Zotero's local
Connector HTTP API. It builds the arXiv `preprint` metadata, then uses Zotero's
save-session endpoints to import the page snapshot and actual PDF file, like the
browser Connector. A single `arxiv-digest` source tag supports duplicate checks.

- **Save to Zotero** popover next to each paper's score, and in the **Score a
  paper** tab.
- **Choose a collection**: the popover lists the personal-library root
  (`(no collection)`) and My Library's collections. Group-library saving is not
  offered. To put a saved paper in a group, move it from My Library in Zotero.
- **Older incomplete saves are repaired**: if the bridge finds its existing
  item but no downloaded PDF, it imports the PDF onto that item instead of
  reporting a false success or creating another preprint.
- **Confirmation**: a transient **Saved ✓** appears next to the score for
  ~30 seconds. Existing complete records are not duplicated.

### Enabling saving to Zotero

1. **Run Zotero**. The sidebar shows **Zotero: connected** when the local
   Connector endpoint is reachable.
2. For the collection picker and duplicate detection, open Zotero → **Settings**
   (macOS: *Preferences*) → **Advanced**, then enable **"Allow other
   applications on this computer to communicate with Zotero"**. Restart if
   prompted. New saves use Zotero's Connector API and do not need an API key.
3. If an existing item needs its missing PDF repaired, Zotero may ask to
   authorize the local API write. Choose **Always Allow** to avoid repeat prompts
   during the multi-step file import.

## Score a paper

Paste an arXiv link or ID (full URL, bare ID, or `arXiv:xxxx`) into the
**Score a paper** tab and click **Score this paper**. It shows:

- The paper's title, authors, subjects, and **total score** under your current
  config.
- A full **breakdown** of which keywords / authors / subjects / penalties
  contributed.
- **Why it did (or didn't) appear in the digest**: if the paper is in the
  current fetch it shows its rank; otherwise it runs a **deterministic check**.
  It fetches the paper's actual submission date and categories, compares them
  against the days present in the fetched feed and your subscribed feeds, and
  tells you precisely whether it was fetched but ranked below `top_n`, submitted
  on a day the fetch didn't cover, or in a category you don't subscribe to.
- A **Save to Zotero** button to save it directly.

## Starter presets

Three built-in, read-only topic bundles (keywords + authors + feeds) give you a
starting point instead of the generic default:

| Preset | Focus |
|--------|-------|
| `open-quantum-systems` | Lindbladian dynamics, dissipation, driven-dissipative & non-Markovian systems |
| `quantum-many-body` | Thermalization, many-body localization, tensor networks, strongly correlated systems |
| `floquet-topological` | Floquet engineering, periodically driven systems & topological matter |

Pick one under **Profiles → Starter presets**: **Load** replaces your working
config, **Add** merges it in. On the CLI use `--preset NAME` / `--add-preset NAME`
(see `--list-presets`). Presets never overwrite your saved profiles or
`arxiv_config.json`; they change only the working config until you save.

## Profiles vs project config

Both save the **complete** configuration: every feed, the keyword / author /
low-priority lists, `top_n`, timeframe, the replacement filter, scoring weights,
and per-feed bonuses. They differ only in *where* the file lives and *who reads
it*:

| | **Profile** | **Project config** |
|---|---|---|
| File | `~/.arxiv_scraper/profiles/<name>.json` | `arxiv_config.json` next to `arxiv_digest.py` |
| How many | Many, named; switch between them | Exactly one |
| Saved via | Profiles tab → **Save** (or sidebar **Load profile**) | Profiles tab → **Write project config** |
| Who reads it | The GUI only | The **CLI** on every run (and the GUI on startup) |
| Use it for | Experimenting, separate "modes" (e.g. `topology-mode`, `cold-atoms`) | Your day-to-day default that the CLI digest uses |

In short: **profiles are personal presets you swap inside the GUI; the project
config is the single file your CLI command picks up.** Push a profile into your
CLI workflow by loading it, then clicking **Write project config**.

Under **Save**, **Download working config (JSON)** and **Copy working config
(JSON)** hand you the config you are working with (say, a preset you just
loaded), unsaved edits included, in the same format as **Export** and
**Import profile from JSON**.

!!! note "Saving and unsaved changes"
    A tab's **Save** button (**Keywords / Authors / Low priority**, **Save feeds**,
    **Apply weights**) writes that tab's settings to the loaded profile, or to
    `arxiv_config.json` when no profile is loaded; other unsaved edits stay unsaved. Other edits (sidebar settings,
    *Add author* on a card, presets, imports) stay unsaved: a bar at the top lists
    them by tab with **Discard** and **Save**, the affected tabs get an orange dot,
    and each tab lists its unsaved entries above its table and marks
    those rows ● in it.

## Moving settings to the iPhone (and back)

Two ways, both described step by step in [Sync across devices](deploy.md):

- **Copy one file, no server**: **Profiles → Export** a profile, AirDrop the
  `.json` to the iPhone and open it with *arXiv Digest*; the other way, the
  app's Settings → **Config file → Export config**, then **Profiles → Import
  profile from JSON** here. See [Copy the config file](deploy.md#copy-the-config-file-without-a-server).
- **Keep them in sync**: run the digest server, then sidebar → **🔄 Sync with
  server** here and Settings → Connection → **Server** in the app. See
  [Connect each device](deploy.md#5-connect-each-device).

## Tips

- The score breakdown is the fastest way to figure out why a low-priority hit overshadowed a keyword match. Open it before re-tweaking weights blindly.
- Profiles are pure JSON; you can hand-edit them outside the GUI or check them into a separate dotfiles repo.
- The GUI writes `arxiv_config.json` only when you ask: **Write project config** in the Profiles tab, or a tab **Save** / **Apply weights** / unsaved-bar **Save** while no profile is loaded (with a profile loaded those save to the profile instead). (With **Sync with server** on, downloading from the server also updates `arxiv_config.json`, so the CLI follows the shared config.)
