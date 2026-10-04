"""Removed papers: hide a paper from the digest, restore it later (ADR 0008).

Removal is per user and never changes a score; `/digest` skips removed papers
while ranking, so the papers below move up one place.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import RemovedPaper, User
from ..schemas import RemoveRequest, RestoreRequest

router = APIRouter(prefix="/removed", tags=["removed"])


@router.get("", response_model=list[str])
def list_removed(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[str]:
    rows = (
        db.query(RemovedPaper)
        .filter(RemovedPaper.user_id == user.id)
        .order_by(RemovedPaper.removed_at)
        .all()
    )
    return [r.arxiv_id for r in rows]


@router.post("", status_code=204)
def remove_paper(
    body: RemoveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Hide a paper. Idempotent: removing it twice is not an error."""
    exists = (
        db.query(RemovedPaper)
        .filter(RemovedPaper.user_id == user.id, RemovedPaper.arxiv_id == body.arxiv_id)
        .first()
    )
    if exists is None:
        db.add(RemovedPaper(user_id=user.id, arxiv_id=body.arxiv_id))
        db.commit()
    return Response(status_code=204)


@router.post("/restore", status_code=204)
def restore_papers(
    body: RestoreRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Un-hide papers. Ids that were not removed are ignored."""
    if body.arxiv_ids:
        (
            db.query(RemovedPaper)
            .filter(RemovedPaper.user_id == user.id, RemovedPaper.arxiv_id.in_(body.arxiv_ids))
            .delete(synchronize_session=False)
        )
        db.commit()
    return Response(status_code=204)
