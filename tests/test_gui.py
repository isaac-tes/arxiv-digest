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


def test_zotero_save_callback_blocks_concurrent_save_in_flight(monkeypatch):
    """While a save is in flight for a paper, a second invocation is blocked
    (prevents a double-click from triggering two concurrent writes)."""
    import arxiv_gui
    import zotero_bridge as zb

    calls = {"n": 0}

    def fake_save(_id, collection_key=None):
        calls["n"] += 1
        return {"ok": True, "item_key": "KEY123"}

    monkeypatch.setattr(zb, "save_to_zotero", fake_save)

    # A save is already in flight for this paper (its id is in zotero_saving).
    arxiv_gui.st.session_state.zotero_saving = {"2608.16520"}
    arxiv_gui.st.session_state["zotero_col_card_2608.16520"] = "My Library"

    arxiv_gui._do_zotero_save("2608.16520", "Test paper")
    assert calls["n"] == 0


def test_zotero_save_callback_allows_resave(monkeypatch):
    """A previously-saved paper can be saved again (duplication is the user's
    call); the callback records a fresh Saved-tick timestamp on success."""
    import time

    import arxiv_gui
    import zotero_bridge as zb

    calls = {"n": 0}

    def fake_save(_id, collection_key=None):
        calls["n"] += 1
        return {"ok": True, "item_key": "KEY123"}

    monkeypatch.setattr(zb, "save_to_zotero", fake_save)
    monkeypatch.setattr(arxiv_gui, "_zotero_collections_cached", lambda: [])

    arxiv_gui.st.session_state.zotero_saving = set()
    arxiv_gui.st.session_state.zotero_saved_at = {}
    arxiv_gui.st.session_state["zotero_col_card_2608.16520"] = "(no collection)"

    # Second save must be allowed (no saved_papers guard anymore).
    arxiv_gui._do_zotero_save("2608.16520", "Test paper")
    arxiv_gui._do_zotero_save("2608.16520", "Test paper")
    assert calls["n"] == 2
    # The ticket records a timestamp close to now for each success.
    saved_at = arxiv_gui.st.session_state.zotero_saved_at["2608.16520"]
    assert abs(time.monotonic() - saved_at) < 5


def test_zotero_save_callback_denied_never_records_success(monkeypatch):
    """A denied local authorization stays an error and cannot show a success tick."""
    import arxiv_gui
    import zotero_bridge as zb

    monkeypatch.setattr(arxiv_gui, "_zotero_collections_cached", lambda: [])
    monkeypatch.setattr(
        zb,
        "save_to_zotero",
        lambda *args, **kwargs: {"ok": False, "error": "Zotero did not grant write access."},
    )
    arxiv_gui.st.session_state.zotero_saving = set()
    arxiv_gui.st.session_state.zotero_saved_at = {}

    arxiv_gui._do_zotero_save("2608.16520", "Test paper")
    assert "2608.16520" not in arxiv_gui.st.session_state.zotero_saved_at
    assert arxiv_gui.st.session_state["zotero_result_2608.16520"] == (
        "error",
        "Zotero did not grant write access.",
    )


def test_zotero_tick_is_fresh(monkeypatch):
    import time

    import arxiv_gui

    assert arxiv_gui._zotero_tick_is_fresh(None) is False
    now = time.monotonic()
    assert arxiv_gui._zotero_tick_is_fresh(now) is True
    assert arxiv_gui._zotero_tick_is_fresh(now - 5, now=now) is True
    assert arxiv_gui._zotero_tick_is_fresh(now - 31, now=now) is False
    assert arxiv_gui._zotero_tick_is_fresh(now - 100, now=now) is False


def test_zotero_tick_app_fresh_caption_stale_popover():
    """A fresh Saved-tick renders the 'Saved ✓' caption only; a stale one
    renders the full popover with its Save button again."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("tests/fixtures/zotero_tick_app.py").run(timeout=15)
    captions = [c.value for c in at.caption]
    assert "Saved ✓" in captions, captions
    save_buttons = [b.label for b in at.button]
    assert "Save" in save_buttons, save_buttons


def test_zotero_collection_options_personal_library(monkeypatch):
    """The save popover offers the personal-library root and collections."""
    import arxiv_gui

    monkeypatch.setattr(
        arxiv_gui, "_zotero_collections_cached",
        lambda: [{"key": "AAAA1111", "name": "To Read"}],
    )
    assert arxiv_gui._zotero_collection_options() == ["(no collection)", "To Read"]
    assert arxiv_gui._zotero_collection_key_for("(no collection)") is None
    assert arxiv_gui._zotero_collection_key_for("To Read") == "AAAA1111"


def test_zotero_save_callback_defaults_to_personal_library(monkeypatch):
    """Saves always target the personal library root or its chosen collection."""
    import arxiv_gui
    import zotero_bridge as zb

    captured = {}
    monkeypatch.setattr(arxiv_gui, "_zotero_collections_cached", lambda: [])

    def fake_save(_id, collection_key=None):
        captured["collection_key"] = collection_key
        return {"ok": True, "item_key": "KEY123"}

    monkeypatch.setattr(zb, "save_to_zotero", fake_save)

    arxiv_gui.st.session_state.zotero_saving = set()
    arxiv_gui._do_zotero_save("2608.16520", "Test paper")
    assert captured["collection_key"] is None


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


def test_pastweek_feeds_to_fetch_keeps_parent_and_subcategories():
    """The export API needs each selected category queried explicitly.

    Unlike arXiv's HTML listing, ``cat:cond-mat`` is not a wildcard for
    dotted subcategories, so dropping ``cond-mat.quant-gas`` here would lose
    papers that are present in the selected subcategory feeds.
    """
    import arxiv_gui

    feeds = (
        ("cond-mat.quant-gas", "u"),
        ("cond-mat.mes-hall", "u"),
        ("quant-ph", "u"),
        ("cond-mat", "u"),
    )
    assert arxiv_gui._pastweek_feeds_to_fetch(feeds) == [
        "cond-mat.quant-gas",
        "cond-mat.mes-hall",
        "quant-ph",
        "cond-mat",
    ]

    # A name that merely shares a prefix (not a dotted child) is kept too.
    feeds2 = (("cond-matx", "u"), ("cond-mat", "u"))
    assert arxiv_gui._pastweek_feeds_to_fetch(feeds2) == ["cond-matx", "cond-mat"]


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


def _atom_entry(published: str, cats: list[str], arxiv_id: str = "2608.16520") -> "object":
    import xml.etree.ElementTree as ET

    cats_xml = "".join(f'<category term="{c}"/>' for c in cats)
    atom = f"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/{arxiv_id}v1</id>
        <published>{published}</published>
        <title>Test</title>
        <summary>Abstract</summary>
        {cats_xml}
      </entry>
    </feed>"""
    return ET.fromstring(atom).find("{http://www.w3.org/2005/Atom}entry")


def test_absence_reason_date_mismatch_with_preset(monkeypatch):
    """Paper submitted on a day the fetched feed doesn't cover -> date reason."""
    import arxiv_digest as ad
    import arxiv_gui
    import zotero_bridge as zb

    # floquet-topological preset subscribes to cond-mat.quant-gas/mes-hall/quant-ph
    cfg = ad.preset_config("floquet-topological")
    entry = _atom_entry("2026-08-17T13:03:36Z", ["cond-mat.quant-gas", "quant-ph"])
    monkeypatch.setattr(zb, "fetch_arxiv_atom", lambda _id: entry)

    fetched = [
        {"id": "x1", "section": "Mon, 18 Aug 2026 (showing 88 of 88 entries )"},
        {"id": "x2", "section": "Tue, 19 Aug 2026 (showing 88 of 88 entries )"},
    ]
    out = arxiv_gui._absence_reason("2608.16520", fetched, cfg)
    assert "submitted on **2026-08-17**" in out
    assert "only covers **2026-08-18, 2026-08-19**" in out
    assert "overlap your subscribed feeds" in out


def test_absence_reason_category_mismatch_with_preset(monkeypatch):
    """Paper in a category the preset doesn't subscribe to -> category reason."""
    import arxiv_digest as ad
    import arxiv_gui
    import zotero_bridge as zb

    cfg = ad.preset_config("floquet-topological")  # quant-gas/mes-hall/quant-ph
    entry = _atom_entry("2026-08-18T10:00:00Z", ["hep-th", "math-ph"])
    monkeypatch.setattr(zb, "fetch_arxiv_atom", lambda _id: entry)

    fetched = [
        {"id": "x1", "section": "Mon, 18 Aug 2026 (showing 88 of 88 entries )"},
    ]
    out = arxiv_gui._absence_reason("2608.16520", fetched, cfg)
    assert "**hep-th, math-ph**" in out
    assert "not among your subscribed feeds" in out


def test_absence_reason_within_days_but_not_listed(monkeypatch):
    """Paper date IS in fetched days but still absent -> 'within fetched days'."""
    import arxiv_digest as ad
    import arxiv_gui
    import zotero_bridge as zb

    cfg = ad.preset_config("floquet-topological")
    entry = _atom_entry("2026-08-18T10:00:00Z", ["quant-ph"])
    monkeypatch.setattr(zb, "fetch_arxiv_atom", lambda _id: entry)

    fetched = [
        {"id": "x1", "section": "Mon, 18 Aug 2026 (showing 88 of 88 entries )"},
    ]
    out = arxiv_gui._absence_reason("2608.16520", fetched, cfg)
    assert "IS within the fetched days" in out
    assert "not yet listed in the feed pages" in out


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


def test_gui_font_tint_checkboxes_checked_by_default():
    """A fresh session shows the font-tint checkboxes ON (fonts tinted by default)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    boxes = {c.label: c for c in at.sidebar.checkbox}
    assert boxes["Font: keywords"].value is True
    assert boxes["Font: authors"].value is True
    # low-priority and subject font tinting stay off by default.
    assert boxes["Font: low priority"].value is False
    assert boxes["Font: subjects"].value is False
    # The config object backs the checkboxes.
    assert at.session_state["cfg"].color_font_keyword is True
    assert at.session_state["cfg"].color_font_author is True


def test_gui_font_defaults_reapply_when_session_version_stale(monkeypatch):
    """A session that kept stale widget state (old default-version) re-applies the
    new ON defaults instead of letting the stale unchecked checkbox win."""
    import arxiv_digest as ad
    from streamlit.testing.v1 import AppTest

    # Reproduce a running session whose cfg exists but whose sidebar already
    # holds an old font value and an out-of-date default version (hot-reload case).
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["cfg"] = ad.Config()                  # defaults: font ON
    at.session_state["cfg_default_version"] = "1"          # older than current
    at.session_state["color_font_keyword"] = False          # stale unchecked box
    at.run(timeout=15)

    boxes = {c.label: c for c in at.sidebar.checkbox}
    assert boxes["Font: keywords"].value is True
    assert boxes["Font: authors"].value is True
    assert not list(at.exception)


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


def _card_paper(pid, title, section="New submissions (showing 3 of 3 entries)"):
    return {"id": pid, "title": title, "authors": "A", "subjects": "physics.optics",
            "abstract": "x" * 50, "link": "", "section": section}


def _tmp_home(monkeypatch, tmp_path):
    """Point REMOVED_PAPERS_PATH at tmp_path (AppTest re-runs the module top level)."""
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path / ".arxiv_scraper" / "removed_papers.json"


def _ranked_titles(at):
    import re

    blob = " ".join(m.value for m in at.markdown)
    return re.findall(r'class="paper-title">(.*?)</div>', blob)


def test_remove_paper_reranks_and_promotes_next_paper(monkeypatch, tmp_path):
    """✕ on a card drops it, shifts the rest up, and pulls paper N+1 into the top N."""
    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    _tmp_home(monkeypatch, tmp_path)
    at = AppTest.from_file("arxiv_gui.py")
    cfg = ad.Config.load(None)
    cfg.top_n = 2
    at.session_state["cfg"] = cfg
    # Identical scores, so ranking falls back to the alphabetical title tiebreak.
    at.session_state["papers"] = [
        _card_paper("p3", "Paper C"), _card_paper("p1", "Paper A"), _card_paper("p2", "Paper B"),
    ]
    at.run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper A", "2. Paper B"]

    at.button(key="remove_p1").click().run(timeout=15)
    assert not list(at.exception)
    assert _ranked_titles(at) == ["1. Paper B", "2. Paper C"]
    assert any("1 removed by you" in c.value for c in at.caption)

    at.button(key="restore_p1").click().run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper A", "2. Paper B"]


def test_removing_every_paper_keeps_restore_available(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [_card_paper("p1", "Paper A")]
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)
    assert not list(at.exception)
    assert _ranked_titles(at) == []
    assert any("restore removed papers" in w.value for w in at.warning)

    at.button(key="restore_all").click().run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper A"]


def _removed_expanders(at):
    return [x.label for x in at.expander if x.label.startswith("Removed papers")]


def test_removed_list_only_offers_papers_that_would_be_ranked(monkeypatch, tmp_path):
    """A removed paper that would rank below the visible top N isn't listed."""
    import json

    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    removed_file = _tmp_home(monkeypatch, tmp_path)
    removed_file.parent.mkdir(parents=True)
    removed_file.write_text(json.dumps(["p1", "p4"]))
    at = AppTest.from_file("arxiv_gui.py")
    cfg = ad.Config.load(None)
    cfg.top_n = 2
    at.session_state["cfg"] = cfg
    at.session_state["papers"] = [_card_paper(f"p{i}", f"Paper {c}") for i, c in enumerate("ABCD", 1)]
    at.run(timeout=15)

    assert _ranked_titles(at) == ["1. Paper B", "2. Paper C"]
    assert _removed_expanders(at) == ["Removed papers (1)"]
    keys = {b.key for b in at.button}
    assert "restore_p1" in keys and "restore_p4" not in keys
    assert not list(at.exception)


def test_yesterdays_removal_resurfaces_only_as_a_ranked_replacement(monkeypatch, tmp_path):
    """In today's digest a paper removed yesterday is listed only if it came back
    as a replacement (and replacements are shown) that would make the top N."""
    import json

    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    removed_file = _tmp_home(monkeypatch, tmp_path)
    removed_file.parent.mkdir(parents=True)
    removed_file.write_text(json.dumps(["2609.00009"]))
    at = AppTest.from_file("arxiv_gui.py")
    cfg = ad.Config.load(None)
    cfg.top_n = 2
    at.session_state["cfg"] = cfg
    at.session_state["papers"] = [
        _card_paper("2609.00001", "Paper B"),
        _card_paper("2609.00002", "Paper C"),
        _card_paper("2609.00009", "Paper A", "Replacement submissions (showing 1 of 1 entries)"),
    ]
    at.run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper B", "2. Paper C"]
    assert _removed_expanders(at) == []

    next(c for c in at.checkbox if c.label == "Include replacement submissions").set_value(True)
    at.run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper B", "2. Paper C"]
    assert _removed_expanders(at) == ["Removed papers (1)"]
    assert not list(at.exception)


def test_removal_persists_into_a_new_session_and_weekly_fetch(monkeypatch, tmp_path):
    """A paper removed from the daily ranking stays out after a reload, including
    in a pastweek fetch where the same paper sits under a day-label section."""
    import json

    from streamlit.testing.v1 import AppTest

    removed_file = _tmp_home(monkeypatch, tmp_path)
    daily = AppTest.from_file("arxiv_gui.py")
    daily.session_state["papers"] = [_card_paper("2609.00001", "Paper A")]
    daily.run(timeout=15)
    daily.button(key="remove_2609.00001").click().run(timeout=15)
    assert json.loads(removed_file.read_text()) == ["2609.00001"]

    day = "Mon, 28 Sep 2026 (showing 2 of 2 entries )"
    weekly = AppTest.from_file("arxiv_gui.py")
    weekly.session_state["papers"] = [
        _card_paper("2609.00001", "Paper A", day), _card_paper("2609.00002", "Paper B", day),
    ]
    weekly.run(timeout=15)
    assert not list(weekly.exception)
    assert _ranked_titles(weekly) == ["1. Paper B"]


def test_load_removed_ids_tolerates_missing_or_corrupt_file(monkeypatch, tmp_path):
    import arxiv_gui

    path = tmp_path / "removed_papers.json"
    monkeypatch.setattr(arxiv_gui, "REMOVED_PAPERS_PATH", path)
    monkeypatch.setattr(arxiv_gui, "REMOVED_DIR", tmp_path / "removed")
    assert arxiv_gui.load_removed_ids(None) == set()
    path.write_text("{not json")
    assert arxiv_gui.load_removed_ids(None) == set()
    arxiv_gui.save_removed_ids(None, {"b", "a"})
    assert arxiv_gui.load_removed_ids(None) == {"a", "b"}
    arxiv_gui.save_removed_ids("topo", {"c"})
    assert (tmp_path / "removed" / "topo.json").exists()
    assert arxiv_gui.load_removed_ids("topo") == {"c"}
    assert arxiv_gui.load_removed_ids(None) == {"a", "b"}


def test_concurrent_removals_from_two_tabs_are_all_kept(monkeypatch, tmp_path):
    """Every browser tab is a thread of one server, so removal-list updates must
    not overwrite each other or collide on a shared temp file."""
    import threading

    import arxiv_gui

    monkeypatch.setattr(arxiv_gui, "REMOVED_DIR", tmp_path / "removed")
    errors = []

    def tab(t):
        for i in range(25):
            try:
                arxiv_gui.update_removed_ids("p", add={f"{t}.{i}"})
            except Exception as exc:  # noqa: BLE001 - collected and asserted below
                errors.append(exc)

    threads = [threading.Thread(target=tab, args=(t,)) for t in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []
    assert len(arxiv_gui.load_removed_ids("p")) == 200
    assert list((tmp_path / "removed").iterdir()) == [tmp_path / "removed" / "p.json"]

    arxiv_gui.update_removed_ids("p", discard={"0.0", "7.24"})
    assert len(arxiv_gui.load_removed_ids("p")) == 198


def test_unreadable_removal_list_is_never_overwritten(monkeypatch, tmp_path):
    """A removal must not replace an existing list it can't read (truncated JSON,
    wrong shape, I/O error) with just the new ID; the file is left untouched."""
    import pytest

    import arxiv_gui

    monkeypatch.setattr(arxiv_gui, "REMOVED_DIR", tmp_path)
    path = tmp_path / "p.json"
    for broken in ('["a", "b", "c"', '{"a": 1}', '[1, 2]'):
        path.write_text(broken)
        with pytest.raises(ValueError):
            arxiv_gui.update_removed_ids("p", add={"d"})
        assert path.read_text() == broken
        assert arxiv_gui.load_removed_ids("p") == set()  # display stays tolerant
    assert [f.name for f in tmp_path.iterdir()] == ["p.json"]  # no temp files left


def test_remove_with_unreadable_list_warns_and_keeps_file(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    removed_file = _tmp_home(monkeypatch, tmp_path)
    removed_file.parent.mkdir(parents=True)
    removed_file.write_text('["a", "b"')
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [_card_paper("p1", "Paper A")]
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)
    assert not list(at.exception)
    assert removed_file.read_text() == '["a", "b"'
    assert any("Nothing was changed" in t.value for t in at.toast)


def test_delete_profile_takes_the_removal_lock(monkeypatch, tmp_path):
    """Deleting waits for an in-flight update, so it can't be undone by one."""
    import threading

    import arxiv_gui

    monkeypatch.setattr(arxiv_gui, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(arxiv_gui, "REMOVED_DIR", tmp_path / "removed")
    arxiv_gui.update_removed_ids("p", add={"x"})
    done = threading.Event()
    with arxiv_gui._removed_ids_lock():
        th = threading.Thread(target=lambda: (arxiv_gui.delete_profile("p"), done.set()))
        th.start()
        assert not done.wait(0.3)  # blocked while an update holds the lock
    th.join(timeout=5)
    assert done.is_set()
    assert not (tmp_path / "removed" / "p.json").exists()


def test_removed_ids_lock_survives_script_reruns():
    """Streamlit re-executes the script on each rerun; the lock must be the same
    object every time, which a plain module-level lock would not be."""
    import runpy
    from pathlib import Path

    script = str(Path(__file__).resolve().parent.parent / "arxiv_gui.py")
    first = runpy.run_path(script, run_name="__rerun__")
    second = runpy.run_path(script, run_name="__rerun__")
    assert first["_removed_ids_lock"]() is second["_removed_ids_lock"]()


def _profiles_dir(tmp_path, *names):
    import arxiv_digest as ad

    d = tmp_path / ".arxiv_scraper" / "profiles"
    d.mkdir(parents=True)
    for n in names:
        ad.Config().dump(d / f"{n}.json")


def test_removals_are_kept_per_profile(monkeypatch, tmp_path):
    import json

    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    _profiles_dir(tmp_path, "atoms", "topology")
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]
    at.run(timeout=15)

    def load(name):
        at.sidebar.selectbox(key="active_profile").set_value(name).run(timeout=15)
        _click_label(at, "Load profile")
        at.run(timeout=15)

    load("atoms")
    assert any("Loaded profile: **atoms**" in c.value for c in at.sidebar.caption)
    at.button(key="remove_p1").click().run(timeout=15)
    assert _ranked_titles(at) == ["1. Paper B"]
    atoms_file = tmp_path / ".arxiv_scraper" / "removed" / "atoms.json"
    assert json.loads(atoms_file.read_text()) == ["p1"]

    load("topology")
    assert _ranked_titles(at) == ["1. Paper A", "2. Paper B"]
    load("atoms")
    assert _ranked_titles(at) == ["1. Paper B"]
    assert not list(at.exception)


def test_loaded_profile_and_removals_survive_new_session(monkeypatch, tmp_path):
    import arxiv_digest as ad
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    profile_path = tmp_path / ".arxiv_scraper" / "profiles" / "atoms.json"
    profile_path.parent.mkdir(parents=True)
    profile = ad.Config()
    profile.core_keywords = ["profile-only"]
    profile.dump(profile_path)
    papers = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]

    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = papers
    at.run(timeout=15)
    at.sidebar.selectbox(key="active_profile").set_value("atoms").run(timeout=15)
    _click_label(at, "Load profile")
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)

    reloaded = AppTest.from_file("arxiv_gui.py")
    reloaded.session_state["papers"] = papers
    reloaded.run(timeout=15)

    assert reloaded.session_state["loaded_profile"] == "atoms"
    assert reloaded.sidebar.selectbox(key="active_profile").value == "atoms"
    assert reloaded.session_state.cfg.core_keywords == ["profile-only"]
    assert _ranked_titles(reloaded) == ["1. Paper B"]
    assert not list(reloaded.exception)


def test_active_profile_widget_tracks_profile_changes(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    _profiles_dir(tmp_path, "atoms", "topology")
    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)

    at.sidebar.selectbox(key="active_profile").set_value("atoms").run(timeout=15)
    _click_label(at, "Load profile")
    at.run(timeout=15)
    assert at.sidebar.selectbox(key="active_profile").value == "atoms"

    at.button(key="load_topology").click().run(timeout=15)
    assert at.session_state["loaded_profile"] == "topology"
    assert at.sidebar.selectbox(key="active_profile").value == "topology"

    at.button(key="preset_load").click().run(timeout=15)
    assert at.session_state["loaded_profile"] is None
    assert at.sidebar.selectbox(key="active_profile").value == "(unsaved)"
    assert not list(at.exception)


def test_profile_name_cannot_escape_storage(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("../outside").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)

    assert not (tmp_path / ".arxiv_scraper" / "outside.json").exists()
    assert at.session_state["loaded_profile"] is None
    assert any("single path-free file name" in e.value for e in at.error)
    assert not list(at.exception)


def test_profile_name_cannot_shadow_unsaved_option(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("(unsaved)").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)

    assert not (tmp_path / ".arxiv_scraper" / "profiles" / "(unsaved).json").exists()
    assert at.session_state["loaded_profile"] is None
    assert not list(at.exception)


def test_profile_path_helpers_reject_traversal(monkeypatch, tmp_path):
    import arxiv_digest as ad
    import arxiv_gui

    home = tmp_path / ".arxiv_scraper"
    outside = home / "outside.json"
    outside.parent.mkdir(parents=True)
    sentinel = ad.Config()
    sentinel.core_keywords = ["sentinel"]
    sentinel.dump(outside)
    monkeypatch.setattr(arxiv_gui, "PROFILES_DIR", home / "profiles")
    monkeypatch.setattr(arxiv_gui, "REMOVED_DIR", home / "removed")

    with pytest.raises(ValueError, match="single path-free file name"):
        arxiv_gui.save_profile(ad.Config(), "../outside")
    with pytest.raises(ValueError, match="single path-free file name"):
        arxiv_gui.load_profile("../outside")
    with pytest.raises(ValueError, match="single path-free file name"):
        arxiv_gui.delete_profile("../outside")
    with pytest.raises(ValueError, match="single path-free file name"):
        arxiv_gui.removed_papers_path("../outside")
    assert ad.Config.load(outside).core_keywords == ["sentinel"]


def test_save_as_carries_removals_and_delete_drops_them(monkeypatch, tmp_path):
    import json

    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)

    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("fresh").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)
    fresh_file = tmp_path / ".arxiv_scraper" / "removed" / "fresh.json"
    active_file = tmp_path / ".arxiv_scraper" / "active_profile.txt"
    assert at.session_state["loaded_profile"] == "fresh"
    assert active_file.read_text() == "fresh"
    assert json.loads(fresh_file.read_text()) == ["p1"]
    assert _ranked_titles(at) == ["1. Paper B"]

    at.button(key="del_fresh").click().run(timeout=15)
    assert not fresh_file.exists()
    assert not active_file.exists()
    assert at.session_state["loaded_profile"] is None
    assert not list(at.exception)


def test_save_as_stays_on_source_when_removal_transfer_fails(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    _profiles_dir(tmp_path, "atoms")
    papers = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = papers
    at.run(timeout=15)
    at.sidebar.selectbox(key="active_profile").set_value("atoms").run(timeout=15)
    _click_label(at, "Load profile")
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)

    destination_removals = tmp_path / ".arxiv_scraper" / "removed" / "topology.json"
    destination_removals.mkdir()
    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("topology").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)

    assert at.session_state["loaded_profile"] == "atoms"
    assert _ranked_titles(at) == ["1. Paper B"]
    assert not (tmp_path / ".arxiv_scraper" / "profiles" / "topology.json").exists()
    assert not list(at.exception)


def test_save_as_stays_on_source_when_source_removal_list_is_unreadable(
    monkeypatch, tmp_path
):
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    _profiles_dir(tmp_path, "atoms")
    papers = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = papers
    at.run(timeout=15)
    at.sidebar.selectbox(key="active_profile").set_value("atoms").run(timeout=15)
    _click_label(at, "Load profile")
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)

    source_removals = tmp_path / ".arxiv_scraper" / "removed" / "atoms.json"
    corrupt_list = '["p1"'
    source_removals.write_text(corrupt_list)
    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("topology").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)

    assert at.session_state["loaded_profile"] == "atoms"
    assert source_removals.read_text() == corrupt_list
    assert not (tmp_path / ".arxiv_scraper" / "profiles" / "topology.json").exists()
    assert not list(at.exception)


@pytest.mark.parametrize("stale", ['["old"]', "{"])
def test_save_as_replaces_existing_target_removals(monkeypatch, tmp_path, stale):
    import json

    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    target = tmp_path / ".arxiv_scraper" / "removed" / "topology.json"
    target.parent.mkdir(parents=True)
    target.write_text(stale)
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [_card_paper("p1", "Paper A"), _card_paper("p2", "Paper B")]
    at.run(timeout=15)
    at.button(key="remove_p1").click().run(timeout=15)

    name_box = next(t for t in at.text_input if t.label == "Save current config as")
    name_box.set_value("topology").run(timeout=15)
    _click_label(at, "Save", keyless=True)
    at.run(timeout=15)

    assert at.session_state["loaded_profile"] == "topology"
    assert json.loads(target.read_text()) == ["p1"]
    assert not list(at.exception)


def test_malformed_active_profile_falls_back_and_can_be_deleted(monkeypatch, tmp_path):
    import arxiv_digest as ad
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    project_config = tmp_path / "project.json"
    config = ad.Config()
    config.core_keywords = ["project-only"]
    config.dump(project_config)
    monkeypatch.setattr(ad, "DEFAULT_CONFIG_PATH", project_config)

    profile_path = tmp_path / ".arxiv_scraper" / "profiles" / "broken.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text("{")
    active_path = tmp_path / ".arxiv_scraper" / "active_profile.txt"
    active_path.write_text("broken")

    at = AppTest.from_file("arxiv_gui.py").run(timeout=15)
    assert not list(at.exception)
    assert at.session_state["loaded_profile"] is None
    assert at.session_state.cfg.core_keywords == ["project-only"]
    assert not active_path.exists()

    at.button(key="del_broken").click().run(timeout=15)
    assert not profile_path.exists()
    assert not list(at.exception)


def test_score_tab_honors_removed_papers(monkeypatch, tmp_path):
    """A removed paper is reported as removed, and ranks ignore removed papers."""
    import json

    import zotero_bridge as zb
    from streamlit.testing.v1 import AppTest

    removed_file = _tmp_home(monkeypatch, tmp_path)
    removed_file.parent.mkdir(parents=True)
    removed_file.write_text(json.dumps(["2608.00001"]))
    monkeypatch.setattr(
        zb, "fetch_arxiv_atom", lambda pid: _atom_entry("2026-09-28T00:00:00Z", ["quant-ph"], pid)
    )
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["papers"] = [
        _card_paper("2608.00001", "Paper A"), _card_paper("2608.00002", "Paper B"),
    ]
    at.run(timeout=15)

    def score(raw):
        next(t for t in at.text_input if t.label == "arXiv link or ID").set_value(raw).run(timeout=15)
        _click_label(at, "Score this paper")
        at.run(timeout=15)

    score("2608.00002v2")  # bare id with a version still matches the digest
    assert any("rank **#1**" in m.value for m in at.success)
    score("https://arxiv.org/abs/2608.00001")
    assert any("You **removed** this paper" in m.value for m in at.info)
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


def _checkbox(at, key):
    for cb in at.checkbox:
        if cb.key == key:
            return cb
    raise AssertionError(f"checkbox {key!r} not found")


def test_load_profile_clears_stale_color_and_font_widget_state(monkeypatch, tmp_path):
    """Load profile must restore color/font-toggle widgets, not just cfg.

    Regression: _reset_widget_state()'s default key list only covered weight
    and editor widgets, so after toggling a color/font checkbox in the
    current session, loading a saved profile kept the stale in-session widget
    value and silently wrote it back over the just-loaded profile.
    """
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import arxiv_digest as ad

    # AppTest re-executes arxiv_gui.py's top-level code fresh (it isn't just
    # reusing the already-imported module), so PROFILES_DIR must be redirected
    # by patching Path.home() before .run(), not by patching the module attr.
    profiles_dir = tmp_path / ".arxiv_scraper" / "profiles"
    profiles_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    saved = ad.Config()
    saved.color_font_keyword = False
    saved.dump(profiles_dir / "plain.json")

    at = AppTest.from_file("arxiv_gui.py").run(timeout=TIMEOUT)
    _checkbox(at, "color_font_keyword").set_value(True)
    at.run(timeout=TIMEOUT)
    assert at.session_state.cfg.color_font_keyword is True

    at.sidebar.selectbox(key="active_profile").set_value("plain")
    at.run(timeout=TIMEOUT)
    _click_label(at, "Load profile")
    at.run(timeout=TIMEOUT)

    assert at.session_state.cfg.color_font_keyword is False, "cfg should reflect loaded profile"
    assert _checkbox(at, "color_font_keyword").value is False, "widget stale after Load profile"


def test_paper_authors_and_meta_text_readable_in_light_mode():
    """Light-mode override must fix contrast without touching dark mode.

    Regression: .paper-authors/.paper-meta hardcoded a near-white (#e6edf3)
    / mid-grey (#8b949e) color tuned for Streamlit's dark theme, making both
    barely visible on light theme's white background. A `prefers-color-scheme:
    light` override should darken them, while the base (dark-mode) rule stays
    exactly as it was.
    """
    import arxiv_gui

    css = arxiv_gui._PAPER_CSS
    base_authors_rule = css.split(".paper-authors {")[1].split("}")[0]
    base_meta_rule = css.split(".paper-meta {")[1].split("}")[0]
    assert "#e6edf3" in base_authors_rule, "dark-mode authors color must be unchanged"
    assert "#8b949e" in base_meta_rule, "dark-mode meta color must be unchanged"

    assert "@media (prefers-color-scheme: light)" in css
    light_block = css.split("@media (prefers-color-scheme: light)")[1]
    light_authors_rule = light_block.split(".paper-authors {")[1].split("}")[0]
    light_meta_rule = light_block.split(".paper-meta {")[1].split("}")[0]
    assert "#e6edf3" not in light_authors_rule, "light mode must not keep the near-white color"
    assert "#8b949e" not in light_meta_rule, "light mode should use a darker, more legible grey"


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


def test_authors_html_highlights_middle_initial_variant():
    import arxiv_gui

    # highlight must stay in sync with the scorer: 'Hannah Price' fires on
    # 'Hannah M. Price' (arxiv_scraper_cli-fix_name_not_firing)
    out = arxiv_gui._authors_html("Hannah M. Price, Alice Smith", ["Hannah Price"], 6)
    assert out.count("hl-author") == 1
    assert "Hannah M. Price" in out
    assert "Alice Smith" in out


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
    assert "schnell" in authors
    assert len(authors) >= before  # union never shrinks


def _score(at, raw):
    next(t for t in at.text_input if t.label == "arXiv link or ID").set_value(raw).run(timeout=15)
    _click_label(at, "Score this paper")
    at.run(timeout=15)


def _score_tab_app(monkeypatch, tmp_path, papers):
    import arxiv_digest as ad
    import zotero_bridge as zb
    from streamlit.testing.v1 import AppTest

    _tmp_home(monkeypatch, tmp_path)
    monkeypatch.setattr(
        zb, "fetch_arxiv_atom", lambda pid: _atom_entry("2026-09-28T00:00:00Z", ["quant-ph"], pid)
    )
    at = AppTest.from_file("arxiv_gui.py")
    at.session_state["cfg"] = ad.Config()  # replacements hidden, like the Papers tab default
    at.session_state["papers"] = papers
    return at.run(timeout=15)


def test_score_tab_rank_matches_papers_tab_issue_7(monkeypatch, tmp_path):
    """#7: Score a paper must rank the same filtered list the Papers tab shows."""
    import arxiv_digest as ad

    kw = ad._default_core_keywords()[0]  # the replacement outscores the new paper
    at = _score_tab_app(monkeypatch, tmp_path, [
        _card_paper("2609.00001", "A new paper"),
        _card_paper("2609.00002", f"A replaced paper on {kw}",
                    section="Replacement submissions (showing 1 of 1 entries)"),
    ])
    assert _ranked_titles(at) == ["1. A new paper"]

    _score(at, "2609.00002")
    assert not any("is** in the current digest" in s.value for s in at.success)
    assert any("replacement" in i.value.lower() for i in at.info)

    _score(at, "2609.00001")
    assert any("rank **#1**" in s.value for s in at.success)


@pytest.mark.parametrize("hidden_by", ["top-n", "day-filter"])
def test_score_tab_does_not_promise_missing_restore_button(monkeypatch, tmp_path, hidden_by):
    import json

    papers = (
        [_card_paper("2609.00001", "Monday paper", section="Mon, 28 Sep 2026"),
         _card_paper("2609.00002", "Tuesday paper", section="Tue, 29 Sep 2026")]
        if hidden_by == "day-filter"
        else [_card_paper("2609.00001", "Paper A"), _card_paper("2609.00002", "Paper B")]
    )
    at = _score_tab_app(monkeypatch, tmp_path, papers)
    removed_file = tmp_path / ".arxiv_scraper" / "removed_papers.json"
    removed_file.parent.mkdir(parents=True, exist_ok=True)
    removed_file.write_text(json.dumps(["2609.00002"]))
    if hidden_by == "top-n":
        at.session_state.cfg.top_n = 1
    at.run(timeout=15)
    if hidden_by == "day-filter":
        at.selectbox(key="papers_day").set_value("Mon, 28 Sep 2026").run(timeout=15)

    _score(at, "2609.00002")

    assert any("adjust the papers tab filters or increase top n" in i.value.lower() for i in at.info)
    assert not list(at.exception)


def test_score_tab_follows_papers_tab_day_picker_issue_7(monkeypatch, tmp_path):
    """#7: with a single day picked in the Papers tab, Score a paper ranks that day."""
    import arxiv_digest as ad

    kw = ad._default_core_keywords()[0]
    at = _score_tab_app(monkeypatch, tmp_path, [
        _card_paper("2609.00001", "Monday paper", section="Mon, 28 Sep 2026"),
        _card_paper("2609.00002", f"Tuesday paper on {kw}", section="Tue, 29 Sep 2026"),
    ])
    at.selectbox(key="papers_day").set_value("Mon, 28 Sep 2026").run(timeout=15)
    assert _ranked_titles(at) == ["1. Monday paper"]

    _score(at, "2609.00001")
    assert any("rank **#1**" in s.value for s in at.success)
    _score(at, "2609.00002")
    assert any("day" in i.value.lower() for i in at.info)


def test_score_tab_zotero_button_does_not_clash_with_card_issue_8(monkeypatch, tmp_path):
    """#8: scoring a paper also shown in the Papers tab must not duplicate widget keys."""
    at = _score_tab_app(monkeypatch, tmp_path, [_card_paper("2609.00001", "A new paper")])
    _score(at, "2609.00001")
    assert not list(at.exception), [e.value for e in at.exception]


def test_add_author_popover_offers_only_unnamed_and_dedupes():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("tests/fixtures/add_author_app.py").run(timeout=15)
    assert not list(at.exception)
    assert [b.label for b in at.button] == ["Bob Jones", "Carol Wu"]

    at.session_state["editor_named_authors"] = {"stale": True}
    at.button[0].click()
    at.run(timeout=15)
    assert at.session_state["cfg"].named_authors == ["alice smith", "Bob Jones"]
    assert "editor_named_authors" not in at.session_state
    assert [b.label for b in at.button] == ["Carol Wu"]


def test_add_named_author_ignores_case_insensitive_duplicate():
    import arxiv_gui

    arxiv_gui.st.session_state.cfg = arxiv_gui.ad.Config(named_authors=["Bob Jones"])
    arxiv_gui._add_named_author("BOB JONES")
    assert arxiv_gui.cfg().named_authors == ["Bob Jones"]
