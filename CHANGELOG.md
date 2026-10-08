# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Update notice for `arxiv-gui`**: launching the GUI prints the same one-line "newer release available, run `arxiv-digest update`" notice as the CLI, and the GUI sidebar shows a small note under the title. Both use the existing release check, which asks GitHub at most once a day and stays silent offline.
- **iOS Standalone mode ("On this device")**, now the default for new installs: the app fetches the past week from the arXiv export API and today's `/new` listing, scores on the phone with a Swift port of the engine (parity-tested against the Python engine), and keeps config and removed papers on the device. No server needed (ADR 0009).
- **iOS math rendering**: inline LaTeX shows as Unicode in titles and lists, and the paper page typesets math abstracts with bundled KaTeX (offline).
- **Add author from a paper**: an *Add author* popover on each GUI paper card (and the Score result) and an authors menu in the iOS paper detail append that paper's author to the highlighted authors. It edits the working config only; Save applies it.
- **iOS app reaches parity with the web GUI** (`ios/`, branch `feat/swift_ios`). Four tabs:
  - **Papers**: the ranked digest for the saved timeframe and Top N, a day picker for past-week fetches, search over title/authors/abstract, swipe (or long-press) to remove a paper with Undo, a *Removed papers* section with Restore / Restore all, fetch notices, and Markdown/JSON export in the GUI's formats. Cards highlight keywords, named authors and feed-bonus subjects the way the GUI does.
  - **Score**: paste an arXiv link or id; shows the score, breakdown, and either the rank in the Papers view or the GUI's reason it is absent (below the cutoff, removed, a replacement, another day, or never fetched).
  - **Config**: keyword / author / low-priority editors, feeds with subscribe toggles and *Include replacement submissions*, scoring weights and per-feed subject bonuses, and the starter presets (Load / Add). Edits stay unsaved until **Save**, which confirms with a toast and re-ranks the digest.
  - **Settings**: server address or **demo mode** (built-in sample papers, no server needed), the Display toggles including *Highlight keywords in summaries*, per-aspect colors with font tint, and Zotero status.
- **Share to Zotero** on iOS when the server has no Zotero key: the share sheet hands the arXiv page to the Zotero app.
- **Digest service**: `GET /digest` takes `day`, skips the user's removed papers while ranking, and returns abstracts, breakdowns, removed papers, available days, filter counts and fetch notices. New `/removed` endpoints; `/config/defaults`, `/config/presets/info` and `/config/presets/{name}/load`; preset load/merge accept the working config and `save=false`.

### Changed
- **iOS highlights**: the dotted underline is off by default (Settings → Display → *Underline highlights*), and highlight text is darkened in light mode for readable contrast.
- **Digest service fetches the past week like the CLI**: through the arXiv export API with a true seven-day window (`fetch_pastweek`), not the unreliable `/pastweek` HTML listing. The fetch cache now holds raw papers keyed on the resolved feeds, so editing keywords, weights, the day or removals re-ranks without re-fetching, and changing feeds can no longer serve another feed set's cache.
- **Score a paper (service)** reports the rank shown in the Papers view or why the paper is absent, like the GUI. A paper already in the fetched digest is scored from it, so scoring keeps working while arXiv's export API is rate-limiting.
- **`GET /config` returns the effective config** with every field filled in; invalid configs are rejected with 422.

### Fixed
- **A cleared keyword, author or low-priority list stays cleared.** Loading a config or profile whose list was saved empty used to bring back the built-in defaults; now only a missing list does.
- **Zotero saves from the service** put given names and surnames in the right fields (they were swapped).
- **Named authors highlight like they score** in the service and the app (middle initials tolerated).

### Removed
- **The service's Zotero `deeplink` mode.** Its `zotero://select` link could only select an existing item, so it saved nothing (ADR 0005, amended).

## [0.6.3] - 2026-09-30

### Added
- **Remove a paper from the digest.** Each paper card in the GUI has a ✕ button that drops it from the ranked list. Papers below it move up one place, and the first paper past the top-N cutoff takes the freed slot. Each profile keeps its own removal list (`~/.arxiv_scraper/removed/<profile>.json`, or `~/.arxiv_scraper/removed_papers.json` while no profile is loaded), so removals survive page reloads, app restarts and later fetches: a paper removed from today's ranking is also absent from the week's. The sidebar now shows which profile is loaded, and **Score a paper** reports a removed paper as removed and ranks the others without it. A *Removed papers* expander above the list offers the removed papers that would otherwise be in the ranking shown (not, say, one removed from yesterday's digest), restorable one at a time or all at once. Markdown/JSON downloads follow the list as shown.

### Fixed
- **Score a paper reports the rank the Papers tab shows** (#7). Both tabs now build the digest the same way: replacement submissions and the Papers tab's Day choice are applied before ranking, and a hidden paper is explained as a replacement, another day, removed, or below the top-N cutoff.
- **Score a paper no longer crashes for a paper also listed in the Papers tab** (#8). Each tab's *Save to Zotero* popover now has its own widget keys.
- **Score a paper only offers a real Restore action.** If the removed paper is hidden by current filters or the top-N cutoff, the message tells you how to reveal it in the Papers tab first.
- **Loaded GUI profiles survive reloads.** A fresh session restores the last loaded profile and its saved config before rendering the digest, keeping that profile's removal list active.
- **Profile names stay within their storage directories.** Path-like names and the reserved `(unsaved)` are rejected before profile and removal files are read, written, or deleted.
- **The sidebar profile selector follows the loaded config.** Switching profiles or loading a preset/import clears stale widget state before the next render.
- **Save as snapshots the current removals.** The new profile's removal list is an exact copy of the current one (stale or damaged lists left under that name are replaced), and if the copy fails nothing is saved and the current profile stays active.
- **Malformed saved profiles no longer block GUI startup.** The app falls back to project config and keeps the damaged file available for deletion.
- **Score a paper matches a bare arXiv ID with a version.** Pasting `2607.21663v2` kept the `v2`, so a paper that was in the digest was reported as never fetched. The version is now stripped, as it already was for pasted URLs.

## [0.6.2] - 2026-09-21

### Fixed
- **Full author names with middle initials now match.** A named author like
  `Hannah Price` now scores and highlights a paper whose author list renders
  the same person as `Hannah M. Price` (and vice versa: a config entry
  carrying the initial matches the bare name). Multi-token names match on
  given + surname within a single author, ignoring middle names/initials on
  either side, while single-token surnames keep the whole-token word-boundary
  check (so `ma` still never matches `Mao`).

## [0.6.1] - 2026-09-15

### Added
- **Persistent fetch cache.** Fetch results are now cached on disk under
  `~/.arxiv_scraper/cache/`, keyed on `(timeframe, feeds, UTC day)`. Unlike the
  previous in-memory-only cache, this survives app restarts and reuses the same
  day's results with no network call, so a routine re-open never re-triggers
  arXiv's rate limiter. A new UTC day misses and refetches; files older than
  3 days are pruned and empty/failed fetches are never cached. **Clear fetch
  cache** now clears both the in-memory and disk layers.
- **HTML `/pastweek` fallback.** When the export API is rate-limited or timing
  out, `pastweek` falls back to arXiv's HTML listing (a more tolerant host)
  instead of failing, and reports the fallback in the CLI (stderr) and GUI
  (warning).

### Fixed
- **`pastweek` no longer hangs for minutes when arXiv rate-limits the export
  API.** Retry backoff is capped and bounded by a ~30s wall-clock budget, a
  blocked API is detected once and skipped for the remaining feeds, and the
  GUI surfaces a clear error instead of crashing. Read timeout raised to
  `(10, 60)s` and request pacing set to arXiv's recommended ~3s.

## [0.6.0] - 2026-09-11

### Added
- **`arxiv-digest update` (alias: `arxiv-digest upgrade`).** The CLI now
  self-updates: it reinstalls the tool from the latest GitHub release tag,
  so the upgrade works even without the original clone. A cached (24 h)
  check prints a one-line notice at the end of normal runs when a newer
  release is out; `--no-update-check` suppresses it, and notice + upgrade
  both fail silently when GitHub is unreachable.
- **Summary highlight toggle.** The sidebar Display section gains a fourth
  checkbox that highlights matched keywords / low-priority terms in the
  truncated abstract summaries on the paper cards, mirroring the full-
  abstract highlight. Off by default.

### Changed
- **Quickstart simplified.** Setup is now clone → `uv tool install '.[gui]'`
  → `arxiv-gui`; the README leads with the quick start and moves defaults,
  starter presets, and the feature overview below it. The GUI guide lists
  the eight tabs the app actually renders, including **Score a paper**.
- **Architecture decision records remain in the repository but are excluded
  from the public GitHub Pages site.**

## [0.5.6] - 2026-09-10

### Changed
- **Pastweek keeps a true seven-day submission window.** Its day labels use
  the announcement sections shown by arXiv, so the GUI and the arXiv listing
  use the same dates.

### Fixed
- **Pastweek fetches now query every selected category.** The export API treats
  `cat:cond-mat` as an exact category rather than a wildcard for feeds such as
  `cond-mat.quant-gas` and `cond-mat.mes-hall`.
- **Scores and fetched results now agree for subcategory papers.** A paper that
  scores within the configured Top N is no longer omitted because its selected
  subcategory was skipped by the GUI.

## [0.5.5] - 2026-09-10

### Added
- **Docs badge** in the README links directly to the GitHub Pages site.

### Changed
- **Feed URL and timeframe handling is shared by the CLI and GUI** through the
  `feed_url()` and `fetch_pastweek()` helpers.
- **Starter presets and package metadata no longer include personal research
  profile details.** The presets remain generic quantum-physics starting points.
- **CLI and GUI documentation now agree** on JSON output, scoring, and the
  available command-line flags.

### Fixed
- **Unknown feeds now fail clearly during pastweek fetches** instead of
  producing an empty digest.
- **Author hover tooltips now render in the GUI** through its CSS tooltip styles.

## [0.5.4] - 2026-09-03

### Added
- **Keyword and author font tinting is on by default** in the GUI: the sidebar
  *Font: keywords* / *Font: authors* toggles default to checked (low-priority and
  subjects remain background-highlight only), matching the original behavior.

### Changed
- **Group-library saving removed.** Zotero's local HTTP API has no supported
  `/groups` listing or write route, so group saves could never use the local
  "Allow this application?" authorization flow. The Save-to-Zotero popover now
  saves to personal **My Library** collections only; to place an item in a group,
  copy/drag it there in Zotero. The cloud-API/key path, its settings, and the
  `zotero_cloud` module were dropped (see ADR 0002, marked superseded).

### Fixed
- **False "Saved to Zotero:" toast after a denied/failed save.** The save outcome
  was consumed only inside the popover, so a denial could linger and fire a
  stale success seconds later. Success is now shown only by the transient
  "Saved ✓" tick, and errors are consumed immediately — a denied or failed save
  never shows as a success.
- **arXiv pastweek fetch hardened against rate limits and timeouts.** The export
  API fetch retries 429/5xx and read/connect timeouts with backoff (honoring
  `Retry-After`), sends a descriptive `User-Agent`, and uses a moderate page size
  (500) so a big query neither trips the 429 limiter nor exceeds the read
  timeout.
- **Duplicate sub-category feed requests removed.** A `cond-mat.*` feed is no
  longer fetched when its parent `cond-mat` is also selected, cutting redundant
  arXiv requests while preserving dedup.

## [0.5.1] - 2026-08-22

### Added
- **README preview image**: a centered screenshot of a ranked paper card
  (highlighted keywords/authors, score breakdown, Save to Zotero) right under
  the badges, synced to the docs site via `scripts/generate_readme.py`.
- **`uvx` run option**: the GUI/CLI can now be run on the fly without
  installing a persistent tool: `uvx --from '.[gui]' arxiv-gui` (or
  `arxiv-digest`). Documented in the README, quickstart, and GUI/CLI guides.

### Fixed
- **GUI no longer auto-opened the browser**: the `arxiv-gui` launcher now
  passes `--server.headless false` to Streamlit so the browser pops up
  automatically instead of requiring a manual copy-paste of the localhost URL.
- **`zotero_bridge` missing from the built package**: `zotero_bridge.py` was
  absent from the wheel/sdist `only-include`/`include` lists, so the GUI
  crashed with `ModuleNotFoundError` when installed via `uv tool install` or
  run via `uvx`. It's now packaged, so the Zotero save feature works in
  installed/`uvx` runs too.
- **Color/font-toggle sidebar widgets could show stale state after switching
  config**: `_reset_widget_state()`'s default key list only covered the
  weight and editor widgets, not the highlight/color/font-tint checkboxes and
  color pickers. Loading a profile, a starter preset, or resetting weights
  now also clears those keys so the sidebar reliably reflects the config that
  was just loaded.
- **Author names and the arXiv-link/subjects line were barely visible in
  light mode**: `.paper-authors` / `.paper-meta` hardcoded a near-white /
  mid-grey color tuned for Streamlit's dark theme. A `prefers-color-scheme:
  light` override now darkens them for light mode; dark mode is unchanged.

## [0.5.0] - 2026-08-21

### Added
- **Zotero bridge** (`zotero_bridge.py`): save papers straight into your local
  Zotero library via Zotero's local HTTP API, the same mechanism the official
  Zotero Connector uses, with no API-key setup. A **Save to Zotero** button sits
  next to each paper's score (and in the Score-a-paper tab). It fetches the paper
  from the arXiv export API and writes a `preprint` item replicating the
  connector's fields, category tags, and PDF/Snapshot attachments, plus an
  `arxiv-digest` source tag. The sidebar shows a **Zotero: connected / not
  running** status pill; the first write triggers Zotero's native authorization
  dialog. See `docs/adr/0001-zotero-local-api-bridge.md`.
- **Score a paper tab**: paste an arXiv link or ID to see how it would score
  under your current config, a full per-aspect breakdown, and *why* it did (or
  didn't) appear in the digest, distinguishing "fetched but below top-N" from
  "never fetched (outside feeds/timeframe)".
- **Per-aspect highlight colors**: keywords, low-priority, authors, and subjects
  each get a configurable color via sidebar color pickers (defaults preserve the
  original palette). Subjects are now highlighted on a new **Subjects** line on
  each paper card. Colors persist in profiles and the project config
  (`color_keyword` / `color_low_priority` / `color_author` / `color_subject`).
- **Per-aspect font-color toggles**: each aspect also has a **"Font: …"** toggle
  to tint the matched text's font with the aspect color (default off for
  keywords/low-priority/subjects, on for authors, preserving prior behavior).
  Persisted as `color_font_keyword` / `color_font_low_priority` /
  `color_font_author` / `color_font_subject`.
- **Zotero collection picker**: the Save-to-Zotero control is now a **popover**
  that lists your Zotero collections (plus **My Library**) with a filter-as-you-type
  search bar; pick one and the paper is saved there
  (`save_to_zotero(arxiv_id, collection_key=…)`).
- **Duplicate-save guard**: saving runs via an `on_click` callback (exactly once
  per click) with a per-paper in-flight guard and a session-state "saved" set, so
  a paper can never be written to Zotero more than once per session, even on a
  double-click or rerun. The button shows **Saved ✓** afterwards.
- **pastweek uses the arXiv API date-range**: the `pastweek` timeframe now fetches
  via the arXiv export API `submittedDate:[...]` query for a true 7-day window,
  because arXiv's `/pastweek` HTML listing is unreliable (it returns 1-5 days).
  `today` keeps the HTML `/new` feed. Fixes papers submitted on days the
  `/pastweek` feed skipped (e.g. `2608.16520`).

### Changed
- **Zotero bridge now detects read-only Zotero**: Zotero versions before 10
  expose a read-only local API (writes return `400 Endpoint does not support
  method`). The bridge detects this via the missing `Zotero-Server-ID` header and
  explains that Zotero 10+ is required, instead of surfacing the cryptic 400. On
  Zotero 10+ it runs the local write-authorization flow (`POST /api/local/
  authorize`) to obtain a key.
- **Zotero 10 connection is memory-efficient**: the server ID and authorized local
  API key are cached, so we don't re-GET the server ID or re-prompt the authorize
  dialog on every save. A consumed single-use key (401) triggers one re-authorize
  and retry.
- **Save confirmation is a toast**: "Saved to Zotero: …" now shows as a toast
  that auto-dismisses after 10 seconds (`st.toast(..., duration=10000)`) instead
  of a persistent success message.
- **Subjects line moved**: the highlighted **Subjects** line now sits on the same
  meta row as the **arXiv ↗** link (below the summary), to the **right** of the
  link, not above the abstract summary.
- **Absence reason is network-safe**: the Score-a-paper tab's deterministic
  absence check now handles arXiv network failures gracefully instead of
  crashing the tab.
- **Deterministic absence reason**: the Score-a-paper tab now fetches the paper's
  actual submission date and categories and compares them against the days
  present in the fetched feed and the subscribed feeds, giving a precise reason
  (e.g. "submitted on 2026-08-17, but the fetched feed only covers 2026-08-18…")
  instead of a vague "likely outside the timeframe".
- **Release automation** (`.github/workflows/release.yml`): pushing a `v*` tag runs the test suite, checks the tag matches `pyproject.toml`'s version, extracts this file's matching section as the release notes, and publishes the GitHub Release. The job fails rather than releasing if the tests fail, the versions disagree, or no changelog section exists for the tag.
- **Release process**: GitHub Releases are now published for every tag, with notes taken verbatim from this file's matching section, so the two can't drift. Backfilled the missing `v0.2.0` release (`v0.3.0` / `v0.4.0` already had one).
- **`.beads/issues.jsonl` and `.beads/interactions.jsonl` are no longer tracked in git.** Per the [beads sync model](https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md) these are passive exports, not the sync channel; cross-machine sync goes through Dolt (`refs/dolt/data` on origin, `bd dolt push` / `bd dolt pull`), which is configured for this repo, so collaborators are unaffected. Tracking them would have published issue text and contributor email addresses when the repo goes public. Beads config (`config.yaml`, `metadata.json`, `recipes.toml`, `hooks/`) stays tracked, as `config.yaml` is required for remote wiring.
- `LICENSE` and `pyproject.toml` now name the copyright holder / author as **isaac-tes** rather than the `isaac-tes` GitHub handle.

### Fixed
- **Zotero save duplicated the same paper repeatedly**: the dedup check
  (`_zotero_item_exists`) searched with Zotero's `q=<url>&qmode=everything`
  full-text parameter, which does not index the `url`/`archiveID` metadata
  fields, so it almost never found a paper that was already saved, and the
  write went through again every time. It now searches the small, bounded set
  of items carrying our own `arxiv-digest` tag and matches `archiveID`
  exactly, which is reliable regardless of Zotero's text-indexing delays.
- **"Saved to Zotero" toast kept re-appearing**: the save result was left in
  `st.session_state` indefinitely, so any unrelated Streamlit rerun while the
  popover stayed open re-displayed the toast, easy to mistake for the paper
  being saved again. The result is now popped after being shown once.
- Confirmed via live testing that the third-party
  [zotero-arxiv-workflow](https://github.com/AllanChain/zotero-arxiv-workflow)
  Zotero plugin, if installed, can compound this by reprocessing arXiv saves;
  disabling it is recommended alongside this fix.

### Known limitations
- The Zotero save still attaches the arXiv PDF as a **linked** URL attachment,
  not a locally-imported/downloaded file the way the official Zotero
  Connector does (`arxiv_scraper_cli-ynp`).

## [0.4.1] - 2026-07-27

### Fixed
- **All `pastweek` papers showed "(No abstract available.)"** (`arxiv_scraper_cli-an7`): `paper["id"]` was taken from the listing link's *text*, which arXiv renders as `arXiv:2512.00001`. The abstract back-fill then requested `https://arxiv.org/abs/arXiv:2512.00001`, which arXiv rejects with **HTTP 406**, and the failure was swallowed unless `--verbose`. `/new` pages inline their abstracts so `today` was unaffected; `/pastweek` pages omit them entirely and depended wholly on that broken fetch. Ids are now parsed from the `/abs/` href and normalized via the new `normalize_arxiv_id` helper.
  - **Scores shift for `pastweek`**: abstract keyword hits and the `+1` long-abstract bonus never fired before, so rankings will differ (correctly) from previous runs.
  - **`paper["id"]` format changed** from `arXiv:2512.00001` to the bare `2512.00001`. It is an internal join key, but it also appears in JSON report output.

### Changed
- `fetch_abstract` is hardened: it re-normalizes its own argument (a prefixed id still resolves), retries transient failures twice with backoff, accepts both `blockquote.abstract` and `div.abstract`, and strips the leading `Abstract:` label with an anchored regex instead of a global `.replace()` that could corrupt body text.
- Back-fill failures are no longer silent: when at least half of them come back empty, a warning is printed to stderr regardless of `--verbose`.
- The inline-abstract fallback no longer risks selecting the title; it skips text already captured as title/authors/subjects.

## [0.4.0] - 2026-07-17

### Fixed
- **Substring matching false-positives** ([#4](https://github.com/isaac-tes/arxiv-digest/issues/4), `arxiv_scraper_cli-28n`): keyword/author/low-priority matching bled across word interiors: `mpo` scored *temporal*/*composition*, author `ma` scored *Mao*, `bloch` scored *Blochwitz*. Matching is now **whole-word by default** via `(?<!\w)term(?!\w)` lookarounds (new helpers `term_pattern` / `term_matches`). Hyphens, spaces, and punctuation count as boundaries, so `MPO-based` and `the mpo ansatz` still match.

### Added
- **`word_boundary_matching` config flag** (default `true`): set `false` for the legacy substring behavior. Exposed as a **Whole-word matching** checkbox in the GUI Scoring tab and persisted in profiles / `arxiv_config.json`.
- **Starter presets** (`arxiv_scraper_cli-7f2`): three read-only built-in topic bundles: `open-quantum-systems`, `quantum-many-body`, `floquet-topological` (keywords + authors + feeds/feed_weights). GUI **Profiles → Starter presets** with **Load** (replace) / **Add** (union) buttons; CLI `--preset NAME`, `--add-preset NAME` (repeatable), `--list-presets`. Non-destructive: presets change only the in-memory config and never write to saved profiles or `arxiv_config.json`. New API: `PRESETS`, `preset_names`, `preset_config`, `merge_preset`.

### Changed
- The GUI keyword/author highlighters now share the scorer's matcher, so highlights and scores stay in sync (a term that no longer scores no longer highlights).
- Subjects/`feed_weights` intentionally keep substring matching, so a parent feed `cond-mat` still scores `cond-mat.quant-gas` papers.

## [0.3.0] - 2026-06-22

### Added
- **Submission-type filtering**: arXiv `today`/`/new` *Replacement submissions* are hidden by default (cross-lists kept). `--include-replacements` CLI flag, `cfg.include_replacements`, and a GUI sidebar toggle. Helpers `section_category` / `filter_papers`.
- **Back-in-time day picker** (GUI): view a single past day's ranking from the days `pastweek` returns. Clearly flags arXiv's hard limit (no arbitrary-day URL → ~last 5 days). Helpers `section_day_label` / `available_day_labels`.
- **Per-feed subject bonuses**: subject scoring is now driven by `Config.feed_weights` (a bonus per configured feed found in a paper's subjects). The Scoring tab auto-generates a field per feed.
- **GUI highlighting**: hover-highlight matched authors, plus core keywords (teal) and low-priority terms (red) in the title and full abstract, each with a weight tooltip. Three persisted display toggles (`highlight_authors` / `highlight_terms_title` / `highlight_terms_abstract`).
- `docs/troubleshooting.md`; docs for filters, day-picker limit, per-feed bonuses, highlighting, and profiles-vs-project-config.

### Fixed
- **GUI state bug**: keyed Streamlit widgets ignored `value=`/`default=` on rerun, so Load profile / Reset / Apply weights / Import left widgets showing stale state. Fixed by clearing the affected widget state before `st.rerun()`.
- **Author scoring**: named authors now match the author list only; "Bloch theorem" in an abstract no longer awards author points.
- Abstract-bonus tooltip now uses a CSS tooltip (Streamlit strips the `title` attribute).

### Changed
- Removed the hardcoded `quant_gas_subject` / `mes_hall_subject` / `quant_ph_subject` fields from `ScoringWeights`; subject scoring unified into `feed_weights`. **Pre-0.3.0 configs auto-migrate on load** (`_hydrate_feed_weights`).
- Test suite grown to 102 (scoring, filters, config round-trip incl. full-field coverage, GUI AppTest).

## [0.2.0] - 2026-05-06

### Added
- **Streamlit GUI** (`arxiv_gui.py`) with seven tabs (Papers, Keywords, Authors, Low priority, Feeds, Scoring, Profiles). Live re-ranking, per-paper score breakdown via `explain_score`, named profile management under `~/.arxiv_scraper/profiles/`.
- `ScoringWeights` dataclass on `Config` so every scoring rule is configurable from the GUI or `arxiv_config.json`.
- `explain_score(paper, cfg)` returns a per-rule contribution breakdown; `score_paper` now delegates to it so the two functions cannot drift.
- 74-test pytest suite covering scoring, config round-trip, fetch (mocked), formatting, CLI flag handling, and a Streamlit AppTest GUI smoke test. Runs in ~1s with no network calls.
- Console-script entry points: `arxiv-digest` (CLI) and `arxiv-gui` (Streamlit launcher), installable via `uv tool install '.[gui]'`.
- mkdocs-material documentation site with Quickstart, GUI guide, CLI guide, Scoring guide.
- GitHub Actions: CI (pytest on Python 3.12) and a docs build/deploy workflow (deploy gated on repo visibility).
- `LICENSE` (MIT), `CHANGELOG.md`, `CONTRIBUTING.md`, `.python-version`, `.streamlit/config.toml` (telemetry opt-out).
- Optional `launch_gui.sh` one-shot wrapper.

### Fixed
- `Config.from_json` now defaults `top_n` to 20 (was 15) and `timeframe` to `"pastweek"` (was `"today"`), matching `Config()` direct-construction defaults. Eliminated silent CLI-vs-JSON drift.
- Removed duplicate `"pumping"` entry from `_default_core_keywords()`.

### Changed
- `pyproject.toml` switched to PEP 735 `[dependency-groups]` (`test`, `gui`, `docs`, `dev`) plus PEP 621 `[project.optional-dependencies] gui` for tool installs.

## [0.1.0] - pre-GUI baseline

### Added
- Single-file CLI (`arxiv_digest.py`) that scrapes arXiv listing pages and ranks papers by user-defined keywords / authors / subjects.
- `arxiv_config.json` persistence with `--save-config` and CLI mutators (`--add-core`, `--add-author`, etc.).
- Markdown and JSON report output (`--output-markdown`, `--output-json`).
