"""Zotero bridge: save arXiv papers to the user's local Zotero library.

Uses Zotero's **local HTTP API** (``http://localhost:23119/api/``) — the same
mechanism the official Zotero Connector browser extension uses. Reads need no
authentication; writes (Zotero 10+) trigger a one-time "Allow this application?"
dialog in Zotero that grants a local API key at runtime.

The saved item replicates what the Zotero Connector's arXiv translator
(``arXiv.org.js``) produces: it fetches the arXiv export API Atom feed and builds
a ``preprint`` item with the same fields, category tags, and PDF/Snapshot
attachments, plus a single ``arxiv-digest`` source tag.

See docs/adr/0001-zotero-local-api-bridge.md for the rationale.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import requests

ZOTERO_LOCAL_BASE = "http://localhost:23119/api"
ZOTERO_API_VERSION = "3"
ARXIV_EXPORT_API = "https://export.arxiv.org/api/query"
SOURCE_TAG = "arxiv-digest"

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
    return _ARXIV_PREFIX_RE.sub("", text).strip()


def zotero_available(timeout: float = 1.0) -> bool:
    """Return True if the Zotero local API is reachable (desktop app running)."""
    try:
        resp = requests.get(f"{ZOTERO_LOCAL_BASE}/users/0/collections", timeout=timeout)
        return resp.status_code < 500
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


def _zotero_server_id(timeout: float = 2.0) -> Optional[str]:
    """Return the Zotero-Server-ID header, or None if absent.

    The header is only present in Zotero 10+. Its absence means the running
    Zotero predates 10 and its local API is read-only (writes unsupported).
    """
    try:
        resp = requests.get(f"{ZOTERO_LOCAL_BASE}/", timeout=timeout)
        return resp.headers.get("Zotero-Server-ID")
    except requests.RequestException:
        return None


def zotero_write_supported(timeout: float = 2.0) -> bool:
    """Return True if the local Zotero supports writes (Zotero 10+).

    Zotero < 10 exposes a read-only local API; write requests return
    ``400 Endpoint does not support method``. Zotero 10+ adds the
    ``Zotero-Server-ID`` header and the local write-authorization flow.
    """
    return _zotero_server_id(timeout=timeout) is not None


def _authorize_write(server_id: str, app_name: str = "arXiv Digest") -> Optional[str]:
    """Request a local API key from Zotero (pops the 'Allow this application?' dialog).

    Returns the key, or None if the user denied or the request failed.
    """
    try:
        resp = requests.post(
            f"{ZOTERO_LOCAL_BASE}/local/authorize",
            headers={
                "Zotero-API-Version": ZOTERO_API_VERSION,
                "Zotero-Server-ID": server_id,
                "Content-Type": "application/json",
            },
            data=json.dumps({"appName": app_name}),
            timeout=30,
        )
    except requests.RequestException:
        return None
    if resp.status_code not in (200, 201):
        return None
    try:
        return resp.json().get("key")
    except (ValueError, AttributeError):
        return None


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


def save_to_zotero(arxiv_id: str, collection_key: Optional[str] = None) -> Dict:
    """Fetch an arXiv paper and save it to the local Zotero library.

    If ``collection_key`` is given, the item is added to that collection.
    Returns a dict with ``ok`` (bool) and either ``item_key`` or ``error``.
    Raises on network/API failures so the caller can surface a message.
    """
    clean = arxiv_id_from_input(arxiv_id)
    if not clean:
        return {"ok": False, "error": "Could not parse an arXiv id from that input."}

    entry = fetch_arxiv_atom(clean)
    if entry is None:
        return {"ok": False, "error": f"No arXiv paper found for id '{clean}'."}

    version = None
    vm = re.search(r"v(\d+)$", clean)
    if vm:
        version = vm.group(1)

    item = build_preprint_item(entry, version=version)
    if collection_key:
        item["collections"] = [collection_key]

    # Zotero < 10 exposes a read-only local API — writes are unsupported.
    server_id = _zotero_server_id()
    if server_id is None:
        return {
            "ok": False,
            "error": (
                "Your Zotero version's local API is read-only (Zotero 10+ is "
                "required for saving). Please upgrade Zotero to 10 or newer, "
                "then try again."
            ),
        }

    # Zotero 10+: request a local API key (pops the 'Allow this application?'
    # dialog), then write with it.
    api_key = _authorize_write(server_id)
    if api_key is None:
        return {
            "ok": False,
            "error": (
                "Zotero did not grant write access. In Zotero, click Allow when "
                "the 'Allow this application to modify your library?' dialog "
                "appears, then try again."
            ),
        }

    headers = {
        "Zotero-API-Version": ZOTERO_API_VERSION,
        "Zotero-Server-ID": server_id,
        "Zotero-API-Key": api_key,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{ZOTERO_LOCAL_BASE}/users/0/items",
        headers=headers,
        data=json.dumps([item]),
        timeout=30,
    )
    if resp.status_code in (200, 201):
        try:
            created = resp.json()
            key = created[0].get("key") if isinstance(created, list) and created else None
        except (ValueError, AttributeError):
            key = None
        return {"ok": True, "item_key": key}
    if resp.status_code == 401:
        return {
            "ok": False,
            "error": (
                "Zotero did not authorize the write. In Zotero, click Allow when "
                "the 'Allow this application to modify your library?' dialog appears, "
                "then try again."
            ),
        }
    if resp.status_code == 403:
        return {
            "ok": False,
            "error": (
                "Zotero's local API is disabled. Enable it in Zotero: "
                "Settings → Advanced → 'Allow other applications on this computer "
                "to communicate with Zotero', then restart Zotero."
            ),
        }
    return {"ok": False, "error": f"Zotero returned HTTP {resp.status_code}."}
