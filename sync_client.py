"""Sync the GUI's config and removed papers with a digest server.

The server (``server/``, docs/deploy.md) is the source of truth: the GUI
downloads from it at start and on request, and uploads on save. Whoever saved
last wins, as between two phones. Settings live in
``~/.arxiv_scraper/sync.json`` (private, 0600); ``ARXIV_DIGEST_SERVER`` /
``ARXIV_DIGEST_TOKEN`` override them.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

import arxiv_digest as ad

SETTINGS_PATH = Path.home() / ".arxiv_scraper" / "sync.json"
TIMEOUT = (5, 30)  # connect, read


class SyncError(Exception):
    """The server couldn't be reached or refused the request."""


BAD_REPLY = "The sync server sent an unexpected reply; check the server address."


@dataclass
class SyncSettings:
    server: str = ""
    token: str = ""
    # Set once the user chose "use server's" / "upload mine" on first connect.
    initialized: bool = False
    # Local changes the server hasn't got yet (saved offline): push before pulling.
    pending: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.server)


def load_settings() -> SyncSettings:
    try:
        raw = json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        raw = {}
    s = SyncSettings(
        server=str(raw.get("server", "")),
        token=str(raw.get("token", "")),
        initialized=bool(raw.get("initialized", False)),
        pending=bool(raw.get("pending", False)),
    )
    s.server = os.environ.get("ARXIV_DIGEST_SERVER", s.server)
    s.token = os.environ.get("ARXIV_DIGEST_TOKEN", s.token)
    s.server = s.server.strip().rstrip("/")
    return s


def save_settings(s: SyncSettings) -> None:
    """Write the settings readable by the owner only (the token is a secret)."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=SETTINGS_PATH.parent, prefix=".sync.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({**asdict(s), "server": s.server.strip().rstrip("/")}, fh, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class SyncClient:
    def __init__(self, settings: SyncSettings):
        self.base = settings.server.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.token}"} if settings.token else {}

    def _call(self, method: str, path: str, body: dict | None = None):
        try:
            resp = requests.request(method, f"{self.base}/{path}", headers=self.headers, json=body, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise SyncError(f"Can't reach the sync server ({type(exc).__name__}).") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            raise SyncError(str(detail) or f"Sync server error ({resp.status_code}).")
        try:
            return None if resp.status_code == 204 else resp.json()
        except ValueError as exc:  # e.g. a captive portal's HTML page
            raise SyncError(BAD_REPLY) from exc

    def get_config(self) -> ad.Config:
        try:
            return ad.Config.from_json(self._call("GET", "config")["data"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise SyncError(BAD_REPLY) from exc

    def put_config(self, cfg: ad.Config) -> None:
        self._call("PUT", "config", {"data": asdict(cfg)})

    def get_removed(self) -> set[str]:
        got = self._call("GET", "removed")
        if not isinstance(got, list):
            raise SyncError(BAD_REPLY)
        return set(got)

    def remove(self, arxiv_id: str) -> None:
        self._call("POST", "removed", {"arxiv_id": arxiv_id})

    def restore(self, arxiv_ids: list[str]) -> None:
        self._call("POST", "removed/restore", {"arxiv_ids": list(arxiv_ids)})
