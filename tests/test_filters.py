"""Tests for submission-type and day filtering (arxiv_scraper_cli-dl4 / -amq)."""
from __future__ import annotations

from arxiv_digest import (
    available_day_labels,
    filter_papers,
    section_category,
    section_day_label,
)

NEW = "New submissions (showing 67 of 67 entries)"
CROSS = "Cross submissions (showing 21 of 21 entries)"
REPL = "Replacement submissions (showing 43 of 43 entries)"
DAY1 = "Fri, 19 Jun 2026 (showing 88 of 88 entries )"
DAY2 = "Thu, 18 Jun 2026 (showing 65 of 65 entries )"


def _p(section, id="x"):
    return {"id": id, "title": "t", "abstract": "", "authors": "", "subjects": "", "section": section}


# ── section_category ──
def test_section_category_classifies_new_cross_replacement():
    assert section_category(NEW) == "new"
    assert section_category(CROSS) == "cross"
    assert section_category(REPL) == "replacement"
    assert section_category(DAY1) == "other"
    assert section_category("") == "other"


# ── section_day_label ──
def test_section_day_label_extracts_date_only_for_date_sections():
    assert section_day_label(DAY1) == "Fri, 19 Jun 2026"
    assert section_day_label(DAY2) == "Thu, 18 Jun 2026"
    assert section_day_label(NEW) is None
    assert section_day_label(REPL) is None
    assert section_day_label("") is None


# ── replacement filtering (B) ──
def test_filter_papers_hides_replacements_by_default():
    papers = [_p(NEW, "a"), _p(CROSS, "b"), _p(REPL, "c")]
    kept = filter_papers(papers)
    ids = {p["id"] for p in kept}
    assert ids == {"a", "b"}  # cross kept, replacement dropped


def test_filter_papers_includes_replacements_when_requested():
    papers = [_p(NEW, "a"), _p(CROSS, "b"), _p(REPL, "c")]
    kept = filter_papers(papers, include_replacements=True)
    assert {p["id"] for p in kept} == {"a", "b", "c"}


# ── day filtering (D) ──
def test_filter_papers_by_day_keeps_only_selected_day():
    papers = [_p(DAY1, "a"), _p(DAY2, "b")]
    kept = filter_papers(papers, days=["Fri, 19 Jun 2026"])
    assert {p["id"] for p in kept} == {"a"}


def test_available_day_labels_sorted_unique_dates_only():
    papers = [_p(DAY2, "a"), _p(DAY1, "b"), _p(NEW, "c"), _p(DAY1, "d")]
    labels = available_day_labels(papers)
    assert labels == ["Thu, 18 Jun 2026", "Fri, 19 Jun 2026"]  # chronological
