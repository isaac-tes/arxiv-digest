"""Score router: score a single paper by arXiv id."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import ScoreRequest, ScoreResponse
from ..scoring import explain_paper, load_user_config

router = APIRouter(prefix="/score", tags=["score"])


@router.post("", response_model=ScoreResponse)
def score_paper_endpoint(
    body: ScoreRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScoreResponse:
    from arxiv_digest import fetch_paper_by_id

    cfg = load_user_config(db, user)
    paper = fetch_paper_by_id(body.arxiv_id)
    if paper is None:
        return ScoreResponse(paper=None, breakdown={"signals": {}, "total": 0}, absence_reason="Paper not found")

    breakdown = explain_paper(paper, cfg)
    return ScoreResponse(paper=paper, breakdown=breakdown)
