# iOS app — session handoff

_Last updated: 2026-10-07 · branch `feat/swift_ios`_

Living handoff for the native iOS app: what exists, how to run it, what's left.
Decisions live in ADRs (`docs/adr/`), terms in `CONTEXT.md`. Beads data is
local to the Mac; ids in brackets refer to it.

## Architecture in one line

The app is a **thin client** of the FastAPI **digest service** (`server/`), which
wraps the same `arxiv_digest.py` engine as the CLI and GUI (ADR 0002). The server
computes the Papers view: filters, day, removed papers, top-N (ADR 0008). The app
renders it and edits config. **Demo mode** serves an engine-generated sample
digest in-process, so the app also runs with no server.

## Try it on a Mac (Xcode installed)

```bash
git fetch origin && git switch feat/swift_ios     # or: wt switch feat/swift_ios
brew install xcodegen                              # once
cd ios && xcodegen generate && open ArxivDigest.xcodeproj
```

In Xcode: scheme **ArxivDigestApp**, pick an iPhone simulator, **Run** (⌘R).

- **No server needed:** Settings → Connection → **Demo** → Reload demo. Or edit
  the scheme (Product → Scheme → Edit Scheme → Run → Arguments) and add `-demo`.
- **Real digest on the simulator:** in a second terminal
  `cd server && uv sync && uv run uvicorn app.main:app` (listens on
  127.0.0.1:8000), then Settings → Digest server → `http://127.0.0.1:8000` →
  Connect. The first past-week load fetches from arXiv (~30 s); later loads use
  the server's 1 h cache. To start from your GUI profile:
  `DIGEST_DEFAULT_CONFIG_PATH=~/.arxiv_scraper/profiles/<name>.json uv run uvicorn app.main:app`.
- **On your iPhone:** run the server with `--host 0.0.0.0`, select the phone as
  the run destination (set your team under Signing & Capabilities once, then
  trust the developer profile on the phone: Settings → General → VPN & Device
  Management), and enter the Mac's LAN address, e.g. `http://192.168.1.20:8000`.

Tests: `cd ios && swift test` (Core, 66 tests, also on Linux), `cd server && uv run pytest`
(43), `uv run pytest` at the root (290).

Screenshots are produced by CI (`.github/workflows/ios.yml`) on every push to
this branch: Actions → latest run → artifact **ios-screenshots**. Locally:
`ios/scripts/screenshots.sh <booted-sim-udid> /tmp/shots` after installing the app.

### Launch options (screenshots / quick checks)

`-demo`, `-standalone`, `-tab papers|score|config|settings`, `-open-paper <rank>`,
`-score <id-or-url>`, `-config-page keywords|authors|low-priority|feeds|scoring|presets`,
`-remove <rank>`, `-day <n>` (n-th available day), `-dirty` (fake unsaved edit).

## What the app does (parity with the web GUI)

| GUI | App |
|---|---|
| Papers tab: cards, highlights, Why this score? / Full abstract | **Papers** list → detail (abstract, breakdown, arXiv/PDF, Zotero, Remove) |
| Day picker, search, caption, Markdown/JSON downloads | Day chips, search, same caption, export from the ⋯ menu |
| ✕ remove + Removed papers (Restore / Restore all) | Swipe left or long-press → Remove (with Undo); Removed papers section |
| Sidebar timeframe / Top N | Papers ⋯ menu (saved immediately via `PATCH /config`) |
| Score a paper (rank or absence reason) | **Score** tab, same wording, same view as Papers |
| Keywords / Authors / Low priority tabs | **Config** → list editors (add, tap to rename, swipe delete, reorder, reset) |
| Feeds tab + sidebar feed multiselect + replacements | Config → Feeds (subscribe toggles, URLs, include replacements) |
| Scoring tab | Config → Scoring (whole-word, weights, per-feed bonuses, reset) |
| Profiles → starter presets Load / Add | Config → Starter presets (unsaved until Save, like the GUI) |
| Sidebar Display: toggles, colors, font tint | **Settings** → Display / Highlight colors (live preview) |
| Save to Zotero | Save via server key, or **Share to Zotero** (share sheet) without one |

Config edits are a working copy: the **unsaved-changes bar** (Config and Settings
tabs, plus a dot on the Config tab) saves, confirms with "Saved ✓", and re-ranks.

Not ported (by design or deferred): named **profiles** (the server has one config
per user; presets cover starting points), the GUI's "Clear fetch cache" button
(pull to refresh does a fresh fetch), JSON profile import/export.

## Server changes on this branch

- `/digest`: pastweek via `fetch_pastweek` like the CLI; `day`; removals; abstracts
  and breakdowns per paper; `removed`, `available_days`, `hidden_by_filters`,
  `fetched_papers`, `notices`, `fetched_at`. Cache holds raw fetches keyed on
  resolved feeds; ranking runs per request.
- `/removed` (GET, POST, POST `/restore`), per user.
- `/score`: `rank` or `absence_reason` against the same view; 502 on arXiv errors.
- `/config`: effective config (all fields), 422 on invalid, `/defaults`,
  `/presets/info`, `/presets/{name}/load`, `save=false` + working-config body.
- Zotero: `deeplink` mode removed (ADR 0005 amendment); creator names fixed.
- Engine: an explicitly empty keyword/author list is no longer replaced by defaults.

## Remaining work

- **Standalone mode** (next feature): app fetches + scores on the device, no
  server. Full plan, steps S1–S8, and Linux setup: [`STANDALONE.md`](STANDALONE.md);
  decision: ADR 0009. Beads epic [`e85`].
- **Stopgap until then** (Mac only): run the server on the Mac at login with a
  user LaunchAgent (`~/Library/LaunchAgents`, no sudo) plus Tailscale on Mac +
  phone. Not written yet.
- **Per-user Zotero key** [`d5q`]: needs an encrypted credential column, an
  endpoint, and a Settings field. Until then Save to Zotero needs
  `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID` on the server; Share to Zotero works without.
- **Zotero PDF attachment** [`ynp`] for Web API saves.
- **Close `4bg`** after a real Web API save; close `92s`, `b9k`, `v2z`, `jtg`,
  `cx0` (done on this branch) on the Mac.
- **Deploy the digest service** [`08f`]: `docs/deploy.md`. Public/remote mode
  should reuse the engine's persistent fetch cache before going multi-user.
- **Offline cache** (SwiftData) per CONTEXT.md.
- **Named profiles on the server** if switching configs on the phone matters.
- **UI tests**: the app target has none; behaviour is pushed into Core (tested)
  and checked visually via the CI screenshots.

## Conventions

- Core logic that can be unit-tested goes in `ArxivDigestCore` with a test;
  views stay thin. New app-target files are picked up by `xcodegen generate`.
- `ios/scripts/make_demo_fixture.py` regenerates the demo fixture from the
  engine; run it after changing scoring, and keep invented names only.
- Conventional Commits per `CONTRIBUTING.md`. Don't push beads/Dolt data to the
  public remote.
