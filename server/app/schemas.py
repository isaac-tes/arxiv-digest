"""Pydantic request/response schemas for the digest service API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Auth ────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Digest ──────────────────────────────────────────────────────────────────
class PaperOut(BaseModel):
    rank: int
    id: str
    title: str
    authors: str
    link: str
    subjects: str
    section: str
    summary: str
    score: int


class DigestResponse(BaseModel):
    papers: list[PaperOut]
    total_papers: int
    requested_top: int


# ── Score ───────────────────────────────────────────────────────────────────
class ScoreRequest(BaseModel):
    arxiv_id: str


class ScoreResponse(BaseModel):
    paper: dict[str, Any] | None
    breakdown: dict[str, Any]
    absence_reason: str | None = None


# ── Config ──────────────────────────────────────────────────────────────────
class ConfigOut(BaseModel):
    data: dict[str, Any]


class ConfigUpdate(BaseModel):
    data: dict[str, Any]


# ── Lists ───────────────────────────────────────────────────────────────────
class ListCreate(BaseModel):
    name: str


class ListPaperIn(BaseModel):
    arxiv_id: str
    title: str = ""
    authors: str = ""
    link: str = ""


class ListPaperOut(BaseModel):
    arxiv_id: str
    title: str
    authors: str
    link: str
    added_at: datetime

    model_config = {"from_attributes": True}


class ListOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    papers: list[ListPaperOut] = []

    model_config = {"from_attributes": True}


# ── Feedback ────────────────────────────────────────────────────────────────
class FeedbackIn(BaseModel):
    arxiv_id: str
    action: Literal["star", "dismiss", "penalize"]
    signal: str = "keyword"


# ── Zotero ──────────────────────────────────────────────────────────────────
class ZoteroSaveRequest(BaseModel):
    arxiv_id: str
    collection_key: str | None = None
    mode: Literal["web", "deeplink"] = "web"


class ZoteroSaveResponse(BaseModel):
    ok: bool
    mode: str
    message: str
    deep_link: str | None = None
