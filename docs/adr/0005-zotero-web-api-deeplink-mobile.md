# ADR 0005 — Zotero Web API + deep-link on mobile

- **Status**: Accepted, amended 2026-10-04 (see *Amendment* below)
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

## Amendment (2026-10-04): the no-key path is the share sheet

The server-generated deep link this ADR described (`zotero://select/items/<id>`)
cannot create an item: Zotero's `select` URI only selects an item that already
exists, addressed by its Zotero item key, not by an arXiv id. It saved nothing.

- The `deeplink` mode is removed from `/zotero/save`; the endpoint is Web-API only.
- The no-key path on iOS is **Share to Zotero**: the app passes the arXiv page
  URL to the OS share sheet, and the Zotero iOS app's share extension saves it
  the way the Connector would. No server involvement.
- Android, when it exists, will use its own share intent in the same way.
