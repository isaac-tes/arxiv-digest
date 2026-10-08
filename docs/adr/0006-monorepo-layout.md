# ADR 0006 — Monorepo layout

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

We're adding a FastAPI backend and a SwiftUI iOS app to a repo that already contains
a Python CLI, a Streamlit GUI, and a Zotero bridge. Where should the new code live?

## Decision

Use a **monorepo**: add `server/` (FastAPI) and `ios/` (SwiftUI app) alongside the
existing Python files. The FastAPI server imports `arxiv_digest.py` directly — that's
the whole point of "same backend" — so keeping everything in one repo avoids a
packaging dance.

## Considered options

- **Separate repos** — one for the Python backend, one for the iOS app. Rejected:
  forces packaging the shared scoring core and complicates cross-repo iteration.

## Consequences

- One repo to clone; shared scoring logic stays in one place.
- The iOS app can be split into its own repo later if it grows independent, without
  affecting the backend.
- Repo gets larger; mitigated by clear `server/` and `ios/` boundaries.
