# iOS app — session handoff

_Last updated: 2026-10-04 · branch `feat/swift_ios` (merged with `main` v0.6.3)_

Living handoff for the native iOS app. Locally, task state lives in **beads**
(`bd ready`, `bd show <id>`); this file is the human-readable narrative + how-to-run.

## Continuing in a cloud session (read first)

- **Beads is local-only** (Dolt data is not on the public remote), so the
  `arxiv_scraper_cli-*` ids below won't resolve in the cloud. Treat the
  "Remaining work" section as the task list; the local beads DB stays authoritative.
- **No Xcode/simulator on Linux.** What works in the cloud:
  - Server: `cd server && uv sync --extra dev && uv run pytest`
  - CLI/GUI engine: `uv sync --group dev && uv run pytest` (root)
  - Swift Core edits are possible, but `swift test` on Linux will fail to build
    until Core and the tests add
    `#if canImport(FoundationNetworking) import FoundationNetworking #endif`
    (URLSession/URLProtocol live there on Linux). Untested on Linux so far.
- App-target UI (SwiftUI views) can be edited but only verified on a Mac
  (`xcodegen generate` + `xcodebuild`, see below). Flag UI changes for a Mac check.

## Architecture in one line

The iOS app is a **thin client**. All arXiv fetching, scoring, and highlighting
lives in the FastAPI **digest service** (`server/`), which CONTEXT.md defines as
"the single source of truth for CLI, GUI, iOS, and Android." The Swift app holds
models, an HTTP client, and display logic only — it renders whatever the server
returns. There is **no on-device engine** and **no bundled offline copy yet**, so
the app needs a reachable server to do anything.

## Running the app

### Simulator (server on the same Mac)
```bash
cd server && uv run uvicorn app.main:app            # 127.0.0.1:8000
cd ios && xcodegen generate                         # only after adding Swift files
xcodebuild -project ios/ArxivDigest.xcodeproj -scheme ArxivDigestApp \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
# then simctl install + launch com.arxivdigest.app
```
The simulator reaches the host server at `127.0.0.1:8000`.

### Physical iPhone (same Wi-Fi as the Mac)
1. Bind the server to the LAN: `cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. Build/run on the device from Xcode (trust dev signing on the phone once:
   Settings → General → VPN & Device Management).
3. In-app Settings → Server → your Mac's LAN IP, e.g. `http://192.168.1.20:8000`
   (**not** `127.0.0.1` — on the phone that's the phone itself).

If it won't connect: macOS firewall on port 8000, or the two devices on different
Wi-Fi bands/VLANs.

### Using the app away from the Mac
Deploy the digest service once to a small host (Fly.io / Render / Railway — it's a
stock uvicorn app) and point Settings → Server at that public URL. Reimplementing
the engine in Swift, or relying on the (unbuilt) offline cache, are not viable
substitutes. See "Deployment / strategic" below and `docs/deploy.md`.

## Dev environment (verified 2026-08)
swift 6.2, xcodebuild, xcodegen all present. Simulator "iPhone 17 Pro" works.
Core logic tests: `cd ios && swift test` (fast, no network, 26 tests green).
Regenerate the Xcode project after adding **app-target** Swift files
(`cd ios && xcodegen generate`); new **Core** files are picked up by SwiftPM
automatically.

## Current state

The app mirrors the web GUI: a ranked **Papers** list (search + pull-to-refresh),
a **Score** tab, and **Settings** (config editors + per-aspect highlight
colors/font toggles + server URL). Swipe/Lists were removed in favour of the
list-based parity with the web app.

### Save to Zotero — `arxiv_scraper_cli-4bg` (in progress; iOS side complete)
- **Core (tested):** `ZoteroPolicy.availability(from: status)` → `.web` /
  `.unavailable`; `APIClient.saveToZotero(arxivId:mode:)` POSTs `/zotero/save`
  with a snake_case body and decodes `ZoteroSaveResult`.
- **App:** `AppModel.saveToZotero` refreshes `GET /zotero/status`, then saves via
  **web** mode only. `PaperDetailView` shows a **Save to Zotero** button when the
  server has a key, else an honest "not configured on the server" row; the result
  is surfaced in an alert.
- **Deliberately does NOT use the server's `deeplink` mode.** Per Zotero's URI
  scheme docs, `zotero://select/items/<id>` only *selects a pre-existing item* by
  its Zotero item key (iOS wants `zotero://select/library/items/<key>`) and cannot
  create an item from an arXiv id — so it would save nothing.
- **Works only when the server runs with** `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID`
  set. Without them the app correctly shows "not configured."

## Remaining work

Ordered by priority. Ids in brackets are local beads ids (for syncing status back
on the Mac); entries without an id were found when merging `main` v0.6.3 and have
no beads issue yet. Each item says where the change lives and how to verify it.

### 1. Server parity with `main`'s engine (Linux-friendly, do these first)

- **Pastweek digest uses the unreliable HTML listing** (no id). After the merge,
  the CLI/GUI fetch pastweek via `arxiv_digest.fetch_pastweek(feed_names, start,
  end, notices=...)` (export API, true 7-day window), but
  `server/app/routers/digest.py::_fetch_scored_papers` still builds `/pastweek`
  URLs and calls `fetch_feeds`. So the app can show a different digest from the
  CLI. Fix: mirror the CLI branch in `arxiv_digest.main()` (search for
  `fetch_pastweek(`). Use `fetch_pastweek` for `timeframe == "pastweek"`, filter
  out `http` feed names, and surface `notices`. Keep `fetch_feeds` for `today`.
  Add a server test with `fetch_pastweek` monkey-patched.
- **Score-a-paper has no rank or absence reason** (no id; related GUI fix: PR #10).
  `server/app/routers/score.py` returns only `paper` + `breakdown`; the
  `absence_reason` field is only set on "Paper not found". The GUI now ranks
  through one shared digest so Score-a-paper reports the rank shown or why a
  fetched paper is hidden (below top_n, filtered as a replacement, outside
  subscribed feeds/timeframe). Port that: compare against the cached digest in
  `digest.py::_cached_scored_papers`, return `rank` + `absence_reason`, and show
  both in `ScoreView` / `PaperDetailView`. The iOS `ScoreResult` already decodes
  `absence_reason`.
- **Zotero `_creators()` swaps first/last name** [`cx0`, P3 bug].
  `server/app/routers/zotero.py`: `last, first = part.rsplit(" ", 1)` on
  "First Last" yields last="First". It should be `first, last = ...`. Add a unit test.
- **Zotero `deeplink` mode is non-functional** [`jtg`, P2 bug]. It returns
  `zotero://select/items/{arxiv_id}`, which only *selects* an existing item by
  Zotero key and can't create one. Drop the mode (iOS doesn't use it) or replace it
  with a real handoff. Update `ZoteroSaveRequest` and the iOS `ZoteroMode` enum to match.

### 2. iOS features (edit anywhere; build/verify on a Mac)

- **Save config: show the confirmation** [`b9k`, P1 bug, partly done].
  `AppModel.saveConfig` already PUTs, sets `statusMessage = "Saved ✓"`, and
  re-fetches with `refresh: true`. Nothing displays `statusMessage` yet. Show it
  in `SettingsView` (and the Config tab below), e.g. a transient overlay that
  clears after ~2 s. Close `b9k` when visible.
- **Dedicated Config tab** [`92s`, P1]. Move keywords/authors/low-priority out of
  Settings into a new Config tab (mirrors the web GUI's tabs), add a **feeds
  (cross-lists) editor** bound to `DigestConfig.defaultFeeds`, suggesting from
  `availableFeedNames` (both exist and are tested), and a profile/preset picker
  (`/config/presets`, `AppModel.mergePreset`). Saving goes through
  `AppModel.saveConfig` (which reloads the digest). New app-target file needs
  `xcodegen generate`.
- **Timeframe + top_n on the Papers page** [`v2z`, P2]. A toolbar `Menu` in
  `PapersListView` bound to `model.config.timeframe` / `topN` that calls
  `model.loadDigest(refresh: true)` on change (`loadDigest` already reads both
  from config).
- **Remove a paper from the digest** (no id; GUI feature from PR #9). The web GUI
  has a per-card ✕ that hides a paper and persists the removal per profile
  (`removed_papers_path` in `arxiv_gui.py`). The server has no endpoint for it.
  Add one (store removed ids per user, exclude them in `/digest`), then a
  swipe-to-remove action on `PaperRowView`. Ask before building; it's a scope call.
- **Summary highlight toggle** (no id). `main` added `highlight_terms_summary`
  (default `False`) to `Config`. Add a `DigestConfig` accessor + Settings toggle,
  and gate keyword highlighting of the list-row summary in `PaperRowView` on it.
- **Color-font defaults drifted** (no id). `main` now defaults
  `color_font_keyword` / `color_font_author` to `True`. `DigestConfig.fontColor`
  falls back to `False` when the key is missing (and `testFontToggleRoundTrip`
  asserts that). The server normally sends the key, so this only bites with a
  sparse config. Align the fallback with `main` and update the test.

### 3. Zotero, per-user (needs design, lower priority)

- **Per-user Zotero key entry** [`d5q`, P3]. The server reads one operator key from
  `ZOTERO_API_KEY` / `ZOTERO_LIBRARY_ID`. Per-user would need an encrypted credential
  column, a PUT endpoint, and a Settings field. Until then web-save works only when
  the server env vars are set; the app shows "not configured" otherwise.
- **Finish `4bg`** [P2, iOS side complete]. Close it once web-save has been
  exercised against a real key (needs the env vars above).

### 4. Deployment / strategic

- **Deploy the digest service** [`08f`, P2]. Runbook + unit exist
  (`docs/deploy.md`, `deploy/arxiv-digest.service`). Remaining: actually run it on
  the always-on Linux box and point the app at it. Public `remote` mode would
  additionally need arXiv fetch caching (note `main` added a persistent fetch
  cache in the engine; check whether the server should rely on it instead of its
  own 1 h in-memory cache).
- **Linux `swift test`**: add `FoundationNetworking` imports (see top section).
- **Offline cache** (SwiftData) per CONTEXT.md: later; still needs an initial
  online fetch.

### Beads safety on other machines

The tracked `.beads/config.yaml` has `sync.remote` pointing at the **public**
GitHub repo, and the beads data (`refs/dolt/data`) is intentionally kept off it
(issue text contains names scrubbed from the public history). On any machine
other than the Mac: **don't run `bd dolt push` / `bd sync`**, and don't `bd init`
against this repo. Track progress in this file and in commit messages; update
the beads issues on the Mac afterwards.

## Conventions
- Task tracking is **beads only** (no TodoWrite / markdown TODO lists). This file
  is narrative, not a task list — keep the authoritative status in beads.
- Core logic that can be unit-tested belongs in `ArxivDigestCore` with a test in
  `ArxivDigestCoreTests` (TDD). App-target views have no test bundle, so push
  decision logic down into Core (e.g. `ZoteroPolicy`, `PaperSearch`,
  `HighlightEngine`).
- Conventional Commits (`feat:`, `fix:`, …) per `CONTRIBUTING.md`.
- Starter presets / test fixtures must stay free of personal or group-specific
  author names (`tests/test_presets.py::test_every_preset_has_authors`).
