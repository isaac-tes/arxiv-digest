# Handoff — `feat/swift_ios` (iOS app, digest server, GUI sync)

_Last updated: 2026-10-08 · merged to `main` in PR #13, released in v0.7.0_

Start here for the next round. It covers **everything this branch changes
compared with `main`**, how to run and verify it, and what's left. Decisions live
in ADRs (`docs/adr/`, not on the public site), terms in `CONTEXT.md`, user docs in
`docs/ios-app.md` and `docs/deploy.md`. Beads data is local to the Mac; ids in
brackets refer to it (never push beads/Dolt data to GitHub).

---

## 1. What this branch adds, by area

### iOS app (`ios/`, new)

A native SwiftUI app (iOS 17+) mirroring the web GUI: **Papers**, **Score**,
**Config**, **Settings** tabs. Three connection modes (Settings → Connection):

| Mode | Where fetching/scoring happens | Config + removed papers |
|---|---|---|
| **On this device** (default for new installs) | On the phone: Swift port of the engine, arXiv export API for the past week, `/new` listing for today | Application Support on the phone |
| **Server** | The digest server (`server/`) | On the server, shared by every device |
| **Demo** | Built-in sample digest | In memory |

- **Architecture**: every screen talks to `APIClient` (the server's JSON). Demo and
  On-this-device answer the same endpoints in-process through a `URLProtocol` +
  shared `DigestRouter` (ADR 0009). `ArxivDigestCore` (SwiftPM, builds on Linux)
  holds all logic; the app target is thin.
- **Engine parity**: scorer, config hydration, presets, Atom/listing parsers and
  `summarize` are ported and pinned by fixtures generated from the Python engine
  (`ios/scripts/make_parity_fixture.py`, `make_demo_fixture.py`). Live check on
  2026-10-08: top-20 ids and scores identical to the Python engine on the same fetch.
  Known deliberate differences: `ios/STANDALONE.md` §4.
- **Features**: day chips, search, remove/undo/restore, Score a paper (rank or
  absence reason), config editors + presets with an unsaved-changes bar, highlight
  colors/toggles with light-mode contrast, **math**: Unicode in lists and titles,
  bundled **KaTeX** (offline, pre-warmed web view) for math abstracts on the paper
  page, **Add author** from a paper, **Save to Zotero** (server key) or **Share to
  Zotero**, **Export / Import config** (one JSON file, same format as the GUI's
  profile export; opens `.json` from AirDrop/Files), access token for Server mode
  (Keychain).
- **Install before the App Store**: `docs/ios-app.md` (Xcode, free Apple ID,
  Developer Mode, renew every 7 days).

### Digest server (`server/`, new)

FastAPI around `arxiv_digest.py`: `/digest` (GUI-equivalent view: day, removals,
top-N, abstracts, breakdowns, notices; 1 h raw-fetch cache, pastweek via
`fetch_pastweek`), `/removed`, `/score` (rank or absence reason, 502 on arXiv
errors), `/config` (+ `/defaults`, presets load/merge with `save=false`),
`/zotero` (Web API only), `/auth` (remote mode).

**Security (audited 2026-10-08, `server/app/security.py`, ADR 0003 amendment)**:
local mode answers only its own machine unless `DIGEST_ACCESS_TOKEN` is set, then
every request except `/health` needs `Authorization: Bearer <token>` (constant-time
compare); `Host` header checked (DNS rebinding); CORS off by default; feed URLs
must be on arxiv.org, ≤ 50 feeds (no SSRF); remote mode refuses the default JWT
secret. **Breaking** for anyone running the server for other devices: set the token.

Removed as unused (ponytail review): `/lists`, `/feedback`, their tables, and the
unused highlight path.

### GUI + engine (shared files, affect `main` users)

- **Sync with server** (`sync_client.py`, sidebar): optional two-way sync of config
  and removed papers with the digest server. First connect asks *Use server's* /
  *Upload mine*; sessions start from the server; Save/Write project config/remove/
  restore upload; offline keeps working from `arxiv_config.json`. Settings in
  `~/.arxiv_scraper/sync.json` (0600) or `ARXIV_DIGEST_SERVER` / `ARXIV_DIGEST_TOKEN`.
- **Add author** popover on each card and in Score a paper.
- **Update notice** for `arxiv-gui` (terminal + sidebar), using the existing
  once-a-day release check (`update_check.newer_release`).
- **Fixes**: inline LaTeX in card titles and full abstracts now renders (cards use
  block-styled `<span>`, never `<div>`; math kept verbatim); card summaries no longer
  cut citations like "Roy et al. (Nat. Commun. …)" (`summarize`); explicitly empty
  keyword/author lists stay empty on config load.
- **Docs**: `docs/deploy.md` (Sync across devices: server, token, LAN/Tailscale/SSH,
  systemd/tmux, file copy both ways), `docs/ios-app.md`, GUI guide section,
  README pointer. `CHANGELOG.md` `[Unreleased]` lists all of it.
- **Tests**: `tests/conftest.py` keeps the update check and sync settings away from
  `~/.arxiv_scraper` in every test. GUI tests must patch `Path.home` and
  `ad.DEFAULT_CONFIG_PATH` (AppTest re-executes the module).

### CI (`.github/workflows/ios.yml`, new)

On pushes to `main` and `feat/swift_ios`: server tests (Linux), `swift test` (Linux + macOS),
app build + screenshots (artifact **ios-screenshots**).

---

## 2. Run and verify

```bash
uv sync --group dev && uv run pytest                 # root: 327 tests
cd server && uv sync --extra dev && uv run pytest    # server: 55
cd ios && swift test                                 # Core: 124 (also on Linux)
uv run mkdocs build --strict                         # docs
uv run python ios/scripts/make_parity_fixture.py && git diff --exit-code ios/   # parity
```

App on a simulator: `cd ios && xcodegen generate && open ArxivDigest.xcodeproj`,
scheme **ArxivDigestApp**, ⌘R. Launch options for quick checks/screenshots:
`-demo`, `-standalone`, `-tab papers|score|config|settings`, `-open-paper <rank>`,
`-score <id-or-url>`, `-config-page keywords|authors|low-priority|feeds|scoring|presets`,
`-remove <rank>`, `-day <n>`, `-dirty`.

Server for the simulator: `cd server && uv run uvicorn app.main:app --port 8799`
(port 8765 is taken by a VS Code extension on this Mac); Settings → Connection →
Server → `http://127.0.0.1:8799`. With `DIGEST_ACCESS_TOKEN=…` enter the token too.

On a phone: `docs/ios-app.md`. Sharing settings: `docs/deploy.md`.

Verified by hand on 2026-10-08 (simulator + live arXiv + a real server): the
standalone device checklist (connect, past-week fetch, re-rank on save, removals,
Score tab, presets, today listing), KaTeX light/dark, light-mode contrast, author menu, token flow
(401/403/200, no CORS, SSRF 422), GUI sync round-trip, config file import from a
GUI export, GUI LaTeX in Safari. The user then checked the app on a physical
iPhone the same day and reported no problems.

---

## 3. Merging

- Merged to `main` in PR #13 and released in v0.7.0. `docs/deploy.md` clones `main`,
  and `.github/workflows/ios.yml` also triggers on `main`.
- Existing `server/digest.db` files keep the dropped `saved_lists` / `list_papers` /
  `feedback` tables; harmless, no migration.

## 4. Remaining work (next round)

- **S8 iCloud config sync** [`e85.8`]: needs a paid Apple Developer account; ask first.
- **Per-user Zotero key** [`d5q`]: encrypted credential column + endpoint + Settings
  field. Until then Save to Zotero needs `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID` on
  the server; Share to Zotero works without. Close [`4bg`] after a real Web API save.
- **Zotero PDF attachment** [`ynp`] for Web API saves.
- **Deploy the server** [`08f`]: runbook in `docs/deploy.md`; the user's managed
  Linux box forbids long-running services, so a Mac LaunchAgent or a small VPS
  are the candidates. Remote (multi-user) mode needs an app login screen first.
- **iOS app login** for remote mode; **named profiles** on the server/app if
  switching configs on the phone matters; **offline cache** (SwiftData) per CONTEXT.md.
- **UI tests**: none for the app target; logic is in Core (tested) and checked via
  CI screenshots.
- **Signals pipeline** (`server/app/signals/`, ADR 0004) has one implementation;
  the ponytail review suggested inlining it, kept on purpose pending ADR 0004's
  future signals.

## 5. Conventions

- Logic goes in `ArxivDigestCore` with a test (TDD); views stay thin. New
  app-target files: `xcodegen generate` (resets the signing team in Xcode).
- When the engine's scoring, config hydration, presets, parsers or `summarize`
  change: regenerate `make_parity_fixture.py` + `make_demo_fixture.py` and update
  the Swift port; Python is the reference.
- Invented names only in fixtures (public repo); presets stay generic.
- Conventional Commits per `CONTRIBUTING.md`; CHANGELOG `[Unreleased]` for every change.
- Never let a test touch `~/.arxiv_scraper` or a real server (see conftest).
