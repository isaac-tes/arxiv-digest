"""Score router: score one paper and place it against the current digest view.

Mirrors the GUI's Score-a-paper tab (`arxiv_gui.render_score_tab` and
`_absence_reason`): the paper's breakdown, plus either its rank in the same view
the Papers tab shows (ADR 0008) or a deterministic reason it is absent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import ScoreRequest, ScoreResponse
from ..scoring import explain_paper, load_user_config
from .digest import digest_view, peek_cache, removed_ids, resolve_feed_names

router = APIRouter(prefix="/score", tags=["score"])

_ATOM = "{http://www.w3.org/2005/Atom}"


def _not_fetched_reason(entry, fetched: list[dict[str, Any]], cfg) -> str:
    """Port of `arxiv_gui._absence_reason` for a paper outside the fetched set."""
    import arxiv_digest as ad

    cats = [c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")]
    pub_node = entry.find(f"{_ATOM}published")
    pub_date = pub_node.text.strip()[:10] if pub_node is not None and pub_node.text else None

    day_dates = set()
    for lbl in ad.available_day_labels(fetched):
        try:
            day_dates.add(datetime.strptime(lbl, "%a, %d %b %Y").date().isoformat())
        except ValueError:
            pass

    feed_names = [f.lower() for f in cfg.feeds]
    matched = [c for c in cats if any(c.lower().startswith(f) for f in feed_names)]

    reasons = []
    if pub_date and day_dates:
        if pub_date not in day_dates:
            reasons.append(
                f"it was submitted on **{pub_date}**, but the fetched feed only "
                f"covers **{', '.join(sorted(day_dates))}**"
            )
        else:
            reasons.append(
                f"it was submitted on **{pub_date}**, which IS within the fetched "
                f"days — so it was likely not yet listed in the feed pages when "
                f"you fetched"
            )
    elif pub_date:
        reasons.append(f"it was submitted on **{pub_date}**")

    if matched:
        reasons.append(f"its categories (**{', '.join(matched)}**) overlap your subscribed feeds")
    else:
        reasons.append(
            f"its categories (**{', '.join(cats) or 'unknown'}**) are **not among "
            f"your subscribed feeds** ({', '.join(cfg.feeds) or 'none'})"
        )
    return "This paper was **not in the fetched set**. Deterministic check: " + "; ".join(reasons) + "."


@router.post("", response_model=ScoreResponse)
def score_paper_endpoint(
    body: ScoreRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScoreResponse:
    import arxiv_digest as ad
    import zotero_bridge as zb

    cfg = load_user_config(db, user)
    timeframe = body.timeframe or cfg.timeframe
    cached = peek_cache(resolve_feed_names(cfg, None), timeframe)

    # A paper already in the cached fetch is scored from it, so Score works
    # while arXiv's export API is rate-limiting. Anything else needs arXiv.
    wanted = zb.arxiv_id_from_input(body.arxiv_id)
    paper = next((dict(p) for p in (cached.papers if cached else []) if p.get("id") == wanted), None)
    entry = None
    if paper is None:
        try:
            entry = zb.fetch_arxiv_atom(body.arxiv_id)
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach arXiv ({type(exc).__name__}); it may be rate-limiting. Try again in a moment.",
            ) from exc
        except Exception:  # noqa: BLE001 - malformed feed etc. -> treat as not found
            entry = None
        if entry is None:
            return ScoreResponse(paper=None, breakdown={"signals": {}, "total": 0}, absence_reason="Paper not found")
        paper = ad._paper_from_api_entry(entry)

    breakdown = explain_paper(paper, cfg)
    paper_id = paper["id"]

    if cached is None:
        return ScoreResponse(
            paper=paper,
            breakdown=breakdown,
            absence_reason="Load the digest first to compare this paper against it.",
        )

    fetched = cached.papers
    removed = removed_ids(db, user)
    view = digest_view(fetched, cfg, removed, body.day, body.top_n or cfg.top_n)
    rank = next((e["rank"] for e in view.entries if e["id"] == paper_id), None)
    if rank is not None:
        return ScoreResponse(paper=paper, breakdown=breakdown, rank=rank)

    fetched_ids = {p.get("id") for p in fetched}
    if paper_id not in fetched_ids:
        reason = _not_fetched_reason(entry, fetched, cfg)
    elif paper_id in removed:
        if paper_id in {e["id"] for e in view.removed}:
            reason = (
                "You **removed** this paper from the digest, so it is not ranked. "
                "Restore it from *Removed papers* in the **Papers** tab."
            )
        else:
            reason = (
                "You **removed** this paper, but the current filters or top-N hide it. "
                "Change the day or increase Top N until it appears under "
                "*Removed papers*, then restore it."
            )
    elif paper_id not in {
        p["id"] for p in ad.filter_papers(fetched, include_replacements=cfg.include_replacements)
    }:
        reason = (
            "This paper was fetched but is a **replacement** submission, which the "
            "digest hides. Turn on *Include replacement submissions* to rank it."
        )
    elif paper_id not in {p["id"] for p in view.visible}:
        reason = (
            f"This paper was fetched but is not from the picked day ({view.day}). "
            "Pick *All days* to rank it."
        )
    else:
        reason = f"This paper **was** fetched but ranked below your top-{body.top_n or cfg.top_n} cutoff."
    return ScoreResponse(paper=paper, breakdown=breakdown, absence_reason=reason)
