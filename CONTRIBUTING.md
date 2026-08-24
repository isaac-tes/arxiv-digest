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
  checks the tag matches `pyproject.toml`, and publishes the GitHub Release
  with GitHub's **auto-generated release notes** (`--generate-notes`), derived
  from the commits since the previous tag.

So cutting a release is just: bump the version, merge to `main`, and let CI do
the rest. The release notes are generated automatically from the commit history;
you don't write them by hand.

### Full release (e.g. 0.6.0)

1. On a branch off `main`, bump `version` in `pyproject.toml` (e.g. `0.6.0`).
2. `uv lock` to refresh the lockfile.
3. Commit as `release: v0.6.0` and push the branch.
4. Merge to `main` (see above). CI tags `v0.6.0` and publishes the release with
   auto-generated notes. No manual `git tag`, `git push --tags`, or release-note
   editing needed.

### Patch / hotfix (e.g. 0.6.1)

Same flow, but bump only the patch digit:

1. Branch off `main`, fix the bug, add a regression test.
2. Bump `version` to `0.6.1` in `pyproject.toml`.
3. `uv lock`, commit (`fix: ...`), push, merge to `main`. CI tags `v0.6.1` and
   releases it.

### Commit conventions that shape the release notes

GitHub's auto-generated release notes group commits by conventional-commit
type and flag breaking changes. Write commit messages accordingly so the
generated release notes read well.

#### Type prefixes (leading flags)

Every commit subject starts with a type prefix followed by a colon and a short
summary. The type decides which section the commit lands in:

| Prefix | Meaning | Release-notes section |
|--------|---------|----------------------|
| `feat:` | A new user-facing feature | **Features** |
| `fix:` | A bug fix | **Bug Fixes** |
| `docs:` | Documentation only | **Other** (or omitted) |
| `chore:` | Maintenance, tooling, deps | **Other** (or omitted) |
| `ci:` | CI / workflow changes | **Other** (or omitted) |
| `refactor:` | Code change with no behaviour change | **Other** (or omitted) |
| `test:` | Adding or updating tests | **Other** (or omitted) |
| `perf:` | A performance improvement | **Other** (or omitted) |
| `style:` | Formatting, whitespace, no logic change | **Other** (or omitted) |
| `build:` | Build system / packaging changes | **Other** (or omitted) |
| `release:` | Version bump for a release | **Other** (or omitted) |

Examples:

```text
feat: add Save to Zotero button to each paper card
fix: strip arXiv: prefix so pastweek abstracts resolve
docs: document the release pipeline
chore: bump streamlit to 1.30
```

Keep the summary under ~72 chars, imperative mood, no trailing period.

#### Trailers (commit body)

Trailers are structured `Key: value` lines at the end of the commit body. They
carry metadata that GitHub and other tools read.

| Trailer | Purpose |
|---------|---------|
| `BREAKING CHANGE:` | Marks the change as breaking. Surfaces it prominently in the release notes and signals a major version bump. |
| `Co-authored-by:` | Credits a co-author. GitHub shows both authors on the commit. |
| `Reviewed-by:` | Records a reviewer. |
| `Signed-off-by:` | Certifies the Developer Certificate of Origin (DCO). |
| `Closes #N` / `Fixes #N` | Links the commit to an issue; GitHub auto-closes it on merge. |
| `Refs #N` | References an issue without closing it. |

Example with a breaking change and an issue link:

```text
feat: switch subject scoring to feed_weights

BREAKING CHANGE: the old weights.*_subject keys are replaced by
feed_weights and migrate automatically on load.

Closes #42
```

The most important trailer for the release notes is `BREAKING CHANGE:`. The
others (`Co-authored-by:`, `Closes #N`, ...) are for attribution and issue
linking, and are read by GitHub regardless of the release-notes generator.

### Manual release (no automation)

If you ever need to cut a release by hand (e.g. the workflows are down, or you
want a one-off tag), here is the manual equivalent of what CI does:

```bash
# 1. Make sure the version is bumped and committed on main.
#    pyproject.toml version must match the tag you're about to create.

# 2. Tag the release commit and push the tag.
git tag v0.6.0
git push origin v0.6.0

# 3. Create the GitHub Release with auto-generated notes.
gh release create v0.6.0 --title v0.6.0 --generate-notes --latest

# 4. (Optional) verify the release.
gh release view v0.6.0
```

To re-publish notes for an existing tag (e.g. after a typo), regenerate them
via the API and edit the release:

```bash
gh api -X POST "repos/isaac-tes/arxiv-digest/releases/generate-notes" \
  -f tag_name="v0.6.0" --jq '.body' > release-notes.md
gh release edit v0.6.0 --notes-file release-notes.md
```

The manual path runs the same test suite and version check that CI runs, so
verify locally first with `uv run pytest -q` and confirm the tag matches
`pyproject.toml`.

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
