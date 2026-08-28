# ADR 0004 — Pluggable scoring pipeline

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

The strategic direction is a trustworthy multi-signal scoring model (keyword +
embedding similarity to anchor papers + author/lab affinity + veto-capable penalties)
with a visible feedback loop. The current engine is keyword/regex only. We need to
ship a working v1 without painting the API into a corner.

## Decision

Expose the backend scoring as a **pluggable pipeline of signals**. Each signal
implements a common protocol (`score`, `explain`, `highlight`). **v1 ships only the
keyword signal** (wrapping the existing `explain_score` / `score_paper`); embedding,
author-affinity, and veto signals slot in later **additively** without breaking the
API or the app.

## Consequences

- v1 is shippable with no behavior change to the existing scoring.
- The mobile UI always gets a per-signal breakdown, satisfying the transparency
  requirement ("why this score?").
- Adding a signal later is additive — no breaking change.
- Slightly more abstraction up front than a single `score_paper` call, but it's the
  difference between a weekend clone and the defensible product.
