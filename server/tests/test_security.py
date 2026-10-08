"""Access control and request hardening for the shared digest service.

Local mode has no user accounts, so the server guards itself:
- with DIGEST_ACCESS_TOKEN set, every request except /health needs
  `Authorization: Bearer <token>`;
- without it, only this machine may call it (loopback client *and* a
  localhost Host header, which also blocks DNS rebinding);
- no CORS by default, so web pages can't drive a server on localhost;
- feed URLs must point at arXiv (no fetching arbitrary/internal URLs);
- remote mode refuses the default JWT secret.
"""

from __future__ import annotations

import pytest
from conftest import TEST_TOKEN
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.security import is_arxiv_url
from app.settings import Settings, get_settings


@pytest.fixture
def settings(monkeypatch):
    """Swap the cached settings for one test; returns a mutable copy."""
    s = get_settings().model_copy()
    monkeypatch.setattr("app.security.get_settings", lambda: s)
    return s


def _client(host: str = "testserver", client_host: str = "testclient", headers=None) -> TestClient:
    return TestClient(app, base_url=f"http://{host}", client=(client_host, 50000), headers=headers or {})


def test_token_required_when_configured(settings):
    settings.access_token = TEST_TOKEN
    c = _client()
    assert c.get("/config").status_code == 401
    assert c.get("/config", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/config", headers={"Authorization": f"Bearer {TEST_TOKEN}"}).status_code == 200


def test_health_is_open(settings):
    settings.access_token = TEST_TOKEN
    assert _client().get("/health").status_code == 200


def test_without_token_only_localhost(settings):
    settings.access_token = ""
    assert _client(host="127.0.0.1:8000", client_host="127.0.0.1").get("/config").status_code == 200
    assert _client(host="localhost:8000", client_host="::1").get("/config").status_code == 200
    # Another device on the network.
    assert _client(host="192.168.1.20:8000", client_host="192.168.1.30").get("/config").status_code == 403
    # DNS rebinding: a page on evil.example resolved to 127.0.0.1.
    assert _client(host="evil.example:8000", client_host="127.0.0.1").get("/config").status_code == 403


def test_no_cors_by_default():
    headers = {"Authorization": f"Bearer {TEST_TOKEN}", "Origin": "https://evil.example"}
    resp = _client(headers=headers).get("/config")
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


def test_is_arxiv_url():
    assert is_arxiv_url("https://arxiv.org/list/quant-ph/new")
    assert is_arxiv_url("http://export.arxiv.org/api/query")
    assert not is_arxiv_url("http://169.254.169.254/latest/meta-data")
    assert not is_arxiv_url("https://arxiv.org.evil.example/list")
    assert not is_arxiv_url("file:///etc/passwd")


def test_config_rejects_non_arxiv_feed_url(client):
    bad = {"feeds": {"quant-ph": "http://169.254.169.254/x"}, "default_feeds": ["quant-ph"]}
    assert client.put("/config", json={"data": bad}).status_code == 422


def test_digest_ignores_non_arxiv_feed_param(client, monkeypatch):
    import arxiv_digest as ad

    fetched: list = []
    monkeypatch.setattr(ad, "fetch_feeds", lambda urls, **k: fetched.extend(urls) or [])
    monkeypatch.setattr(ad, "fetch_pastweek", lambda *a, **k: [])
    client.get("/digest", params={"timeframe": "today", "feeds": "http://10.0.0.1/admin", "refresh": "true"})
    assert not any("10.0.0.1" in u for u in fetched)


def test_config_caps_feed_count(client):
    many = {f"quant-ph.x{i}": f"https://arxiv.org/list/quant-ph{i}/new" for i in range(60)}
    resp = client.put("/config", json={"data": {"feeds": many, "default_feeds": list(many)}})
    assert resp.status_code == 422


def test_remote_mode_refuses_default_jwt_secret(monkeypatch):
    s = Settings(mode="remote", jwt_secret="dev-secret-change-me")
    monkeypatch.setattr("app.main.get_settings", lambda: s)
    with pytest.raises(RuntimeError, match="DIGEST_JWT_SECRET"):
        create_app()
