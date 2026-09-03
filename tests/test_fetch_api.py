from __future__ import annotations

from datetime import datetime

import pytest

import arxiv_digest as ad

SAMPLE_API_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2608.16520v1</id>
    <published>2026-08-17T13:03:36Z</published>
    <title>Non-invertible Lattice 1-Form Symmetries</title>
    <summary>We study non-invertible symmetries.</summary>
    <author><name>Frank Pollmann</name></author>
    <category term="cond-mat.str-el"/>
    <category term="quant-ph"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2608.19180v1</id>
    <published>2026-08-19T10:00:00Z</published>
    <title>Electrostriction in a BEC</title>
    <summary>We study electrostriction.</summary>
    <author><name>Jane Doe</name></author>
    <category term="quant-ph"/>
  </entry>
</feed>
"""


class _MockResponse:
    def __init__(self, content: bytes = b"", status_code: int = 200, headers: dict | None = None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_paper_from_api_entry_builds_paper_dict():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(SAMPLE_API_FEED)
    entry = root.find("{http://www.w3.org/2005/Atom}entry")
    paper = ad._paper_from_api_entry(entry)
    assert paper["id"] == "2608.16520"
    assert paper["title"] == "Non-invertible Lattice 1-Form Symmetries"
    assert paper["authors"] == "Frank Pollmann"
    assert paper["subjects"] == "cond-mat.str-el, quant-ph"
    assert paper["link"] == "http://arxiv.org/abs/2608.16520"
    assert paper["section"] == "Mon, 17 Aug 2026"  # day label from published date


def test_fetch_feed_api_parses_entries_and_sets_day_labels(monkeypatch):
    calls = {}

    def _get(url, *args, **kwargs):
        calls["params"] = kwargs.get("params", {})
        return _MockResponse(content=SAMPLE_API_FEED.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    papers = ad.fetch_feed_api(
        "quant-ph",
        datetime(2026, 8, 14),
        datetime(2026, 8, 20),
    )
    assert len(papers) == 2
    assert papers[0]["id"] == "2608.16520"
    assert papers[0]["section"] == "Mon, 17 Aug 2026"
    assert papers[1]["section"] == "Wed, 19 Aug 2026"
    # The query uses a submittedDate range for a true 7-day window.
    q = calls["params"]["search_query"]
    assert "submittedDate:[202608140000 TO 202608200000]" in q
    assert "cat:quant-ph" in q


def test_fetch_feed_api_paginates(monkeypatch):
    """When totalResults > page size, it keeps fetching until all are collected."""
    import xml.etree.ElementTree as ET

    monkeypatch.setattr(ad.time, "sleep", lambda s: None)  # keep page pacing instant

    # Build a feed with totalResults=150 but only 100 entries per page.
    entries = "".join(
        f'<entry><id>http://arxiv.org/abs/2608.{10000+i}</id>'
        f'<published>2026-08-19T10:00:00Z</published>'
        f'<title>Paper {i}</title><summary>abs</summary>'
        f'<author><name>A</name></author><category term="quant-ph"/></entry>'
        for i in range(100)
    )
    feed = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        f'<opensearch:totalResults>150</opensearch:totalResults>{entries}</feed>'
    )
    starts = []

    def _get(url, *args, **kwargs):
        starts.append(kwargs.get("params", {}).get("start"))
        return _MockResponse(content=feed.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    papers = ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    # First page returns 100; second page returns the same 100 (mock), so it
    # stops once len(papers) >= total (150). Page size is 500, so the second
    # request advances start by 500.
    assert len(starts) >= 2
    assert starts[0] == 0
    assert starts[1] == 500


def test_fetch_feed_api_retries_read_timeout_then_succeeds(monkeypatch):
    """A transient ReadTimeout is retried with backoff, then the fetch succeeds."""
    sleeps: list[float] = []
    calls = {"n": 0}

    class _FakeReadTimeout(ad.requests.ReadTimeout):
        pass

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakeReadTimeout("Read timed out.")
        return _MockResponse(content=SAMPLE_API_FEED.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    monkeypatch.setattr(ad.time, "sleep", lambda s: sleeps.append(s))
    papers = ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    assert len(papers) == 2
    assert calls["n"] == 2
    # One retry happened, waiting the base backoff (1s).
    assert sleeps == [ad._ARXIV_RATE_LIMIT_SECONDS * 1]


def test_fetch_feed_api_raises_after_transport_retries_exhausted(monkeypatch):
    """Persistent timeouts are retried _MAX_API_RETRIES times, then re-raised."""
    monkeypatch.setattr(ad.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class _FakeReadTimeout(ad.requests.ReadTimeout):
        pass

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        raise _FakeReadTimeout("Read timed out.")

    monkeypatch.setattr(ad.requests, "get", _get)
    with pytest.raises(ad.requests.ReadTimeout):
        ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    assert calls["n"] == ad._MAX_API_RETRIES + 1


def test_fetch_feed_api_sends_user_agent(monkeypatch):
    """The export API call sends a descriptive User-Agent (arXiv asks for this)."""
    captured = {}

    def _get(url, *args, **kwargs):
        captured["headers"] = kwargs.get("headers", {})
        return _MockResponse(content=SAMPLE_API_FEED.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    assert captured["headers"]["User-Agent"].startswith("arxiv-digest")


def test_fetch_feed_api_retries_429_then_succeeds(monkeypatch):
    """A single 429 is retried (honoring Retry-After) and the fetch succeeds."""
    sleeps: list[float] = []
    calls = {"n": 0}

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _MockResponse(status_code=429, headers={"Retry-After": "2"})
        return _MockResponse(content=SAMPLE_API_FEED.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    monkeypatch.setattr(ad.time, "sleep", lambda s: sleeps.append(s))
    papers = ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    assert len(papers) == 2
    assert calls["n"] == 2
    # One retry happened, waiting the Retry-After (2s).
    assert sleeps == [2.0]


def test_fetch_feed_api_raises_after_retries_exhausted(monkeypatch):
    """Persistent 429 (or 5xx) is retried _MAX_API_RETRIES times, then raises."""
    monkeypatch.setattr(ad.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        return _MockResponse(status_code=503)

    monkeypatch.setattr(ad.requests, "get", _get)
    with pytest.raises(Exception):  # HTTPError after retries exhausted
        ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    assert calls["n"] == ad._MAX_API_RETRIES + 1


def test_fetch_feed_api_backs_off_exponentially_without_retry_after(monkeypatch):
    """Without a Retry-After header, backoff starts at the rate-limit interval."""
    sleeps: list[float] = []
    calls = {"n": 0}

    def _get(url, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            return _MockResponse(status_code=429)
        return _MockResponse(content=SAMPLE_API_FEED.encode("utf-8"))

    monkeypatch.setattr(ad.requests, "get", _get)
    monkeypatch.setattr(ad.time, "sleep", lambda s: sleeps.append(s))
    ad.fetch_feed_api("quant-ph", datetime(2026, 8, 14), datetime(2026, 8, 20))
    # attempt 0 -> 1s, attempt 1 -> 2s (exponential), then success on attempt 2.
    assert sleeps == [ad._ARXIV_RATE_LIMIT_SECONDS * 1, ad._ARXIV_RATE_LIMIT_SECONDS * 2]
