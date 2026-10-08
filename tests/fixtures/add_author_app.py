"""Renders the Add-author popover for one paper so AppTest can click it."""
import streamlit as st

import arxiv_gui

arxiv_gui.init_state()
if "seeded" not in st.session_state:
    st.session_state.seeded = True
    arxiv_gui.cfg().named_authors = ["alice smith"]
arxiv_gui._render_add_author("Alice Smith, Bob Jones, Carol Wu")
st.write(arxiv_gui.cfg().named_authors)
