# ADR 0002 — FastAPI REST backend + native mobile apps

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

We want a native iOS/iPadOS app (and later Android) that reuses the existing Python
scoring/fetch engine. The core question is how to share the backend across platforms.

## Decision

Expose the existing `arxiv_digest.py` scoring/fetch logic as a **FastAPI REST
service**, and build **native SwiftUI (iOS/iPadOS)** and later **native Android**
apps that consume the same JSON API. The server imports `arxiv_digest.py` as a module
(the Streamlit GUI already does `import arxiv_digest as ad`), so no refactor of the
single-file core is required.

## Considered options

1. **Kotlin Multiplatform (KMP)** — shared logic in Kotlin; conflicts with the
   Swift-first goal (core would be Kotlin, not Swift).
2. **Flutter** — single Dart codebase; not Swift, abandons native iOS.
3. **On-device Python** (embedded interpreter / BeeWare) — heavy, poor iOS fit.

## Consequences

- Maximum "same backend" reuse; one scoring engine for CLI, GUI, iOS, Android.
- Native feel on each platform; Android later consumes the same API unchanged.
- Requires hosting the FastAPI service (local and/or remote — see ADR 0003).
- FastAPI's OpenAPI output can generate client SDKs for Swift/Android if we ever want
  them, but v1 uses a hand-rolled `URLSession` + `Codable` client.
