"""Save arXiv preprints to the user's local Zotero library.

Metadata comes from arXiv's Atom API; new saves use Zotero's local Connector
HTTP API so PDFs and page snapshots are imported like the browser extension.
Legacy records missing a PDF are repaired through the local file-upload API. See
`docs/adr/0001-zotero-local-api-bridge.md` for the rationale.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import requests

ZOTERO_LOCAL_BASE = "http://localhost:23119/api"
ZOTERO_API_VERSION = "3"
ARXIV_EXPORT_API = "https://export.arxiv.org/api/query"
SOURCE_TAG = "arxiv-digest"

_CACHE: Dict[str, Optional[str]] = {"server_id": None, "api_key": None}

# Atom namespace used by the arXiv export API.
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# Human-readable arXiv category names, mirroring the Zotero Connector's
# arXivCategories table. Subcategory values are the sub-field name only (the
# parent prefix is added by `_category_tag`), matching the connector exactly.
# Unknown categories fall back to the raw term.
_ARXIV_CATEGORIES = {
    "cond-mat": "Condensed Matter",
    "cond-mat.dis-nn": "Disordered Systems and Neural Networks",
    "cond-mat.mes-hall": "Mesoscale and Nanoscale Physics",
    "cond-mat.mtrl-sci": "Materials Science",
    "cond-mat.other": "Other Condensed Matter",
    "cond-mat.quant-gas": "Quantum Gases",
    "cond-mat.soft": "Soft Condensed Matter",
    "cond-mat.stat-mech": "Statistical Mechanics",
    "cond-mat.str-el": "Strongly Correlated Electrons",
    "cond-mat.supr-con": "Superconductivity",
    "quant-ph": "Quantum Physics",
    "math-ph": "Mathematical Physics",
    "hep-th": "High Energy Physics - Theory",
    "hep-ph": "High Energy Physics - Phenomenology",
    "hep-ex": "High Energy Physics - Experiment",
    "hep-lat": "High Energy Physics - Lattice",
    "gr-qc": "General Relativity and Quantum Cosmology",
    "astro-ph": "Astrophysics",
    "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
    "astro-ph.GA": "Astrophysics of Galaxies",
    "astro-ph.HE": "High Energy Astrophysical Phenomena",
    "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
    "astro-ph.SR": "Solar and Stellar Astrophysics",
    "physics": "Physics",
    "cs": "Computer Science",
    "cs.AI": "Artificial Intelligence",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision and Pattern Recognition",
    "cs.LG": "Machine Learning",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.SE": "Software Engineering",
    "cs.SY": "Systems and Control",
    "math": "Mathematics",
    "stat": "Statistics",
    "nlin": "Nonlinear Sciences",
    "eess": "Electrical Engineering and Systems Science",
    "econ": "Economics",
    "q-fin": "Quantitative Finance",
    "q-bio": "Quantitative Biology",
}

# Full URL / bare ID / arXiv:xxxx forms.
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^?#]+?)(?:\.pdf)?(?:v\d+)?$", re.IGNORECASE)
_ARXIV_PREFIX_RE = re.compile(r"^\s*arxiv\s*:\s*", re.IGNORECASE)
_ARXIV_VERSION_RE = re.compile(r"(?<=\d)v\d+$", re.IGNORECASE)


def arxiv_id_from_input(raw: str) -> str:
    """Extract a canonical arXiv id from a URL, bare id, or ``arXiv:xxxx``.

    Returns ``""`` if nothing recognizable is found.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    m = _ARXIV_URL_RE.search(text)
    if m:
        return m.group(1).strip()
    # Bare id or arXiv:xxxx — strip any version suffix and the prefix.
    return _ARXIV_VERSION_RE.sub("", _ARXIV_PREFIX_RE.sub("", text).strip())


def zotero_available(timeout: float = 1.0) -> bool:
    """Return True if Zotero's local Connector API is reachable."""
    try:
        resp = requests.post(
            f"{ZOTERO_LOCAL_BASE.removesuffix('/api')}/connector/ping",
            headers={"X-Zotero-Connector-API-Version": ZOTERO_API_VERSION},
            json={},
            timeout=timeout,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def list_collections(timeout: float = 10.0) -> list[Dict]:
    """Return the user's Zotero collections as ``[{key, name}]`` (read-only).

    Returns an empty list if the local API is unreachable or returns no data.
    """
    try:
        resp = requests.get(
            f"{ZOTERO_LOCAL_BASE}/users/0/collections",
            headers={"Zotero-API-Version": ZOTERO_API_VERSION},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []
    out = []
    for c in data or []:
        key = c.get("key")
        name = (c.get("data") or {}).get("name", "")
        if key:
            out.append({"key": key, "name": name})
    return out


def _zotero_server_id(timeout: float = 2.0) -> str | None:
    """Return the local API server ID needed to authorize a repair upload."""
    if _CACHE["server_id"] is not None:
        return _CACHE["server_id"]
    try:
        resp = requests.get(f"{ZOTERO_LOCAL_BASE}/", timeout=timeout)
    except requests.RequestException:
        return None
    server_id = resp.headers.get("Zotero-Server-ID")
    _CACHE["server_id"] = server_id
    return server_id


def _authorize_write(server_id: str) -> str | None:
    """Get a local write key, caching it only when Zotero marks it persistent."""
    if _CACHE["api_key"] is not None:
        return _CACHE["api_key"]
    try:
        resp = requests.post(
            f"{ZOTERO_LOCAL_BASE}/local/authorize",
            headers={
                "Zotero-API-Version": ZOTERO_API_VERSION,
                "Zotero-Server-ID": server_id,
                "Content-Type": "application/json",
            },
            json={"appName": "arXiv Digest"},
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            return None
        result = resp.json()
    except (requests.RequestException, ValueError):
        return None
    key = result.get("key")
    if key and result.get("remember"):
        _CACHE["api_key"] = key
    return key


def _local_write_headers(
    server_id: str, content_type: str
) -> dict[str, str] | None:
    api_key = _authorize_write(server_id)
    if api_key is None:
        return None
    return {
        "Zotero-API-Version": ZOTERO_API_VERSION,
        "Zotero-Server-ID": server_id,
        "Zotero-API-Key": api_key,
        "Zotero-Write-Token": secrets.token_hex(16),
        "Content-Type": content_type,
    }


def fetch_arxiv_atom(arxiv_id: str) -> Optional[ET.Element]:
    """Fetch the arXiv export API Atom feed for a single id.

    Returns the parsed ``<entry>`` element, or None if the id is invalid/not found.
    """
    clean = arxiv_id_from_input(arxiv_id)
    if not clean:
        return None
    resp = requests.get(
        ARXIV_EXPORT_API,
        params={"id_list": clean, "max_results": 1},
        timeout=30,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    return root.find(f"{_ATOM}entry")


def _category_tag(term: str) -> str:
    """Map an arXiv category term to its human-readable tag name."""
    main = term.split(".")[0]
    if main != term and main in _ARXIV_CATEGORIES:
        return f"{_ARXIV_CATEGORIES[main]} - {_ARXIV_CATEGORIES.get(term, term)}"
    return _ARXIV_CATEGORIES.get(term, term)


def _entry_text(entry: ET.Element, tag: str) -> str:
    node = entry.find(f"{_ATOM}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def build_preprint_item(entry: ET.Element, version: Optional[str] = None) -> Dict:
    """Build a Zotero ``preprint`` item from an arXiv Atom ``<entry>``.

    Replicates the Zotero Connector's arXiv translator output: same fields,
    category tags, and PDF/Snapshot attachments, plus the ``arxiv-digest``
    source tag.
    """
    title = _entry_text(entry, "title")
    date = _entry_text(entry, "updated")
    abstract = _entry_text(entry, "summary")
    versioned_url = _entry_text(entry, "id")
    arxiv_url = re.sub(r"v\d+$", "", versioned_url)
    article_id = arxiv_url.rsplit("/abs/", 1)[-1] if "/abs/" in arxiv_url else ""

    creators = []
    for author in entry.findall(f"{_ATOM}author"):
        name = author.find(f"{_ATOM}name")
        if name is None or not name.text:
            continue
        full = name.text.strip()
        parts = full.rsplit(" ", 1)
        if len(parts) == 2:
            creators.append(
                {"creatorType": "author", "firstName": parts[0], "lastName": parts[1]}
            )
        else:
            creators.append({"creatorType": "author", "firstName": "", "lastName": full})

    notes = []
    for comment in entry.findall(f"{_ARXIV_NS}comment"):
        if comment.text and comment.text.strip():
            notes.append({"note": f"Comment: {comment.text.strip()}"})

    tags = []
    for cat in entry.findall(f"{_ATOM}category"):
        term = cat.get("term")
        if term:
            tags.append({"tag": _category_tag(term)})
    tags.append({"tag": SOURCE_TAG})

    primary = entry.find(f"{_ARXIV_NS}primary_category")
    primary_term = primary.get("term") if primary is not None else None
    extra = f"arXiv:{article_id}"
    if primary_term:
        extra += f" [{primary_term}]"
    if version:
        extra += f"\nversion: {version}"

    pdf_url = versioned_url.replace("/abs/", "/pdf/")

    item = {
        "itemType": "preprint",
        "title": title,
        "creators": creators,
        "abstractNote": abstract,
        "date": date,
        "url": arxiv_url,
        "archiveID": f"arXiv:{article_id}",
        "extra": extra,
        "repository": "arXiv",
        "publisher": "arXiv",
        "number": f"arXiv:{article_id}",
        "DOI": f"10.48550/arXiv.{article_id}",
        "tags": tags,
        "notes": notes,
        "attachments": [
            {"title": "Preprint PDF", "url": pdf_url, "mimeType": "application/pdf"},
            {"title": "Snapshot", "url": arxiv_url, "mimeType": "text/html"},
        ],
    }
    return item


def _connector_url(endpoint: str) -> str:
    """Build a URL for Zotero's local Connector API."""
    return f"{ZOTERO_LOCAL_BASE.removesuffix('/api')}/connector/{endpoint}"


def _connector_headers() -> dict[str, str]:
    return {
        "X-Zotero-Connector-API-Version": ZOTERO_API_VERSION,
        "Content-Type": "application/json",
    }


def _collection_target_id(collection_key: str, timeout: float = 10.0) -> str | None:
    """Resolve a local API collection key to the Connector's tree-view ID."""
    resp = requests.get(
        f"{ZOTERO_LOCAL_BASE}/users/0/collections", timeout=timeout
    )
    resp.raise_for_status()
    collections = resp.json() or []
    by_key = {c.get("key"): c.get("data", {}) for c in collections}

    path = []
    seen = set()
    key = collection_key
    while key:
        if key in seen or key not in by_key:
            return None
        seen.add(key)
        collection = by_key[key]
        name = collection.get("name")
        if not name:
            return None
        path.append(name)
        parent = collection.get("parentCollection")
        key = parent if isinstance(parent, str) else None
    path.reverse()
    if not path:
        return None

    response = requests.post(
        _connector_url("getSelectedCollection"),
        headers=_connector_headers(),
        json={},
        timeout=timeout,
    )
    response.raise_for_status()
    targets = response.json().get("targets", [])

    target_path = []
    in_my_library = False
    matches = []
    for target in targets:
        target_id = target.get("id", "")
        if target_id.startswith("L"):
            in_my_library = target_id == "L1"
            target_path = []
            continue
        if not in_my_library:
            continue
        level = target.get("level", 0)
        if not isinstance(level, int) or level < 1:
            continue
        target_path = target_path[: level - 1]
        target_path.append(target.get("name", ""))
        if target_path == path:
            matches.append(target_id)
    return matches[0] if len(matches) == 1 else None


def _zotero_item_key(archive_id: str, timeout: float = 10.0) -> str | None:
    """Return the saved item key for an arXiv archive ID, if present."""
    start = 0
    while True:
        try:
            resp = requests.get(
                f"{ZOTERO_LOCAL_BASE}/users/0/items",
                headers={"Zotero-API-Version": ZOTERO_API_VERSION},
                params={"tag": SOURCE_TAG, "start": start, "limit": 100},
                timeout=timeout,
            )
            resp.raise_for_status()
            items = resp.json() or []
        except (requests.RequestException, ValueError):
            return None
        for item in items:
            if (item.get("data") or {}).get("archiveID") == archive_id:
                return item.get("key")
        if len(items) < 100:
            return None
        start += 100


def _existing_pdf_attachment(
    item_key: str, timeout: float = 10.0
) -> tuple[str, bool] | None:
    """Return an existing PDF attachment key and whether it has file data."""
    resp = requests.get(
        f"{ZOTERO_LOCAL_BASE}/users/0/items/{item_key}/children",
        headers={"Zotero-API-Version": ZOTERO_API_VERSION},
        timeout=timeout,
    )
    resp.raise_for_status()
    partial_key = None
    for child in resp.json() or []:
        data = child.get("data") or {}
        if data.get("contentType") != "application/pdf":
            continue
        key = child.get("key")
        has_file = bool(
            data.get("filename")
            and (child.get("links") or {}).get("enclosure", {}).get("length", 0) > 0
        )
        if has_file and key:
            return key, True
        if key and data.get("linkMode") == "imported_file":
            partial_key = key
    return (partial_key, False) if partial_key else None


def _download_arxiv_pdf(url: str) -> bytes | None:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content if resp.content.startswith(b"%PDF-") else None


def _repair_existing_item_pdf(
    item_key: str, pdf_bytes: bytes, attachment_key: str | None = None
) -> str | None:
    """Import a PDF onto a legacy item using Zotero's local file-upload API."""
    server_id = _zotero_server_id()
    if server_id is None:
        return "Could not identify Zotero's local API server for the PDF repair."

    if attachment_key is None:
        headers = _local_write_headers(server_id, "application/json")
        if headers is None:
            return "Zotero did not grant permission to repair the missing PDF."
        attachment = {
            "itemType": "attachment",
            "linkMode": "imported_file",
            "parentItem": item_key,
            "title": "Preprint PDF",
            "contentType": "application/pdf",
            "filename": "preprint.pdf",
        }
        resp = requests.post(
            f"{ZOTERO_LOCAL_BASE}/users/0/items",
            headers=headers,
            json=[attachment],
            timeout=30,
        )
        resp.raise_for_status()
        created = resp.json().get("successful", {}).get("0", {})
        attachment_key = created.get("key")
        if not attachment_key:
            return "Zotero did not create the PDF attachment."

    file_url = f"{ZOTERO_LOCAL_BASE}/users/0/items/{attachment_key}/file"
    upload_fields = {
        "md5": hashlib.md5(pdf_bytes, usedforsecurity=False).hexdigest(),
        "filename": "preprint.pdf",
        "filesize": len(pdf_bytes),
        "mtime": int(time.time() * 1000),
        "contentType": "application/pdf",
    }
    headers = _local_write_headers(server_id, "application/x-www-form-urlencoded")
    if headers is None:
        return "Zotero did not authorize the PDF upload."
    headers["If-None-Match"] = "*"
    resp = requests.post(file_url, headers=headers, data=upload_fields, timeout=30)
    resp.raise_for_status()
    upload = resp.json()

    resp = requests.post(
        upload["url"],
        headers={"Content-Type": "application/octet-stream"},
        data=pdf_bytes,
        timeout=60,
    )
    resp.raise_for_status()

    headers = _local_write_headers(server_id, "application/x-www-form-urlencoded")
    if headers is None:
        return "Zotero did not authorize finalizing the PDF upload."
    headers["If-None-Match"] = "*"
    resp = requests.post(
        file_url,
        headers=headers,
        data={"upload": upload["uploadKey"]},
        timeout=30,
    )
    resp.raise_for_status()
    return None


def save_to_zotero(arxiv_id: str, collection_key: Optional[str] = None) -> Dict:
    """Save an arXiv preprint with imported attachments, like the Connector.

    New items use Zotero's Connector save session. Existing metadata-only items
    are repaired by importing the PDF through Zotero's local file-upload API.
    ``collection_key`` selects a personal-library collection; group libraries
    are not offered by the GUI.
    """
    clean = arxiv_id_from_input(arxiv_id)
    if not clean:
        return {"ok": False, "error": "Could not parse an arXiv id from that input."}

    entry = fetch_arxiv_atom(clean)
    if entry is None:
        return {"ok": False, "error": f"No arXiv paper found for id '{clean}'."}

    item = build_preprint_item(entry)
    archive_id = item.get("archiveID", "")
    existing_item_key = _zotero_item_key(archive_id)
    if existing_item_key:
        existing_pdf = _existing_pdf_attachment(existing_item_key)
        if existing_pdf and existing_pdf[1]:
            return {
                "ok": False,
                "already_exists": True,
                "error": "Already in your Zotero library.",
            }
        pdf_url = item["attachments"][0]["url"]
        pdf_bytes = _download_arxiv_pdf(pdf_url)
        if pdf_bytes is None:
            return {"ok": False, "error": "arXiv did not return a valid PDF."}
        attachment_key = existing_pdf[0] if existing_pdf else None
        error = _repair_existing_item_pdf(
            existing_item_key, pdf_bytes, attachment_key=attachment_key
        )
        if error:
            return {"ok": False, "error": error}
        return {"ok": True, "item_key": existing_item_key}

    target_id = "L1"
    if collection_key:
        target_id = _collection_target_id(collection_key)
        if target_id is None:
            return {
                "ok": False,
                "error": "Could not find that Zotero collection in My Library.",
            }

    pdf_url = item["attachments"][0]["url"]
    pdf_bytes = _download_arxiv_pdf(pdf_url)
    if pdf_bytes is None:
        return {"ok": False, "error": "arXiv did not return a valid PDF."}

    page_resp = requests.get(item["url"], timeout=30)
    page_resp.raise_for_status()
    snapshot_html = page_resp.content.decode("utf-8", errors="replace")

    session_id = secrets.token_hex(16)
    connector_item_id = secrets.token_hex(8)
    item["id"] = connector_item_id
    payload = {"sessionID": session_id, "url": item["url"], "items": [item]}

    resp = requests.post(
        _connector_url("saveItems"),
        headers=_connector_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    if resp.status_code != 201:
        return {
            "ok": False,
            "error": (
                f"Zotero could not save the item (HTTP {resp.status_code})."
            ),
        }

    resp = requests.post(
        _connector_url("updateSession"),
        headers=_connector_headers(),
        json={"sessionID": session_id, "target": target_id},
        timeout=30,
    )
    resp.raise_for_status()

    resp = requests.post(
        _connector_url("saveSingleFile"),
        headers=_connector_headers(),
        json={
            "sessionID": session_id,
            "url": item["url"],
            "title": "Snapshot",
            "items": [{"id": connector_item_id}],
            "snapshotContent": snapshot_html,
        },
        timeout=60,
    )
    resp.raise_for_status()
    if resp.status_code != 201:
        return {"ok": False, "error": "Zotero did not save the page snapshot."}

    metadata = {
        "sessionID": session_id,
        "parentItemID": connector_item_id,
        "title": "Preprint PDF",
        "url": pdf_url,
    }
    resp = requests.post(
        _connector_url("saveAttachment"),
        params={"sessionID": session_id},
        headers={
            "Content-Type": "application/pdf",
            "X-Metadata": json.dumps(metadata),
        },
        data=pdf_bytes,
        timeout=60,
    )
    resp.raise_for_status()
    if resp.status_code != 201:
        return {"ok": False, "error": "Zotero did not save the PDF attachment."}

    return {"ok": True, "item_key": _zotero_item_key(archive_id)}
