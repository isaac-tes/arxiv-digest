from __future__ import annotations

import arxiv_digest as ad


def _use_tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "_FETCH_CACHE_DIR", tmp_path / "cache")


def test_cache_key_stable_and_order_independent():
    k1 = ad._fetch_cache_key("pastweek", ["quant-ph", "cond-mat"], day="2026-09-15")
    k2 = ad._fetch_cache_key("pastweek", ["cond-mat", "quant-ph"], day="2026-09-15")
    assert k1 == k2  # feed order must not change the key


def test_cache_key_varies_by_day_and_timeframe():
    base = ad._fetch_cache_key("pastweek", ["quant-ph"], day="2026-09-15")
    assert base != ad._fetch_cache_key("pastweek", ["quant-ph"], day="2026-09-16")
    assert base != ad._fetch_cache_key("today", ["quant-ph"], day="2026-09-15")


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    _use_tmp_cache(tmp_path, monkeypatch)
    papers = [{"id": "2609.1", "title": "T", "abstract": "a"}]
    key = ad._fetch_cache_key("today", ["quant-ph"], day="2026-09-15")
    assert ad.load_fetch_cache(key) is None  # miss before save
    ad.save_fetch_cache(key, papers)
    assert ad.load_fetch_cache(key) == papers


def test_empty_result_is_not_cached(tmp_path, monkeypatch):
    _use_tmp_cache(tmp_path, monkeypatch)
    key = ad._fetch_cache_key("today", ["quant-ph"], day="2026-09-15")
    ad.save_fetch_cache(key, [])
    assert ad.load_fetch_cache(key) is None  # blocked/failed fetch must retry


def test_clear_fetch_cache_removes_files(tmp_path, monkeypatch):
    _use_tmp_cache(tmp_path, monkeypatch)
    key = ad._fetch_cache_key("today", ["quant-ph"], day="2026-09-15")
    ad.save_fetch_cache(key, [{"id": "x", "abstract": "y"}])
    assert ad.load_fetch_cache(key) is not None
    ad.clear_fetch_cache()
    assert ad.load_fetch_cache(key) is None


def test_save_prunes_stale_files(tmp_path, monkeypatch):
    import os
    import time

    _use_tmp_cache(tmp_path, monkeypatch)
    old_key = ad._fetch_cache_key("today", ["old"], day="2026-01-01")
    ad.save_fetch_cache(old_key, [{"id": "old", "abstract": "z"}])
    old_file = ad._FETCH_CACHE_DIR / f"{old_key}.json"
    stale = time.time() - (ad._FETCH_CACHE_MAX_AGE_DAYS + 1) * 86400
    os.utime(old_file, (stale, stale))

    ad.save_fetch_cache(ad._fetch_cache_key("today", ["new"], day="2026-09-15"),
                        [{"id": "new", "abstract": "w"}])
    assert not old_file.exists()  # stale file pruned on the next save
