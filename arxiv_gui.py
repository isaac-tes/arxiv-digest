"""Streamlit GUI for the arXiv digest tool.

Run with:
    uv run streamlit run arxiv_gui.py

Imports `arxiv_digest` directly so all fetch / score / format logic stays in
one place. The CLI flow (`python arxiv_digest.py ...`) is unaffected.
"""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd
import streamlit as st

import arxiv_digest as ad
import zotero_bridge as zb

PROFILES_DIR = Path.home() / ".arxiv_scraper" / "profiles"
ACTIVE_PROFILE_PATH = Path.home() / ".arxiv_scraper" / "active_profile.txt"
REMOVED_PAPERS_PATH = Path.home() / ".arxiv_scraper" / "removed_papers.json"
REMOVED_DIR = Path.home() / ".arxiv_scraper" / "removed"
PROJECT_CONFIG = ad.DEFAULT_CONFIG_PATH


# ────────────────────────── Profile management ──────────────────────────

def _validate_profile_name(name: str) -> str:
    if (
        not name
        or name != name.strip()
        or name in {".", "..", "(unsaved)"}
        or any(char in name for char in ("/", "\\", ":", "\0"))
    ):
        raise ValueError("Profile names must be a single path-free file name.")
    return name


def list_profiles() -> list[str]:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles: list[str] = []
    for path in PROFILES_DIR.glob("*.json"):
        try:
            _validate_profile_name(path.stem)
        except ValueError:
            continue
        profiles.append(path.stem)
    return sorted(profiles)


def save_profile(cfg: ad.Config, name: str) -> Path:
    name = _validate_profile_name(name)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target = PROFILES_DIR / f"{name}.json"
    cfg.dump(target)
    return target


def load_profile(name: str) -> ad.Config:
    name = _validate_profile_name(name)
    return ad.Config.load(PROFILES_DIR / f"{name}.json")


def _saved_active_profile() -> str | None:
    try:
        name = _validate_profile_name(
            ACTIVE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        )
    except (OSError, UnicodeError, ValueError):
        return None
    return name if name in list_profiles() else None


def _persist_active_profile(name: str | None) -> None:
    if name is None:
        ACTIVE_PROFILE_PATH.unlink(missing_ok=True)
        return
    name = _validate_profile_name(name)
    ACTIVE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=ACTIVE_PROFILE_PATH.parent,
        prefix=f".{ACTIVE_PROFILE_PATH.stem}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(name)
        os.replace(tmp, ACTIVE_PROFILE_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _set_loaded_profile(name: str | None) -> None:
    _persist_active_profile(name)
    st.session_state.loaded_profile = name
    st.session_state.reset_active_profile_widget = True


def delete_profile(name: str) -> None:
    name = _validate_profile_name(name)
    (PROFILES_DIR / f"{name}.json").unlink(missing_ok=True)
    with _removed_ids_lock():  # else an in-flight update could recreate the list
        removed_papers_path(name).unlink(missing_ok=True)


# ────────────────────────── Removed papers ──────────────────────────

def removed_papers_path(profile: str | None) -> Path:
    """Each profile has its own removal list; with no profile loaded, a shared one."""
    if profile is None:
        return REMOVED_PAPERS_PATH
    return REMOVED_DIR / f"{_validate_profile_name(profile)}.json"


@st.cache_resource
def _removed_ids_lock() -> threading.RLock:
    """One lock shared by every session of this server for the removal files.

    Each browser tab is a session running in its own thread of the same
    process. Streamlit re-executes this script on every rerun, so a plain
    module-level lock would be a new object each time; cache_resource keeps one.
    """
    return threading.RLock()


def _read_removed_ids(profile: str | None) -> set[str]:
    """Strict read: a missing file is an empty list, any other failure raises."""
    try:
        text = removed_papers_path(profile).read_text()
    except FileNotFoundError:
        return set()
    ids = json.loads(text)
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError("expected a JSON list of arXiv IDs")
    return set(ids)


def load_removed_ids(profile: str | None) -> set[str]:
    """IDs of papers the user removed from the digest under `profile`.

    Kept on disk so a removal survives page reloads, app restarts, and later
    fetches (a paper removed from a daily ranking stays out of the weekly one).
    For display, an unreadable file means nothing has been removed.
    """
    with _removed_ids_lock():
        try:
            return _read_removed_ids(profile)
        except (OSError, ValueError):
            return set()


def save_removed_ids(profile: str | None, ids: set[str]) -> None:
    # Write a uniquely named temp file, then rename it over the list: an
    # interrupted save never truncates the only copy, and writers never share
    # a temp file.
    path = removed_papers_path(profile)
    with _removed_ids_lock():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(sorted(ids), indent=2))
                fh.flush()
                os.fsync(fh.fileno())  # data on disk before the rename, or a crash can leave it empty
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def update_removed_ids(
    profile: str | None, *, add: Iterable[str] = (), discard: Iterable[str] = ()
) -> None:
    """Add/discard IDs in `profile`'s list as one read-modify-write under the lock,
    so removals made at the same moment in two browser tabs are both kept.

    Raises (leaving the file untouched) if the list exists but can't be read,
    rather than overwriting every earlier removal with just this change.
    """
    with _removed_ids_lock():
        save_removed_ids(profile, _read_removed_ids(profile).union(add).difference(discard))


def _update_removed_ids_or_warn(profile: str | None, **change: Iterable[str]) -> None:
    try:
        update_removed_ids(profile, **change)
    except (OSError, ValueError) as exc:
        st.toast(
            f"Couldn't update `{removed_papers_path(profile)}` ({exc}). "
            "Nothing was changed; fix or delete the file.",
            icon="⚠️",
        )


def _copy_removed_ids_or_warn(source: str | None, target: str) -> bool:
    """Make `target`'s removal list an exact copy of `source`'s (Save as = snapshot)."""
    with _removed_ids_lock():
        try:
            save_removed_ids(target, _read_removed_ids(source))
        except (OSError, ValueError) as exc:
            st.toast(
                f"Couldn't copy removals to profile `{target}` ({exc}). "
                "Nothing was saved; fix or delete the file.",
                icon="⚠️",
            )
            return False
        return True


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


_NO_COLLECTION = "(no collection)"


def _zotero_collection_options() -> list[str]:
    """Labels for the personal-library collection dropdown."""
    return [_NO_COLLECTION] + [c["name"] for c in _zotero_collections_cached()]


def _zotero_collection_key_for(name: str) -> str | None:
    """Map a personal-library collection label to its key."""
    if name == _NO_COLLECTION:
        return None
    for c in _zotero_collections_cached():
        if c["name"] == name:
            return c["key"]
    return None


# How long the transient "Saved ✓" indicator stays visible after a save, and
# the auto-re-run interval used to retire it. The fragment timer is only live
# while a tick is fresh, so idle papers carry no recurring work.
SAVED_TICK_SECONDS = 30.0
FRAGMENT_RERUN_SECONDS = 10.0


def _zotero_tick_is_fresh(saved_at: float | None, now: float | None = None) -> bool:
    """Whether a saved timestamp is still within the "Saved ✓" window.

    ``None`` (never saved) is never fresh. ``now`` defaults to ``time.monotonic()``
    but is injectable for deterministic tests.
    """
    if saved_at is None:
        return False
    now = time.monotonic() if now is None else now
    return (now - saved_at) < SAVED_TICK_SECONDS


def _set_zotero_saved(arxiv_id: str) -> None:
    """Record a successful save so the transient 'Saved ✓' tick shows."""
    if "zotero_saved_at" not in st.session_state:
        st.session_state.zotero_saved_at = {}
    st.session_state.zotero_saved_at[arxiv_id] = time.monotonic()


def _do_zotero_save(arxiv_id: str, title: str, col_key: str | None = None) -> None:
    """Callback for the Save button — runs exactly once per click.

    Saves to the user's **personal** Zotero library via the local bridge (the
    fast, no-key path that pops Zotero's own "Allow this application?" dialog).
    Records a transient outcome so the render can show it. A denied/failed save
    is stored as an error and must never show a success toast.
    """
    if arxiv_id in st.session_state.zotero_saving:
        return  # a save is already in flight for this paper
    st.session_state.zotero_saving.add(arxiv_id)
    # A retry supersedes any outcome still waiting to be rendered.
    st.session_state.pop(f"zotero_result_{arxiv_id}", None)

    collection = st.session_state.get(col_key or f"zotero_col_card_{arxiv_id}", _NO_COLLECTION)
    collection_key = _zotero_collection_key_for(collection)

    try:
        result = zb.save_to_zotero(arxiv_id, collection_key=collection_key)
    except Exception as exc:  # noqa: BLE001 - surface any bridge failure
        st.session_state[f"zotero_result_{arxiv_id}"] = ("error", f"Zotero save failed: {exc}")
        st.session_state.zotero_saving.discard(arxiv_id)
        return

    if result.get("ok") or result.get("already_exists"):
        # Success (or already present) — record the transient 'Saved ✓' tick.
        # The tick, not a lingering one-shot, is the success indicator, so a
        # later rerun can never fire a stale 'Saved to Zotero:' toast.
        _set_zotero_saved(arxiv_id)
    else:
        st.session_state[f"zotero_result_{arxiv_id}"] = (
            "error", result.get("error", "Zotero save failed."),
        )
    st.session_state.zotero_saving.discard(arxiv_id)


def _zotero_saved_at(arxiv_id: str) -> float | None:
    """Return the recorded save timestamp for a paper, or None if never saved."""
    records = st.session_state.zotero_saved_at if "zotero_saved_at" in st.session_state else {}
    return records.get(arxiv_id)


def _render_zotero_save_button(arxiv_id: str, title: str, scope: str = "card") -> None:
    """A 'Save to Zotero' popover next to a paper, like the Zotero Connector.

    Opens a popover with a **Collection** dropdown for the personal My Library
    and a Save button. Group-library saving is intentionally not offered because
    Zotero's local API has no supported group-library route. After a successful save a transient 'Saved ✓' caption replaces the
    popover for ``SAVED_TICK_SECONDS``; it then returns on its own because the
    decorative fragment carries a ``run_every`` auto-re-run while the tick is
    fresh. The timer is only registered while the tick is fresh, so idle papers
    carry no recurring background work (the small residue after a tick expires
    is dropped on the next full re-render).
    """
    fresh_tick = _zotero_tick_is_fresh(_zotero_saved_at(arxiv_id))
    # Keys carry the tab (`scope`): Streamlit renders every tab on each run, so a
    # paper shown on its card and in Score a paper would otherwise reuse keys.
    col_key = f"zotero_col_{scope}_{arxiv_id}"

    @st.fragment(run_every=f"{FRAGMENT_RERUN_SECONDS}s" if fresh_tick else None)
    def _tick_or_popover() -> None:
        # Consume the pending result before the fresh-tick early return. The
        # old implementation popped inside the popover, so an error/success
        # could linger unseen and a stale success toast appeared seconds later.
        result = st.session_state.pop(f"zotero_result_{arxiv_id}", None)
        if result:
            kind, msg = result
            if kind == "error":
                st.error(msg)

        if _zotero_tick_is_fresh(_zotero_saved_at(arxiv_id)):
            st.caption("Saved ✓")
            return

        with st.popover("Save to Zotero", width="stretch"):
            st.caption("Choose a collection, then save to My Library.")
            st.selectbox(
                "Collection",
                options=_zotero_collection_options(),
                key=col_key,
            )
            st.button(
                "Save",
                key=f"zotero_do_{scope}_{arxiv_id}",
                type="primary",
                on_click=_do_zotero_save,
                args=(arxiv_id, title, col_key),
            )

    _tick_or_popover()


# ────────────────────────── Fetching with cache ──────────────────────────

def _pastweek_feeds_to_fetch(feeds_key: Tuple[Tuple[str, str], ...]) -> list[str]:
    """Return every selected category for the export-API fetch.

    The export API's ``cat:cond-mat`` query is *not* a wildcard for dotted
    subcategories such as ``cond-mat.quant-gas``. Keep parent and child feeds
    here; :func:`arxiv_digest.fetch_pastweek` deduplicates overlapping papers by
    arXiv id after querying each category.
    """
    return [name for name, _ in feeds_key]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_papers_cached(
    timeframe: str, feeds_key: Tuple[Tuple[str, str], ...]
) -> tuple[list[dict], list[str]]:
    """Cached fetch keyed on (timeframe, sorted feed URLs).

    feeds_key is a tuple of (name, url) pairs because lists/dicts aren't hashable.

    `today` uses the HTML /new feed (unchanged). `pastweek` uses the arXiv export
    API with a true 7-day date-range window, because arXiv's /pastweek HTML
    listing is unreliable (it returns 1–5 days, not a guaranteed week).
    """
    # Persistent disk cache (survives restarts, keyed on the UTC day) sits under
    # the in-memory st.cache_data layer, so re-selecting the same feeds — even
    # after restarting the app — reuses saved papers instead of re-hitting arXiv
    # and tripping the rate limiter.
    feed_names = [name for name, _ in feeds_key]
    cache_key = ad._fetch_cache_key(timeframe, feed_names)
    cached = ad.load_fetch_cache(cache_key)
    if cached is not None:
        return cached, []

    if timeframe == "pastweek":
        end = datetime.now(UTC)
        start = end - timedelta(days=7)
        to_fetch = _pastweek_feeds_to_fetch(feeds_key)
        notices: list[str] = []
        papers = ad.fetch_pastweek(to_fetch, start, end, notices=notices)
        ad.save_fetch_cache(cache_key, papers)
        return papers, notices

    # today: HTML /new feed
    urls = []
    for _, base_url in feeds_key:
        urls.append(ad.feed_url(base_url, "today"))
    papers = ad.fetch_feeds(urls)
    ad.save_fetch_cache(cache_key, papers)
    return papers, []


# ────────────────────────── Session state init ──────────────────────────

# Bump whenever a config default changes (eg. keyword/author font tinting
# switched to ON) so an already-open session re-applies the new defaults once,
# instead of keeping stale sidebar widget state that overrides them.
_FONT_DEFAULT_VERSION = "2"


def init_state():
    if st.session_state.pop("reset_active_profile_widget", False):
        st.session_state.pop("active_profile", None)
    if "loaded_profile" not in st.session_state:
        st.session_state.loaded_profile = _saved_active_profile()
    if "cfg" not in st.session_state:
        profile = loaded_profile()
        if profile:
            try:
                st.session_state.cfg = load_profile(profile)
            except Exception as exc:
                st.session_state.loaded_profile = None
                try:
                    _persist_active_profile(None)
                except OSError:
                    pass
                st.warning(
                    f"Couldn't load profile '{profile}' ({exc}); using project config. "
                    "Repair or delete the saved profile in the Profiles tab."
                )
                profile = None
        if not profile:
            st.session_state.cfg = ad.Config.load(
                PROJECT_CONFIG if PROJECT_CONFIG.exists() else None
            )
        st.session_state.cfg_default_version = _FONT_DEFAULT_VERSION
        # A fresh session should show the config's actual defaults (e.g. keyword
        # and author font tinting now default ON). Without this, Streamlit would
        # return a stale sidebar checkbox value from a widget key seeded earlier
        # in the session and silently overwrite the config default (the same
        # staleness _reset_widget_state guards against on profile load).
        _reset_widget_state(*_DISPLAY_KEYS)
    elif st.session_state.get("cfg_default_version") != _FONT_DEFAULT_VERSION:
        # The defaults changed while this session was already alive (Streamlit
        # keeps session_state across a hot-reload rerun). Re-apply the new
        # defaults once by clearing the display widget keys so they re-read cfg.
        st.session_state.cfg_default_version = _FONT_DEFAULT_VERSION
        _reset_widget_state(*_DISPLAY_KEYS)
    if "papers" not in st.session_state:
        st.session_state.papers = []
    if "last_fetch" not in st.session_state:
        st.session_state.last_fetch = None
    if "zotero_saved_at" not in st.session_state:
        st.session_state.zotero_saved_at = {}
    if "zotero_saving" not in st.session_state:
        st.session_state.zotero_saving = set()


def cfg() -> ad.Config:
    return st.session_state.cfg


def loaded_profile() -> str | None:
    """Name of the saved profile cfg() was last loaded from or saved to."""
    return st.session_state.get("loaded_profile")


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
# Sidebar "Display" checkboxes/color pickers — same staleness risk as weights
# and editors, but were missed when this guard was first introduced, so a
# loaded profile's colors/font toggles kept getting silently overwritten by
# whatever was already showing in the sidebar.
_DISPLAY_KEYS = [
    "highlight_authors",
    "highlight_terms_title",
    "highlight_terms_abstract",
    "highlight_terms_summary",
    "color_keyword",
    "color_low_priority",
    "color_author",
    "color_subject",
    "color_font_keyword",
    "color_font_low_priority",
    "color_font_author",
    "color_font_subject",
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
        loaded = loaded_profile()
        index = profiles.index(loaded) + 1 if loaded in profiles else 0
        active = st.selectbox(
            "Active",
            options=["(unsaved)"] + profiles,
            index=index,
            key="active_profile",
        )
        if active != "(unsaved)" and st.button("Load profile", width="stretch"):
            try:
                profile_cfg = load_profile(active)
            except Exception as exc:
                st.error(f"Couldn't load profile '{active}': {exc}")
            else:
                st.session_state.cfg = profile_cfg
                _set_loaded_profile(active)
                _reset_widget_state()
                st.success(f"Loaded {active}")
                st.rerun()
        st.caption(
            f"Loaded profile: **{loaded_profile()}**" if loaded_profile() else "No profile loaded."
        )

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
                try:
                    papers, notices = fetch_papers_cached(timeframe, feeds_key)
                    st.session_state.papers = papers
                    st.session_state.last_fetch = datetime.now()
                except ad.requests.RequestException as exc:
                    st.error(
                        f"arXiv fetch failed ({type(exc).__name__}). "
                        "arXiv may be slow or down — try again in a moment."
                    )
                else:
                    for note in notices:
                        st.warning(note)
                    st.success(f"Fetched {len(st.session_state.papers)} papers.")

        if st.session_state.last_fetch:
            st.caption(f"Last fetched: {st.session_state.last_fetch:%Y-%m-%d %H:%M:%S}")

        if st.button("Clear fetch cache", width="stretch"):
            fetch_papers_cached.clear()
            ad.clear_fetch_cache()
            st.session_state.papers = []
            st.session_state.last_fetch = None
            st.rerun()

        st.divider()
        st.subheader("Display")
        st.caption("Hover-highlight matched terms in the Papers tab.")
        cfg().highlight_authors = st.checkbox(
            "Highlight authors", value=cfg().highlight_authors,
            help="Highlight authors that appear in your Authors list.",
            key="highlight_authors",
        )
        cfg().highlight_terms_title = st.checkbox(
            "Highlight keywords in titles", value=cfg().highlight_terms_title,
            help="Light highlight of matched keywords / low-priority terms in titles.",
            key="highlight_terms_title",
        )
        cfg().highlight_terms_abstract = st.checkbox(
            "Highlight keywords in abstracts", value=cfg().highlight_terms_abstract,
            help="Light highlight of matched keywords / low-priority terms in full abstracts.",
            key="highlight_terms_abstract",
        )
        cfg().highlight_terms_summary = st.checkbox(
            "Highlight keywords in summaries", value=cfg().highlight_terms_summary,
            help="Same highlight as full abstracts, applied to the truncated abstract summary on each paper card. Off by default.",
            key="highlight_terms_summary",
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
            "Save papers to your personal Zotero library via the local API. "
            "Group-library saving is not available through Zotero's local API."
        )


# ────────────────────────── Tab: Papers ──────────────────────────

_PAPER_CSS = """
<style>
.paper-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; margin: 0 0 .15rem 0; }
.paper-authors { font-size: 1.02rem; color: #e6edf3; margin: 0 0 .25rem 0; }
.paper-meta { font-size: .9rem; color: #8b949e; margin: .25rem 0 0 0; }
.paper-meta a { color: #58a6ff; text-decoration: none; }
/* The colors above are tuned for Streamlit's dark theme (near-white/mid-grey
   on a dark background) and are barely legible on light theme's white
   background. Override just for light, so dark theme is untouched. */
@media (prefers-color-scheme: light) {
  .paper-authors { color: #24292f; }
  .paper-meta { color: #57606a; }
}
.paper-meta a:hover { text-decoration: underline; }
.paper-authors .hl-author {
  font-weight: 700; border-bottom: 1px dotted; cursor: help; padding: 0 1px;
  border-radius: 3px; transition: background .12s; position: relative;
}
.paper-authors .hl-author:hover { background: rgba(127,127,127,.18); }
.paper-authors .hl-author .hl-tip {
  visibility: hidden; opacity: 0; transition: opacity .12s;
  position: absolute; z-index: 1000; bottom: 145%; left: 0;
  background: #1f2630; color: #e6edf3; padding: 6px 9px; border-radius: 6px;
  width: max-content; max-width: 320px; font-size: .8rem; font-weight: 400;
  line-height: 1.35; border: 1px solid #30363d; box-shadow: 0 4px 12px rgba(0,0,0,.45);
  white-space: normal;
}
.paper-authors .hl-author:hover .hl-tip { visibility: visible; opacity: 1; }
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
        if any(ad.author_matches(n, a, word_boundary=word_boundary) for n in named):
            style = f"border-bottom-color:{color};"
            if font:
                style += f"color:{color};"
            out.append(
                f'<span class="hl-author" style="{style}">{esc}'
                f'<span class="hl-tip">Highlighted author (+{bonus} to score)</span></span>'
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


def _remove_paper(arxiv_id: str) -> None:
    """Callback for a card's ✕ button: hide the paper from every later ranking.

    Removed papers are dropped before ranking, so every paper below moves up one
    place and the first one past the top-N cutoff takes the freed slot.
    """
    _update_removed_ids_or_warn(loaded_profile(), add={arxiv_id})


def _restore_papers(arxiv_ids: list[str]) -> None:
    _update_removed_ids_or_warn(loaded_profile(), discard=arxiv_ids)


def _render_removed_papers(removed: list[dict]) -> None:
    """Expander listing removed papers that would otherwise be in the ranking shown."""
    if not removed:
        return
    with st.expander(f"Removed papers ({len(removed)})"):
        owner = f"profile **{loaded_profile()}**" if loaded_profile() else "no loaded profile"
        st.caption(
            "Only papers that would otherwise appear in this ranking are listed. "
            f"The removal list belongs to {owner}; other profiles keep their own. "
            "Removed papers stay hidden across reloads and later fetches "
            f"(saved in `{removed_papers_path(loaded_profile())}`)."
        )
        for p in removed:
            title_col, restore_col = st.columns([5, 1])
            title_col.write(p.get("title", "") or "(Untitled)")
            restore_col.button(
                "Restore",
                key=f"restore_{p['id']}",
                on_click=_restore_papers,
                args=([p["id"]],),
                width="stretch",
            )
        st.button(
            "Restore all",
            key="restore_all",
            on_click=_restore_papers,
            args=([p["id"] for p in removed],),
        )


def _selected_days() -> list[str] | None:
    """The Papers tab's Day picker choice (None = all days)."""
    choice = st.session_state.get("papers_day", "All days")
    return None if choice == "All days" else [choice]


def _digest(fetched: list[dict], days: list[str] | None) -> tuple[list[dict], list[dict], list[dict]]:
    """The ranking the Papers tab shows: (entries, removed, visible papers).

    Single source of truth for both the Papers and the Score-a-paper tab, so the
    two can never disagree on rank. Removed papers are skipped while walking the
    full ranking; only those met before the top N fills up are returned in
    `removed` (the ones that would be showing had they not been removed).
    """
    papers = ad.filter_papers(
        fetched, include_replacements=cfg().include_replacements, days=days
    )
    removed_ids = load_removed_ids(loaded_profile())
    entries: list[dict] = []
    removed: list[dict] = []
    for e in ad.build_ranked_entries(papers, cfg(), top_n=len(papers)):
        if len(entries) == cfg().top_n:
            break
        if e["id"] in removed_ids:
            removed.append(e)
        else:
            entries.append({**e, "rank": len(entries) + 1})
    return entries, removed, [p for p in papers if p["id"] not in removed_ids]


def render_papers_tab():
    fetched = st.session_state.papers
    if not fetched:
        st.info("Click **Fetch papers** in the sidebar to load papers.")
        return

    # Back-in-time day picker (only days arXiv's pastweek feed still lists).
    day_labels = ad.available_day_labels(fetched)
    if st.session_state.get("papers_day") not in (None, "All days", *day_labels):
        st.session_state.pop("papers_day")  # the picked day left the fetch
    if day_labels:
        st.selectbox(
            "Day",
            options=["All days"] + day_labels,
            help=(
                "Pick a single past day to see just its ranking. Only the days "
                "arXiv's pastweek feed still returns (~last 5 days) are available "
                "— arXiv provides no URL for arbitrary older days."
            ),
            key="papers_day",
        )

    entries, removed, papers = _digest(fetched, _selected_days())
    hidden = len(fetched) - len(ad.filter_papers(
        fetched, include_replacements=cfg().include_replacements, days=_selected_days()
    ))
    _render_removed_papers(removed)
    if not papers:
        st.warning(
            "No papers left after filtering. Adjust the day or replacement filter"
            + (", or restore removed papers." if removed else ".")
        )
        return

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
    if removed:
        caption += f" {len(removed)} removed by you."
    st.caption(caption)
    st.markdown(_PAPER_CSS, unsafe_allow_html=True)

    for e in filtered:
        with st.container(border=True):
            head, score_col, remove_col = st.columns([5, 1, 0.3])

            def _hl(t: str) -> str:
                return _highlight_terms(
                    t, cfg().core_keywords, cfg().low_priority_kw, kw_bonus, lp_pen,
                    word_boundary=cfg().word_boundary_matching,
                    color_kw=cfg().color_keyword, color_lp=cfg().color_low_priority,
                    font_kw=cfg().color_font_keyword, font_lp=cfg().color_font_low_priority,
                )

            with head:
                kw_bonus = cfg().weights.core_keyword
                lp_pen = cfg().weights.low_priority_penalty
                if cfg().highlight_terms_title:
                    title_html = _hl(e["title"])
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
                if cfg().highlight_terms_summary:
                    st.markdown(f'{_hl(e["summary"])}', unsafe_allow_html=True)
                else:
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
            with remove_col:
                st.button(
                    "✕",
                    key=f"remove_{e['id']}",
                    help="Remove from this and later rankings; the papers below move up one place.",
                    on_click=_remove_paper,
                    args=(e["id"],),
                )

            with st.expander("Why this score?"):
                full_paper = paper_by_id.get(e["id"], {})
                breakdown = ad.explain_score(full_paper, cfg())
                _render_breakdown(breakdown)
            with st.expander("Full abstract"):
                abstract = paper_by_id.get(e["id"], {}).get("abstract", "") or "(unavailable)"
                if cfg().highlight_terms_abstract and abstract != "(unavailable)":
                    st.markdown(
                        f'<div class="paper-abstract">{_hl(abstract)}</div>',
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
        _set_loaded_profile(None)
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
        try:
            target = _validate_profile_name(name.strip())
        except ValueError as exc:
            st.error(str(exc))
        else:
            # Transfer first; a failure must leave the source profile active.
            if _copy_removed_ids_or_warn(loaded_profile(), target):
                save_profile(cfg(), target)
                _set_loaded_profile(target)
                st.success(f"Saved profile '{target}'.")
                st.rerun()

    profiles = list_profiles()
    if profiles:
        st.markdown("**Saved profiles:**")
        for p in profiles:
            cols = st.columns([3, 1, 1, 1])
            cols[0].write(p)
            try:
                profile_cfg = load_profile(p)
            except Exception as exc:
                cols[0].caption(f"Unreadable profile: {exc}")
                cols[1].button("Load", key=f"load_{p}", disabled=True)
                cols[2].download_button(
                    "Export",
                    data="",
                    file_name=f"{p}.json",
                    mime="application/json",
                    key=f"export_{p}",
                    disabled=True,
                )
            else:
                if cols[1].button("Load", key=f"load_{p}"):
                    st.session_state.cfg = profile_cfg
                    _set_loaded_profile(p)
                    _reset_widget_state()
                    st.success(f"Loaded {p}")
                    st.rerun()
                cols[2].download_button(
                    "Export",
                    data=json.dumps(asdict(profile_cfg), indent=2, ensure_ascii=False),
                    file_name=f"{p}.json",
                    mime="application/json",
                    key=f"export_{p}",
                )
            if cols[3].button("Delete", key=f"del_{p}"):
                delete_profile(p)
                if loaded_profile() == p:
                    _set_loaded_profile(None)
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
            _set_loaded_profile(None)
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
            fetched_ids = {p.get("id") for p in fetched}
            days = _selected_days()
            entries, _, visible = _digest(fetched, days)
            rank = next((e["rank"] for e in entries if e["id"] == paper_id), None)
            if rank is not None:
                st.success(
                    f"This paper **is** in the current digest at rank **#{rank}** "
                    f"with score **{breakdown['total']}**."
                )
            elif paper_id not in fetched_ids:
                st.info(_absence_reason(paper_id, fetched, cfg()))
            elif paper_id in load_removed_ids(loaded_profile()):
                st.info(
                    "You **removed** this paper from the digest, so it is not ranked. "
                    "Restore it from *Removed papers* in the **Papers** tab."
                )
            elif paper_id not in {p["id"] for p in ad.filter_papers(
                fetched, include_replacements=cfg().include_replacements
            )}:
                st.info(
                    "This paper was fetched but is a **replacement** submission, which "
                    "the digest hides. Tick *Include replacement submissions* to rank it."
                )
            elif paper_id not in {p["id"] for p in visible}:
                st.info(
                    f"This paper was fetched but is not from the day picked in the "
                    f"**Papers** tab ({days[0]}). Pick *All days* to rank it."
                )
            else:
                st.info(
                    f"This paper **was** fetched but ranked below your "
                    f"top-{cfg().top_n} cutoff."
                )
        else:
            st.caption("Fetch papers first to compare against the current digest.")

        st.divider()
        _render_zotero_save_button(paper_id, paper["title"], scope="score")


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
