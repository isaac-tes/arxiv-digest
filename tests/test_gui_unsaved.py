"""Unsaved-changes marks, tab Save buttons that persist, and the card's Open PDF."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import arxiv_digest as ad

TIMEOUT = 25


def _paper(pid="2601.00001", authors="Zed Quill", link=""):
    return {"id": pid, "title": "Paper", "authors": authors, "subjects": "physics.optics",
            "abstract": "x" * 50, "link": link, "section": "New submissions (showing 1 of 1 entries)"}


def _app(papers=()):
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = list(papers)
    return at.run(timeout=TIMEOUT)


def _markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _click(at, label):
    next(b for b in at.button if b.label == label).click()
    return at.run(timeout=TIMEOUT)


def _add_author(at):
    next(b for b in at.button if (b.key or "").startswith("add_author_card_")).click()
    return at.run(timeout=TIMEOUT)


# ── pure helpers ──────────────────────────────────────────────────────────

def test_unsaved_changes_are_grouped_by_tab_with_entries():
    import arxiv_gui

    saved = ad.Config()
    cur = copy.deepcopy(saved)
    cur.named_authors.append("Zed Quill")
    cur.top_n = saved.top_n + 7
    cur.weights.core_keyword = saved.weights.core_keyword + 1
    cur.feeds["new-feed"] = "https://arxiv.org/list/new-feed/new"

    changes = arxiv_gui._unsaved_changes(saved, cur)

    assert changes["Authors"] == ["+ Zed Quill"]
    assert changes["Sidebar"] == [f"top n: {saved.top_n} → {saved.top_n + 7}"]
    assert changes["Scoring"] == [
        f"core keyword: {saved.weights.core_keyword} → {saved.weights.core_keyword + 1}"
    ]
    assert changes["Feeds"] == ["+ new-feed"]
    assert arxiv_gui._unsaved_changes(saved, copy.deepcopy(saved)) == {}


def test_tab_marker_css_marks_only_real_tabs_by_position():
    import arxiv_gui

    css = arxiv_gui._tab_marker_css(["Authors", "Sidebar"])
    assert f"nth-of-type({arxiv_gui._TAB_LABELS.index('Authors') + 1})" in css
    assert css.count("nth-of-type") == 1  # 'Sidebar' is not a tab
    assert arxiv_gui._tab_marker_css([]) == ""


# ── unsaved bar ───────────────────────────────────────────────────────────

def test_add_author_shows_bar_with_tab_and_entry_then_discard_restores():
    at = _add_author(_app([_paper()]))

    text = _markdown(at)
    assert "Unsaved changes" in text
    assert "Authors:" in text and "+ Zed Quill" in text
    assert "Unsaved here:" in text  # the Authors tab's own note

    at = _click(at, "Discard")
    assert "Zed Quill" not in at.session_state.cfg.named_authors
    assert "Unsaved changes" not in _markdown(at)


def test_bar_save_writes_project_config_and_clears_bar():
    at = _add_author(_app([_paper()]))
    at = _click(at, "Write project config")

    written = json.loads(ad.DEFAULT_CONFIG_PATH.read_text())
    assert "Zed Quill" in written["named_authors"]
    assert "Unsaved changes" not in _markdown(at)


# ── tab Save buttons persist ──────────────────────────────────────────────

def test_list_save_writes_project_config_without_profile():
    at = _app()
    _click(at, "Save core keywords")
    assert json.loads(ad.DEFAULT_CONFIG_PATH.read_text())["core_keywords"] == ad.Config().core_keywords


def test_list_save_writes_the_loaded_profile():
    root = Path.home() / ".arxiv_scraper"
    profile = root / "profiles" / "mine.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"core_keywords": ["only-this"]}))
    (root / "active_profile.txt").write_text("mine")

    _click(_app(), "Save core keywords")

    saved = json.loads(profile.read_text())
    assert saved["core_keywords"] == ["only-this"]
    assert "weights" in saved  # rewritten as a full config, i.e. Save hit the profile
    assert not ad.DEFAULT_CONFIG_PATH.exists()


# ── card actions ──────────────────────────────────────────────────────────

def test_card_open_pdf_links_to_the_pdf_page():
    at = _app([_paper(link="https://arxiv.org/abs/2601.00001")])
    urls = [lb.proto.url for lb in at.get("link_button")]
    assert urls == ["https://arxiv.org/pdf/2601.00001"]


def test_card_without_arxiv_link_has_no_pdf_button():
    assert not list(_app([_paper(link="")]).get("link_button"))


def _load_profile(name="mine", **content):
    root = Path.home() / ".arxiv_scraper"
    profile = root / "profiles" / f"{name}.json"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps(content))
    (root / "active_profile.txt").write_text(name)
    return profile


def test_tab_save_does_not_write_other_unsaved_edits():
    """Save core keywords writes keywords only; an unsaved Add author stays unsaved."""
    at = _add_author(_app([_paper()]))
    at = _click(at, "Save core keywords")

    written = json.loads(ad.DEFAULT_CONFIG_PATH.read_text())
    assert "Zed Quill" not in written["named_authors"]
    assert "Zed Quill" in at.session_state.cfg.named_authors
    assert "+ Zed Quill" in _markdown(at)  # still listed in the bar


def test_apply_weights_writes_the_loaded_profile():
    profile = _load_profile()
    at = _app()
    box = next(n for n in at.number_input if n.key == "weight_core_keyword")
    box.set_value(box.value + 3).run(timeout=TIMEOUT)
    _click(at, "Apply weights")

    assert json.loads(profile.read_text())["weights"]["core_keyword"] == ad.ScoringWeights().core_keyword + 3


def test_save_feeds_writes_the_loaded_profile():
    profile = _load_profile(feeds={"quant-ph": "https://arxiv.org/list/quant-ph/new"})
    _click(_app(), "Save feeds")

    assert json.loads(profile.read_text())["feeds"] == {"quant-ph": "https://arxiv.org/list/quant-ph/new"}
    assert "weights" in json.loads(profile.read_text())  # rewritten by the Save


def test_preset_load_compares_against_the_project_config():
    """Load preset unloads the profile, so the bar diffs against what Save will overwrite."""
    project = ad.Config(named_authors=["Proj Author"])
    project.dump(ad.DEFAULT_CONFIG_PATH)
    _load_profile(named_authors=["Profile Author"])

    at = _click(_app(), "Load preset")

    assert at.session_state.saved_cfg.named_authors == ["Proj Author"]


def test_unloading_profile_survives_a_broken_project_config():
    _load_profile()
    ad.DEFAULT_CONFIG_PATH.write_text("{ broken")

    at = _click(_app(), "Load preset")

    assert not list(at.exception)


def test_padded_entry_is_not_reported_as_unsaved():
    ad.Config(core_keywords=[" mpo", "ising"]).dump(ad.DEFAULT_CONFIG_PATH)
    assert "Not saved yet" not in _markdown(_app())


def test_empty_new_row_cells_are_dropped_not_saved_as_none():
    """A row added in the table arrives as None/NaN; it must not become the text 'None'."""
    import arxiv_gui

    assert [arxiv_gui._cell_text(v) for v in (" mpo ", None, float("nan"), "")] == ["mpo", "", "", ""]


def test_table_marks_unsaved_rows():
    """The Authors table puts ● on the row added by Add author, and only there."""
    at = _add_author(_app([_paper()]))
    table = next(d.value for d in at.get("dataframe") if d.key == "editor_named_authors")

    marked = table.loc[table["unsaved"] == "●", "Highlighted authors"].tolist()
    assert marked == ["Zed Quill"]
