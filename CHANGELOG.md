# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-07-17

### Fixed
- **Substring matching false-positives** ([#4](https://github.com/isaac-tes/arxiv-digest/issues/4), `arxiv_scraper_cli-28n`): keyword/author/low-priority matching bled across word interiors — `mpo` scored *temporal*/*composition*, author `ma` scored *Mao*, `bloch` scored *Blochwitz*. Matching is now **whole-word by default** via `(?<!\w)term(?!\w)` lookarounds (new helpers `term_pattern` / `term_matches`). Hyphens, spaces, and punctuation count as boundaries, so `MPO-based` and `the mpo ansatz` still match.

### Added
- **`word_boundary_matching` config flag** (default `true`): set `false` for the legacy substring behavior. Exposed as a **Whole-word matching** checkbox in the GUI Scoring tab and persisted in profiles / `arxiv_config.json`.

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
