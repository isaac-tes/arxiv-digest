from __future__ import annotations

import pytest

import arxiv_digest
from arxiv_digest import fetch_feed, fetch_feeds


class _MockResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def mock_arxiv_get(monkeypatch, sample_feed_html):
    """Mock requests.get so list page returns sample_feed_html, abs pages return a stub."""

    def _get(url, *args, **kwargs):
        if "/abs/" in url:
            return _MockResponse(
                '<html><body><blockquote class="abstract">'
                "Abstract: stub abstract for back-fill."
                "</blockquote></body></html>"
            )
        return _MockResponse(sample_feed_html)

    monkeypatch.setattr(arxiv_digest.requests, "get", _get)
    return _get


def test_fetch_feed_parses_two_papers(mock_arxiv_get):
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert len(papers) == 2


def test_fetch_feed_extracts_title_and_authors(mock_arxiv_get):
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    p = papers[0]
    assert "Topological flat bands" in p["title"]
    assert "Bob Bloch" in p["authors"]
    assert p["id"] == "arXiv:2512.00001"
    assert p["link"] == "https://arxiv.org/abs/2512.00001"
    assert "cond-mat.quant-gas" in p["subjects"]


def test_fetch_feed_extracts_inline_abstract(mock_arxiv_get):
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert "Berry curvature" in papers[0]["abstract"]


def test_fetch_feed_backfills_missing_abstract(mock_arxiv_get):
    """Second paper in fixture has no <p class='mathjax'> — should trigger fetch_abstract."""
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert papers[1]["abstract"] == "stub abstract for back-fill."


def test_fetch_feed_carries_section_label(mock_arxiv_get):
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert papers[0]["section"] == "Thu, 4 Dec 2025"


def test_fetch_feeds_dedupes_by_id(mock_arxiv_get):
    """Two URLs returning the same papers → deduped output."""
    papers = fetch_feeds(
        [
            "https://arxiv.org/list/cond-mat.quant-gas/pastweek",
            "https://arxiv.org/list/cond-mat/pastweek",
        ]
    )
    assert len(papers) == 2
    ids = [p["id"] for p in papers]
    assert len(ids) == len(set(ids))


def test_fetch_abstract_returns_empty_on_network_error(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(arxiv_digest.requests, "get", _raise)
    assert arxiv_digest.fetch_abstract("2512.99999") == ""
