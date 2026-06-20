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
    edited = {"named_author": 99, "quant_ph_subject": 77}
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
