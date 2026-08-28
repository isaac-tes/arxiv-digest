# ADR 0003 — Multi-tenant-ready backend from the start

- **Status**: Accepted
- **Date**: 2026-08-24

## Context

The app starts as a personal tool, but the goal is to go public with multiple users
and a freemium model. Retrofitting auth and per-user data isolation into a
single-user backend is a painful migration (data migration + breaking API changes).

## Decision

Build the backend **multi-tenant-ready from day one**: JWT auth (OAuth2 password
flow), a `users` table, and every config/list/feedback record scoped by `user_id`.
v1 runs effectively single-user (one account), but the schema and API are already
multi-tenant. Billing/tiers are explicitly out of scope until the business model is
discussed (Phase 5).

## Consequences

- Cheap to add `user_id` scoping now; expensive to retrofit later.
- Cross-device sync falls out naturally once auth lands (server is the source of
  truth).
- Slightly more upfront work in Phase 0/1 (auth plumbing), but no migration later.
- Single-user local mode keeps a no-op auth path so development stays frictionless.
