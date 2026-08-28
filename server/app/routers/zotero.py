"""Zotero router: save a paper to Zotero from mobile.

Two modes (ADR 0005):
- **web**: Zotero Web API — requires a zotero.org API key (works on iOS + Android).
- **deeplink**: return a zotero:// deep-link for the Zotero iOS app.

The desktop GUI keeps its own local bridge (zotero_bridge.py); this endpoint is
for the mobile apps.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import User
from ..schemas import ZoteroSaveRequest, ZoteroSaveResponse

router = APIRouter(prefix="/zotero", tags=["zotero"])

# zotero.org API key for the Web API path (set via env, not committed).
ZOTERO_API_KEY = os.environ.get("ZOTERO_API_KEY", "")
ZOTERO_LIBRARY_ID = os.environ.get("ZOTERO_LIBRARY_ID", "")


@router.get("/status")
def zotero_status(user: User = Depends(get_current_user)) -> dict:
    return {
        "web_api_available": bool(ZOTERO_API_KEY and ZOTERO_LIBRARY_ID),
        "deeplink_supported": True,
    }


@router.post("/save", response_model=ZoteroSaveResponse)
def save_to_zotero(
    body: ZoteroSaveRequest,
    user: User = Depends(get_current_user),
) -> ZoteroSaveResponse:
    if body.mode == "deeplink":
        # zotero://select/items/<key> — the Zotero iOS app handles this.
        return ZoteroSaveResponse(
            ok=True,
            mode="deeplink",
            message="Open in Zotero app",
            deep_link=f"zotero://select/items/{body.arxiv_id}",
        )

    # Web API path.
    if not (ZOTERO_API_KEY and ZOTERO_LIBRARY_ID):
        raise HTTPException(
            status_code=503,
            detail="Zotero Web API not configured. Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID.",
        )

    # Fetch the paper's metadata and POST a preprint item to the Zotero Web API.
    from arxiv_digest import fetch_paper_by_id

    paper = fetch_paper_by_id(body.arxiv_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    import requests

    item = {
        "itemType": "preprint",
        "title": paper.get("title", ""),
        "creators": _creators(paper.get("authors", "")),
        "url": paper.get("link", ""),
        "archive": "arXiv",
        "archiveID": body.arxiv_id,
        "tags": [{"tag": "arxiv-digest"}],
    }
    if body.collection_key:
        item["collections"] = [body.collection_key]

    resp = requests.post(
        f"https://api.zotero.org/users/{ZOTERO_LIBRARY_ID}/items",
        headers={
            "Zotero-API-Key": ZOTERO_API_KEY,
            "Zotero-API-Version": "3",
            "Content-Type": "application/json",
        },
        json=[item],
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Zotero API error: {resp.status_code} {resp.text[:200]}")

    return ZoteroSaveResponse(ok=True, mode="web", message="Saved to Zotero")


def _creators(authors: str) -> list[dict]:
    """Parse a comma-separated author string into Zotero creator objects."""
    out = []
    for part in (authors or "").split(","):
        part = part.strip()
        if not part:
            continue
        if " " in part:
            last, first = part.rsplit(" ", 1)
            out.append({"creatorType": "author", "firstName": first, "lastName": last})
        else:
            out.append({"creatorType": "author", "lastName": part})
    return out
