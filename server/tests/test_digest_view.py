"""Digest view, removed papers, Score-a-paper placement, and config endpoints.

arXiv is never contacted: `fetch_pastweek` / `fetch_feeds` /
`zotero_bridge.fetch_arxiv_atom` are monkey-patched per test.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import arxiv_digest as ad
import pytest
import requests
import zotero_bridge as zb

from app.routers import digest as digest_router

FEEDS = {
    "quant-ph": "https://arxiv.org/list/quant-ph/new",
    "cond-mat.quant-gas": "https://arxiv.org/list/cond-mat.quant-gas/new",
}

CONFIG = {
    "feeds": FEEDS,
    "default_feeds": ["quant-ph"],
    "core_keywords": ["floquet", "anyon"],
    "named_authors": ["Ada Lovelace"],
    "low_priority_kw": ["review"],
    "feed_weights": {"quant-ph": 2},
    "top_n": 2,
    "timeframe": "pastweek",
}

DAY1 = "Mon, 28 Sep 2026"
DAY2 = "Tue, 29 Sep 2026"


def _paper(pid: str, title: str, section: str, authors: str = "Bo Example", abstract: str = "") -> dict:
    return {
        "id": pid,
        "title": title,
        "authors": authors,
        "link": f"https://arxiv.org/abs/{pid}",
        "subjects": "Quantum Physics (quant-ph)",
        "abstract": abstract or f"An abstract about {title.lower()}. Second sentence. Third one.",
        "section": section,
    }


# Scores under CONFIG (keyword +6 each, author +6, quant-ph +2, review -5):
#   A: floquet + anyon + author = 6+6+6+2 = 20
#   B: floquet = 8
#   C: anyon = 8 (title sorts after B)
#   D: nothing = 2
#   R: replacement with floquet = 8 (hidden by default)
PAPERS = [
    _paper("2609.00001", "Floquet anyon pumps", DAY1, authors="Ada M. Lovelace, Bo Example"),
    _paper("2609.00002", "B Floquet drive", DAY2),
    _paper("2609.00003", "C anyon braiding", DAY1),
    _paper("2609.00004", "D unrelated topic", DAY2),
    _paper("2609.00005", "R Floquet replacement", "Replacement submissions (showing 1 of 1 entries)"),
]


@pytest.fixture(autouse=True)
def _reset(client, monkeypatch):
    digest_router._fetch_cache.clear()
    client.put("/config", json={"data": CONFIG})
    client.post("/removed/restore", json={"arxiv_ids": [p["id"] for p in PAPERS]})
    calls: dict[str, list] = {"pastweek": [], "feeds": []}

    def fake_pastweek(names, start, end, verbose=False, notices=None):
        calls["pastweek"].append(list(names))
        assert (end - start).days == 7
        if notices is not None:
            notices.append("export API rate-limited")
        return [dict(p) for p in PAPERS]

    def fake_feeds(urls, sections=None, verbose=False):
        calls["feeds"].append(list(urls))
        return [dict(p) for p in PAPERS]

    monkeypatch.setattr(ad, "fetch_pastweek", fake_pastweek)
    monkeypatch.setattr(ad, "fetch_feeds", fake_feeds)
    return calls


def ids(papers):
    return [p["id"] for p in papers]


# ── Fetch path parity with the CLI ────────────────────────────────────────────

def test_pastweek_uses_export_api_and_surfaces_notices(client, _reset):
    client.put("/config", json={"data": {**CONFIG, "default_feeds": ["quant-ph", "cond-mat.quant-gas"]}})
    body = client.get("/digest").json()
    assert _reset["pastweek"] == [["quant-ph", "cond-mat.quant-gas"]]
    assert _reset["feeds"] == []
    assert body["notices"] == ["export API rate-limited"]
    assert body["timeframe"] == "pastweek"
    assert body["feeds"] == ["quant-ph", "cond-mat.quant-gas"]


def test_pastweek_skips_explicit_url_feeds(client, _reset):
    client.get("/digest", params={"feeds": "quant-ph,https://example.org/list/x/new,unknown"})
    assert _reset["pastweek"] == [["quant-ph"]]


def test_today_uses_html_new_listing(client, _reset):
    body = client.get("/digest", params={"timeframe": "today"}).json()
    assert _reset["feeds"] == [["https://arxiv.org/list/quant-ph/new"]]
    assert _reset["pastweek"] == []
    assert body["timeframe"] == "today"


def test_timeframe_defaults_to_config(client, _reset):
    client.put("/config", json={"data": {**CONFIG, "timeframe": "today"}})
    assert client.get("/digest").json()["timeframe"] == "today"


def test_bad_timeframe_is_422(client):
    assert client.get("/digest", params={"timeframe": "yesterday"}).status_code == 422


def test_fetch_failure_is_502(client, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(ad, "fetch_pastweek", boom)
    resp = client.get("/digest")
    assert resp.status_code == 502
    assert "arXiv fetch failed" in resp.json()["detail"]


def test_cache_reused_until_refresh_and_keyed_on_feeds(client, _reset):
    client.get("/digest")
    client.get("/digest", params={"top_n": 3})
    assert len(_reset["pastweek"]) == 1
    client.get("/digest", params={"refresh": "true"})
    assert len(_reset["pastweek"]) == 2
    # Changing subscribed feeds must not serve the old feeds' cache.
    client.put("/config", json={"data": {**CONFIG, "default_feeds": ["cond-mat.quant-gas"]}})
    client.get("/digest")
    assert _reset["pastweek"][-1] == ["cond-mat.quant-gas"]


# ── Ranking view (port of arxiv_gui._digest) ─────────────────────────────────

def test_ranking_matches_engine_and_hides_replacements(client):
    body = client.get("/digest").json()
    assert ids(body["papers"]) == ["2609.00001", "2609.00002"]
    assert [p["rank"] for p in body["papers"]] == [1, 2]
    assert body["fetched_papers"] == 5
    assert body["hidden_by_filters"] == 1
    assert body["total_papers"] == 4
    assert body["requested_top"] == 2
    assert body["available_days"] == [DAY1, DAY2]
    assert body["day"] is None


def test_include_replacements(client):
    client.put("/config", json={"data": {**CONFIG, "include_replacements": True, "top_n": 10}})
    body = client.get("/digest").json()
    assert "2609.00005" in ids(body["papers"])
    assert body["hidden_by_filters"] == 0


def test_papers_carry_abstract_and_breakdown_matching_score(client):
    body = client.get("/digest").json()
    top = body["papers"][0]
    assert top["abstract"].startswith("An abstract about floquet anyon pumps.")
    assert top["summary"] == "An abstract about floquet anyon pumps. Second sentence."
    kw = top["breakdown"]["signals"]["keyword"]
    assert top["breakdown"]["total"] == top["score"] == 20
    assert [k for k, _ in kw["authors"]] == ["Ada Lovelace"]  # middle initial tolerated


def test_day_reranks_within_that_day(client):
    body = client.get("/digest", params={"day": DAY2}).json()
    assert ids(body["papers"]) == ["2609.00002", "2609.00004"]
    assert body["day"] == DAY2
    assert body["hidden_by_filters"] == 3  # 2 from DAY1 + the replacement


def test_unknown_day_is_ignored(client):
    body = client.get("/digest", params={"day": "Sun, 01 Jan 2023"}).json()
    assert body["day"] is None
    assert ids(body["papers"]) == ["2609.00001", "2609.00002"]


# ── Removed papers ───────────────────────────────────────────────────────────

def test_remove_moves_next_paper_up_and_restore_brings_it_back(client, _reset):
    assert client.post("/removed", json={"arxiv_id": "2609.00001"}).status_code == 204
    # Idempotent.
    assert client.post("/removed", json={"arxiv_id": "2609.00001"}).status_code == 204
    assert client.get("/removed").json() == ["2609.00001"]

    body = client.get("/digest").json()
    assert ids(body["papers"]) == ["2609.00002", "2609.00003"]
    assert [p["rank"] for p in body["papers"]] == [1, 2]
    assert ids(body["removed"]) == ["2609.00001"]
    assert body["total_papers"] == 3
    assert len(_reset["pastweek"]) == 1  # removal re-ranks the cache, no re-fetch

    assert client.post("/removed/restore", json={"arxiv_ids": ["2609.00001"]}).status_code == 204
    assert client.get("/removed").json() == []
    assert ids(client.get("/digest").json()["papers"]) == ["2609.00001", "2609.00002"]


def test_remove_rejects_ids_longer_than_the_column(client, _reset):
    assert client.post("/removed", json={"arxiv_id": "x" * 65}).status_code == 422
    assert client.get("/removed").json() == []


def test_removed_list_only_shows_papers_that_would_be_in_ranking(client):
    client.post("/removed", json={"arxiv_id": "2609.00004"})  # ranked last, outside top 2
    body = client.get("/digest").json()
    assert body["removed"] == []


# ── Score-a-paper placement ──────────────────────────────────────────────────

ATOM = "http://www.w3.org/2005/Atom"


def _atom_entry(pid: str, title: str, cats: list[str], published: str, authors=("Bo Example",)) -> ET.Element:
    e = ET.Element(f"{{{ATOM}}}entry")
    ET.SubElement(e, f"{{{ATOM}}}id").text = f"http://arxiv.org/abs/{pid}v1"
    ET.SubElement(e, f"{{{ATOM}}}title").text = title
    ET.SubElement(e, f"{{{ATOM}}}summary").text = f"An abstract about {title.lower()}."
    ET.SubElement(e, f"{{{ATOM}}}published").text = published
    for a in authors:
        ET.SubElement(ET.SubElement(e, f"{{{ATOM}}}author"), f"{{{ATOM}}}name").text = a
    for c in cats:
        ET.SubElement(e, f"{{{ATOM}}}category", term=c)
    return e


@pytest.fixture
def atom(monkeypatch):
    entries: dict[str, ET.Element] = {}

    def fake(arxiv_id):
        return entries.get(zb.arxiv_id_from_input(arxiv_id))

    monkeypatch.setattr(zb, "fetch_arxiv_atom", fake)
    for p in PAPERS:
        entries[p["id"]] = _atom_entry(p["id"], p["title"], ["quant-ph"], "2026-09-28T10:00:00Z")
    return entries


def score(client, arxiv_id, **extra):
    resp = client.post("/score", json={"arxiv_id": arxiv_id, **extra})
    assert resp.status_code == 200
    return resp.json()


def test_score_without_loaded_digest_asks_to_load(client, atom):
    body = score(client, "2609.00001")
    assert body["rank"] is None
    assert body["absence_reason"].startswith("Load the digest first")
    assert body["breakdown"]["total"] > 0


def test_score_reports_rank_shown_in_papers_tab(client, atom):
    client.get("/digest")
    body = score(client, "https://arxiv.org/abs/2609.00002v3")
    assert body["rank"] == 2
    assert body["absence_reason"] is None
    assert body["paper"]["id"] == "2609.00002"


def test_score_rank_respects_day_and_removal(client, atom):
    client.get("/digest")
    assert score(client, "2609.00004", day=DAY2)["rank"] == 2
    client.post("/removed", json={"arxiv_id": "2609.00001"})
    assert score(client, "2609.00003")["rank"] == 2


def test_score_absence_below_top_n(client, atom):
    client.get("/digest")
    body = score(client, "2609.00004")
    assert "ranked below your top-2 cutoff" in body["absence_reason"]


def test_score_absence_removed(client, atom):
    client.get("/digest")
    client.post("/removed", json={"arxiv_id": "2609.00001"})
    assert "You **removed** this paper from the digest" in score(client, "2609.00001")["absence_reason"]
    client.post("/removed", json={"arxiv_id": "2609.00004"})
    assert "current filters or top-N hide it" in score(client, "2609.00004")["absence_reason"]


def test_score_absence_replacement(client, atom):
    client.get("/digest")
    assert "**replacement** submission" in score(client, "2609.00005")["absence_reason"]


def test_score_absence_other_day(client, atom):
    client.get("/digest")
    reason = score(client, "2609.00001", day=DAY2)["absence_reason"]
    assert f"not from the picked day ({DAY2})" in reason


def test_score_absence_not_fetched(client, atom):
    client.get("/digest")
    atom["2609.09999"] = _atom_entry("2609.09999", "Elsewhere", ["hep-th"], "2026-09-20T10:00:00Z")
    reason = score(client, "2609.09999")["absence_reason"]
    assert reason.startswith("This paper was **not in the fetched set**")
    assert "submitted on **2026-09-20**" in reason
    assert "**not among your subscribed feeds**" in reason


def test_score_not_found(client, atom):
    body = score(client, "2609.88888")
    assert body["paper"] is None
    assert body["absence_reason"] == "Paper not found"


def test_score_network_error_is_502(client, monkeypatch):
    def boom(_):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(zb, "fetch_arxiv_atom", boom)
    assert client.post("/score", json={"arxiv_id": "2609.00001"}).status_code == 502


# ── Config: effective values, presets, defaults ─────────────────────────────

def test_get_config_returns_every_field(client):
    data = client.get("/config").json()["data"]
    assert data["core_keywords"] == ["floquet", "anyon"]
    for key in ("weights", "feed_weights", "highlight_terms_summary", "color_font_keyword"):
        assert key in data
    assert data["color_font_keyword"] is True  # engine default


def test_put_invalid_config_is_422(client):
    resp = client.put("/config", json={"data": {"top_n": "lots"}})
    assert resp.status_code == 422


def test_defaults_endpoint(client):
    data = client.get("/config/defaults").json()["data"]
    assert data["weights"]["core_keyword"] == 6
    assert data["top_n"] == 20


def test_preset_info(client):
    info = client.get("/config/presets/info").json()
    assert [i["name"] for i in info] == ad.preset_names()
    assert all(i["description"] for i in info)


def test_preset_load_replaces_and_merge_unions(client):
    name = ad.preset_names()[0]
    loaded = client.post(f"/config/presets/{name}/load").json()["data"]
    assert loaded["core_keywords"] == ad.PRESETS[name]["core_keywords"]
    assert loaded["default_feeds"] == ad.PRESETS[name]["default_feeds"]

    client.put("/config", json={"data": CONFIG})
    merged = client.post(f"/config/presets/{name}/merge").json()["data"]
    assert merged["core_keywords"][:2] == ["floquet", "anyon"]
    assert set(ad.PRESETS[name]["core_keywords"]) <= set(merged["core_keywords"])
    assert merged["top_n"] == 2  # scalar prefs kept


def test_preset_unsaved_merge_uses_working_config_and_stores_nothing(client):
    name = ad.preset_names()[0]
    working = {**CONFIG, "core_keywords": ["draft-only"]}
    merged = client.post(f"/config/presets/{name}/merge", params={"save": "false"}, json={"data": working}).json()["data"]
    assert merged["core_keywords"][0] == "draft-only"
    loaded = client.post(f"/config/presets/{name}/load", params={"save": "false"}).json()["data"]
    assert loaded["core_keywords"] == ad.PRESETS[name]["core_keywords"]
    # Stored config untouched.
    assert client.get("/config").json()["data"]["core_keywords"] == ["floquet", "anyon"]


def test_unknown_preset_is_404(client):
    assert client.post("/config/presets/nope/load").status_code == 404
    assert client.post("/config/presets/nope/merge").status_code == 404


def test_cleared_author_list_stays_cleared(client):
    data = client.put("/config", json={"data": {**CONFIG, "named_authors": []}}).json()["data"]
    assert data["named_authors"] == []
    assert client.get("/config").json()["data"]["named_authors"] == []
    top = client.get("/digest").json()["papers"][0]
    assert top["breakdown"]["signals"]["keyword"]["authors"] == []


def test_score_uses_cached_paper_when_arxiv_is_down(client, monkeypatch):
    client.get("/digest")

    def boom(_):
        raise requests.HTTPError("429 Too Many Requests")

    monkeypatch.setattr(zb, "fetch_arxiv_atom", boom)
    body = score(client, "arXiv:2609.00002v2")
    assert body["rank"] == 2
    assert body["paper"]["title"] == "B Floquet drive"
    assert body["breakdown"]["total"] == 8
    # A paper outside the fetch still needs arXiv and reports the outage.
    resp = client.post("/score", json={"arxiv_id": "2609.77777"})
    assert resp.status_code == 502
    assert "rate-limiting" in resp.json()["detail"]


def test_cache_keyed_on_feed_urls_not_just_names(client, _reset):
    client.get("/digest", params={"timeframe": "today"})
    feeds = {**FEEDS, "quant-ph": "https://arxiv.org/list/quant-ph.fixed/new"}
    client.put("/config", json={"data": {**CONFIG, "feeds": feeds}})
    client.get("/digest", params={"timeframe": "today"})
    assert _reset["feeds"] == [
        ["https://arxiv.org/list/quant-ph/new"],
        ["https://arxiv.org/list/quant-ph.fixed/new"],
    ]


def test_blank_feeds_param_uses_config_feeds(client, _reset):
    body = client.get("/digest", params={"feeds": ""}).json()
    assert body["feeds"] == ["quant-ph"]
    assert _reset["pastweek"] == [["quant-ph"]]


def test_empty_fetch_is_not_cached(client, monkeypatch, _reset):
    monkeypatch.setattr(ad, "fetch_pastweek", lambda *a, **k: [])
    client.get("/digest")
    assert digest_router._fetch_cache == {}


def test_score_fetches_arxiv_with_normalized_id(client, monkeypatch):
    seen = []

    def fake(arxiv_id):
        seen.append(arxiv_id)
        return None

    monkeypatch.setattr(zb, "fetch_arxiv_atom", fake)
    client.post("/score", json={"arxiv_id": "https://arxiv.org/abs/2609.55555v3"})
    assert seen == ["2609.55555"]
