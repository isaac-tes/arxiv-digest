# ADR 0007 — iOS 17+ with Swift Package Manager core

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

We need to pick the iOS deployment target and project format. The user develops with
Swift 6.3.3 (via swiftly) and the Swift VS Code extension, and wants to iterate in VS
Code where possible.

## Decision

Target **iOS 17+** and structure the app as a **Swift Package Manager** package with
a thin Xcode app target:

- `ArxivDigestCore` — a pure SPM library (models, API client, scoring display) that
  builds and tests from VS Code via `swift build` / `swift test`.
- `ArxivDigestApp` — a thin SwiftUI app target that must be opened in Xcode for
  simulator/device runs, asset catalogs, Info.plist, and code signing.

## Considered options

- **iOS 16+** — broader device reach but older APIs (ObservableObject/CoreData
  instead of `@Observable`/SwiftData). Rejected: iOS 17's `@Observable` and SwiftData
  are cleaner and the user's devices are modern.
- **Xcode project only** — rejected: doesn't fit the VS Code + SPM workflow for the
  logic layer.

## Consequences

- Logic layer is fully iterable in VS Code; Xcode is only needed at the
  "run on simulator/device" milestone.
- iOS 17+ excludes older devices, acceptable for a personal-first tool.
- SwiftData gives offline caching with minimal boilerplate.
