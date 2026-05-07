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
