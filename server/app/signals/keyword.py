"""Keyword signal — wraps the existing arxiv_digest scoring.

This is the v1 signal. It delegates to ``arxiv_digest.explain_score`` so the
mobile app's scores match the CLI/GUI exactly. Later signals (embedding,
author-affinity, veto) slot in alongside it without changing this one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arxiv_digest import Config


class KeywordSignal:
    name = "keyword"

    def score(self, paper: dict, cfg: "Config") -> int:
        from arxiv_digest import score_paper

        return score_paper(paper, cfg)

    def explain(self, paper: dict, cfg: "Config") -> dict:
        from arxiv_digest import explain_score

        return explain_score(paper, cfg)

    def highlight(self, paper: dict, cfg: "Config") -> dict:
        """Return matched terms per aspect for the UI to highlight.

        Mirrors the GUI's highlight logic: keywords/low-priority match title +
        abstract, authors match the author list only, subjects match the subject
        string.
        """
        from arxiv_digest import term_matches

        wb = cfg.word_boundary_matching
        txt = " ".join(
            [paper.get("title", ""), paper.get("abstract", ""), paper.get("authors", ""), paper.get("subjects", "")]
        ).lower()
        authors_txt = paper.get("authors", "").lower()
        subjects = paper.get("subjects", "").lower()

        return {
            "keywords": [kw for kw in cfg.core_keywords if term_matches(kw, txt, word_boundary=wb)],
            "authors": [a for a in cfg.named_authors if term_matches(a, authors_txt, word_boundary=wb)],
            "low_priority": [k for k in cfg.low_priority_kw if term_matches(k, txt, word_boundary=wb)],
            "subjects": [name for name, w in (cfg.feed_weights or {}).items() if w and name.lower() in subjects],
        }
