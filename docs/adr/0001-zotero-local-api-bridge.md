# ADR 0001 — Use Zotero's local HTTP API for the save bridge

- **Status**: Accepted
- **Date**: 2026-08-20

## Context

The GUI needs a one-click "Save to Zotero" action that writes a paper into the
user's Zotero library, behaving like the official Zotero Connector when saving an
arXiv page. Two integration paths were considered:

1. **Zotero local HTTP API** (`http://localhost:23119/api/`) — the same mechanism
   the Zotero Connector browser extension uses. Serves the user's local library;
   reads need no auth; writes (Zotero 10+) require a local API key granted at
   runtime via a Zotero "Allow this application?" dialog.
2. **Zotero Web API** via `pyzotero` — requires the user to create a zotero.org
   API key and provide their library ID, and writes to the *online* library (which
   then syncs down to the desktop app).

## Decision

Use the **Zotero local HTTP API** (`http://localhost:23119/api/`). Save actions
POST a `preprint` item to `/users/0/items` with `Zotero-API-Version: 3`, replicating
the Zotero Connector's arXiv translator output (fields, category tags, PDF/Snapshot
attachments) plus a single `arxiv-digest` source tag.

## Consequences

- **No API-key setup** for the user — the first write triggers Zotero's native
  authorization dialog, matching the connector's feel.
- **Writes go to the local library** immediately; sync to zotero.org happens via
  Zotero's own sync, not our code.
- **Requires the Zotero desktop app to be running.** We surface this with a sidebar
  status indicator and a graceful per-click error with the enable hint
  (Settings → Advanced → "Allow other applications on this computer to communicate
  with Zotero").
- **Requires Zotero 10+ for writes.** Zotero versions before 10 expose a
  read-only local API — write requests return `400 Endpoint does not support
  method`. The bridge detects this via the missing `Zotero-Server-ID` header
  (only present in Zotero 10+) and explains that Zotero 10+ is required. On
  Zotero 10+, the bridge runs the local write-authorization flow
  (`POST /api/local/authorize`) to obtain a key, then writes with it.
- **No new dependency** — `requests` (already used) is sufficient; `pyzotero` is
  not needed.
- **Trade-off accepted**: the local API is desktop-only and cannot run headless.
  If a headless/remote save path is ever needed, the web API can be added as a
  separate fallback without removing the local bridge.
