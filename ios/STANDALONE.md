# Standalone mode ("On this device")

_Written 2026-10-07 · branch `feat/swift_ios` · decision: [ADR 0009](../docs/adr/0009-standalone-mode.md)_

How **Standalone mode** ("On this device") works: the app fetches from arXiv
itself and scores papers on the device, with no digest service. Built
2026-10-07/08 in steps S1–S7; the step-by-step plan is in git history. The general app
handoff is [`HANDOFF.md`](HANDOFF.md); domain terms are in `CONTEXT.md`.

---

## 1. Why, in one paragraph

Server mode needs an always-on machine the phone can reach. The user's available
Linux machine forbids long-running services, cron, and Tailscale, so for personal
use the app needs to work alone. The arXiv export API is plain HTTPS, so the phone
can fetch; what's missing is the Python engine. We port the pieces the app needs
to Swift and pin them to the Python engine with generated parity fixtures. Server
mode stays as the synced option. Full reasoning: ADR 0009.

## 2. Design

```
AppModel.Mode: .server | .demo | .standalone
                                   │
APIClient ── URLSession(protocolClasses: [LocalURLProtocol]) ──┐
                                                                ▼
                        DigestRouter  (shared: routing, digest view, score wording,
                         ▲      ▲      presets/config endpoints, removals)
                         │      │
             DemoSource ─┘      └─ LiveSource
     (fixture papers +            (ArxivFetcher → papers, Scorer → scores,
      precomputed scores)          LocalStore → config/removed/cache on disk)
```

- Extract the routing and view logic out of `DemoBackend` into a shared type
  (name it `DigestRouter` or similar). Demo becomes "router + fixture source";
  Standalone is "router + live source". **Demo's behaviour and its tests must not
  change** (`DemoBackendTests.swift` is the guard).
- `handle` becomes `async` (live fetching is network I/O). In the URL protocol,
  start a `Task` in `startLoading()` and call `client?.urlProtocol(...)` when it
  finishes; handle `stopLoading()` by cancelling the task.
- Standalone answers with the **same JSON** the server returns. Compare against
  `server/app/schemas.py` and `server/app/routers/*.py` when in doubt; the
  server's tests (`server/tests/test_api.py`) show the expected shapes.

## 3. Progress log

| Step | Status | Commit / notes |
|---|---|---|
| S1 scorer + parity | done | `Scorer.swift`, `RawPaper`; 30 parity cases from `make_parity_fixture.py` |
| S2 router + mode | done | `Local/DigestRouter.swift` (actor, shared by Demo + Standalone), `LiveSource` (stub fetcher until S3, demo config until S4), `LocalURLProtocol`, Settings → On this device, `-standalone` |
| S3 past-week fetch | done | `Fetch/ArxivFetcher.swift` (HTTPS endpoint for ATS; no HTML fallback, failed feeds become a notice); Atom parse parity in `FetchParityFixture` |
| S4 storage/defaults/presets | done | `Local/EngineConfig.swift` (hydrate = `Config.from_json`, `merge_preset`, `LocalStore`), generated `EngineDefaults.swift`; config/removed/fetch cache in Application Support/Standalone |
| S5 score by id | done | `ArxivFetcher.fetchPaper` (id_list, with retry), cached paper first like the server; `LiveSource.notFetchedReason` ports `_not_fetched_reason` (feed list sorted, Python keeps config order); 502 on transport/HTTP errors |
| S6 day labels | done | `ArxivFetcher.listingDayLabels` + minimal `HTMLNode` tree (same h3 → sibling dt walk as BeautifulSoup); one plain GET per fetched feed, API label kept on failure; parity on an invented listing page |
| S7 today feed | done (listing) | Kept (a) `fetchTodayListing` (closest to the GUI: on 2026-10-08 it matched the engine's `/new` scrape exactly, 329 papers, while (b) export API returned 66 papers none of which were in the listing). (b), `TodaySource`, the Settings switch and `-today-source` removed. |
| S8 iCloud sync | deferred | |

Session log (2026-10-07, Linux, Swift 6.2 tarball in `~/.local/swift`): baseline
was root 290 / server 48 / Swift 66; now Swift 97. One commit per step plus
`fix(ios): name arXiv errors the same on macOS and Linux` (the macOS CI job caught
a bridged `URLError` reporting as `NSError`).

## 4. Known differences from the Python engine

Deliberate, small, and marked `ponytail:` in the code:

- **Export API over HTTPS** (`https://export.arxiv.org`); the engine uses plain
  HTTP, which App Transport Security blocks.
- **No HTML `/pastweek` fallback.** When the API fails for a feed, that feed and
  the rest are skipped and a notice says which ("Pull to refresh to try again").
- **Dict order.** Swift dictionaries are unordered, so two places sort feed names
  where Python keeps config order: `default_feeds` rebuilt from `feeds` when a
  config has no `default_feeds` key at all, and the subscribed-feed list in the
  "not among your subscribed feeds (…)" sentence.
- **HTML entities** in listing pages stay undecoded (ids and day labels have none).
- **Score-a-paper by id retries** 429/5xx like the past-week fetch; the server's
  `fetch_arxiv_atom` makes one request.
- **Today (a)** back-fills missing abstracts once over the deduplicated set
  (the engine back-fills per feed: same result, fewer requests). Only common
  named HTML entities are decoded (`HTMLNode.unescape`).
- **Demo** keeps storing configs as sent (no hydration); the router's preset
  merge now uses the engine's `merge_preset` port for both modes (same result
  on the demo's presets; `DemoBackendTests` unchanged and green).

Python quirk worth knowing (ported as is, not "fixed"): `Config.from_json`
coerces with `bool()`, so a JSON string `"false"` hydrates to `true`; and the
listing parser keeps a version suffix (`/abs/…v2`) in the id, so such a link
never relabels its paper.

Working on Core from Linux: `cd ios && swift test` builds and tests there (CI runs it too); app-target code needs macOS/Xcode. Regenerate fixtures with `uv run python ios/scripts/make_parity_fixture.py` and keep invented names only.
