# Contributing

Contribution guidelines live in [CONTRIBUTING.md](https://github.com/isaac-tes/arxiv-digest/blob/main/CONTRIBUTING.md) at the repo root.

In short:

- `uv sync --group dev` to set up.
- `uv run pytest -q` must stay green.
- `arxiv_digest.py` stays a single file (it's pasteable into ChatGPT, a load-bearing property).
- Use conventional-commit types (`fix:`, `feat:`, ...) and `BREAKING CHANGE:`
  trailers, since GitHub release notes are generated from commits.

## Commit conventions

Commit subjects start with a type prefix that decides where the change lands in
the release notes:

- `feat:` → **Features**
- `fix:` → **Bug Fixes**
- `docs:` / `chore:` / `ci:` / `refactor:` / `test:` / `perf:` / `style:` /
  `build:` / `release:` → **Other** (or omitted)

Trailers at the end of the commit body carry extra metadata:

- `BREAKING CHANGE:` marks a breaking change (surfaced prominently, signals a
  major bump)
- `Co-authored-by:` credits a co-author
- `Closes #N` / `Fixes #N` links and auto-closes an issue
- `Signed-off-by:` certifies the DCO

See [CONTRIBUTING.md](https://github.com/isaac-tes/arxiv-digest/blob/main/CONTRIBUTING.md#commit-conventions-that-shape-the-release-notes) for the full guide with examples.

## Releases

Releases are automated: bump `version` in `pyproject.toml`, merge to `main`,
and CI tags `v<version>` and publishes the release with auto-generated notes.
See [CONTRIBUTING.md](https://github.com/isaac-tes/arxiv-digest/blob/main/CONTRIBUTING.md#releases) for the full flow.

To cut a release manually (no automation):

```bash
git tag v0.6.0 && git push origin v0.6.0
gh release create v0.6.0 --title v0.6.0 --generate-notes --latest
```
