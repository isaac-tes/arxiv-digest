# ADR 0008 — The digest view is computed on the server

- **Status**: Accepted
- **Date**: 2026-10-04

## Context

The web GUI builds its Papers view in one function: filter replacements, keep the
picked **Day**, skip **Removed papers** while walking the full ranking, and stop at
top-N. Score-a-paper reuses that function, so both tabs agree on every rank.

The iOS app needs the same view. It could get it two ways:

1. Fetch the whole scored paper set once and filter, remove, and rank on the device.
2. Ask the digest service for the finished view, passing the day and top-N.

## Decision

The digest service computes the view (option 2). `GET /digest` takes `day` and
`top_n`, excludes the user's removed papers, and returns the ranked papers with
their abstracts and breakdowns, plus the removed papers that would otherwise be
shown, the available days, filter counts, and fetch notices. Removed papers are
stored per user on the server. `POST /score` ranks the paper against the same
view, so the Score tab reports the same rank or absence reason as the Papers tab.

Picking a day or removing a paper re-ranks the cached fetch on the server. It
never re-fetches from arXiv.

## Considered options

- **Rank on the device.** One fewer request when switching days. Rejected: it
  ships every fetched paper (hundreds per week) to the phone, and it duplicates
  ranking and scoring in Swift. That breaks the thin-client rule (ADR 0002), and
  the two copies would drift.
- **Filter the returned top-N by day on the device.** Cheapest, but wrong: it
  shows the part of the week's top-N that falls on that day, not that day's own
  ranking, which is what the GUI shows.

## Consequences

- One ranking implementation (`arxiv_digest.build_ranked_entries`) serves the CLI,
  GUI, and app.
- Switching day or removing a paper costs a round-trip to the server, which is
  cheap because the fetch is cached.
- Removals follow the **User** across devices instead of a local profile.
