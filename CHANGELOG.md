# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Zotero bridge** (`zotero_bridge.py`): save papers straight into your local
  Zotero library via Zotero's local HTTP API — the same mechanism the official
  Zotero Connector uses, with no API-key setup. A **Save to Zotero** button sits
  next to each paper's score (and in the Score-a-paper tab). It fetches the paper
  from the arXiv export API and writes a `preprint` item replicating the
  connector's fields, category tags, and PDF/Snapshot attachments, plus an
  `arxiv-digest` source tag. The sidebar shows a **Zotero: connected / not
  running** status pill; the first write triggers Zotero's native authorization
  dialog. See `docs/adr/0001-zotero-local-api-bridge.md`.
- **Score a paper tab**: paste an arXiv link or ID to see how it would score
  under your current config, a full per-aspect breakdown, and *why* it did (or
  didn't) appear in the digest — distinguishing "fetched but below top-N" from
  "never fetched (outside feeds/timeframe)".
- **Per-aspect highlight colors**: keywords, low-priority, authors, and subjects
  each get a configurable color via sidebar color pickers (defaults preserve the
  original palette). Subjects are now highlighted on a new **Subjects** line on
  each paper card. Colors persist in profiles and the project config
  (`color_keyword` / `color_low_priority` / `color_author` / `color_subject`).
- **Per-aspect font-color toggles**: each aspect also has a **"Font: …"** toggle
  to tint the matched text's font with the aspect color (default off for
  keywords/low-priority/subjects, on for authors — preserving prior behavior).
  Persisted as `color_font_keyword` / `color_font_low_priority` /
  `color_font_author` / `color_font_subject`.

### Changed
- **Zotero bridge now detects read-only Zotero**: Zotero versions before 10
  expose a read-only local API (writes return `400 Endpoint does not support
  method`). The bridge detects this via the missing `Zotero-Server-ID` header and
  explains that Zotero 10+ is required, instead of surfacing the cryptic 400. On
  Zotero 10+ it runs the local write-authorization flow (`POST /api/local/
  authorize`) to obtain a key.
- **Subjects line moved**: the highlighted **Subjects** line now sits on the same
  meta row as the **arXiv ↗** link (below the summary), not above the abstract
  summary.
- **Deterministic absence reason**: the Score-a-paper tab now fetches the paper's
  actual submission date and categories and compares them against the days
  present in the fetched feed and the subscribed feeds, giving a precise reason
  (e.g. "submitted on 2026-08-17, but the fetched feed only covers 2026-08-18…")
  instead of a vague "likely outside the timeframe".
- **Release automation** (`.github/workflows/release.yml`): pushing a `v*` tag runs the test suite, checks the tag matches `pyproject.toml`'s version, extracts this file's matching section as the release notes, and publishes the GitHub Release. The job fails rather than releasing if the tests fail, the versions disagree, or no changelog section exists for the tag.

### Changed
- **Release process**: GitHub Releases are now published for every tag, with notes taken verbatim from this file's matching section, so the two can't drift. Backfilled the missing `v0.2.0` release (`v0.3.0` / `v0.4.0` already had one).
- **`.beads/issues.jsonl` and `.beads/interactions.jsonl` are no longer tracked in git.** Per the [beads sync model](https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md) these are passive exports, not the sync channel — cross-machine sync goes through Dolt (`refs/dolt/data` on origin, `bd dolt push` / `bd dolt pull`), which is configured for this repo, so collaborators are unaffected. Tracking them would have published issue text and contributor email addresses when the repo goes public. Beads config (`config.yaml`, `metadata.json`, `recipes.toml`, `hooks/`) stays tracked, as `config.yaml` is required for remote wiring.
- `LICENSE` and `pyproject.toml` now name the copyright holder / author as **Isaac Tesfaye** rather than the `isaac-tes` GitHub handle.

## [0.4.1] — 2026-07-27

### Fixed
- **All `pastweek` papers showed "(No abstract available.)"** (`arxiv_scraper_cli-an7`): `paper["id"]` was taken from the listing link's *text*, which arXiv renders as `arXiv:2512.00001`. The abstract back-fill then requested `https://arxiv.org/abs/arXiv:2512.00001`, which arXiv rejects with **HTTP 406**, and the failure was swallowed unless `--verbose`. `/new` pages inline their abstracts so `today` was unaffected; `/pastweek` pages omit them entirely and depended wholly on that broken fetch. Ids are now parsed from the `/abs/` href and normalized via the new `normalize_arxiv_id` helper.
  - **Scores shift for `pastweek`**: abstract keyword hits and the `+1` long-abstract bonus never fired before, so rankings will differ (correctly) from previous runs.
  - **`paper["id"]` format changed** from `arXiv:2512.00001` to the bare `2512.00001`. It is an internal join key, but it also appears in JSON report output.

### Changed
- `fetch_abstract` is hardened: it re-normalizes its own argument (a prefixed id still resolves), retries transient failures twice with backoff, accepts both `blockquote.abstract` and `div.abstract`, and strips the leading `Abstract:` label with an anchored regex instead of a global `.replace()` that could corrupt body text.
- Back-fill failures are no longer silent: when at least half of them come back empty, a warning is printed to stderr regardless of `--verbose`.
- The inline-abstract fallback no longer risks selecting the title — it skips text already captured as title/authors/subjects.

## [0.4.0] — 2026-07-17

### Fixed
- **Substring matching false-positives** ([#4](https://github.com/isaac-tes/arxiv-digest/issues/4), `arxiv_scraper_cli-28n`): keyword/author/low-priority matching bled across word interiors — `mpo` scored *temporal*/*composition*, author `ma` scored *Mao*, `bloch` scored *Blochwitz*. Matching is now **whole-word by default** via `(?<!\w)term(?!\w)` lookarounds (new helpers `term_pattern` / `term_matches`). Hyphens, spaces, and punctuation count as boundaries, so `MPO-based` and `the mpo ansatz` still match.

### Added
- **`word_boundary_matching` config flag** (default `true`): set `false` for the legacy substring behavior. Exposed as a **Whole-word matching** checkbox in the GUI Scoring tab and persisted in profiles / `arxiv_config.json`.
- **Starter presets** (`arxiv_scraper_cli-7f2`): three read-only built-in topic bundles — `open-quantum-systems`, `quantum-many-body`, `floquet-topological` (keywords + authors + feeds/feed_weights, seeded from the TU Berlin AG Eckardt profile). GUI **Profiles → Starter presets** with **Load** (replace) / **Add** (union) buttons; CLI `--preset NAME`, `--add-preset NAME` (repeatable), `--list-presets`. Non-destructive: presets change only the in-memory config and never write to saved profiles or `arxiv_config.json`. New API: `PRESETS`, `preset_names`, `preset_config`, `merge_preset`.

### Changed
- The GUI keyword/author highlighters now share the scorer's matcher, so highlights and scores stay in sync (a term that no longer scores no longer highlights).
- Subjects/`feed_weights` intentionally keep substring matching, so a parent feed `cond-mat` still scores `cond-mat.quant-gas` papers.

## [0.3.0] — 2026-06-22

### Added
- **Submission-type filtering**: arXiv `today`/`/new` *Replacement submissions* are hidden by default (cross-lists kept). `--include-replacements` CLI flag, `cfg.include_replacements`, and a GUI sidebar toggle. Helpers `section_category` / `filter_papers`.
- **Back-in-time day picker** (GUI): view a single past day's ranking from the days `pastweek` returns. Clearly flags arXiv's hard limit (no arbitrary-day URL → ~last 5 days). Helpers `section_day_label` / `available_day_labels`.
- **Per-feed subject bonuses**: subject scoring is now driven by `Config.feed_weights` (a bonus per configured feed found in a paper's subjects). The Scoring tab auto-generates a field per feed.
- **GUI highlighting**: hover-highlight matched authors, plus core keywords (teal) and low-priority terms (red) in the title and full abstract, each with a weight tooltip. Three persisted display toggles (`highlight_authors` / `highlight_terms_title` / `highlight_terms_abstract`).
- `docs/troubleshooting.md`; docs for filters, day-picker limit, per-feed bonuses, highlighting, and profiles-vs-project-config.

### Fixed
- **GUI state bug**: keyed Streamlit widgets ignored `value=`/`default=` on rerun, so Load profile / Reset / Apply weights / Import left widgets showing stale state. Fixed by clearing the affected widget state before `st.rerun()`.
- **Author scoring**: named authors now match the author list only — "Bloch theorem" in an abstract no longer awards author points.
- Abstract-bonus tooltip now uses a CSS tooltip (Streamlit strips the `title` attribute).

### Changed
- Removed the hardcoded `quant_gas_subject` / `mes_hall_subject` / `quant_ph_subject` fields from `ScoringWeights`; subject scoring unified into `feed_weights`. **Pre-0.3.0 configs auto-migrate on load** (`_hydrate_feed_weights`).
- Test suite grown to 102 (scoring, filters, config round-trip incl. full-field coverage, GUI AppTest).

## [0.2.0] — 2026-05-06

### Added
- **Streamlit GUI** (`arxiv_gui.py`) with seven tabs (Papers, Keywords, Authors, Low priority, Feeds, Scoring, Profiles). Live re-ranking, per-paper score breakdown via `explain_score`, named profile management under `~/.arxiv_scraper/profiles/`.
- `ScoringWeights` dataclass on `Config` so every scoring rule is configurable from the GUI or `arxiv_config.json`.
- `explain_score(paper, cfg)` returns a per-rule contribution breakdown; `score_paper` now delegates to it so the two functions cannot drift.
- 74-test pytest suite covering scoring, config round-trip, fetch (mocked), formatting, CLI flag handling, and a Streamlit AppTest GUI smoke test. Runs in ~1s with no network calls.
- Console-script entry points: `arxiv-digest` (CLI) and `arxiv-gui` (Streamlit launcher) — installable via `uv tool install '.[gui]'`.
- mkdocs-material documentation site with Quickstart, GUI guide, CLI guide, Scoring guide.
- GitHub Actions: CI (pytest on Python 3.12) and a docs build/deploy workflow (deploy gated on repo visibility).
- `LICENSE` (MIT), `CHANGELOG.md`, `CONTRIBUTING.md`, `.python-version`, `.streamlit/config.toml` (telemetry opt-out).
- Optional `launch_gui.sh` one-shot wrapper.

### Fixed
- `Config.from_json` now defaults `top_n` to 20 (was 15) and `timeframe` to `"pastweek"` (was `"today"`), matching `Config()` direct-construction defaults. Eliminated silent CLI-vs-JSON drift.
- Removed duplicate `"pumping"` entry from `_default_core_keywords()`.

### Changed
- `pyproject.toml` switched to PEP 735 `[dependency-groups]` (`test`, `gui`, `docs`, `dev`) plus PEP 621 `[project.optional-dependencies] gui` for tool installs.

## [0.1.0] — pre-GUI baseline

### Added
- Single-file CLI (`arxiv_digest.py`) that scrapes arXiv listing pages and ranks papers by user-defined keywords / authors / subjects.
- `arxiv_config.json` persistence with `--save-config` and CLI mutators (`--add-core`, `--add-author`, etc.).
- Markdown and JSON report output (`--output-markdown`, `--output-json`).
