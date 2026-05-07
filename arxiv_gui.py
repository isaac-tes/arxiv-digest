"""Streamlit GUI for the arXiv digest tool.

Run with:
    uv run streamlit run arxiv_gui.py

Imports `arxiv_digest` directly so all fetch / score / format logic stays in
one place. The CLI flow (`python arxiv_digest.py ...`) is unaffected.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

import arxiv_digest as ad

PROFILES_DIR = Path.home() / ".arxiv_scraper" / "profiles"
PROJECT_CONFIG = ad.DEFAULT_CONFIG_PATH


# ────────────────────────── Profile management ──────────────────────────

def list_profiles() -> list[str]:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def save_profile(cfg: ad.Config, name: str) -> Path:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target = PROFILES_DIR / f"{name}.json"
    cfg.dump(target)
    return target


def load_profile(name: str) -> ad.Config:
    return ad.Config.load(PROFILES_DIR / f"{name}.json")


def delete_profile(name: str) -> None:
    (PROFILES_DIR / f"{name}.json").unlink(missing_ok=True)


# ────────────────────────── Fetching with cache ──────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_papers_cached(timeframe: str, feeds_key: Tuple[Tuple[str, str], ...]) -> list[dict]:
    """Cached fetch keyed on (timeframe, sorted feed URLs).

    feeds_key is a tuple of (name, url) pairs because lists/dicts aren't hashable.
    """
    suffix = "new" if timeframe == "today" else "pastweek"
    urls = []
    for _, base_url in feeds_key:
        url = (
            base_url.replace("/new", f"/{suffix}")
            .replace("/recent", f"/{suffix}")
            .replace("/pastweek", f"/{suffix}")
        )
        urls.append(url)
    return ad.fetch_feeds(urls)


# ────────────────────────── Session state init ──────────────────────────

def init_state():
    if "cfg" not in st.session_state:
        st.session_state.cfg = ad.Config.load(PROJECT_CONFIG if PROJECT_CONFIG.exists() else None)
    if "papers" not in st.session_state:
        st.session_state.papers = []
    if "last_fetch" not in st.session_state:
        st.session_state.last_fetch = None


def cfg() -> ad.Config:
    return st.session_state.cfg


# ────────────────────────── Sidebar ──────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("arXiv Digest")

        st.subheader("Profile")
        profiles = list_profiles()
        active = st.selectbox(
            "Active",
            options=["(unsaved)"] + profiles,
            index=0,
            key="active_profile",
        )
        if active != "(unsaved)" and st.button("Load profile", width="stretch"):
            st.session_state.cfg = load_profile(active)
            st.success(f"Loaded {active}")
            st.rerun()

        st.divider()

        st.subheader("Fetch")
        timeframe = st.radio(
            "Timeframe",
            options=["today", "pastweek"],
            index=1 if cfg().timeframe == "pastweek" else 0,
        )
        cfg().timeframe = timeframe

        top_n = st.number_input(
            "Top N",
            min_value=1,
            max_value=500,
            value=cfg().top_n,
            step=5,
        )
        cfg().top_n = int(top_n)

        feed_options = list(cfg().feeds.keys())
        defaults_in_feeds = [f for f in cfg().default_feeds if f in feed_options]
        selected_feeds = st.multiselect(
            "Feeds",
            options=feed_options,
            default=defaults_in_feeds,
        )
        cfg().default_feeds = selected_feeds

        if st.button(
            "Fetch papers",
            type="primary",
            width="stretch",
            disabled=not selected_feeds,
        ):
            with st.spinner("Fetching from arXiv..."):
                feeds_key = tuple(sorted((f, cfg().feeds[f]) for f in selected_feeds))
                st.session_state.papers = fetch_papers_cached(timeframe, feeds_key)
                st.session_state.last_fetch = datetime.now()
            st.success(f"Fetched {len(st.session_state.papers)} papers.")

        if st.session_state.last_fetch:
            st.caption(f"Last fetched: {st.session_state.last_fetch:%Y-%m-%d %H:%M:%S}")

        if st.button("Clear fetch cache", width="stretch"):
            fetch_papers_cached.clear()
            st.session_state.papers = []
            st.session_state.last_fetch = None
            st.rerun()


# ────────────────────────── Tab: Papers ──────────────────────────

def _render_breakdown(breakdown: dict):
    if breakdown["keywords"]:
        st.markdown("**Keywords matched:**")
        st.write(", ".join(f"`{kw}` (+{w})" for kw, w in breakdown["keywords"]))
    if breakdown["authors"]:
        st.markdown("**Authors matched:**")
        st.write(", ".join(f"`{a}` (+{w})" for a, w in breakdown["authors"]))
    if breakdown["subjects"]:
        st.markdown("**Subject bonuses:**")
        st.write(", ".join(f"`{s}` (+{w})" for s, w in breakdown["subjects"].items()))
    if breakdown["low_priority_hits"]:
        st.markdown(
            f"**Low-priority hits:** {', '.join(breakdown['low_priority_hits'])} "
            f"(penalty: {breakdown['low_priority_penalty']})"
        )
    if breakdown["abstract_bonus"]:
        st.markdown(f"**Abstract bonus:** +{breakdown['abstract_bonus']}")


def render_papers_tab():
    papers = st.session_state.papers
    if not papers:
        st.info("Click **Fetch papers** in the sidebar to load papers.")
        return

    entries = ad.build_ranked_entries(papers, cfg(), top_n=cfg().top_n)
    paper_by_id = {p["id"]: p for p in papers}

    col_search, col_export_md, col_export_json = st.columns([3, 1, 1])
    with col_search:
        query = st.text_input("Search title / authors / abstract", placeholder="e.g. fractional")
    with col_export_md:
        md = ad.format_markdown(entries, total_papers=len(papers), requested_top=cfg().top_n)
        st.download_button(
            "Markdown",
            data=md,
            file_name=f"digest-{datetime.now():%Y-%m-%d}.md",
            mime="text/markdown",
            width="stretch",
        )
    with col_export_json:
        payload = {
            "generated_at": datetime.now().isoformat(),
            "top_n": cfg().top_n,
            "total_papers": len(papers),
            "entries": entries,
        }
        st.download_button(
            "JSON",
            data=json.dumps(payload, indent=2, ensure_ascii=False),
            file_name=f"digest-{datetime.now():%Y-%m-%d}.json",
            mime="application/json",
            width="stretch",
        )

    if query:
        q = query.lower()
        filtered = [
            e for e in entries
            if q in e["title"].lower()
            or q in e["authors"].lower()
            or q in (paper_by_id.get(e["id"], {}).get("abstract", "").lower())
        ]
    else:
        filtered = entries

    st.caption(f"Showing {len(filtered)} of {len(entries)} ranked (out of {len(papers)} fetched).")

    for e in filtered:
        with st.container(border=True):
            head, score_col = st.columns([5, 1])
            with head:
                st.markdown(f"**{e['rank']}. {e['title']}**")
                st.caption(e["authors"])
                if e["section"]:
                    st.caption(f"Section: {e['section']}")
                st.write(e["summary"])
                if e["link"]:
                    st.markdown(f"[arXiv ↗]({e['link']})")
            with score_col:
                st.metric("Score", e["score"])

            with st.expander("Why this score?"):
                full_paper = paper_by_id.get(e["id"], {})
                breakdown = ad.explain_score(full_paper, cfg())
                _render_breakdown(breakdown)
            with st.expander("Full abstract"):
                st.write(paper_by_id.get(e["id"], {}).get("abstract", "(unavailable)"))


# ────────────────────────── Tab: list editors ──────────────────────────

def _render_list_editor(label: str, attr: str):
    st.subheader(label)
    st.caption(f"Edit, add, or remove entries. Empty rows are dropped on save.")
    df = pd.DataFrame({label: getattr(cfg(), attr)})
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        width="stretch",
        key=f"editor_{attr}",
        column_config={label: st.column_config.TextColumn(label, required=False)},
    )
    col_save, col_reset = st.columns(2)
    with col_save:
        if st.button(f"Save {label.lower()}", key=f"save_{attr}", type="primary"):
            cleaned = [str(v).strip() for v in edited[label].tolist() if str(v).strip() and v == v]
            setattr(cfg(), attr, cleaned)
            st.success(f"Saved {len(cleaned)} entries.")
            st.rerun()
    with col_reset:
        if st.button(f"Reset to defaults", key=f"reset_{attr}"):
            defaults_map = {
                "core_keywords": ad._default_core_keywords,
                "named_authors": ad._default_named_authors,
                "low_priority_kw": ad._default_low_priority_kw,
            }
            setattr(cfg(), attr, defaults_map[attr]())
            st.rerun()


def render_keywords_tab():
    _render_list_editor("Core keywords", "core_keywords")


def render_authors_tab():
    _render_list_editor("Highlighted authors", "named_authors")


def render_low_priority_tab():
    _render_list_editor("Low-priority terms", "low_priority_kw")


# ────────────────────────── Tab: Feeds ──────────────────────────

def render_feeds_tab():
    st.subheader("Feeds")
    st.caption("Map a short name to a full arXiv listing URL (e.g. `https://arxiv.org/list/cond-mat/new`).")
    rows = [{"name": n, "url": u} for n, u in cfg().feeds.items()]
    df = pd.DataFrame(rows or [{"name": "", "url": ""}])
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        width="stretch",
        key="editor_feeds",
        column_config={
            "name": st.column_config.TextColumn("name", required=True),
            "url": st.column_config.TextColumn("url", required=True),
        },
    )
    if st.button("Save feeds", type="primary"):
        new_feeds = {}
        for _, row in edited.iterrows():
            n = str(row.get("name", "")).strip()
            u = str(row.get("url", "")).strip()
            if n and u:
                new_feeds[n] = u
        cfg().feeds = new_feeds
        cfg().default_feeds = [f for f in cfg().default_feeds if f in new_feeds]
        st.success(f"Saved {len(new_feeds)} feeds.")
        st.rerun()


# ────────────────────────── Tab: Scoring ──────────────────────────

def render_scoring_tab():
    st.subheader("Scoring weights")
    st.caption(
        "Tweak how strongly each rule contributes to a paper's score. "
        "Rankings update live in the **Papers** tab — no re-fetch needed."
    )

    w = cfg().weights
    new_values: dict[str, int] = {}
    for f in fields(ad.ScoringWeights):
        new_values[f.name] = st.number_input(
            f.name.replace("_", " "),
            value=getattr(w, f.name),
            step=1,
            key=f"weight_{f.name}",
        )

    col_apply, col_reset = st.columns(2)
    with col_apply:
        if st.button("Apply weights", type="primary"):
            cfg().weights = ad.ScoringWeights(**new_values)
            st.success("Weights applied.")
            st.rerun()
    with col_reset:
        if st.button("Reset to defaults"):
            cfg().weights = ad.ScoringWeights()
            st.rerun()


# ────────────────────────── Tab: Profiles ──────────────────────────

def render_profiles_tab():
    st.subheader("Profiles")
    st.caption(f"Profiles are saved as JSON under `{PROFILES_DIR}` and reusable across sessions.")

    name = st.text_input("Save current config as", placeholder="e.g. topology-mode")
    if st.button("Save", disabled=not name.strip()):
        save_profile(cfg(), name.strip())
        st.success(f"Saved profile '{name.strip()}'.")
        st.rerun()

    profiles = list_profiles()
    if profiles:
        st.markdown("**Saved profiles:**")
        for p in profiles:
            cols = st.columns([3, 1, 1, 1])
            cols[0].write(p)
            if cols[1].button("Load", key=f"load_{p}"):
                st.session_state.cfg = load_profile(p)
                st.success(f"Loaded {p}")
                st.rerun()
            cols[2].download_button(
                "Export",
                data=json.dumps(asdict(load_profile(p)), indent=2, ensure_ascii=False),
                file_name=f"{p}.json",
                mime="application/json",
                key=f"export_{p}",
            )
            if cols[3].button("Delete", key=f"del_{p}"):
                delete_profile(p)
                st.rerun()

    st.divider()
    st.markdown("**Save back to project config** (`arxiv_config.json` next to `arxiv_digest.py`)")
    st.caption("Persists the current config so the CLI picks it up on the next run.")
    if st.button("Write project config"):
        cfg().dump(PROJECT_CONFIG)
        st.success(f"Wrote {PROJECT_CONFIG}")

    uploaded = st.file_uploader("Import profile from JSON", type="json")
    if uploaded is not None:
        try:
            raw = json.load(uploaded)
            st.session_state.cfg = ad.Config.from_json(raw)
            st.success("Profile imported into current session.")
        except Exception as exc:
            st.error(f"Failed to parse JSON: {exc}")


# ────────────────────────── Main ──────────────────────────

def main():
    st.set_page_config(page_title="arXiv Digest", layout="wide")
    init_state()
    render_sidebar()

    tab_papers, tab_kw, tab_authors, tab_lp, tab_feeds, tab_scoring, tab_profiles = st.tabs(
        ["Papers", "Keywords", "Authors", "Low priority", "Feeds", "Scoring", "Profiles"]
    )
    with tab_papers:
        render_papers_tab()
    with tab_kw:
        render_keywords_tab()
    with tab_authors:
        render_authors_tab()
    with tab_lp:
        render_low_priority_tab()
    with tab_feeds:
        render_feeds_tab()
    with tab_scoring:
        render_scoring_tab()
    with tab_profiles:
        render_profiles_tab()


if __name__ == "__main__":
    main()
