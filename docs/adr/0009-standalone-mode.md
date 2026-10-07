# ADR 0009 — Standalone mode: fetch and score on the device

- **Status**: Accepted
- **Date**: 2026-10-07
- **Amends**: ADR 0002 (thin client) and ADR 0008 (view computed on the server),
  for the standalone connection mode only.

## Context

The app is a thin client of the digest service (ADR 0002), and the service
computes the Papers view (ADR 0008). That needs an always-on machine the phone
can reach. For a personal user this is often not available: a shared or managed
Linux machine may forbid long-running services, cron, and VPN daemons such as
Tailscale, and a laptop sleeps. Without a reachable service the app only has
**Demo mode**, whose rankings are fixed.

The arXiv export API is plain HTTPS, so the phone can fetch papers itself. What
it lacks is the engine, which is Python (`arxiv_digest.py`).

## Decision

Add a third connection mode, **Standalone**, next to **Server** and **Demo**:

- The app fetches the past week from the arXiv export API, scores papers with a
  Swift port of the engine's scorer, and computes the Papers view on the device.
- It plugs in the way Demo mode does: a `URLProtocol` routes the app's requests to
  an in-process backend that answers the digest service's endpoints with the same
  JSON. `AppModel`, the views, and `APIClient` don't change beyond the mode switch.
- Demo and Standalone share one implementation of the view, Score-a-paper,
  preset, and config routing (today in `DemoBackend`). They differ only in where
  papers and scores come from.
- Config, removed papers, and the fetch cache are stored on the device.
- **Server mode stays the synced option** and the source of truth for anyone who
  runs the service. Standalone is single-device unless config sync is added later.

## Drift control

A second engine copy can drift. Every ported behaviour is pinned by **parity
fixtures generated from the Python engine** (as `make_demo_fixture.py` already
does for Demo mode): the same papers and configs go through `explain_score` /
the parsers in Python, and Swift tests must reproduce the output exactly. A
scoring change in Python then fails the Swift tests until the port follows.

## Considered options

- **Server only (status quo).** No duplicate engine, but no usable app for users
  without an always-on, reachable machine.
- **Run Python on the phone** (embedded interpreter). Large binary, App Store
  friction, and the GUI/HTML parsing stack doesn't port cleanly. Rejected.
- **Pre-computed digest published as a static file** (generated elsewhere, read
  by the app). Still needs a scheduler somewhere, and config edits on the phone
  can't re-rank. Rejected.
- **Separate standalone client code path** (a `DigestService` protocol with two
  implementations instead of a `URLProtocol`). Cleaner types, but every call
  site changes and Standalone could drift from the server's JSON contract. The
  `URLProtocol` seam keeps Standalone on the exact contract the server serves.

## Consequences

- Scoring, the export-API fetch, and later the listing parsers exist twice
  (Python and Swift), held together by parity tests.
- arXiv rate limits now apply per device: the Swift fetch must pace requests
  (3 s), back off on 429/5xx, and cache fetches for an hour, like the engine.
- The "today" feed (HTML `/new`) is the hardest part to port and comes last.
- Standalone has no Zotero Web API key; **Share to Zotero** covers saving.
