"""Digest router: fetch, filter, score, rank papers (ADR 0008).

The view this returns mirrors the GUI's Papers tab (`arxiv_gui._digest`):
replacements are filtered, an optional announcement day is kept, the user's
removed papers are skipped while walking the full ranking, and the walk stops
at top-N. Score-a-paper ranks against the same view (see `digest_view`).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import RemovedPaper, User
from ..schemas import DigestResponse, PaperOut
from ..scoring import explain_paper, load_user_config

router = APIRouter(prefix="/digest", tags=["digest"])

# In-memory fetch cache ("cache aggressively (1h)"). A pastweek fetch queries
# the export API per category with rate-limit pauses and can take 30 s+, which
# times out mobile clients on every load. The cache holds the *raw* fetched
# papers, keyed by (timeframe, resolved feed names); filtering, removal and
# ranking run per request against the current config, so editing keywords,
# weights, the day, or removals never re-fetches.
_CACHE_TTL_SECONDS = 60 * 60
_cache_lock = threading.Lock()


@dataclass
class FetchResult:
    papers: list[dict[str, Any]]
    notices: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_fetch_cache: dict[tuple, tuple[float, FetchResult]] = {}


def resolve_feed_names(cfg, feeds: list[str] | None) -> list[str]:
    """Requested feeds (or the config's subscribed ones), known names/URLs only.

    Blank entries are ignored, so `?feeds=` falls back to the config's feeds.
    """
    requested = [f.strip() for f in (feeds or []) if f.strip()]
    names = requested or cfg.default_feeds
    return [n for n in names if n in cfg.feeds or n.startswith(("http://", "https://"))]


def _cache_key(cfg, names: list[str], timeframe: str) -> tuple:
    """Key on the URLs actually fetched, not just feed names: editing a feed's
    URL, or two users mapping one name to different URLs, must not share a fetch."""
    return (timeframe, tuple((n, cfg.feeds.get(n, n)) for n in names))


def _fetch(cfg, names: list[str], timeframe: str) -> FetchResult:
    """Fetch exactly like the CLI (`arxiv_digest.main`).

    `pastweek` uses the export API for a true seven-day window
    (`fetch_pastweek`); explicit URL feeds only work on the HTML path, so they
    are skipped there. `today` scrapes the HTML /new listing.
    """
    import arxiv_digest as ad

    notices: list[str] = []
    if timeframe == "pastweek":
        end = datetime.now(UTC)
        start = end - timedelta(days=7)
        api_names = [n for n in names if not n.startswith("http")]
        papers = ad.fetch_pastweek(api_names, start, end, notices=notices)
    else:
        urls = [ad.feed_url(cfg.feeds[n], timeframe) if n in cfg.feeds else n for n in names]
        papers = ad.fetch_feeds(urls)
    return FetchResult(papers=papers, notices=notices)


_CACHE_MAX_ENTRIES = 64


def cached_fetch(cfg, names: list[str], timeframe: str, refresh: bool = False) -> FetchResult:
    key = _cache_key(cfg, names, timeframe)
    if not refresh:
        with _cache_lock:
            hit = _fetch_cache.get(key)
            if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
                return hit[1]
    try:
        result = _fetch(cfg, names, timeframe)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"arXiv fetch failed ({type(exc).__name__}). arXiv may be slow or down; try again in a moment.",
        ) from exc
    if not result.papers:
        return result  # never cache an empty fetch (nothing subscribed / arXiv hiccup)
    with _cache_lock:
        # Stamp after the fetch: a cold past-week fetch can take 30 s or more.
        _fetch_cache[key] = (time.monotonic(), result)
        if len(_fetch_cache) > _CACHE_MAX_ENTRIES:
            oldest = min(_fetch_cache, key=lambda k: _fetch_cache[k][0])
            del _fetch_cache[oldest]
    return result


def peek_cache(cfg, names: list[str], timeframe: str) -> FetchResult | None:
    """The cached fetch for these feeds, if still fresh (never fetches)."""
    with _cache_lock:
        hit = _fetch_cache.get(_cache_key(cfg, names, timeframe))
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
        return hit[1]
    return None


def removed_ids(db: Session, user: User) -> set[str]:
    rows = db.query(RemovedPaper.arxiv_id).filter(RemovedPaper.user_id == user.id).all()
    return {r[0] for r in rows}


@dataclass
class DigestView:
    entries: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    visible: list[dict[str, Any]]
    filtered: list[dict[str, Any]]
    day: str | None
    available_days: list[str]


def digest_view(
    fetched: list[dict[str, Any]], cfg, removed: set[str], day: str | None, top_n: int
) -> DigestView:
    """The ranking the Papers tab shows. Port of `arxiv_gui._digest`.

    A `day` no longer present in the fetch is dropped (the GUI does the same).
    """
    import arxiv_digest as ad

    days = ad.available_day_labels(fetched)
    if day not in days:
        day = None
    filtered = ad.filter_papers(
        fetched, include_replacements=cfg.include_replacements, days=[day] if day else None
    )
    limit = max(top_n, 1)
    entries: list[dict[str, Any]] = []
    removed_entries: list[dict[str, Any]] = []
    for e in ad.build_ranked_entries(filtered, cfg, top_n=len(filtered)):
        if len(entries) == limit:
            break
        if e["id"] in removed:
            removed_entries.append(e)
        else:
            entries.append({**e, "rank": len(entries) + 1})
    visible = [p for p in filtered if p["id"] not in removed]
    return DigestView(entries, removed_entries, visible, filtered, day, days)


def _paper_out(entry: dict[str, Any], by_id: dict[str, dict], cfg) -> PaperOut:
    full = by_id.get(entry["id"], {})
    return PaperOut(
        **entry,
        abstract=full.get("abstract", "") or "",
        breakdown=explain_paper(full, cfg) if full else None,
    )


@router.get("", response_model=DigestResponse)
def get_digest(
    timeframe: str | None = None,
    top_n: int | None = None,
    feeds: str | None = None,
    day: str | None = None,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DigestResponse:
    cfg = load_user_config(db, user)
    timeframe = timeframe or cfg.timeframe
    if timeframe not in ("today", "pastweek"):
        raise HTTPException(status_code=422, detail="timeframe must be 'today' or 'pastweek'")
    names = resolve_feed_names(cfg, feeds.split(",") if feeds else None)
    limit = top_n or cfg.top_n

    result = cached_fetch(cfg, names, timeframe, refresh)
    view = digest_view(result.papers, cfg, removed_ids(db, user), day, limit)
    by_id = {p["id"]: p for p in result.papers}

    return DigestResponse(
        papers=[_paper_out(e, by_id, cfg) for e in view.entries],
        total_papers=len(view.visible),
        requested_top=limit,
        fetched_papers=len(result.papers),
        hidden_by_filters=len(result.papers) - len(view.filtered),
        removed=[_paper_out(e, by_id, cfg) for e in view.removed],
        available_days=view.available_days,
        day=view.day,
        timeframe=timeframe,
        feeds=names,
        notices=result.notices,
        fetched_at=result.fetched_at,
    )


@router.post("/refresh", response_model=DigestResponse)
def refresh_digest(
    timeframe: str | None = None,
    top_n: int | None = None,
    feeds: str | None = None,
    day: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DigestResponse:
    """Force a refetch, bypassing the 1h cache."""
    return get_digest(
        timeframe=timeframe, top_n=top_n, feeds=feeds, day=day, refresh=True, user=user, db=db
    )
