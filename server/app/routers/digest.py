"""Digest router: fetch, filter, score, rank papers."""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import DigestResponse, PaperOut
from ..scoring import load_user_config, score_paper

router = APIRouter(prefix="/digest", tags=["digest"])

# In-memory fetch cache (ADR/plan §11: "cache aggressively (1h)"). Scraping
# several arXiv list pages for a pastweek digest takes 30–40s, which times out
# mobile clients on every load; caching the fetched+scored papers keeps repeat
# loads instant. Keyed by (user_id, timeframe, feeds); the top_n slice is
# applied per-request so different top_n reuse the same fetch.
_CACHE_TTL_SECONDS = 60 * 60
_cache_lock = threading.Lock()
_digest_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}


def _fetch_scored_papers(cfg, feed_list: list[str] | None, timeframe: str) -> list[dict[str, Any]]:
    from arxiv_digest import fetch_feeds, filter_papers

    urls = _feed_urls(cfg, feed_list, timeframe)
    papers = fetch_feeds(urls)
    papers = filter_papers(papers, include_replacements=cfg.include_replacements)
    for p in papers:
        p["score"] = score_paper(p, cfg)
    return papers


def _cached_scored_papers(
    user_id: int, cfg, feed_list: list[str] | None, timeframe: str, refresh: bool
) -> list[dict[str, Any]]:
    key = (user_id, timeframe, tuple(feed_list) if feed_list else None)
    now = time.monotonic()
    if not refresh:
        with _cache_lock:
            hit = _digest_cache.get(key)
            if hit and (now - hit[0]) < _CACHE_TTL_SECONDS:
                return hit[1]
    papers = _fetch_scored_papers(cfg, feed_list, timeframe)
    with _cache_lock:
        _digest_cache[key] = (now, papers)
    return papers


def _feed_urls(cfg, feeds: list[str] | None, timeframe: str) -> list[str]:
    """Build arXiv listing URLs for the requested feeds + timeframe.

    Mirrors arxiv_digest.determine_feed's URL rewriting: /new = today,
    /pastweek = last ~5 days.
    """
    suffix = "new" if timeframe == "today" else "pastweek"
    names = feeds or cfg.default_feeds
    urls: list[str] = []
    for name in names:
        if name in cfg.feeds:
            base = cfg.feeds[name]
            url = (
                base.replace("/new", f"/{suffix}")
                .replace("/recent", f"/{suffix}")
                .replace("/pastweek", f"/{suffix}")
            )
            urls.append(url)
        elif name.startswith("http"):
            urls.append(name)
    return urls


@router.get("", response_model=DigestResponse)
def get_digest(
    timeframe: str = "pastweek",
    top_n: int | None = None,
    feeds: str | None = None,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DigestResponse:
    from arxiv_digest import build_ranked_entries

    cfg = load_user_config(db, user)
    feed_list = feeds.split(",") if feeds else None

    papers = _cached_scored_papers(user.id, cfg, feed_list, timeframe, refresh)

    entries = build_ranked_entries(papers, cfg, top_n=top_n)
    return DigestResponse(
        papers=[PaperOut(**e) for e in entries],
        total_papers=len(papers),
        requested_top=top_n or cfg.top_n,
    )


@router.post("/refresh", response_model=DigestResponse)
def refresh_digest(
    timeframe: str = "pastweek",
    top_n: int | None = None,
    feeds: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DigestResponse:
    """Force a refetch, bypassing the 1h cache (plan §4)."""
    return get_digest(
        timeframe=timeframe, top_n=top_n, feeds=feeds, refresh=True, user=user, db=db
    )
