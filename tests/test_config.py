from __future__ import annotations

import json

import pytest

from arxiv_digest import (
    Config,
    ScoringWeights,
    _default_core_keywords,
    _default_named_authors,
    _find_index_casefold,
    _parse_add_url,
    _parse_rename_arg,
    modify_list,
)


def _fully_customised_config() -> Config:
    """A Config with every field set to a non-default value."""
    return Config(
        feeds={"foo": "https://arxiv.org/list/foo/new", "bar": "https://arxiv.org/list/bar/new"},
        default_feeds=["foo"],
        core_keywords=["kw-one", "kw-two"],
        named_authors=["author-x"],
        low_priority_kw=["lp-term"],
        top_n=42,
        timeframe="today",
        include_replacements=True,
        feed_weights={"foo": 9, "bar": -3},
        highlight_authors=False,
        highlight_terms_title=False,
        highlight_terms_abstract=False,
        color_keyword="#112233",
        color_low_priority="#445566",
        color_author="#778899",
        color_subject="#aabbcc",
        color_font_keyword=True,
        color_font_low_priority=True,
        color_font_author=True,
        color_font_subject=True,
        weights=ScoringWeights(
            core_keyword=11,
            named_author=12,
            low_priority_penalty=-7,
            long_abstract_bonus=2,
            long_abstract_threshold=321,
        ),
    )


def test_dump_load_roundtrip_preserves_every_field(tmp_path):
    """Profiles and project config both use Config.dump/load — this guards that
    saving persists ALL settings (feeds, keywords, authors, low-priority,
    scoring weights, per-feed bonuses, filters)."""
    cfg = _fully_customised_config()
    path = tmp_path / "profile.json"
    cfg.dump(path)
    loaded = Config.load(path)
    assert loaded == cfg


def test_dump_load_roundtrip_covers_all_dataclass_fields():
    """If a new Config field is added but not round-tripped, this fails."""
    import dataclasses

    cfg = _fully_customised_config()
    restored = Config.from_json(json.loads(json.dumps(dataclasses.asdict(cfg))))
    for f in dataclasses.fields(Config):
        assert getattr(restored, f.name) == getattr(cfg, f.name), f"field {f.name} not preserved"


def test_default_config_basics():
    cfg = Config()
    assert set(cfg.feeds) == {"cond-mat.quant-gas", "cond-mat.mes-hall", "quant-ph", "cond-mat"}
    assert cfg.top_n == 20
    assert cfg.timeframe == "pastweek"
    assert cfg.weights == ScoringWeights()


def test_default_keyword_list_no_duplicates():
    kws = _default_core_keywords()
    assert len(kws) == len(set(kws)), "default core_keywords must not contain duplicates"


def test_default_keywords_contain_known_terms():
    kws = [k.lower() for k in _default_core_keywords()]
    for needle in ("topological", "fqhe", "dmrg", "floquet"):
        assert needle in kws


def test_default_authors_contain_known_names():
    authors = [a.lower() for a in _default_named_authors()]
    for needle in ("bloch", "cirac"):
        assert needle in authors


def test_config_json_roundtrip(tmp_path):
    cfg = Config()
    cfg.core_keywords.append("custom_kw")
    cfg.weights = ScoringWeights(core_keyword=10, low_priority_penalty=-7)
    p = tmp_path / "cfg.json"
    cfg.dump(p)
    loaded = Config.load(p)
    assert loaded.core_keywords == cfg.core_keywords
    assert loaded.named_authors == cfg.named_authors
    assert loaded.weights == cfg.weights
    assert loaded.feeds == cfg.feeds
    assert loaded.timeframe == cfg.timeframe


def test_legacy_default_feed_singular_migrates(tmp_path):
    raw = {
        "feeds": {
            "cond-mat": "https://arxiv.org/list/cond-mat/new",
            "quant-ph": "https://arxiv.org/list/quant-ph/new",
        },
        "default_feed": "cond-mat",
    }
    cfg = Config.from_json(raw)
    assert cfg.default_feeds == ["cond-mat"]


def test_legacy_json_without_weights_uses_defaults():
    raw = {"feeds": {}, "core_keywords": ["x"]}
    cfg = Config.from_json(raw)
    assert cfg.weights == ScoringWeights()


def test_from_json_defaults_match_dataclass_defaults():
    """Regression: empty JSON should produce Config equivalent to Config()."""
    cfg_a = Config()
    cfg_b = Config.from_json({})
    assert cfg_a.top_n == cfg_b.top_n
    assert cfg_a.timeframe == cfg_b.timeframe


def test_load_returns_default_when_path_missing(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.json")
    assert cfg == Config()


def test_load_returns_default_when_path_none():
    assert Config.load(None) == Config()


def test_modify_list_add_remove_rename():
    seq = ["alpha", "beta", "gamma"]
    modify_list(seq, additions=["delta"], removals=["beta"], renames=["alpha:Alpha"])
    assert seq == ["Alpha", "gamma", "delta"]


def test_modify_list_casefold_dedup():
    seq = ["Topological"]
    modify_list(seq, additions=["topological"], removals=[], renames=[])
    assert len(seq) == 1


def test_modify_list_remove_is_case_insensitive():
    seq = ["Topological"]
    modify_list(seq, additions=[], removals=["topological"], renames=[])
    assert seq == []


def test_modify_list_strips_whitespace_on_add():
    seq = []
    modify_list(seq, additions=["  spaced  "], removals=[], renames=[])
    assert seq == ["spaced"]


def test_find_index_casefold():
    seq = ["Foo", "Bar", "Baz"]
    assert _find_index_casefold(seq, "BAR") == 1
    assert _find_index_casefold(seq, "missing") is None


def test_parse_rename_arg():
    assert _parse_rename_arg("old:new") == ("old", "new")
    assert _parse_rename_arg(" Old : New ") == ("Old", "New")


def test_parse_rename_arg_rejects_malformed():
    with pytest.raises(ValueError):
        _parse_rename_arg("no-colon")


def test_parse_add_url():
    assert _parse_add_url("name=https://x.example") == ("name", "https://x.example")


def test_parse_add_url_rejects_malformed():
    with pytest.raises(ValueError):
        _parse_add_url("no-equals-sign")


def test_scoring_weights_from_json_partial():
    """Missing keys fall back to defaults."""
    w = ScoringWeights.from_json({"core_keyword": 99})
    assert w.core_keyword == 99
    assert w.named_author == ScoringWeights().named_author


def test_scoring_weights_from_json_none():
    assert ScoringWeights.from_json(None) == ScoringWeights()
    assert ScoringWeights.from_json({}) == ScoringWeights()


def test_dumped_config_is_valid_json(tmp_path):
    cfg = Config()
    p = tmp_path / "cfg.json"
    cfg.dump(p)
    data = json.loads(p.read_text())
    assert "weights" in data
    assert data["weights"]["core_keyword"] == 6
