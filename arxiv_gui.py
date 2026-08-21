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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

import arxiv_digest as ad
import zotero_bridge as zb

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


# ────────────────────────── Zotero bridge ──────────────────────────

@st.cache_data(ttl=10, show_spinner=False)
def _zotero_available_cached() -> bool:
    """Cached reachability check for the Zotero local API (short TTL)."""
    return zb.zotero_available()


def render_zotero_status_pill() -> None:
    """Sidebar status indicator: connected vs not running."""
    ok = _zotero_available_cached()
    if ok:
        st.sidebar.markdown(
            '<span style="color:#3fb950;">● Zotero: connected</span>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            '<span style="color:#f85149;">● Zotero: not running</span>',
            unsafe_allow_html=True,
        )


@st.cache_data(ttl=30, show_spinner=False)
def _zotero_collections_cached() -> list[dict]:
    """Cached list of Zotero collections (short TTL so new ones appear)."""
    return zb.list_collections()


def _do_zotero_save(arxiv_id: str, title: str) -> None:
    """Callback for the Save button — runs exactly once per click.

    Performs the save and records the outcome in session state so the render
    can display it. Guarded so each paper saves at most once per session and a
    double-click can't trigger a second write.
    """
    if arxiv_id in st.session_state.saved_papers:
        return
    if arxiv_id in st.session_state.zotero_saving:
        return  # a save is already in flight for this paper
    st.session_state.zotero_saving.add(arxiv_id)

    # Resolve the chosen collection name -> key from the cached list.
    collection_key = None
    chosen = st.session_state.get(f"zotero_col_{arxiv_id}")
    if chosen and chosen != "My Library":
        collection_key = next(
            (c["key"] for c in _zotero_collections_cached() if c["name"] == chosen), None
        )

    try:
        result = zb.save_to_zotero(arxiv_id, collection_key=collection_key)
    except Exception as exc:  # noqa: BLE001 - surface any bridge failure
        st.session_state[f"zotero_result_{arxiv_id}"] = ("error", f"Zotero save failed: {exc}")
        st.session_state.zotero_saving.discard(arxiv_id)
        return

    if result.get("ok"):
        st.session_state.saved_papers.add(arxiv_id)
        st.session_state[f"zotero_result_{arxiv_id}"] = ("ok", title)
    elif result.get("already_exists"):
        # Already in the library — treat as saved so we stop trying.
        st.session_state.saved_papers.add(arxiv_id)
        st.session_state[f"zotero_result_{arxiv_id}"] = ("ok", title)
    else:
        st.session_state[f"zotero_result_{arxiv_id}"] = (
            "error", result.get("error", "Zotero save failed."),
        )
    st.session_state.zotero_saving.discard(arxiv_id)


def _render_zotero_save_button(arxiv_id: str, title: str) -> None:
    """A 'Save to Zotero' popover next to a paper, like the Zotero Connector.

    Opens a popover listing the user's Zotero collections (plus 'My Library').
    Saving runs via an on_click callback (exactly once per click) and is guarded
    so each paper saves at most once per session. The confirmation toast
    auto-dismisses after 10s.
    """
    if arxiv_id in st.session_state.saved_papers:
        st.caption("Saved ✓")
        return

    with st.popover("Save to Zotero", width="stretch"):
        st.caption("Choose a collection, then save.")
        collections = _zotero_collections_cached()
        # Filter-as-you-type search bar at the top of the dropdown.
        search = st.text_input(
            "Search collections", placeholder="Filter…", key=f"zotero_search_{arxiv_id}"
        ).strip().lower()
        if search:
            collections = [c for c in collections if search in c["name"].lower()]
        options = ["My Library"] + [c["name"] for c in collections]
        st.selectbox("Collection", options=options, key=f"zotero_col_{arxiv_id}")
        st.button(
            "Save",
            key=f"zotero_do_{arxiv_id}",
            type="primary",
            on_click=_do_zotero_save,
            args=(arxiv_id, title),
        )

        # Show the outcome of the last save attempt for this paper, once —
        # the result is popped so an unrelated rerun with the popover still
        # open doesn't keep re-firing the "Saved" toast (which looked like
        # the paper was being saved over and over).
        result = st.session_state.pop(f"zotero_result_{arxiv_id}", None)
        if result:
            kind, msg = result
            if kind == "ok":
                st.toast(f"Saved to Zotero: {msg}", duration=10000)
            else:
                st.error(msg)


# ────────────────────────── Fetching with cache ──────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_papers_cached(timeframe: str, feeds_key: Tuple[Tuple[str, str], ...]) -> list[dict]:
    """Cached fetch keyed on (timeframe, sorted feed URLs).

    feeds_key is a tuple of (name, url) pairs because lists/dicts aren't hashable.

    `today` uses the HTML /new feed (unchanged). `pastweek` uses the arXiv export
    API with a true 7-day date-range window, because arXiv's /pastweek HTML
    listing is unreliable (it returns 1–5 days, not a guaranteed week).
    """
    if timeframe == "pastweek":
        end = datetime.now()
        start = end - timedelta(days=7)
        all_papers: list[dict] = []
        seen: set[str] = set()
        for name, _ in feeds_key:
            for p in ad.fetch_feed_api(name, start, end):
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                all_papers.append(p)
        return all_papers

    # today: HTML /new feed
    urls = []
    for _, base_url in feeds_key:
        url = (
            base_url.replace("/new", "/new")
            .replace("/recent", "/new")
            .replace("/pastweek", "/new")
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
    if "saved_papers" not in st.session_state:
        st.session_state.saved_papers = set()
    if "zotero_saving" not in st.session_state:
        st.session_state.zotero_saving = set()


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

        st.caption("Highlight colors (per aspect)")
        cfg().color_keyword = st.color_picker(
            "Keywords", value=cfg().color_keyword, key="color_keyword"
        )
        cfg().color_low_priority = st.color_picker(
            "Low priority", value=cfg().color_low_priority, key="color_low_priority"
        )
        cfg().color_author = st.color_picker(
            "Authors", value=cfg().color_author, key="color_author"
        )
        cfg().color_subject = st.color_picker(
            "Subjects", value=cfg().color_subject, key="color_subject"
        )
        st.caption("Also tint the font with the aspect color:")
        cfg().color_font_keyword = st.checkbox(
            "Font: keywords", value=cfg().color_font_keyword, key="color_font_keyword"
        )
        cfg().color_font_low_priority = st.checkbox(
            "Font: low priority", value=cfg().color_font_low_priority, key="color_font_low_priority"
        )
        cfg().color_font_author = st.checkbox(
            "Font: authors", value=cfg().color_font_author, key="color_font_author"
        )
        cfg().color_font_subject = st.checkbox(
            "Font: subjects", value=cfg().color_font_subject, key="color_font_subject"
        )
        st.caption(
            "Colors apply live in this session and persist when you save a "
            "profile or write the project config."
        )

        st.divider()
        st.subheader("Zotero")
        render_zotero_status_pill()
        st.caption(
            "Save papers to your Zotero library via the local API. Requires the "
            "Zotero desktop app to be running."
        )


# ────────────────────────── Tab: Papers ──────────────────────────

_PAPER_CSS = """
<style>
.paper-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; margin: 0 0 .15rem 0; }
.paper-authors { font-size: 1.02rem; color: #e6edf3; margin: 0 0 .25rem 0; }
.paper-meta { font-size: .9rem; color: #8b949e; margin: .25rem 0 0 0; }
.paper-meta a { color: #58a6ff; text-decoration: none; }
.paper-meta a:hover { text-decoration: underline; }
.paper-authors .hl-author {
  font-weight: 700; border-bottom: 1px dotted; cursor: help; padding: 0 1px;
  border-radius: 3px; transition: background .12s;
}
.paper-authors .hl-author:hover { background: rgba(127,127,127,.18); }
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
/* Light hover-highlight for matched keywords / low-priority terms (subtler than authors).
   Colors are applied inline per-aspect from the config; only structure lives here. */
.hl-term { position: relative; cursor: help; border-radius: 3px; padding: 0 1px;
  border-bottom: 1px dotted transparent; transition: background .12s; }
.hl-term:hover { background: rgba(127,127,127,.18); }
.hl-term .hl-tip {
  visibility: hidden; opacity: 0; transition: opacity .12s;
  position: absolute; z-index: 1000; bottom: 145%; left: 0;
  background: #1f2630; color: #e6edf3; padding: 4px 7px; border-radius: 6px;
  width: max-content; max-width: 260px; font-size: .75rem; font-weight: 400;
  line-height: 1.3; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,.45);
  white-space: normal;
}
.hl-term:hover .hl-tip { visibility: visible; opacity: 1; }
/* Subject highlight (feed-name matches) — color applied inline. */
.hl-subject { position: relative; cursor: help; border-radius: 3px; padding: 0 1px;
  border-bottom: 1px dotted transparent; transition: background .12s; }
.hl-subject:hover { background: rgba(127,127,127,.18); }
.hl-subject .hl-tip {
  visibility: hidden; opacity: 0; transition: opacity .12s;
  position: absolute; z-index: 1000; bottom: 145%; left: 0;
  background: #1f2630; color: #e6edf3; padding: 4px 7px; border-radius: 6px;
  width: max-content; max-width: 260px; font-size: .75rem; font-weight: 400;
  line-height: 1.3; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,.45);
  white-space: normal;
}
.hl-subject:hover .hl-tip { visibility: visible; opacity: 1; }
</style>
"""


def _highlight_terms(
    text: str,
    keywords: list[str],
    lp_terms: list[str],
    kw_bonus: int,
    lp_penalty: int,
    word_boundary: bool = True,
    color_kw: str = "#388bfd",
    color_lp: str = "#f85149",
    font_kw: bool = False,
    font_lp: bool = False,
) -> str:
    """HTML-escape `text` and wrap matched keyword / low-priority spans.

    Keywords use `color_kw`, low-priority `color_lp`, each with a hover tooltip
    showing its weight. When `font_kw` / `font_lp` is True, the matched text's
    font is also tinted with the aspect color. Overlapping matches are resolved
    earliest-start, longest-first. Matching mirrors the scorer
    (`ad.term_pattern`), so highlights and score stay in sync.
    """
    spans: list[tuple[int, int, str]] = []
    for terms, kind in ((keywords, "kw"), (lp_terms, "lp")):
        for t in terms:
            pat = ad.term_pattern(t, word_boundary=word_boundary)
            if pat is None:
                continue
            for m in pat.finditer(text):
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
            color = color_kw
            font = font_kw
        else:
            tip = f"low-priority term ({lp_penalty})"
            color = color_lp
            font = font_lp
        style = f"background:{_rgba(color, .10)};border-bottom-color:{color};"
        if font:
            style += f"color:{color};"
        out.append(
            f'<span class="hl-term" style="{style}">{frag}'
            f'<span class="hl-tip">{tip}</span></span>'
        )
        i = end
    out.append(html.escape(text[i:]))
    return "".join(out)


def _rgba(hex_color: str, alpha: float) -> str:
    """Convert a `#rrggbb` hex color to an `rgba(r,g,b,a)` string."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _authors_html(
    authors: str,
    named: list[str],
    bonus: int,
    word_boundary: bool = True,
    color: str = "#3fb950",
    font: bool = True,
) -> str:
    """Render the author line, highlighting authors present in `named`.

    Matching mirrors the scorer so a named author 'ma' no longer lights up
    'Mao' and 'bloch' no longer lights up 'Blochwitz'. The author font is
    tinted with `color` when `font` is True (the default, matching the original
    behavior).
    """
    parts = [a.strip() for a in authors.split(",") if a.strip()]
    out = []
    for a in parts:
        esc = html.escape(a)
        if any(ad.term_matches(n, a, word_boundary=word_boundary) for n in named):
            style = f"border-bottom-color:{color};"
            if font:
                style += f"color:{color};"
            out.append(
                f'<span class="hl-author" style="{style}" title="Highlighted author '
                f'(+{bonus} to score)">{esc}</span>'
            )
        else:
            out.append(esc)
    return ", ".join(out) or "(No authors listed)"


def _highlight_subjects(
    subjects: str, feed_weights: dict, color: str = "#a371f7", font: bool = False
) -> str:
    """Render the subjects line, highlighting feed names that carry a bonus.

    Matching mirrors the scorer: each feed name whose (lowercased) name appears
    in the subjects string is highlighted with the subject aspect color and a
    tooltip showing its bonus. When `font` is True, the matched text's font is
    also tinted with the aspect color.
    """
    if not subjects:
        return html.escape(subjects)
    spans: list[tuple[int, int, str]] = []
    for name, w in (feed_weights or {}).items():
        if not w:
            continue
        low = name.lower()
        start = 0
        while True:
            idx = subjects.lower().find(low, start)
            if idx == -1:
                break
            spans.append((idx, idx + len(name), name, w))
            start = idx + len(name)
    if not spans:
        return html.escape(subjects)

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen: list[tuple[int, int, str, int]] = []
    last_end = -1
    for s in spans:
        if s[0] >= last_end:
            chosen.append(s)
            last_end = s[1]

    out: list[str] = []
    i = 0
    for start, end, name, w in chosen:
        out.append(html.escape(subjects[i:start]))
        frag = html.escape(subjects[start:end])
        style = f"background:{_rgba(color, .10)};border-bottom-color:{color};"
        if font:
            style += f"color:{color};"
        out.append(
            f'<span class="hl-subject" style="{style}">{frag}'
            f'<span class="hl-tip">subject bonus (+{w})</span></span>'
        )
        i = end
    out.append(html.escape(subjects[i:]))
    return "".join(out)


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
                        e["title"], cfg().core_keywords, cfg().low_priority_kw, kw_bonus, lp_pen,
                        word_boundary=cfg().word_boundary_matching,
                        color_kw=cfg().color_keyword, color_lp=cfg().color_low_priority,
                        font_kw=cfg().color_font_keyword, font_lp=cfg().color_font_low_priority,
                    )
                else:
                    title_html = html.escape(e["title"])
                st.markdown(
                    f'<div class="paper-title">{e["rank"]}. {title_html}</div>',
                    unsafe_allow_html=True,
                )
                if cfg().highlight_authors:
                    authors_html = _authors_html(
                        e["authors"], cfg().named_authors, cfg().weights.named_author,
                        word_boundary=cfg().word_boundary_matching,
                        color=cfg().color_author, font=cfg().color_font_author,
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
                if e["subjects"] or e["link"]:
                    meta_parts = []
                    if e["link"]:
                        meta_parts.append(f'<a href="{e["link"]}" target="_blank">arXiv ↗</a>')
                    if e["subjects"]:
                        subjects_html = _highlight_subjects(
                            e["subjects"], cfg().feed_weights, color=cfg().color_subject,
                            font=cfg().color_font_subject,
                        )
                        meta_parts.append(f'<span class="paper-subjects">Subjects: {subjects_html}</span>')
                    st.markdown(
                        '<div class="paper-meta">' + " &nbsp;·&nbsp; ".join(meta_parts) + "</div>",
                        unsafe_allow_html=True,
                    )
            with score_col:
                st.metric("Score", e["score"])
                _render_zotero_save_button(e["id"], e["title"])

            with st.expander("Why this score?"):
                full_paper = paper_by_id.get(e["id"], {})
                breakdown = ad.explain_score(full_paper, cfg())
                _render_breakdown(breakdown)
            with st.expander("Full abstract"):
                abstract = paper_by_id.get(e["id"], {}).get("abstract", "") or "(unavailable)"
                if cfg().highlight_terms_abstract and abstract != "(unavailable)":
                    st.markdown(
                        f'<div class="paper-abstract">'
                        f'{_highlight_terms(abstract, cfg().core_keywords, cfg().low_priority_kw, cfg().weights.core_keyword, cfg().weights.low_priority_penalty, word_boundary=cfg().word_boundary_matching, color_kw=cfg().color_keyword, color_lp=cfg().color_low_priority, font_kw=cfg().color_font_keyword, font_lp=cfg().color_font_low_priority)}'
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

    cfg().word_boundary_matching = st.checkbox(
        "Whole-word matching",
        value=cfg().word_boundary_matching,
        help=(
            "Match keywords / authors / low-priority terms as whole words, so "
            "'mpo' won't score 'temporal' and author 'ma' won't score 'Mao'. "
            "Uncheck for legacy substring matching. Subjects are unaffected."
        ),
    )
    st.divider()

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

    # ── Starter presets: built-in read-only topic bundles ────────────────
    st.markdown("**Starter presets**")
    st.caption(
        "Built-in topic bundles (keywords + authors + feeds) to start from. "
        "**Load** replaces your working config; **Add** merges the preset in. "
        "Your saved profiles and `arxiv_config.json` are never touched — Load/Add "
        "change only the in-memory config until you Save or Write project config."
    )
    preset_choice = st.selectbox(
        "Starter preset",
        options=ad.preset_names(),
        format_func=lambda n: n.replace("-", " ").title(),
        key="starter_preset",
        label_visibility="collapsed",
    )
    st.caption(ad.preset_description(preset_choice))
    pc_load, pc_add = st.columns(2)
    if pc_load.button("Load preset", key="preset_load", width="stretch"):
        st.session_state.cfg = ad.preset_config(preset_choice)
        _reset_widget_state()
        st.success(f"Loaded preset '{preset_choice}' (replaced working config).")
        st.rerun()
    if pc_add.button("Add preset", key="preset_add", width="stretch"):
        st.session_state.cfg = ad.merge_preset(cfg(), preset_choice)
        _reset_widget_state()
        st.success(f"Merged preset '{preset_choice}' into the current config.")
        st.rerun()

    st.divider()

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


# ────────────────────────── Tab: Score a paper ──────────────────────────

def _paper_from_atom(entry) -> dict:
    """Build a paper dict (compatible with `explain_score`) from an arXiv Atom entry."""
    _ATOM = "{http://www.w3.org/2005/Atom}"

    def text(tag: str) -> str:
        node = entry.find(f"{_ATOM}{tag}")
        return (node.text or "").strip() if node is not None and node.text else ""

    authors = ", ".join(
        (a.find(f"{_ATOM}name").text or "").strip()
        for a in entry.findall(f"{_ATOM}author")
        if a.find(f"{_ATOM}name") is not None and a.find(f"{_ATOM}name").text
    )
    subjects = ", ".join(
        c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")
    )
    versioned_url = text("id")
    arxiv_url = re.sub(r"v\d+$", "", versioned_url)
    article_id = arxiv_url.rsplit("/abs/", 1)[-1] if "/abs/" in arxiv_url else ""
    return {
        "id": article_id,
        "title": text("title"),
        "authors": authors,
        "abstract": text("summary"),
        "subjects": subjects,
        "link": arxiv_url,
        "section": "",
    }


def _absence_reason(paper_id: str, fetched: list[dict], cfg: ad.Config) -> str:
    """Explain deterministically why a paper is not in the current digest.

    Distinguishes 'fetched but below top-N' from 'never fetched', and for the
    latter checks the paper's actual submission date against the days present
    in the fetched feed and its categories against the subscribed feeds.
    """
    fetched_ids = {p.get("id") for p in fetched}
    if paper_id in fetched_ids:
        # It was fetched; it must have ranked below top_n (or been filtered).
        return (
            f"This paper **was** fetched in the current digest but ranked below "
            f"your top-{cfg.top_n} cutoff (or was filtered out by the "
            f"replacement/day filters)."
        )

    # Not in the fetched set — fetch its metadata to reason deterministically.
    try:
        entry = zb.fetch_arxiv_atom(paper_id)
    except Exception:  # noqa: BLE001 - network failure shouldn't crash the tab
        return (
            "Could not reach arXiv to compare this paper against the digest "
            "(network error). Try again in a moment."
        )
    if entry is None:
        return "Could not fetch this paper's metadata from arXiv to compare feeds."
    _ATOM = "{http://www.w3.org/2005/Atom}"
    cats = [c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")]

    # Paper's submission date (YYYY-MM-DD from the Atom <published>).
    pub_node = entry.find(f"{_ATOM}published")
    pub_date = None
    if pub_node is not None and pub_node.text:
        pub_date = pub_node.text.strip()[:10]

    # Days actually present in the fetched feed.
    day_labels = ad.available_day_labels(fetched)
    day_dates = set()
    for lbl in day_labels:
        try:
            day_dates.add(datetime.strptime(lbl, "%a, %d %b %Y").date().isoformat())
        except ValueError:
            pass

    feed_names = [f.lower() for f in cfg.feeds]
    matched = [c for c in cats if any(c.lower().startswith(f) for f in feed_names)]

    reasons = []
    if pub_date and day_dates:
        if pub_date not in day_dates:
            reasons.append(
                f"it was submitted on **{pub_date}**, but the fetched feed only "
                f"covers **{', '.join(sorted(day_dates))}**"
            )
        else:
            reasons.append(
                f"it was submitted on **{pub_date}**, which IS within the fetched "
                f"days — so it was likely not yet listed in the feed pages when "
                f"you fetched"
            )
    elif pub_date:
        reasons.append(f"it was submitted on **{pub_date}**")

    if matched:
        reasons.append(
            f"its categories (**{', '.join(matched)}**) overlap your subscribed feeds"
        )
    else:
        reasons.append(
            f"its categories (**{', '.join(cats) or 'unknown'}**) are **not among "
            f"your subscribed feeds** ({', '.join(cfg.feeds) or 'none'})"
        )

    return (
        "This paper was **not in the fetched set**. Deterministic check: "
        + "; ".join(reasons)
        + "."
    )


def render_score_tab():
    st.subheader("Score a paper")
    st.caption(
        "Paste an arXiv link or ID to see how it would score under your current "
        "config, and why it did (or didn't) appear in the digest."
    )
    raw = st.text_input(
        "arXiv link or ID",
        placeholder="https://arxiv.org/abs/2607.21663  or  2607.21663",
    )
    if not raw.strip():
        return

    paper_id = zb.arxiv_id_from_input(raw)
    if not paper_id:
        st.error("Could not parse an arXiv id from that input.")
        return

    if st.button("Score this paper", type="primary"):
        try:
            entry = zb.fetch_arxiv_atom(paper_id)
        except Exception as exc:  # noqa: BLE001 - surface network failures
            st.error(f"Failed to fetch paper: {exc}")
            return
        if entry is None:
            st.error(f"No arXiv paper found for id '{paper_id}'.")
            return

        paper = _paper_from_atom(entry)
        breakdown = ad.explain_score(paper, cfg())
        st.markdown(f"### {paper['title']}")
        st.write(paper["authors"])
        if paper["subjects"]:
            st.caption(f"Subjects: {paper['subjects']}")
        st.metric("Score", breakdown["total"])
        _render_breakdown(breakdown)

        # Absence / presence explanation relative to the current digest.
        fetched = st.session_state.papers
        if fetched:
            st.divider()
            st.markdown("**Why it did / didn't appear in the digest**")
            if paper_id in {p.get("id") for p in fetched}:
                entries = ad.build_ranked_entries(fetched, cfg(), top_n=cfg().top_n)
                rank = next(
                    (e["rank"] for e in entries if e["id"] == paper_id), None
                )
                if rank is not None:
                    st.success(
                        f"This paper **is** in the current digest at rank **#{rank}** "
                        f"with score **{breakdown['total']}**."
                    )
                else:
                    st.info(_absence_reason(paper_id, fetched, cfg()))
            else:
                st.info(_absence_reason(paper_id, fetched, cfg()))
        else:
            st.caption("Fetch papers first to compare against the current digest.")

        st.divider()
        _render_zotero_save_button(paper_id, paper["title"])


# ────────────────────────── Main ──────────────────────────

def main():
    st.set_page_config(page_title="arXiv Digest", layout="wide")
    init_state()
    render_sidebar()

    tab_papers, tab_score, tab_kw, tab_authors, tab_lp, tab_feeds, tab_scoring, tab_profiles = st.tabs(
        ["Papers", "Score a paper", "Keywords", "Authors", "Low priority", "Feeds", "Scoring", "Profiles"]
    )
    with tab_papers:
        render_papers_tab()
    with tab_score:
        render_score_tab()
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
