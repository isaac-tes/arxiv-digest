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
    # Full abstract and per-signal breakdown, so the app can show a paper's
    # detail without another arXiv round-trip. Optional for older servers.
    abstract: str = ""
    breakdown: dict[str, Any] | None = None


class DigestResponse(BaseModel):
    papers: list[PaperOut]
    # Papers left after the replacement/day filters and removals.
    total_papers: int
    requested_top: int
    # Everything the fetch returned, before any filter.
    fetched_papers: int = 0
    # Dropped by the replacement or day filter.
    hidden_by_filters: int = 0
    # Removed papers that would otherwise be in this ranking (restorable).
    removed: list[PaperOut] = []
    # Announcement days present in the fetch (chronological), and the one applied.
    available_days: list[str] = []
    day: str | None = None
    timeframe: str = "pastweek"
    feeds: list[str] = []
    # Warnings about a degraded fetch (e.g. export API rate-limited).
    notices: list[str] = []
    fetched_at: datetime | None = None


# ── Score ───────────────────────────────────────────────────────────────────
class ScoreRequest(BaseModel):
    arxiv_id: str
    # The Papers view to compare against (defaults: config timeframe/top_n, all days).
    timeframe: str | None = None
    top_n: int | None = None
    day: str | None = None


class ScoreResponse(BaseModel):
    paper: dict[str, Any] | None
    breakdown: dict[str, Any]
    # Rank in the current digest view, when the paper is shown there.
    rank: int | None = None
    # Why the paper is not in the current digest view (markdown, **bold**).
    absence_reason: str | None = None


# ── Removed papers ──────────────────────────────────────────────────────────
class RemoveRequest(BaseModel):
    arxiv_id: str = Field(min_length=1, max_length=64)  # RemovedPaper.arxiv_id column


class RestoreRequest(BaseModel):
    arxiv_ids: list[str]


class PresetInfo(BaseModel):
    name: str
    description: str


# ── Config ──────────────────────────────────────────────────────────────────
class ConfigOut(BaseModel):
    data: dict[str, Any]


class ConfigUpdate(BaseModel):
    data: dict[str, Any]


# ── Zotero ──────────────────────────────────────────────────────────────────
class ZoteroSaveRequest(BaseModel):
    arxiv_id: str
    collection_key: str | None = None
    # Web API only. The old "deeplink" mode returned a zotero://select link that
    # cannot create an item; iOS uses the share sheet instead (ADR 0005 amendment).
    mode: Literal["web"] = "web"


class ZoteroSaveResponse(BaseModel):
    ok: bool
    mode: str
    message: str
