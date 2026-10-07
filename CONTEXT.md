# CONTEXT.md: arXiv Digest domain glossary

This file is a glossary of the project's domain terms. It is deliberately free of
implementation details. Terms are captured as they are resolved during design
discussions.

## Core concepts

- **Digest**: the ranked, scored list of arXiv papers produced from a fetch,
  filtered and sliced to `top_n`. The primary output of the tool.

- **Paper**: a single arXiv submission as scraped/fetched: id, title, authors,
  abstract, subjects, link, section. The unit of scoring, ranking, and saving.

- **Aspect**: a scored-and-highlightable dimension of a paper. The canonical set
  is: **keywords**, **authors**, **subjects**, **low-priority**. Every aspect that
  contributes to a score is also highlightable, and every highlight maps back to a
  score contribution. (Reconciled from the older, narrower "highlight" vocabulary
  that covered only keywords / low-priority / authors.)

- **Score**: the integer relevance total for a paper, computed by summing per-aspect
  contributions (keyword hits, named-author hits, subject/feed bonuses, low-priority
  penalty, long-abstract bonus).

- **Breakdown**: the per-aspect explanation of how a score was reached. Shown in
  the "Why this score?" expander and in the Score-a-paper tab.

- **Feed**: a named arXiv listing (e.g. `cond-mat.quant-gas`) that the tool
  subscribes to and fetches. Feeds drive both what gets fetched and the subject
  score bonus.

- **Profile**: a named, saved `Config` (keywords, authors, feeds, weights, colors)
  stored under `~/.arxiv_scraper/profiles/`. The project config (`arxiv_config.json`)
  is the same shape.

- **Removed paper**: a paper the user has hidden from the digest. Removal is
  not a score change: the paper is skipped while ranking, so every paper below it
  moves up one place and the first paper past the top-N cutoff fills the freed
  slot. A removal persists across reloads and later fetches until the user
  restores it. In the GUI it belongs to the loaded profile; on the digest
  service it belongs to the **User**.

- **Day**: one arXiv announcement day within a past-week fetch (e.g.
  `Fri, 19 Jun 2026`). Picking a day re-ranks only that day's papers; it never
  re-fetches. Only days present in the current fetch can be picked.

- **Notice**: a human-readable warning attached to a fetch when it degraded
  (e.g. the export API was rate-limited and a shorter HTML listing was used).

## Zotero integration

- **Zotero bridge**: the connection from the GUI to the user's local Zotero
  library via Zotero's local HTTP API (`localhost:23119`). Enables one-click
  "Save to Zotero" without manual API-key setup.

- **Save to Zotero**: the action of writing a paper into a chosen Zotero library
  as a `preprint` item, replicating what the Zotero Connector produces for an arXiv
  page (same fields, category tags, and PDF/Snapshot attachments), plus a single
  `arxiv-digest` source tag. The GUI never blocks a save; it shows a transient
  "Saved ✓" indicator that expires after 30 seconds so the same paper can be
  re-saved. Duplicate prevention is a My-Library concern, not the tool's decision.

- **Save target**: the personal My Library root or one of its collections chosen
  in the Zotero save popover. Group-library targets are intentionally not
  offered because Zotero's local HTTP API has no supported group-library route.

- **Connector-faithful**: describing a saved item whose fields and tags match what
  the official Zotero Connector would produce for the same arXiv page.

- **Share to Zotero**: the mobile no-key path. The app hands the paper's arXiv
  page to the OS share sheet, where the Zotero iOS app's share extension saves
  it like the Connector would. Distinct from **Save to Zotero**, which writes the
  item through the Zotero Web API and needs a key on the digest service.

## Score-a-paper

- **Score-a-paper**: the workflow of pasting an arXiv link/ID and getting its score,
  breakdown, and an explanation of why it did or did not appear in the current digest.

- **Absence reason**: the explanation for a paper not appearing in the digest:
  it was fetched but ranked below `top_n`, removed by the user, hidden as a
  replacement submission, or outside the picked **Day**; or it was never
  fetched (outside the subscribed feeds or the timeframe).

## Mobile app

- **Digest service** — the FastAPI backend that exposes the shared scoring/fetch
  engine to the mobile apps. The single source of truth for CLI, GUI, iOS, and
  Android.

- **Triage** — *(deferred; not in the current app)* quickly deciding a paper's fate
  by swiping and recording **Feedback**. The current app's only swipe is
  **Remove**, which hides a paper and does not change any score.

- **Swipe action** — *(deferred)* a triage decision (star, dismiss, or penalize)
  sent to the backend as feedback. Distinct from a *score*: a swipe *changes*
  future scores. Distinct from **Removed paper**, which never changes a score.

- **List** — a named, user-curated collection of saved papers (e.g. one per subfield,
  the way Floquet/topological/anyon-Hubbard work is tracked separately). Multi-list
  support is a strategic differentiator.

- **Anchor paper** — a paper the user marks as core interest; used (in a later phase)
  as an embedding-similarity reference to catch semantically related work that misses
  the exact keywords.

- **Signal** — a pluggable scoring dimension in the backend pipeline (keyword,
  embedding, author-affinity, veto). Each signal contributes a score, an explanation,
  and highlight ranges. The pipeline sums signals; adding one later is additive.

- **Veto** — a penalty channel that can *suppress* a paper even with a decent positive
  score (e.g. a blocked author or a blocked sub-keyword). Distinct from a negative
  weight on the same axis.

- **Feedback** — *(deferred)* a recorded swipe action that reweights the relevant signal so the
  model visibly adapts to the user's triage.

- **User** — an account in the multi-tenant backend. Every config, list, and feedback
  record is scoped to a user. v1 runs single-user but the schema is multi-tenant.

- **Demo mode** — a self-contained run of the app against a bundled sample digest,
  with no digest service. For trying the UI and producing screenshots; its
  rankings do not react to config edits.

- **Standalone mode** — a run of the app that fetches the past week from the arXiv
  export API and scores papers on the device, with no digest service (ADR 0009).
  Single-device: config and removed papers live on the phone. Distinct from
  **Demo mode** (fixed sample) and **Server mode** (synced via the digest service).

- **Offline cache** — the app's local (SwiftData) copy of the last digest, saved
  papers, and PDFs, so the app works without a connection. The server remains the
  source of truth; the cache is a convenience.

## Release & changelog

- **Release notes**: the description attached to a GitHub Release. They are
  generated automatically by GitHub from the commits since the previous tag
  (`--generate-notes`), so they stay in sync with the commit history without
  hand-writing.

- **Conventional commit**: a commit whose subject starts with a type prefix
  (`fix:`, `feat:`, `docs:`, `chore:`, `ci:`, `release:`). The type drives how
  the change is grouped in the generated release notes.

- **Commit trailer**: a structured line at the end of a commit message body.
  `BREAKING CHANGE:` marks a change as breaking, which surfaces it prominently
  in the release notes.
