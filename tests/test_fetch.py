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
    # Bare id — the "arXiv:" display prefix must be stripped, since /abs/
    # rejects the prefixed form with HTTP 406.
    assert p["id"] == "2512.00001"
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
    assert arxiv_digest.fetch_abstract("2512.99999", retries=0) == ""


# ── Regressions for the "arXiv:"-prefixed id bug ─────────────────────────────
#
# arXiv renders the abstract link text as "arXiv:2512.00001" but /abs/ only
# accepts the bare id; the prefixed URL 406s. Because /pastweek pages carry no
# inline abstracts, every pastweek paper depended on that broken fetch and
# rendered "(No abstract available.)".


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("arXiv:2512.00001", "2512.00001"),
        ("arxiv:2512.00001", "2512.00001"),
        ("  arXiv: 2512.00001 ", "2512.00001"),
        ("2512.00001", "2512.00001"),
        ("cond-mat/0512001", "cond-mat/0512001"),
        ("", ""),
    ],
)
def test_normalize_arxiv_id(raw, expected):
    assert arxiv_digest.normalize_arxiv_id(raw) == expected


def test_fetch_abstract_rejects_prefixed_id_url(monkeypatch):
    """A prefixed id must still resolve: it is normalized before the request."""
    seen: list[str] = []

    def _get(url, *args, **kwargs):
        seen.append(url)
        if url != "https://arxiv.org/abs/2512.00001":
            return _MockResponse("", status_code=406)
        return _MockResponse(
            '<html><blockquote class="abstract">Abstract: real one.</blockquote></html>'
        )

    monkeypatch.setattr(arxiv_digest.requests, "get", _get)
    assert arxiv_digest.fetch_abstract("arXiv:2512.00001") == "real one."
    assert seen == ["https://arxiv.org/abs/2512.00001"]


def test_backfill_survives_strict_arxiv_406(monkeypatch, sample_feed_html):
    """End-to-end: a server that 406s the prefixed form still yields abstracts."""

    def _get(url, *args, **kwargs):
        if "/abs/" in url:
            if "arXiv:" in url or "arxiv:" in url:
                return _MockResponse("", status_code=406)
            return _MockResponse(
                '<html><blockquote class="abstract">Abstract: backfilled.</blockquote></html>'
            )
        return _MockResponse(sample_feed_html)

    monkeypatch.setattr(arxiv_digest.requests, "get", _get)
    papers = fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert all(p["abstract"] for p in papers)
    assert papers[1]["abstract"] == "backfilled."


def test_fetch_abstract_retries_transient_failure(monkeypatch):
    calls = {"n": 0}

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return _MockResponse(
            '<html><blockquote class="abstract">Abstract: second try.</blockquote></html>'
        )

    monkeypatch.setattr(arxiv_digest.requests, "get", _get)
    monkeypatch.setattr(arxiv_digest.time, "sleep", lambda _s: None)
    assert arxiv_digest.fetch_abstract("2512.00001") == "second try."
    assert calls["n"] == 2


def test_bulk_backfill_failure_warns_on_stderr(monkeypatch, capsys, sample_feed_html):
    def _get(url, *args, **kwargs):
        if "/abs/" in url:
            return _MockResponse("", status_code=406)
        return _MockResponse(sample_feed_html)

    monkeypatch.setattr(arxiv_digest.requests, "get", _get)
    monkeypatch.setattr(arxiv_digest.time, "sleep", lambda _s: None)
    fetch_feed("https://arxiv.org/list/cond-mat.quant-gas/pastweek")
    assert "could not be retrieved" in capsys.readouterr().err
