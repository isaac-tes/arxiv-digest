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


def test_summarize_does_not_split_citations_or_abbreviations():
    text = (
        "A recent experiment by Roy et al. (Nat. Commun. 17, 2853 (2026)) demonstrated a plateau. "
        "We prove a theorem. The corollary is an impossibility statement."
    )
    assert summarize(text) == (
        "A recent experiment by Roy et al. (Nat. Commun. 17, 2853 (2026)) demonstrated a plateau. "
        "We prove a theorem."
    )
    assert summarize("As shown in Fig. 2 and Eq. 3, it works. Then more. And more.") == (
        "As shown in Fig. 2 and Eq. 3, it works. Then more."
    )
    assert summarize("We use e.g. DMRG here. Second one. Third.") == "We use e.g. DMRG here. Second one."


def test_summarize_unbalanced_paren_does_not_swallow_abstract():
    assert summarize("Unbalanced (paren. Still one. Two. Three.") == "Unbalanced (paren. Still one."


def test_summarize_still_splits_on_lowercase_free_starts():
    # Sentences may start with digits or math, not only capitals.
    assert summarize("One works. 2D materials follow. Three.") == "One works. 2D materials follow."
    assert summarize("Intro here. $\\nu=1$ states appear. More.") == "Intro here. $\\nu=1$ states appear."


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
