"""Shared fixtures: a temp SQLite DB and a TestClient for the digest service."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Repo root so arxiv_digest.py / zotero_bridge.py are importable.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Point the server at a temp SQLite DB before importing the app.
_tmpdir = tempfile.mkdtemp(prefix="digest-test-")
os.environ["DIGEST_DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["DIGEST_MODE"] = "local"
os.environ.pop("DIGEST_DEFAULT_CONFIG_PATH", None)
# The shared client authenticates with an access token (the server refuses
# token-less requests from anywhere but this machine; see test_security.py).
TEST_TOKEN = "test-access-token"
os.environ["DIGEST_ACCESS_TOKEN"] = TEST_TOKEN
os.environ.pop("DIGEST_CORS_ORIGINS", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"}) as c:
        yield c
