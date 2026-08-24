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

## Git workflow

### Commit and push a change

```bash
git add <files>
git commit -m "type: short summary"     # conventional commits: fix:, feat:, docs:, chore:, release:
git push                                # push the current branch to origin
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
`fix:` for bug fixes, `feat:` for new features, `docs:` for documentation,
`chore:` for maintenance, `release:` for version bumps. Keep the summary under
~72 chars and add a body for anything non-obvious.

### Merge a feature branch into `main`

Work happens on a branch off `main` (e.g. `feat/...`, `fix/...`), then merges
back via a pull request. Two ways to land it:

```bash
# Option A: merge commit (preserves history)
git switch main
git pull --rebase
git merge --no-ff <branch>
git push

# Option B: squash (one clean commit on main)
git switch main
git pull --rebase
git merge --squash <branch>
git commit -m "type: summary"
git push
```

Or open a PR with `gh pr create --base main` and merge it in the GitHub UI.
After merging, delete the branch: `git branch -d <branch>` and
`git push origin --delete <branch>`.

## Releases

Releases are **automated** by two GitHub Actions workflows, so you never push a
tag by hand:

- `.github/workflows/tag-on-version-bump.yml`: when a push to `main` changes
  the `version` in `pyproject.toml`, it tags that commit `v<version>`.
- `.github/workflows/release.yml`: fires on the `v*` tag, runs the test suite,
  checks the tag matches `pyproject.toml`, and publishes a GitHub Release with
  notes taken verbatim from the matching `CHANGELOG.md` section.

So cutting a release is just: bump the version, merge to `main`, and let CI do
the rest.

### Full release (e.g. 0.6.0)

1. On a branch off `main`, bump `version` in `pyproject.toml` (e.g. `0.6.0`).
2. Add a `## [0.6.0] - YYYY-MM-DD` section at the top of `CHANGELOG.md` (above
   `[Unreleased]`) with the user-visible changes.
3. `uv lock` to refresh the lockfile.
4. Commit as `release: v0.6.0` and push the branch.
5. Merge to `main` (see above). CI tags `v0.6.0` and publishes the release
   automatically. No manual `git tag` or `git push --tags` needed.

### Patch / hotfix (e.g. 0.6.1)

Same flow, but bump only the patch digit and add a `## [0.6.1]` section:

1. Branch off `main`, fix the bug, add a regression test.
2. Bump `version` to `0.6.1` in `pyproject.toml`; add the `## [0.6.1]` changelog
   section.
3. `uv lock`, commit (`fix: ...`), push, merge to `main`. CI tags `v0.6.1` and
   releases it.

### If you ever need to tag manually

The workflows cover the normal path, but the manual equivalent is:

```bash
git tag v0.6.0
git push origin v0.6.0
```

To re-publish notes for an existing tag (e.g. after a typo), run the Release
workflow manually from the Actions tab with the tag as input, or:

```bash
gh workflow run release.yml -f tag=v0.6.0
```
