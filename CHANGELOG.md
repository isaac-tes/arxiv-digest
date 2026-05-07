# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
