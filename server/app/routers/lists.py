"""Lists router: multi-list saved papers (strategic differentiator)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import ListPaper, SavedList, User
from ..schemas import ListCreate, ListOut, ListPaperIn, ListPaperOut

router = APIRouter(prefix="/lists", tags=["lists"])


@router.get("", response_model=list[ListOut])
def list_lists(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SavedList]:
    return db.query(SavedList).filter(SavedList.user_id == user.id).order_by(SavedList.name).all()


@router.post("", response_model=ListOut, status_code=201)
def create_list(body: ListCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SavedList:
    existing = db.query(SavedList).filter(SavedList.user_id == user.id, SavedList.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="List already exists")
    lst = SavedList(user_id=user.id, name=body.name)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return lst


def _get_list(db: Session, user: User, list_id: int) -> SavedList:
    lst = db.query(SavedList).filter(SavedList.id == list_id, SavedList.user_id == user.id).first()
    if lst is None:
        raise HTTPException(status_code=404, detail="List not found")
    return lst


@router.get("/{list_id}", response_model=ListOut)
def get_list(list_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SavedList:
    return _get_list(db, user, list_id)


@router.post("/{list_id}/papers", response_model=ListPaperOut, status_code=201)
def add_paper(
    list_id: int,
    body: ListPaperIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListPaper:
    lst = _get_list(db, user, list_id)
    existing = (
        db.query(ListPaper).filter(ListPaper.list_id == lst.id, ListPaper.arxiv_id == body.arxiv_id).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Paper already in list")
    paper = ListPaper(
        list_id=lst.id,
        arxiv_id=body.arxiv_id,
        title=body.title,
        authors=body.authors,
        link=body.link,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/{list_id}/papers/{arxiv_id}", status_code=204)
def remove_paper(
    list_id: int,
    arxiv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    lst = _get_list(db, user, list_id)
    paper = (
        db.query(ListPaper).filter(ListPaper.list_id == lst.id, ListPaper.arxiv_id == arxiv_id).first()
    )
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not in list")
    db.delete(paper)
    db.commit()


@router.patch("/{list_id}", response_model=ListOut)
def rename_list(
    list_id: int,
    body: ListCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedList:
    lst = _get_list(db, user, list_id)
    lst.name = body.name
    db.commit()
    db.refresh(lst)
    return lst
