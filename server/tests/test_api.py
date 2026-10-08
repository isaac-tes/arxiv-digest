"""Tests for the digest service API.

Uses a temporary SQLite DB and FastAPI's TestClient (set up in conftest.py).
No network calls hit arXiv.
"""

from __future__ import annotations


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


def test_zotero_status(client):
    resp = client.get("/zotero/status")
    assert resp.status_code == 200
    assert resp.json() == {"web_api_available": False}


def test_zotero_deeplink_mode_removed(client):
    # The zotero://select link could not create an item (ADR 0005 amendment).
    resp = client.post("/zotero/save", json={"arxiv_id": "arXiv:2601.0001", "mode": "deeplink"})
    assert resp.status_code == 422


def test_zotero_web_without_key_is_503(client):
    resp = client.post("/zotero/save", json={"arxiv_id": "2601.0001"})
    assert resp.status_code == 503


def test_zotero_creators_first_last():
    from app.routers.zotero import _creators

    assert _creators("Ada Q. Lovelace, Plato, Grace Hopper") == [
        {"creatorType": "author", "firstName": "Ada Q.", "lastName": "Lovelace"},
        {"creatorType": "author", "lastName": "Plato"},
        {"creatorType": "author", "firstName": "Grace", "lastName": "Hopper"},
    ]
