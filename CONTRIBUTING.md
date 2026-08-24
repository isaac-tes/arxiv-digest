# Contributing

Thanks for your interest in arxiv-digest. This is a small personal tool, but contributions, bug reports, and ideas are welcome.

## Development setup

```bash
git clone https://github.com/isaac-tes/arxiv-digest.git
cd arxiv-digest
uv sync --group dev          # CLI + GUI + tests + docs deps
uv run pytest -q             # 74 tests, ~1s, no network
```

Prerequisite: [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

Python floor: 3.12 (see `.python-version`).

## Workflow

1. Branch off `main`: `git switch -c <kind>/<short-summary>` (e.g. `fix/score-explain-drift`).
2. Make your change. Keep `arxiv_digest.py` single-file and pasteable into ChatGPT; that's a load-bearing property.
3. Add or update tests under `tests/`. The suite must stay green and network-free.
4. Update `CHANGELOG.md` under `[Unreleased]`.
5. Open a PR against `main`.

## Code style

- Type hints on public functions; small `dataclass`es over dicts where possible.
- Default to no comments; only add them when the *why* is non-obvious.
- Keep the CLI surface stable. Flags don't change without a deprecation note in `CHANGELOG.md`.

## Testing

```bash
uv run pytest -q                             # full suite
uv run pytest tests/test_scoring.py -v       # one file
uv run pytest -k weight                      # by name
```

`requests.get` is monkey-patched in `tests/test_fetch.py` so no network calls hit arXiv during the suite.

## GUI changes

- The Streamlit app lives in `arxiv_gui.py` and imports `arxiv_digest as ad`. Don't duplicate scoring or fetch logic in the GUI; extend `arxiv_digest.py` and call it.
- After GUI changes, run `tests/test_gui.py` (uses `streamlit.testing.v1.AppTest`, headless).

## Docs

```bash
uv run python scripts/generate_readme.py     # syncs README.md → docs/index.md
uv run mkdocs serve                          # http://localhost:8000
uv run mkdocs build --strict                 # CI-equivalent build
```

The docs site auto-deploys to GitHub Pages once the repo is public; on a private repo the workflow runs the build but skips the deploy step.

## Reporting issues

Open an issue with:

- arxiv-digest version (`uv run python arxiv_digest.py --list-config | head -5` or check `pyproject.toml`)
- Python version (`python --version`)
- OS
- Minimal reproduction (the exact command and any non-default config)

## Releases

1. Bump `version` in `pyproject.toml` and add a `[X.Y.Z]` section in `CHANGELOG.md` with today's date.
2. `uv lock` to refresh.
3. Commit, tag `git tag vX.Y.Z`, push: `git push && git push --tags`.
4. GitHub auto-generates release notes from `.github/release.yml`.
