from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def make_paper():
    def _make(
        *,
        id: str = "arXiv:2601.0001",
        title: str = "",
        abstract: str = "",
        authors: str = "",
        subjects: str = "",
        link: str = "",
        section: str = "",
    ) -> dict:
        return {
            "id": id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "subjects": subjects,
            "link": link,
            "section": section,
        }

    return _make


@pytest.fixture
def empty_cfg():
    """Config with empty keyword/author/low-priority lists — only weights defaults active."""
    from arxiv_digest import Config

    return Config(core_keywords=[], named_authors=[], low_priority_kw=[])


@pytest.fixture
def sample_feed_html():
    return (Path(__file__).parent / "fixtures" / "sample_feed.html").read_text()


@pytest.fixture(autouse=True)
def _offline_update_check(monkeypatch, tmp_path):
    """Keep the GitHub release check offline and out of ~/.arxiv_scraper in
    every test (the GUI and CLI both call it); tests that exercise it patch
    `urlopen` / `CACHE_PATH` themselves, which overrides this."""
    import update_check

    def offline(*a, **k):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(update_check, "CACHE_PATH", tmp_path / "update_check.json")
    monkeypatch.setattr(update_check.urllib.request, "urlopen", offline)


@pytest.fixture(autouse=True)
def _no_real_sync(monkeypatch, tmp_path):
    """Never read the user's ~/.arxiv_scraper/sync.json or sync env vars, so no
    test talks to a real digest server; sync tests set their own settings."""
    import sync_client

    monkeypatch.setattr(sync_client, "SETTINGS_PATH", tmp_path / "sync-settings.json")
    monkeypatch.delenv("ARXIV_DIGEST_SERVER", raising=False)
    monkeypatch.delenv("ARXIV_DIGEST_TOKEN", raising=False)
