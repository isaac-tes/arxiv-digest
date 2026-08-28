"""Feedback router: record swipe actions (star/dismiss/penalize).

This is the "cheap feedback loop" — a recorded swipe reweights the relevant
signal. v1 records the event; the reweighting logic lands with the later
signals (embedding/author/veto) in Phase 3.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Feedback, User
from ..schemas import FeedbackIn

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
def record_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    fb = Feedback(user_id=user.id, arxiv_id=body.arxiv_id, action=body.action, signal=body.signal)
    db.add(fb)
    db.commit()
    return {"ok": True, "action": body.action, "arxiv_id": body.arxiv_id}
