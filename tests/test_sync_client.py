"""Two-way sync between the GUI and a digest server (docs/deploy.md).

The server is the source of truth; `sync_client` is the GUI's HTTP side and
its settings (file + environment overrides).
"""
from __future__ import annotations

import json
import stat

import pytest
import requests

import sync_client as sc


class FakeResp:
    def __init__(self, status: int = 200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body

    @property
    def text(self):
        return json.dumps(self._body)


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "sync.json"
    monkeypatch.setattr(sc, "SETTINGS_PATH", path)
    monkeypatch.delenv("ARXIV_DIGEST_SERVER", raising=False)
    monkeypatch.delenv("ARXIV_DIGEST_TOKEN", raising=False)
    return path


def test_settings_roundtrip_private_file(settings_file):
    sc.save_settings(sc.SyncSettings(server="http://box:8000/", token="t0k", initialized=True))
    s = sc.load_settings()
    assert (s.server, s.token, s.initialized) == ("http://box:8000", "t0k", True)
    assert stat.S_IMODE(settings_file.stat().st_mode) == 0o600
    assert s.enabled


def test_env_overrides_file(settings_file, monkeypatch):
    sc.save_settings(sc.SyncSettings(server="http://file:8000", token="filetok"))
    monkeypatch.setenv("ARXIV_DIGEST_SERVER", "http://env:9000")
    monkeypatch.setenv("ARXIV_DIGEST_TOKEN", "envtok")
    s = sc.load_settings()
    assert (s.server, s.token) == ("http://env:9000", "envtok")


def test_disabled_without_server(settings_file):
    assert not sc.load_settings().enabled


def test_get_config_sends_token(monkeypatch):
    seen = {}

    def fake(method, url, headers=None, json=None, timeout=None):
        seen.update(method=method, url=url, auth=headers.get("Authorization"))
        return FakeResp(200, {"data": {"core_keywords": ["floquet"], "top_n": 7}})

    monkeypatch.setattr(sc.requests, "request", fake)
    client = sc.SyncClient(sc.SyncSettings(server="http://box:8000", token="t0k"))
    cfg = client.get_config()
    assert cfg.core_keywords == ["floquet"] and cfg.top_n == 7
    assert seen == {"method": "GET", "url": "http://box:8000/config", "auth": "Bearer t0k"}


def test_put_config_and_removed(monkeypatch):
    calls = []

    def fake(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url.rsplit("/", 2)[-2:], json))
        if url.endswith("/removed") and method == "GET":
            return FakeResp(200, ["2601.1"])
        return FakeResp(204 if "removed" in url else 200, {"data": json["data"]} if json and "data" in json else None)

    monkeypatch.setattr(sc.requests, "request", fake)
    import arxiv_digest as ad

    client = sc.SyncClient(sc.SyncSettings(server="http://box:8000"))
    client.put_config(ad.Config(core_keywords=["anyon"]))
    assert calls[-1][0] == "PUT" and calls[-1][2]["data"]["core_keywords"] == ["anyon"]
    assert client.get_removed() == {"2601.1"}
    client.remove("2601.2")
    assert calls[-1][:1] == ("POST",) and calls[-1][2] == {"arxiv_id": "2601.2"}
    client.restore(["2601.1"])
    assert calls[-1][2] == {"arxiv_ids": ["2601.1"]}


def test_errors_become_syncerror(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(sc.requests, "request", boom)
    with pytest.raises(sc.SyncError, match="Can't reach"):
        sc.SyncClient(sc.SyncSettings(server="http://box:8000")).get_config()

    monkeypatch.setattr(sc.requests, "request", lambda *a, **k: FakeResp(401, {"detail": "Missing or wrong access token."}))
    with pytest.raises(sc.SyncError, match="access token"):
        sc.SyncClient(sc.SyncSettings(server="http://box:8000")).get_config()


class HtmlResp(FakeResp):
    def json(self):
        raise ValueError("not JSON")


@pytest.mark.parametrize("resp", [HtmlResp(200), FakeResp(200, {"no": "data"}), FakeResp(200, ["a list"])])
def test_unexpected_reply_becomes_syncerror(monkeypatch, resp):
    """A captive portal or the wrong host answering 200 must not crash the GUI."""
    monkeypatch.setattr(sc.requests, "request", lambda *a, **k: resp)
    client = sc.SyncClient(sc.SyncSettings(server="http://box:8000"))
    with pytest.raises(sc.SyncError, match="unexpected reply"):
        client.get_config()


def test_unexpected_removed_reply_becomes_syncerror(monkeypatch):
    monkeypatch.setattr(sc.requests, "request", lambda *a, **k: HtmlResp(200))
    with pytest.raises(sc.SyncError, match="unexpected reply"):
        sc.SyncClient(sc.SyncSettings(server="http://box:8000")).get_removed()


def test_pending_flag_roundtrips(settings_file):
    sc.save_settings(sc.SyncSettings(server="http://box:8000", initialized=True, pending=True))
    assert sc.load_settings().pending


# ── GUI wiring (AppTest, fake in-memory server) ───────────────────────────────


@pytest.fixture
def fake_server(monkeypatch, tmp_path):
    """A dict-backed digest server behind sync_client.requests.request."""
    from dataclasses import asdict

    import arxiv_digest as ad

    state = {"config": {**asdict(ad.Config()), "core_keywords": ["from-server"]}, "removed": ["2601.0009"],
             "down": False}

    def fake(method, url, headers=None, json=None, timeout=None):
        path = url.split("8000/", 1)[1]
        if state["down"]:
            raise requests.ConnectionError("down")
        if headers.get("Authorization") != "Bearer tok":
            return FakeResp(401, {"detail": "Missing or wrong access token."})
        if (method, path) == ("GET", "config"):
            return FakeResp(200, {"data": state["config"]})
        if (method, path) == ("PUT", "config"):
            state["config"] = json["data"]
            return FakeResp(200, {"data": json["data"]})
        if (method, path) == ("GET", "removed"):
            return FakeResp(200, list(state["removed"]))
        if (method, path) == ("POST", "removed"):
            state["removed"].append(json["arxiv_id"])
            return FakeResp(204)
        if (method, path) == ("POST", "removed/restore"):
            state["removed"] = [i for i in state["removed"] if i not in json["arxiv_ids"]]
            return FakeResp(204)
        return FakeResp(404, {"detail": "Not found"})

    monkeypatch.setattr(sc.requests, "request", fake)
    monkeypatch.setattr(sc, "SETTINGS_PATH", tmp_path / "sync.json")
    # AppTest re-executes arxiv_gui.py, so its module constants are recomputed
    # from Path.home() and ad.DEFAULT_CONFIG_PATH: patch those (never real files).
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ad, "DEFAULT_CONFIG_PATH", tmp_path / "arxiv_config.json")
    monkeypatch.delenv("ARXIV_DIGEST_SERVER", raising=False)
    monkeypatch.delenv("ARXIV_DIGEST_TOKEN", raising=False)
    state["paths"] = {
        "config": tmp_path / "arxiv_config.json",
        "removed": tmp_path / ".arxiv_scraper" / "removed_papers.json",
    }
    return state


def _app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file("arxiv_gui.py")


def test_gui_sync_off_by_default(fake_server):
    at = _app().run(timeout=15)
    assert "from-server" not in at.session_state["cfg"].core_keywords


def test_gui_first_connect_use_servers(fake_server):
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok"))
    at = _app().run(timeout=15)
    at.button(key="sync_use_server").click().run(timeout=15)
    assert at.session_state["cfg"].core_keywords == ["from-server"]
    assert sc.load_settings().initialized
    # Local offline copy written, removals pulled down.
    assert json.loads(fake_server["paths"]["config"].read_text())["core_keywords"] == ["from-server"]
    assert json.loads(fake_server["paths"]["removed"].read_text()) == ["2601.0009"]


def test_gui_upload_mine_and_save_to_server(fake_server):
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok"))
    at = _app().run(timeout=15)
    at.session_state["cfg"].core_keywords = ["mine"]
    at.button(key="sync_upload_mine").click().run(timeout=15)
    assert fake_server["config"]["core_keywords"] == ["mine"]
    at.session_state["cfg"].core_keywords = ["mine", "edited"]
    at.button(key="sync_up").click().run(timeout=15)
    assert fake_server["config"]["core_keywords"] == ["mine", "edited"]


def test_gui_starts_from_server_when_synced(fake_server):
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok", initialized=True))
    at = _app().run(timeout=15)
    assert at.session_state["cfg"].core_keywords == ["from-server"]


def test_gui_offline_keeps_local_copy(fake_server):
    fake_server["paths"]["config"].write_text(json.dumps({"core_keywords": ["local-copy"]}))
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="WRONG", initialized=True))
    at = _app().run(timeout=15)
    assert at.session_state["cfg"].core_keywords == ["local-copy"]
    assert any("Offline" in w.value for w in at.sidebar.warning)


def test_gui_offline_save_is_pushed_next_session(fake_server):
    """A save while the server is down is not lost: the next session pushes it first."""
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok", initialized=True))
    fake_server["down"] = True
    at = _app().run(timeout=15)
    at.session_state["cfg"].core_keywords = ["offline-edit"]
    at.button(key="sync_up").click().run(timeout=15)
    assert sc.load_settings().pending
    # The paper removed offline went to the local list only.
    fake_server["paths"]["removed"].parent.mkdir(parents=True, exist_ok=True)
    fake_server["paths"]["removed"].write_text(json.dumps(["2601.0042"]))
    fake_server["paths"]["config"].write_text(json.dumps({"core_keywords": ["offline-edit"]}))

    fake_server["down"] = False
    at = _app().run(timeout=15)
    assert at.session_state["cfg"].core_keywords == ["offline-edit"]
    assert fake_server["config"]["core_keywords"] == ["offline-edit"]
    assert fake_server["removed"] == ["2601.0042"]
    assert json.loads(fake_server["paths"]["removed"].read_text()) == ["2601.0042"]
    assert not sc.load_settings().pending


def test_gui_upload_mine_offline_finishes_later(fake_server):
    """'Upload mine' that can't reach the server stays decided and retries, never half-applies."""
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok"))
    fake_server["paths"]["config"].write_text(json.dumps({"core_keywords": ["mine"]}))
    fake_server["down"] = True
    at = _app().run(timeout=15)
    at.button(key="sync_upload_mine").click().run(timeout=15)
    s = sc.load_settings()
    assert s.initialized and s.pending
    assert any("Offline" in w.value for w in at.sidebar.warning)

    fake_server["down"] = False
    _app().run(timeout=15)
    assert fake_server["config"]["core_keywords"] == ["mine"]
    assert fake_server["removed"] == []
    assert not sc.load_settings().pending


def test_gui_bad_server_reply_does_not_crash(fake_server, monkeypatch):
    monkeypatch.setattr(sc.requests, "request", lambda *a, **k: HtmlResp(200))
    sc.save_settings(sc.SyncSettings(server="http://box:8000", token="tok", initialized=True))
    at = _app().run(timeout=15)
    assert not at.exception
    assert any("unexpected reply" in w.value for w in at.sidebar.warning)
