# iOS app — session handoff

_Last updated: 2026-08-28 · branch `feat/swift_ios`_

Living handoff for the native iOS app. Task state lives in **beads** (`bd ready`,
`bd show <id>`); this file is the human-readable narrative + how-to-run.

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
3. In-app Settings → Server → your Mac's LAN IP, e.g. `http://192.168.2.133:8000`
   (**not** `127.0.0.1` — on the phone that's the phone itself).

If it won't connect: macOS firewall on port 8000, or the two devices on different
Wi-Fi bands/VLANs.

### Using the app away from the Mac
Deploy the digest service once to a small host (Fly.io / Render / Railway — it's a
stock uvicorn app) and point Settings → Server at that public URL. Reimplementing
the engine in Swift, or relying on the (unbuilt) offline cache, are not viable
substitutes. See "Deferred / strategic" below.

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

## Remaining work (by beads id)

### Zotero follow-ups
- `arxiv_scraper_cli-jtg` (P2 bug) — server `deeplink` mode returns a
  non-functional `zotero://select` link; implement a real save handoff or drop it.
- `arxiv_scraper_cli-cx0` (P3 bug) — server `_creators()` swaps first/last name
  (`rsplit(" ",1)` assigns them backwards).
- `arxiv_scraper_cli-d5q` (P3 feature) — per-user Zotero key entry in Settings; the
  server currently reads a single operator key from env, not per-user.
- `arxiv_scraper_cli-ynp` (P3) — Zotero save: attach the downloaded PDF (match
  Connector import behaviour).

### iOS features next up
- `arxiv_scraper_cli-92s` (P1) — dedicated **Config tab**: profile picker +
  keywords/authors/low-priority/feeds(cross-lists) editor. Groundwork exists:
  `DigestConfig.defaultFeeds` and `availableFeedNames` were added this session.
- `arxiv_scraper_cli-b9k` (P1 bug) — **Save config** should reload the digest +
  confirm after `PUT /config`. Partially done: `AppModel.saveConfig` now re-fetches
  with `refresh: true` and sets `statusMessage`; still needs the confirmation
  surfaced in `SettingsView`.
- `arxiv_scraper_cli-v2z` (P2) — timeframe + top_n controls on the Papers list page.

### Deferred / strategic
- `arxiv_scraper_cli-08f` (P2) — **Deploy the digest service** so the app works
  without the Mac. Runbook + systemd unit landed: `docs/deploy.md`,
  `deploy/arxiv-digest.service`. Personal path is local mode on an always-on Linux
  box (LAN or Tailscale); public path needs remote mode + arXiv fetch caching.
- **Offline cache** (SwiftData) per CONTEXT.md — a convenience layer over a prior
  server response, still requires an initial online fetch.

## Conventions
- Task tracking is **beads only** (no TodoWrite / markdown TODO lists). This file
  is narrative, not a task list — keep the authoritative status in beads.
- Core logic that can be unit-tested belongs in `ArxivDigestCore` with a test in
  `ArxivDigestCoreTests` (TDD). App-target views have no test bundle, so push
  decision logic down into Core (e.g. `ZoteroPolicy`, `PaperSearch`,
  `HighlightEngine`).
- Git on this branch is conservative: no commits/pushes without explicit request.
