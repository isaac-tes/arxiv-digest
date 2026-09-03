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

## Score-a-paper

- **Score-a-paper**: the workflow of pasting an arXiv link/ID and getting its score,
  breakdown, and an explanation of why it did or did not appear in the current digest.

- **Absence reason**: the explanation for a paper not appearing in the digest:
  either it was fetched but ranked below `top_n`, or it was never fetched (outside
  the subscribed feeds or the timeframe).

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
