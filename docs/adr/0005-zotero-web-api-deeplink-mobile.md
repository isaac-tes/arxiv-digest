# ADR 0005 — Zotero Web API + deep-link on mobile

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

The desktop GUI saves to Zotero via the **local** HTTP API (`localhost:23119`), which
only works on the user's desktop. A phone has no local Zotero, and Android has no
Zotero app at all. We still want "Save to Zotero" on mobile (full parity).

## Decision

On mobile, support **both** save paths:

1. **Zotero Web API** — the user provides a zotero.org API key; saves go to their
   online library (which syncs to desktop). This is the only path that works on
   Android.
2. **Deep-link / share-sheet** to the Zotero iOS app — no API key; hands the paper
   off to Zotero's own app.

The `/zotero/save` endpoint accepts a `mode` so the app chooses per availability. The
desktop GUI keeps the existing local bridge unchanged.

## Consequences

- Full parity on iOS; a working path on Android.
- Requires the user to set up a zotero.org API key for the Web API path (mitigated by
  the deep-link fallback).
- Two code paths to maintain on the client, but both are thin.
