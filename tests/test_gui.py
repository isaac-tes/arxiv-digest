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


def test_gui_has_seven_tabs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    assert len(at.tabs) == 7


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
    assert "hl-kw" in out and "core keyword (+6)" in out
    assert "hl-lp" in out and "low-priority term (-5)" in out
    assert "topological" in out and "film" in out


def test_highlight_terms_no_match_is_plain_escaped():
    import arxiv_gui

    assert arxiv_gui._highlight_terms("plain <x> text", ["zzz"], [], 6, -5) == "plain &lt;x&gt; text"


def test_highlight_terms_case_insensitive_and_escapes():
    import arxiv_gui

    out = arxiv_gui._highlight_terms("Bloch & TOPOLOGY", ["topology"], [], 6, -5)
    assert "hl-kw" in out
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
    assert "hl-kw" in hit


def test_highlight_terms_substring_mode_when_boundary_off():
    import arxiv_gui

    out = arxiv_gui._highlight_terms(
        "temporal", ["mpo"], [], 6, -5, word_boundary=False
    )
    assert "hl-kw" in out


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
