# CONTEXT.md — arXiv Digest domain glossary

This file is a glossary of the project's domain terms. It is deliberately free of
implementation details. Terms are captured as they are resolved during design
discussions.

## Core concepts

- **Digest** — the ranked, scored list of arXiv papers produced from a fetch,
  filtered and sliced to `top_n`. The primary output of the tool.

- **Paper** — a single arXiv submission as scraped/fetched: id, title, authors,
  abstract, subjects, link, section. The unit of scoring, ranking, and saving.

- **Aspect** — a scored-and-highlightable dimension of a paper. The canonical set
  is: **keywords**, **authors**, **subjects**, **low-priority**. Every aspect that
  contributes to a score is also highlightable, and every highlight maps back to a
  score contribution. (Reconciled from the older, narrower "highlight" vocabulary
  that covered only keywords / low-priority / authors.)

- **Score** — the integer relevance total for a paper, computed by summing per-aspect
  contributions (keyword hits, named-author hits, subject/feed bonuses, low-priority
  penalty, long-abstract bonus).

- **Breakdown** — the per-aspect explanation of how a score was reached. Shown in
  the "Why this score?" expander and in the Score-a-paper tab.

- **Feed** — a named arXiv listing (e.g. `cond-mat.quant-gas`) that the tool
  subscribes to and fetches. Feeds drive both what gets fetched and the subject
  score bonus.

- **Profile** — a named, saved `Config` (keywords, authors, feeds, weights, colors)
  stored under `~/.arxiv_scraper/profiles/`. The project config (`arxiv_config.json`)
  is the same shape.

## Zotero integration

- **Zotero bridge** — the connection from the GUI to the user's local Zotero
  library via Zotero's local HTTP API (`localhost:23119`). Enables one-click
  "Save to Zotero" without manual API-key setup.

- **Save to Zotero** — the action of writing a paper into the user's Zotero library
  as a `preprint` item, replicating what the Zotero Connector produces for an arXiv
  page (same fields, category tags, and PDF/Snapshot attachments), plus a single
  `arxiv-digest` source tag.

- **Connector-faithful** — describing a saved item whose fields and tags match what
  the official Zotero Connector would produce for the same arXiv page.

## Score-a-paper

- **Score-a-paper** — the workflow of pasting an arXiv link/ID and getting its score,
  breakdown, and an explanation of why it did or did not appear in the current digest.

- **Absence reason** — the explanation for a paper not appearing in the digest:
  either it was fetched but ranked below `top_n`, or it was never fetched (outside
  the subscribed feeds or the timeframe).

## Mobile app

- **Digest service** — the FastAPI backend that exposes the shared scoring/fetch
  engine to the mobile apps. The single source of truth for CLI, GUI, iOS, and
  Android.

- **Triage** — the act of quickly deciding a paper's fate in the mobile app by
  swiping: right = star/save to a list, left = dismiss/penalize. The primary mobile
  interaction.

- **Swipe action** — a single triage decision (star, dismiss, or penalize) sent to
  the backend as feedback. Distinct from a *score*: a swipe *changes* future scores.

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

- **Feedback** — a recorded swipe action that reweights the relevant signal so the
  model visibly adapts to the user's triage.

- **User** — an account in the multi-tenant backend. Every config, list, and feedback
  record is scoped to a user. v1 runs single-user but the schema is multi-tenant.

- **Offline cache** — the app's local (SwiftData) copy of the last digest, saved
  papers, and PDFs, so the app works without a connection. The server remains the
  source of truth; the cache is a convenience.
