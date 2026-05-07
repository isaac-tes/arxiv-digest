from __future__ import annotations

from arxiv_digest import format_digest, format_markdown, summarize


def _entry(rank=1, title="A title", authors="A. Author", **overrides):
    base = {
        "rank": rank,
        "id": "arXiv:1",
        "title": title,
        "authors": authors,
        "link": "https://arxiv.org/abs/1",
        "subjects": "cond-mat.quant-gas",
        "section": "Thu, 4 Dec 2025",
        "summary": "First sentence. Second sentence.",
        "score": 12,
    }
    base.update(overrides)
    return base


def test_summarize_empty_returns_placeholder():
    assert summarize("") == "(No abstract available.)"
    assert summarize("   ") == "(No abstract available.)"


def test_summarize_collapses_whitespace():
    assert summarize("One\n  sentence.") == "One sentence."


def test_summarize_takes_first_two_sentences():
    assert summarize("One. Two. Three. Four.") == "One. Two."


def test_summarize_handles_single_sentence():
    assert summarize("Just one.") == "Just one."


def test_format_digest_includes_rank_title_authors():
    out = format_digest([_entry()], total_papers=10, requested_top=1)
    assert "1. A title" in out
    assert "A. Author" in out
    assert "Showing top 1" in out
    assert "Total papers fetched: 10" in out


def test_format_digest_shows_section_and_link():
    out = format_digest([_entry()], total_papers=5, requested_top=1)
    assert "Section: Thu, 4 Dec 2025" in out
    assert "https://arxiv.org/abs/1" in out


def test_format_digest_clamps_requested_top_to_available():
    out = format_digest([_entry()], total_papers=1, requested_top=999)
    assert "Showing top 1" in out


def test_format_markdown_header():
    out = format_markdown([_entry()], total_papers=3, requested_top=1)
    assert out.startswith("# Daily arXiv cond-mat/quant-ph digest")
    assert "## 1. A title" in out
    assert "**Authors:** A. Author" in out
    assert "**Link:** https://arxiv.org/abs/1" in out


def test_format_markdown_includes_subjects_when_present():
    out = format_markdown([_entry()], total_papers=1, requested_top=1)
    assert "**Subjects:** cond-mat.quant-gas" in out
