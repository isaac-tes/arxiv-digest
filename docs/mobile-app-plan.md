# Mobile App Plan — arXiv Digest for iOS / iPadOS / Android

- **Status**: Accepted (design confirmed 2026-08-24)
- **Branch**: `feat/swift_ios`
- **Scope**: Turn the arXiv digest web app (Streamlit GUI + Python CLI) into a native
  mobile app family, reusing the same Python scoring/fetch backend so iOS, iPadOS,
  and Android all share one engine.

This document is the single source of truth for the mobile architecture. It records
the decisions reached during design (see `docs/adr/` for the individual ADRs) and the
phased roadmap for building it.

---

## 1. Goal & non-goals

### Goal
A native **iOS/iPadOS app** (SwiftUI) that delivers the arXiv digest experience on a
phone: fetch, score, rank, triage, and save papers — with the same scoring engine as
the existing CLI/GUI. The backend is a shared **FastAPI REST service** so a native
**Android app** can be added later against the same API.

### Non-goals (for now)
- **Not** competing with alphaXiv on community/summarization/Q&A. We build the
  *filtering/triage layer upstream* of reading.
- **Not** shipping the freemium business model yet — the architecture is
  multi-tenant-ready, but billing/tiers are deferred (see §9).
- **Not** building the Android app in this phase — the API is designed so it can be
  added later without backend changes.

---

## 2. Confirmed design decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Backend sharing strategy | **REST API (FastAPI) + native SwiftUI iOS + native Android later** |
| D2 | Backend hosting | **Both** — local (dev) and remote-deployable (prod) |
| D3 | Audience | **Personal now, multi-tenant-ready** (public freemium later) |
| D4 | iOS v1 scope | **Full parity** — digest + config + score-a-paper + Zotero |
| D5 | Multi-tenant | **From the start** — auth + per-user config isolation |
| D6 | Scoring engine | **Pluggable pipeline, keyword signal first**; embeddings/anchors/veto later |
| D7 | Zotero on mobile | **Web API + share sheet to the Zotero iOS app** (both; the deep-link idea was dropped, see ADR 0005 amendment) |
| D8 | iOS UI | **Hybrid** — swipe-triage primary + settings tab |
| D9 | Project layout | **Monorepo** — `server/` + `ios/` alongside existing Python |
| D10 | iOS target/tooling | **iOS 17+, Swift Package Manager** core + thin Xcode app target |

Minor decisions (recommended, not separately grilled): **JWT auth** (OAuth2 password
flow), **SQLite local / Postgres remote** (same ORM/schema), **hand-rolled
`URLSession` + `Codable` API client** with OpenAPI as the contract.

---

## 3. Monorepo layout

```
arxiv_scraper_cli.feat-swift_ios/
├── arxiv_digest.py          # existing CLI — shared scoring/fetch core (unchanged)
├── arxiv_gui.py             # existing Streamlit GUI (unchanged)
├── zotero_bridge.py         # existing Zotero LOCAL bridge (desktop only, unchanged)
├── server/                  # NEW: FastAPI backend
│   ├── pyproject.toml       # server deps (fastapi, uvicorn, sqlalchemy, pydantic, jwt)
│   ├── app/
│   │   ├── main.py          # FastAPI app factory + router mounting
│   │   ├── settings.py      # env config: DB URL, JWT secret, mode (local/remote)
│   │   ├── db.py            # SQLAlchemy engine/session (SQLite | Postgres)
│   │   ├── models.py        # ORM: User, Config, SavedList, ListPaper, Feedback
│   │   ├── schemas.py       # Pydantic request/response models
│   │   ├── auth.py          # JWT issue/verify, OAuth2 password flow
│   │   ├── scoring.py       # pluggable scoring pipeline (wraps arxiv_digest)
│   │   ├── signals/
│   │   │   ├── base.py      # Signal protocol (score + explain + highlight)
│   │   │   ├── keyword.py   # keyword signal (v1)
│   │   │   ├── embedding.py # (later) anchor-paper similarity
│   │   │   ├── author.py    # (later) author/lab affinity
│   │   │   └── veto.py      # (later) veto-capable penalty channel
│   │   └── routers/
│   │       ├── auth.py      # /auth/*
│   │       ├── digest.py    # /digest/*
│   │       ├── score.py     # /score
│   │       ├── config.py    # /config/*
│   │       ├── lists.py     # /lists/*
│   │       ├── feedback.py  # /feedback
│   │       └── zotero.py    # /zotero/*
│   └── tests/
├── ios/                     # NEW: SwiftUI app
│   ├── Package.swift        # SPM package (logic layer, VS Code-friendly)
│   ├── Sources/
│   │   ├── ArxivDigestCore/ # pure logic: models, API client, scoring display
│   │   │   ├── Models/      # Paper, Digest, DigestConfig, SavedList, Breakdown, User
│   │   │   ├── Networking/  # APIClient (URLSession+async/await), AuthStore (Keychain)
│   │   │   └── Scoring/     # ScoreDisplay, HighlightEngine (mirrors Python term_pattern)
│   │   └── ArxivDigestApp/  # thin SwiftUI app target (opened in Xcode)
│   │       ├── ArxivDigestApp.swift
│   │       ├── AppModel.swift            # @Observable root state
│   │       ├── Views/
│   │       │   ├── Triage/               # swipe card stack (primary)
│   │       │   ├── Settings/             # config editors (keywords/authors/feeds/scoring)
│   │       │   ├── Score/                # score-a-paper + breakdown
│   │       │   └── Lists/                # saved lists
│   │       ├── ViewModels/
│   │       └── Persistence/              # SwiftData offline cache
│   └── Tests/
├── docs/
│   ├── mobile-app-plan.md   # THIS PLAN
│   └── adr/                 # 0002-0007 (see §10)
└── CONTEXT.md               # updated domain glossary
```

**Key reuse point**: the FastAPI server imports `arxiv_digest.py` as a module (the
Streamlit GUI already does `import arxiv_digest as ad`), so **no refactor of the
existing single-file core is required** — respecting the minimal-diff preference. The
server adds a thin scoring-pipeline layer *around* the existing `explain_score` /
`score_paper` functions.

---

## 4. Backend API surface

All endpoints are JSON. Auth-protected endpoints require `Authorization: Bearer <JWT>`
(no-op in single-user local mode until Phase 2).

### Auth
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/register` | Create account (multi-user, Phase 2) |
| POST | `/auth/token` | OAuth2 password flow → JWT |
| GET | `/auth/me` | Current user |

### Digest
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/digest` | Ranked papers for `timeframe`, `feeds`, `top_n` (with per-paper breakdowns) |
| POST | `/digest/refresh` | Force refetch (bypass 1h cache) |

### Score
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/score` | Body `{arxiv_id}` → score + breakdown + absence reason |

### Config
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/config` | Current user's `Config` |
| PUT | `/config` | Replace `Config` |
| PATCH | `/config` | Partial update |
| GET | `/config/presets` | List starter presets |
| POST | `/config/presets/{name}/merge` | Merge a preset into current config |

### Lists (multi-list support — the strategic differentiator)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/lists` | User's saved lists |
| POST | `/lists` | Create list |
| GET | `/lists/{id}` | List with its papers |
| POST | `/lists/{id}/papers` | Add paper |
| DELETE | `/lists/{id}/papers/{paper_id}` | Remove paper |
| PATCH | `/lists/{id}` | Rename / reorder |

### Feedback (swipe → reweight, the "cheap feedback loop")
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/feedback` | Body `{paper_id, action: star\|dismiss\|penalize, signal}` → reweight |

### Zotero
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/zotero/status` | Availability (`web_api_available`) |
| POST | `/zotero/save` | Body `{arxiv_id, collection_key, mode: web}` → save via the Web API |

---

## 5. Pluggable scoring pipeline (D6)

The backend exposes a scoring pipeline with swappable **signals**. Each signal
implements a common protocol:

```python
class Signal(Protocol):
    name: str
    def score(self, paper: dict, cfg: Config) -> int: ...
    def explain(self, paper: dict, cfg: Config) -> list[dict]: ...  # per-hit breakdown
    def highlight(self, paper: dict, cfg: Config) -> dict: ...      # term ranges for UI
```

- **v1**: `KeywordSignal` — wraps the existing `explain_score` / `score_paper`
  keyword/author/subject logic. Ships first, no behavior change.
- **Later**: `EmbeddingSignal` (cosine similarity to anchor papers), `AuthorSignal`
  (author/lab affinity + co-authorship), `VetoSignal` (blocked author/sub-keyword can
  suppress a paper even with a positive score).

The pipeline sums signal scores and merges explanations, so the mobile UI can always
show a per-signal breakdown ("why this score?") — the transparency requirement from
the strategic docs. Adding a signal later is additive and does **not** break the API
or the app.

---

## 6. iOS app structure (SwiftUI, iOS 17+)

### ArxivDigestCore (SPM package — builds from VS Code)
- **Models** (`Codable`): `Paper`, `Digest`, `DigestConfig`, `SavedList`,
  `ScoreBreakdown`, `User`.
- **Networking**: `APIClient` (async/await `URLSession`), `Endpoint` enum,
  `AuthStore` (JWT in Keychain).
- **Scoring**: `ScoreDisplay` (renders breakdown), `HighlightEngine` (mirrors the
  Python `term_pattern` so highlights match scores — same invariant as the GUI).

### ArxivDigestApp (thin SwiftUI target — opened in Xcode)
- **Triage** (primary): a card stack. Swipe **right** = star/save to list, swipe
  **left** = dismiss/penalize, tap = full paper + score breakdown. Swiping posts to
  `/feedback` and shows the score change (the "cheap feedback loop").
- **Settings**: config editors for keywords / authors / feeds / scoring, plus
  profiles — ported from the Streamlit tabs.
- **Score**: score-a-paper (paste arXiv ID → score + breakdown + absence reason).
- **Lists**: saved lists, cross-device synced via the backend.
- **Persistence**: SwiftData offline cache of the digest + saved papers + PDFs.

### Xcode vs VS Code workflow
- **VS Code + SPM** for `ArxivDigestCore` (models, API client, scoring display) —
  `swift build` / `swift test` from the terminal. The SPM package builds only the
  core library (the app is an Xcode project, not an SPM executable).
- **Xcode** for the `ArxivDigestApp` target — required for simulator/device runs,
  asset catalogs, Info.plist, and code signing.
- The Xcode project is **generated with XcodeGen** from `ios/project.yml`
  (regenerate with `xcodegen generate`). The SPM executable target cannot produce a
  real iOS app bundle (no bundle ID), which is why the app is an Xcode app target
  that links the `ArxivDigestCore` package. Open `ios/ArxivDigest.xcodeproj` in
  Xcode, select the `ArxivDigestApp` scheme + a simulator, and Run.

---

## 7. Zotero on mobile (D7)

- **Desktop GUI** keeps the existing **local** bridge (`zotero_bridge.py`,
  `localhost:23119`) — unchanged.
- **iOS app** supports **both**:
  1. **Zotero Web API** — user provides a zotero.org API key; saves go to their
     online library (syncs to desktop). This is the only path that works on
     **Android** (no Zotero app there).
  2. **Deep-link / share-sheet** to the Zotero iOS app — no API key, hands the paper
     off to Zotero's own app.
- The `/zotero/save` endpoint accepts a `mode` so the app can choose per availability.

---

## 8. Offline & sync

- **Offline**: SwiftData caches the last digest, saved papers, and downloaded PDFs so
  the app is usable without a connection.
- **Sync**: config and lists are stored server-side (per-user) and pulled on launch;
  the app is the cache, the server is the source of truth. This gives cross-device
  sync for free once multi-tenant auth lands.

---

## 9. Phased roadmap

### Phase 0 — Backend foundation
- Monorepo layout, FastAPI server scaffolding.
- Reuse `arxiv_digest.py`; implement `/digest`, `/score`, `/config` (single-user, no
  auth yet).
- Local SQLite mode; tests.

### Phase 1 — iOS app v1 (personal, full parity)
- SPM package + SwiftUI app.
- Swipe-triage UI + settings tab; digest fetch + breakdown + highlights.
- Config editing, score-a-paper, Zotero (Web API + share sheet).
- SwiftData offline cache. Run on simulator (Xcode milestone).

### Phase 2 — Multi-tenant
- JWT auth, `users` table, per-user config/lists.
- Postgres mode for remote deployment; cross-device sync.

### Phase 3 — Scoring moat
- Pluggable signals: embedding (anchor papers), author affinity, veto channel.
- Feedback loop (swipe reweights visibly); calibration/benchmark vs the user's old
  keyword script (recall/precision surfaced in-app).

### Phase 4 — Android
- Native Android app consuming the same API; Zotero Web API path.

### Phase 5 — Public / freemium *(deferred — discuss later)*
- Billing, tiers, institutional licensing.

---

## 10. ADRs

The hard-to-reverse decisions are recorded as ADRs in `docs/adr/`:

- **0002** — FastAPI REST backend + native apps (D1)
- **0003** — Multi-tenant-ready from the start (D3/D5)
- **0004** — Pluggable scoring pipeline (D6)
- **0005** — Zotero Web API + deep-link on mobile (D7; amended: share sheet instead of deep-link)
- **0006** — Monorepo layout (D9)
- **0007** — iOS 17+ / Swift Package Manager (D10)

---

## 11. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| arXiv API rate limits / ToS on scraping | Cache aggressively (1h), respect backoff, use the Atom API where possible; monitor usage |
| iOS App Store review (Zotero key handling) | Store API key in Keychain; document the flow; no private API use |
| Zotero Web API requires user key setup | Share-sheet fallback (Share to Zotero); clear onboarding |
| Multi-tenant auth complexity | JWT + OAuth2 password flow; keep single-user mode as a no-op auth path |
| Embedding model cost/latency (Phase 3) | Small open models; compute server-side, cache per paper |
| Low willingness-to-pay (freemium) | Institutional/lab licensing over individual subs (Phase 5) |
