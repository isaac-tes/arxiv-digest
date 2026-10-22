# ADR 0001: Use Zotero's local Connector API for the save bridge

- **Status**: Accepted
- **Date**: 2026-08-20

## Context

The GUI needs a one-click “Save to Zotero” action that behaves like the official
Zotero Connector when saving an arXiv page. The local Zotero HTTP server exposes
both a read-only library API (`/api/`) and the Connector API (`/connector/`).
Writing item metadata directly through `/api/` is insufficient: Zotero ignores
attachment URLs in item-creation requests, and Zotero 10+ local writes require
per-session authorization.

## Decision

Use Zotero's local **Connector API** (`http://localhost:23119/connector/`) for
new saves, and the local library API for collection lookup and duplicate
detection. The save flow follows the Connector session protocol:

1. Fetch arXiv Atom metadata and build the same `preprint` fields and category
tags as Zotero's `arXiv.org.js` translator, plus the `arxiv-digest` source tag.
2. Download the arXiv abstract-page HTML and PDF.
3. Create the item through `/connector/saveItems`, move the session to the
selected personal-library target through `/connector/updateSession`, attach the
page snapshot through `/connector/saveSingleFile`, and stream the PDF bytes to
`/connector/saveAttachment`.

If duplicate detection finds a pre-existing item without a local PDF, repair that
record with a child attachment and Zotero's local file-upload protocol. This
Zotero 10+ fallback uses the local write-authorization flow and caches keys only
when Zotero marks them persistent.

## Consequences

- PDF and snapshot attachments are imported into Zotero's local storage instead
  of being left as remote URL stubs or silently discarded.
- Normal new saves use Zotero's Connector path and do not require an API key or
  the Zotero 10+ local write-authorization dialog. Repairing a legacy item may
  prompt for local write authorization.
- The Zotero desktop app must be running with its local HTTP server available.
- Group-library targets are not offered; the GUI selects My Library or one of
  its collections.
- The bridge still adds one `arxiv-digest` source tag for reliable duplicate
  detection.
- No new dependency is required; `requests` is already used by the project.
