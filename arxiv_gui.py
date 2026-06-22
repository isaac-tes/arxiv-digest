"""Streamlit GUI for the arXiv digest tool.

Run with:
    uv run streamlit run arxiv_gui.py

Imports `arxiv_digest` directly so all fetch / score / format logic stays in
one place. The CLI flow (`python arxiv_digest.py ...`) is unaffected.
"""
from __future__ import annotations

import html
import json
import re
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


# Keyed widgets cache their value in st.session_state[key] and IGNORE the
# `value=`/`default=` arg on rerun. So when a button handler replaces cfg()
# from a non-widget source (Load profile, Reset, Import) the keyed widgets keep
# showing stale state. Pop those keys before st.rerun() to force re-init from cfg.
_WEIGHT_KEYS = [f"weight_{f.name}" for f in fields(ad.ScoringWeights)]
_EDITOR_KEYS = [
    "editor_core_keywords",
    "editor_named_authors",
    "editor_low_priority_kw",
    "editor_feeds",
]


def _reset_widget_state(*keys: str) -> None:
    """Drop cached widget state so widgets re-read from cfg() on next run."""
    for k in keys or (*_WEIGHT_KEYS, *_EDITOR_KEYS):
        st.session_state.pop(k, None)


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
            _reset_widget_state()
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

        cfg().include_replacements = st.checkbox(
            "Include replacement submissions",
            value=cfg().include_replacements,
            help=(
                "arXiv's 'today' feed lists re-submitted papers under "
                "'Replacement submissions'. Hidden by default to avoid repeats; "
                "tick to keep them. (The 'pastweek' feed has none.)"
            ),
        )

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

        st.divider()
        st.subheader("Display")
        st.caption("Hover-highlight matched terms in the Papers tab.")
        cfg().highlight_authors = st.checkbox(
            "Highlight authors", value=cfg().highlight_authors,
            help="Highlight authors that appear in your Authors list.",
        )
        cfg().highlight_terms_title = st.checkbox(
            "Highlight keywords in titles", value=cfg().highlight_terms_title,
            help="Light highlight of matched keywords / low-priority terms in titles.",
        )
        cfg().highlight_terms_abstract = st.checkbox(
            "Highlight keywords in abstracts", value=cfg().highlight_terms_abstract,
            help="Light highlight of matched keywords / low-priority terms in full abstracts.",
        )


# ────────────────────────── Tab: Papers ──────────────────────────

_PAPER_CSS = """
<style>
.paper-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; margin: 0 0 .15rem 0; }
.paper-authors { font-size: 1.02rem; color: #e6edf3; margin: 0 0 .25rem 0; }
.paper-authors .hl-author {
  color: #3fb950; font-weight: 700; border-bottom: 1px dotted #3fb950;
  cursor: help; padding: 0 1px; border-radius: 3px; transition: background .12s;
}
.paper-authors .hl-author:hover { background: rgba(63,185,80,.22); }
/* CSS tooltip — Streamlit strips the `title` attribute, so we roll our own. */
.tip { position: relative; border-bottom: 1px dotted #8b949e; cursor: help; }
.tip .tip-text {
  visibility: hidden; opacity: 0; transition: opacity .15s;
  position: absolute; z-index: 1000; top: 135%; left: 0;
  background: #1f2630; color: #e6edf3; padding: 6px 9px; border-radius: 6px;
  width: max-content; max-width: 320px; font-size: .8rem; font-weight: 400;
  line-height: 1.35; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,.45);
  white-space: normal;
}
.tip:hover .tip-text { visibility: visible; opacity: 1; }
/* Light hover-highlight for matched keywords / low-priority terms (subtler than authors). */
.hl-term { position: relative; cursor: help; border-radius: 3px; padding: 0 1px;
  border-bottom: 1px dotted transparent; transition: background .12s; }
.hl-term .hl-tip {
  visibility: hidden; opacity: 0; transition: opacity .12s;
  position: absolute; z-index: 1000; bottom: 145%; left: 0;
  background: #1f2630; color: #e6edf3; padding: 4px 7px; border-radius: 6px;
  width: max-content; max-width: 260px; font-size: .75rem; font-weight: 400;
  line-height: 1.3; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,.45);
  white-space: normal;
}
.hl-term:hover .hl-tip { visibility: visible; opacity: 1; }
.hl-kw { background: rgba(56,139,253,.10); border-bottom-color: rgba(88,166,255,.5); }
.hl-kw:hover { background: rgba(56,139,253,.24); }
.hl-lp { background: rgba(248,81,73,.10); border-bottom-color: rgba(248,81,73,.5); }
.hl-lp:hover { background: rgba(248,81,73,.24); }
</style>
"""


def _highlight_terms(
    text: str,
    keywords: list[str],
    lp_terms: list[str],
    kw_bonus: int,
    lp_penalty: int,
) -> str:
    """HTML-escape `text` and wrap matched keyword / low-priority spans.

    Keywords get the teal `.hl-kw` style, low-priority the red `.hl-lp` style,
    each with a hover tooltip showing its weight. Overlapping matches are
    resolved earliest-start, longest-first.
    """
    spans: list[tuple[int, int, str]] = []
    for terms, kind in ((keywords, "kw"), (lp_terms, "lp")):
        for t in terms:
            t = t.strip()
            if not t:
                continue
            for m in re.finditer(re.escape(t), text, re.IGNORECASE):
                spans.append((m.start(), m.end(), kind))
    if not spans:
        return html.escape(text)

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen: list[tuple[int, int, str]] = []
    last_end = -1
    for s in spans:
        if s[0] >= last_end:
            chosen.append(s)
            last_end = s[1]

    out: list[str] = []
    i = 0
    for start, end, kind in chosen:
        out.append(html.escape(text[i:start]))
        frag = html.escape(text[start:end])
        if kind == "kw":
            tip = f"core keyword (+{kw_bonus})"
            cls = "hl-term hl-kw"
        else:
            tip = f"low-priority term ({lp_penalty})"
            cls = "hl-term hl-lp"
        out.append(f'<span class="{cls}">{frag}<span class="hl-tip">{tip}</span></span>')
        i = end
    out.append(html.escape(text[i:]))
    return "".join(out)


def _authors_html(authors: str, named: list[str], bonus: int) -> str:
    """Render the author line, highlighting authors present in `named`."""
    named_low = [n.strip().lower() for n in named if n.strip()]
    parts = [a.strip() for a in authors.split(",") if a.strip()]
    out = []
    for a in parts:
        esc = html.escape(a)
        if any(n in a.lower() for n in named_low):
            out.append(
                f'<span class="hl-author" title="Highlighted author '
                f'(+{bonus} to score)">{esc}</span>'
            )
        else:
            out.append(esc)
    return ", ".join(out) or "(No authors listed)"


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
        thr = cfg().weights.long_abstract_threshold
        st.markdown(
            f'<span class="tip"><b>Abstract bonus:</b> +{breakdown["abstract_bonus"]}'
            f'<span class="tip-text">Awarded because the abstract is longer than '
            f'{thr} characters — a rough signal of a substantial paper.</span></span>',
            unsafe_allow_html=True,
        )


def render_papers_tab():
    fetched = st.session_state.papers
    if not fetched:
        st.info("Click **Fetch papers** in the sidebar to load papers.")
        return

    # Back-in-time day picker (only days arXiv's pastweek feed still lists).
    day_labels = ad.available_day_labels(fetched)
    selected_days = None
    if day_labels:
        choice = st.selectbox(
            "Day",
            options=["All days"] + day_labels,
            help=(
                "Pick a single past day to see just its ranking. Only the days "
                "arXiv's pastweek feed still returns (~last 5 days) are available "
                "— arXiv provides no URL for arbitrary older days."
            ),
        )
        if choice != "All days":
            selected_days = [choice]

    papers = ad.filter_papers(
        fetched,
        include_replacements=cfg().include_replacements,
        days=selected_days,
    )
    hidden = len(fetched) - len(papers)
    if not papers:
        st.warning("No papers left after filtering. Adjust the day or replacement filter.")
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

    caption = (
        f"Showing {len(filtered)} of {len(entries)} ranked "
        f"(out of {len(papers)} shown / {len(fetched)} fetched)."
    )
    if hidden:
        caption += f" {hidden} hidden by replacement/day filters."
    st.caption(caption)
    st.markdown(_PAPER_CSS, unsafe_allow_html=True)

    for e in filtered:
        with st.container(border=True):
            head, score_col = st.columns([5, 1])
            with head:
                kw_bonus = cfg().weights.core_keyword
                lp_pen = cfg().weights.low_priority_penalty
                if cfg().highlight_terms_title:
                    title_html = _highlight_terms(
                        e["title"], cfg().core_keywords, cfg().low_priority_kw, kw_bonus, lp_pen
                    )
                else:
                    title_html = html.escape(e["title"])
                st.markdown(
                    f'<div class="paper-title">{e["rank"]}. {title_html}</div>',
                    unsafe_allow_html=True,
                )
                if cfg().highlight_authors:
                    authors_html = _authors_html(
                        e["authors"], cfg().named_authors, cfg().weights.named_author
                    )
                else:
                    authors_html = html.escape(e["authors"]) or "(No authors listed)"
                st.markdown(
                    f'<div class="paper-authors">{authors_html}</div>',
                    unsafe_allow_html=True,
                )
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
                abstract = paper_by_id.get(e["id"], {}).get("abstract", "") or "(unavailable)"
                if cfg().highlight_terms_abstract and abstract != "(unavailable)":
                    st.markdown(
                        f'<div class="paper-abstract">'
                        f'{_highlight_terms(abstract, cfg().core_keywords, cfg().low_priority_kw, cfg().weights.core_keyword, cfg().weights.low_priority_penalty)}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.write(abstract)


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
            _reset_widget_state(f"editor_{attr}")
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
            _reset_widget_state(f"editor_{attr}")
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
        _reset_widget_state("editor_feeds")
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

    # Subject scoring — one bonus field per configured feed (single source of
    # truth; the old quant-gas/mes-hall/quant-ph bonuses are just defaults here).
    feed_names = list(cfg().feeds)
    new_feed_weights: dict[str, int] = {}
    st.divider()
    st.markdown("**Per-feed subject bonuses**")
    st.caption(
        "Each configured feed scores this bonus when its name appears in a "
        "paper's subjects. Raise or lower per feed; 0 disables it. "
        "Add/remove feeds in the **Feeds** tab — fields here follow."
    )
    if not feed_names:
        st.info("No feeds configured. Add some in the **Feeds** tab.")
    for name in feed_names:
        new_feed_weights[name] = st.number_input(
            name,
            value=int(cfg().feed_weights.get(name, 0)),
            step=1,
            key=f"fw_{name}",
        )

    feed_keys = [f"fw_{name}" for name in feed_names]

    col_apply, col_reset = st.columns(2)
    with col_apply:
        if st.button("Apply weights", type="primary"):
            cfg().weights = ad.ScoringWeights(**new_values)
            cfg().feed_weights = {n: int(v) for n, v in new_feed_weights.items() if v}
            _reset_widget_state(*_WEIGHT_KEYS, *feed_keys)
            st.success("Weights applied.")
            st.rerun()
    with col_reset:
        if st.button("Reset to defaults"):
            cfg().weights = ad.ScoringWeights()
            cfg().feed_weights = ad._default_feed_weights()
            _reset_widget_state(*_WEIGHT_KEYS, *feed_keys)
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
                _reset_widget_state()
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
            _reset_widget_state()
            st.success("Profile imported into current session.")
            st.rerun()
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
