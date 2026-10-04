"""Tests for the digest service API.

Uses a temporary SQLite DB and FastAPI's TestClient. No network calls hit arXiv
(the digest endpoint's fetch is not exercised here; scoring/config/lists are).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Repo root so arxiv_digest.py is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Point the server at a temp SQLite DB before importing the app.
_tmpdir = tempfile.mkdtemp(prefix="digest-test-")
os.environ["DIGEST_DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["DIGEST_MODE"] = "local"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_config_roundtrip(client):
    cfg = {"core_keywords": ["floquet", "anyon"], "top_n": 10}
    put = client.put("/config", json={"data": cfg})
    assert put.status_code == 200
    assert put.json()["data"]["core_keywords"] == ["floquet", "anyon"]

    get = client.get("/config")
    assert get.status_code == 200
    assert get.json()["data"]["top_n"] == 10


def test_config_patch_merges(client):
    client.put("/config", json={"data": {"core_keywords": ["floquet"]}})
    patch = client.patch("/config", json={"data": {"named_authors": ["einstein"]}})
    data = patch.json()["data"]
    assert data["core_keywords"] == ["floquet"]
    assert data["named_authors"] == ["einstein"]


def test_presets_listed(client):
    resp = client.get("/config/presets")
    assert resp.status_code == 200
    names = resp.json()
    assert "open-quantum-systems" in names


def test_lists_crud(client):
    created = client.post("/lists", json={"name": "floquet"})
    assert created.status_code == 201
    list_id = created.json()["id"]

    add = client.post(
        f"/lists/{list_id}/papers",
        json={"arxiv_id": "arXiv:2601.0001", "title": "A Floquet paper", "authors": "A. Einstein"},
    )
    assert add.status_code == 201

    got = client.get(f"/lists/{list_id}")
    assert got.status_code == 200
    assert len(got.json()["papers"]) == 1

    dup = client.post(
        f"/lists/{list_id}/papers",
        json={"arxiv_id": "arXiv:2601.0001", "title": "dup"},
    )
    assert dup.status_code == 409

    rm = client.delete(f"/lists/{list_id}/papers/arXiv:2601.0001")
    assert rm.status_code == 204


def test_feedback_recorded(client):
    resp = client.post("/feedback", json={"arxiv_id": "arXiv:2601.0001", "action": "star"})
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


def test_zotero_status(client):
    resp = client.get("/zotero/status")
    assert resp.status_code == 200
    assert resp.json()["deeplink_supported"] is True


def test_zotero_deeplink(client):
    resp = client.post("/zotero/save", json={"arxiv_id": "arXiv:2601.0001", "mode": "deeplink"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "deeplink"
    assert resp.json()["deep_link"].startswith("zotero://")
