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
