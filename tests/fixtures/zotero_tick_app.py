"""Minimal Streamlit app that renders the Zotero save button for a paper whose
tick is fresh and one whose tick is stale, so AppTest can assert the 'Saved ✓'
caption shows for the former and the full popover (Save button) for the latter.
"""
import time

import streamlit as st

import arxiv_gui

# Keep the render hermetic: the popover reads the personal collection list,
# so stub it (no network / real Zotero in AppTest).
arxiv_gui._zotero_collections_cached = lambda: []

now = time.monotonic()
st.session_state.zotero_saved_at = {
    "FRESH": now,        # saved moments ago -> caption
    "STALE": now - 100,  # saved long ago      -> popover with Save button
}
arxiv_gui._render_zotero_save_button("FRESH", "Fresh paper")
arxiv_gui._render_zotero_save_button("STALE", "Stale paper")
