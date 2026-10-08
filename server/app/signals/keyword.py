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
