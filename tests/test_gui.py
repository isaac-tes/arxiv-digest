"""Smoke tests for the Streamlit GUI.

Uses streamlit.testing.v1.AppTest to render the app server-side without a
browser. We don't exercise network-dependent buttons (Fetch papers); we just
confirm every tab mounts without raising.
"""
from __future__ import annotations

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1", reason="Streamlit not installed")


def test_gui_initial_render_has_no_exceptions():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    assert not list(at.exception), f"Unexpected exception(s): {list(at.exception)}"


def test_gui_has_eight_tabs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    assert len(at.tabs) == 8


def test_gui_sidebar_has_fetch_button():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    labels = [b.label for b in at.sidebar.button]
    assert "Fetch papers" in labels


def test_authors_html_highlights_named_authors():
    import arxiv_gui

    out = arxiv_gui._authors_html("Immanuel Bloch, Alice Smith", ["bloch"], 6)
    assert "hl-author" in out
    assert "Immanuel Bloch" in out
    assert "Alice Smith" in out
    # only the named one is wrapped
    assert out.count("hl-author") == 1
    assert "+6 to score" in out


def test_highlight_terms_wraps_keyword_and_low_priority():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "A topological film study", ["topological"], ["film"], 6, -5
    )
    assert "hl-term" in out and "core keyword (+6)" in out
    assert "hl-term" in out and "low-priority term (-5)" in out
    assert "topological" in out and "film" in out
    # keyword and low-priority use their per-aspect colors inline
    assert "#388bfd" in out  # keyword color
    assert "#f85149" in out  # low-priority color


def test_highlight_terms_no_match_is_plain_escaped():
    import arxiv_gui

    assert arxiv_gui._highlight_terms("plain <x> text", ["zzz"], [], 6, -5) == "plain &lt;x&gt; text"


def test_highlight_terms_case_insensitive_and_escapes():
    import arxiv_gui

    out = arxiv_gui._highlight_terms("Bloch & TOPOLOGY", ["topology"], [], 6, -5)
    assert "hl-term" in out
    assert "&amp;" in out  # escaped ampersand


def test_highlight_terms_overlap_no_nested_spans():
    import arxiv_gui

    # "spin" and "spin chain" overlap; longest-first should win, single span.
    out = arxiv_gui._highlight_terms("a spin chain", ["spin chain", "spin"], [], 6, -5)
    assert out.count('<span class="hl-term') == 1


def test_authors_html_escapes_and_handles_empty():
    import arxiv_gui

    assert arxiv_gui._authors_html("", [], 6) == "(No authors listed)"
    out = arxiv_gui._authors_html("A <b>x</b>, B", [], 6)
    assert "&lt;b&gt;" in out  # escaped


def test_highlight_subjects_wraps_matched_feed_names():
    import arxiv_gui

    out = arxiv_gui._highlight_subjects(
        "cond-mat.quant-gas (Quantum Gases); quant-ph (Quantum Physics)",
        {"cond-mat.quant-gas": 4, "quant-ph": 2},
    )
    assert "hl-subject" in out
    assert "subject bonus (+4)" in out
    assert "subject bonus (+2)" in out
    assert "Quantum Gases" in out


def test_highlight_subjects_no_match_is_plain():
    import arxiv_gui

    out = arxiv_gui._highlight_subjects("Mathematics", {"quant-ph": 2})
    assert "hl-subject" not in out
    assert out == "Mathematics"


def test_highlight_subjects_empty():
    import arxiv_gui

    assert arxiv_gui._highlight_subjects("", {"quant-ph": 2}) == ""


def test_highlight_terms_uses_custom_colors():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "topological film", ["topological"], ["film"], 6, -5,
        color_kw="#111111", color_lp="#222222",
    )
    assert "#111111" in out
    assert "#222222" in out


def test_authors_html_uses_custom_color():
    import arxiv_gui

    out = arxiv_gui._authors_html("Immanuel Bloch", ["bloch"], 6, color="#abcdef")
    assert "#abcdef" in out


def test_highlight_terms_font_color_when_enabled():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "topological", ["topological"], [], 6, -5, color_kw="#111111", font_kw=True
    )
    assert ";color:#111111" in out


def test_highlight_terms_no_font_color_by_default():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "topological", ["topological"], [], 6, -5, color_kw="#111111"
    )
    assert ";color:#111111" not in out


def test_authors_html_font_off_removes_color():
    import arxiv_gui

    out = arxiv_gui._authors_html("Immanuel Bloch", ["bloch"], 6, color="#abcdef", font=False)
    assert ";color:#abcdef" not in out


def test_highlight_subjects_font_color_when_enabled():
    import arxiv_gui

    out = arxiv_gui._highlight_subjects(
        "quant-ph (Quantum Physics)", {"quant-ph": 2}, color="#a371f7", font=True
    )
    assert ";color:#a371f7" in out


def test_absence_reason_deterministic_date_and_category(monkeypatch):
    import xml.etree.ElementTree as ET

    import arxiv_digest as ad
    import arxiv_gui
    import zotero_bridge as zb

    atom = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2608.16520</id>
        <published>2026-08-17T13:03:36Z</published>
        <title>Test</title>
        <summary>Abstract</summary>
        <category term="cond-mat.str-el"/>
        <category term="quant-ph"/>
      </entry>
    </feed>"""
    entry = ET.fromstring(atom).find("{http://www.w3.org/2005/Atom}entry")
    monkeypatch.setattr(zb, "fetch_arxiv_atom", lambda _id: entry)

    fetched = [
        {"id": "x1", "section": "Mon, 18 Aug 2026 (showing 88 of 88 entries )"},
        {"id": "x2", "section": "Tue, 19 Aug 2026 (showing 88 of 88 entries )"},
    ]
    cfg = ad.Config.load(None)
    cfg.feeds = {"cond-mat.quant-gas": "x", "quant-ph": "x"}

    out = arxiv_gui._absence_reason("2608.16520", fetched, cfg)
    assert "2026-08-17" in out
    assert "2026-08-18" in out
    assert "overlap your subscribed feeds" in out


def test_absence_reason_fetched_but_below_topn():
    import arxiv_digest as ad
    import arxiv_gui

    fetched = [{"id": "2608.16520", "section": "Mon, 18 Aug 2026"}]
    cfg = ad.Config.load(None)
    cfg.top_n = 5
    out = arxiv_gui._absence_reason("2608.16520", fetched, cfg)
    assert "**was** fetched" in out
    assert "top-5" in out


def test_scoring_tab_has_per_feed_weight_field():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    keys = {ni.key for ni in at.number_input if ni.key}
    # 'cond-mat' is a default feed and not a builtin subject -> gets a fw_ field
    assert "fw_cond-mat" in keys


def test_gui_sidebar_has_replacement_toggle():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    labels = [c.label for c in at.sidebar.checkbox]
    assert "Include replacement submissions" in labels


def test_gui_sidebar_has_three_highlight_toggles():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    labels = {c.label for c in at.sidebar.checkbox}
    assert {"Highlight authors", "Highlight keywords in titles",
            "Highlight keywords in abstracts"} <= labels


def test_gui_papers_tab_filters_replacements_and_offers_day_picker():
    """With pastweek + replacement papers loaded, the day picker appears and the
    replacement is hidden by default (arxiv_scraper_cli-dl4 / -amq)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [
        {"id": "n1", "title": "New paper", "authors": "A", "subjects": "quant-ph",
         "abstract": "x" * 50, "link": "", "section": "Fri, 19 Jun 2026 (showing 2 of 2 entries )"},
        {"id": "n2", "title": "Older paper", "authors": "B", "subjects": "quant-ph",
         "abstract": "y" * 50, "link": "", "section": "Thu, 18 Jun 2026 (showing 1 of 1 entries )"},
        {"id": "r1", "title": "Replaced paper", "authors": "C", "subjects": "quant-ph",
         "abstract": "z" * 50, "link": "", "section": "Replacement submissions (showing 1 of 1 entries)"},
    ]
    at.run(timeout=15)
    assert not list(at.exception)
    # Day picker present with both days
    day_pickers = [s for s in at.selectbox if s.label == "Day"]
    assert day_pickers, "expected a Day selectbox"
    assert "Fri, 19 Jun 2026" in day_pickers[0].options


def test_abstract_bonus_uses_css_tooltip_not_title_attr():
    """Streamlit strips `title`, so the hover must be a CSS .tip/.tip-text span."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [
        {"id": "1", "title": "T", "authors": "A", "subjects": "quant-ph",
         "abstract": "long " * 100, "link": "", "section": "New submissions (showing 1 of 1 entries)"},
    ]
    at.run(timeout=15)
    blob = " ".join(m.value for m in at.markdown)
    assert "Abstract bonus" in blob
    assert "tip-text" in blob  # CSS tooltip present
    assert "<abbr" not in blob  # old broken approach gone


def test_gui_renders_after_loading_synthetic_papers(monkeypatch):
    """Pre-populate session state with synthetic papers and confirm Papers tab still renders."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [
        {
            "id": "arXiv:1",
            "title": "Topological flat band",
            "authors": "Bloch et al",
            "subjects": "cond-mat.quant-gas",
            "abstract": "abstract " * 50,
            "link": "https://arxiv.org/abs/1",
            "section": "Thu, 4 Dec 2025",
        }
    ]
    at.run(timeout=15)
    assert not list(at.exception)


# ───────────────── Regression: keyed widgets vs cfg() state (arxiv_scraper_cli-e7b) ─────────────────
#
# Streamlit ignores `value=`/`default=` once a widget has an explicit `key` and
# `session_state[key]` already exists. So mutating st.session_state.cfg in a
# button handler (Apply weights / Reset to defaults) does NOT update the keyed
# widget the user sees -> "preferences not saved" / "counter stuck".

TIMEOUT = 25


def _weight_input(at, name):
    for ni in at.number_input:
        if ni.key == f"weight_{name}":
            return ni
    raise AssertionError(f"weight_{name} number_input not found")


def _click_label(at, label, *, keyless=False):
    for b in at.button:
        if b.label == label and (not keyless or not b.key):
            return b.click()
    raise AssertionError(f"button {label!r} (keyless={keyless}) not found")


def test_apply_weights_updates_cfg():
    """Sanity: applying a changed weight writes through to cfg.weights."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=TIMEOUT)
    default = _weight_input(at, "core_keyword").value
    _weight_input(at, "core_keyword").set_value(default + 50)
    at.run(timeout=TIMEOUT)
    _click_label(at, "Apply weights")
    at.run(timeout=TIMEOUT)
    assert at.session_state.cfg.weights.core_keyword == default + 50


def test_reset_weights_restores_default_in_widget():
    """After Reset to defaults the *visible* weight widget must show the default.

    Fails before the key-clearing fix: cfg resets but the keyed number_input
    keeps the stale value.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=TIMEOUT)
    default = _weight_input(at, "core_keyword").value
    _weight_input(at, "core_keyword").set_value(default + 50)
    at.run(timeout=TIMEOUT)
    _click_label(at, "Apply weights")
    at.run(timeout=TIMEOUT)

    # Scoring tab's reset button is the keyless "Reset to defaults".
    _click_label(at, "Reset to defaults", keyless=True)
    at.run(timeout=TIMEOUT)

    assert at.session_state.cfg.weights.core_keyword == default, "cfg should reset"
    assert _weight_input(at, "core_keyword").value == default, "widget should show default"


def test_reset_weights_clears_all_keyed_widgets():
    """Reset must restore every keyed weight widget, not just cfg.

    Fails before the fix for any field the user had edited.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=TIMEOUT)
    edited = {"named_author": 99, "low_priority_penalty": 77}
    defaults = {name: _weight_input(at, name).value for name in edited}

    for name, val in edited.items():
        _weight_input(at, name).set_value(val)
    at.run(timeout=TIMEOUT)
    _click_label(at, "Apply weights")
    at.run(timeout=TIMEOUT)
    _click_label(at, "Reset to defaults", keyless=True)
    at.run(timeout=TIMEOUT)

    for name, default in defaults.items():
        assert _weight_input(at, name).value == default, f"{name} widget stale after reset"


# --- word-boundary matching mirrors the scorer (arxiv_scraper_cli-28n) -------

def test_highlight_terms_word_boundary_no_substring_bleed():
    import arxiv_gui

    out = arxiv_gui._highlight_terms("temporal composition", ["mpo"], [], 6, -5)
    assert "hl-term" not in out  # 'mpo' must NOT highlight inside 'teMPOral'
    hit = arxiv_gui._highlight_terms("an mpo ansatz", ["mpo"], [], 6, -5)
    assert "hl-term" in hit


def test_highlight_terms_substring_mode_when_boundary_off():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "temporal", ["mpo"], [], 6, -5, word_boundary=False
    )
    assert "hl-term" in out


def test_authors_html_word_boundary_no_substring_bleed():
    import arxiv_gui

    out = arxiv_gui._authors_html("Yun Mao, Anna Blochwitz", ["ma", "bloch"], 6)
    assert "hl-author" not in out
    hit = arxiv_gui._authors_html("Immanuel Bloch", ["bloch"], 6)
    assert "hl-author" in hit


# --- starter presets in the Profiles tab (arxiv_scraper_cli-7f2) -------------

def test_gui_starter_preset_selectbox_present():
    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    assert not list(at.exception)
    values = {sb.value for sb in at.selectbox}
    # the starter-preset selectbox defaults to the first preset name
    assert ad.preset_names()[0] in values


def test_gui_load_preset_replaces_cfg():
    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    at.selectbox(key="starter_preset").set_value("floquet-topological").run()
    at.button(key="preset_load").click().run()
    assert not list(at.exception)
    kws = [k.lower() for k in at.session_state["cfg"].core_keywords]
    assert "floquet" in kws


def test_gui_add_preset_merges_cfg():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    before = len(at.session_state["cfg"].named_authors)
    at.selectbox(key="starter_preset").set_value("open-quantum-systems").run()
    at.button(key="preset_add").click().run()
    assert not list(at.exception)
    authors = [a.lower() for a in at.session_state["cfg"].named_authors]
    assert "eckardt" in authors
    assert len(authors) >= before  # union never shrinks
