"""Built-in starter presets (arxiv_scraper_cli-7f2).

Three read-only research-topic bundles a user can Load (replace) or Add
(union) without touching their own profile / arxiv_config.json.
"""
from __future__ import annotations

from arxiv_digest import (
    Config,
    PRESETS,
    apply_cli_modifications,
    merge_preset,
    parse_args,
    preset_config,
    preset_names,
)

EXPECTED = {"open-quantum-systems", "quantum-many-body", "floquet-topological"}


def test_three_presets_registered():
    assert set(preset_names()) == EXPECTED
    assert set(PRESETS) == EXPECTED


def test_each_preset_is_populated():
    for name in preset_names():
        cfg = preset_config(name)
        assert isinstance(cfg, Config)
        assert cfg.core_keywords, name
        assert cfg.named_authors, name
        assert cfg.feeds, name
        assert cfg.default_feeds, name
        # every default feed must resolve to a URL in the feeds map
        for f in cfg.default_feeds:
            assert f in cfg.feeds, (name, f)


def test_every_preset_has_authors():
    for name in preset_names():
        authors = [a.lower() for a in preset_config(name).named_authors]
        assert authors, name
        # no personal/private-group author names leak into the public presets
        assert not (set(authors) & { ""}), name


def test_author_count_capped_at_ten():
    for name in preset_names():
        assert len(preset_config(name).named_authors) <= 10, name


def test_no_noisy_short_surnames():
    """'wu'/'link'/'ma' over-match even with whole-word matching — keep them out."""
    banned = {"wu", "link", "ma"}
    for name in preset_names():
        authors = {a.lower() for a in preset_config(name).named_authors}
        assert not (authors & banned), (name, authors & banned)


def test_floquet_preset_signature_content():
    cfg = preset_config("floquet-topological")
    kws = " ".join(cfg.core_keywords).lower()
    assert "floquet" in kws
    assert any("topological" in k.lower() or "chern" in k.lower() for k in cfg.core_keywords)
    assert "cond-mat.mes-hall" in cfg.feeds


# --- Load (replace) vs Add (merge) -----------------------------------------

def test_preset_config_is_full_replace_from_defaults():
    cfg = preset_config("open-quantum-systems")
    # scalar prefs stay at Config defaults; content is the preset's
    assert cfg.top_n == Config().top_n
    assert cfg.timeframe == Config().timeframe
    assert "quant-ph" in cfg.feeds


def test_merge_preset_unions_without_touching_scalars():
    base = Config(core_keywords=["mykw"], named_authors=["myauthor"],
                  feeds={"myfeed": "https://arxiv.org/list/hep-th/new"},
                  default_feeds=["myfeed"], top_n=7, timeframe="today")
    merged = merge_preset(base, "quantum-many-body")
    # base content preserved
    assert "mykw" in merged.core_keywords
    assert "myauthor" in merged.named_authors
    assert "myfeed" in merged.feeds
    # preset content added
    assert "eisert" in [a.lower() for a in merged.named_authors]
    assert len(merged.core_keywords) > 1
    # scalars untouched
    assert merged.top_n == 7
    assert merged.timeframe == "today"


def test_merge_preset_dedups_case_insensitively_preserving_order():
    base = Config(core_keywords=["Floquet", "unique-base-kw"], named_authors=["Einstein"],
                  feeds={}, default_feeds=[])
    merged = merge_preset(base, "floquet-topological")
    lowered = [k.lower() for k in merged.core_keywords]
    assert lowered.count("floquet") == 1               # no dup despite preset also having it
    assert merged.core_keywords[0] == "Floquet"        # base order kept first
    assert "unique-base-kw" in merged.core_keywords
    assert [a.lower() for a in merged.named_authors].count("einstein") == 1


def test_merge_preset_does_not_mutate_input():
    base = Config(core_keywords=["only"], named_authors=[], feeds={}, default_feeds=[])
    merge_preset(base, "open-quantum-systems")
    assert base.core_keywords == ["only"]  # input untouched


# --- CLI --------------------------------------------------------------------

def test_cli_preset_replaces_base_config():
    args = parse_args(["--preset", "floquet-topological"])
    assert args.preset == "floquet-topological"
    cfg = preset_config(args.preset)
    apply_cli_modifications(cfg, args)
    assert any("floquet" in k.lower() for k in cfg.core_keywords)


def test_cli_add_preset_flag_parsed():
    args = parse_args(["--add-preset", "open-quantum-systems", "--add-preset", "quantum-many-body"])
    assert args.add_preset == ["open-quantum-systems", "quantum-many-body"]


def test_cli_list_presets_flag():
    args = parse_args(["--list-presets"])
    assert args.list_presets is True


def test_preset_roundtrips_through_dump(tmp_path):
    cfg = preset_config("quantum-many-body")
    p = tmp_path / "c.json"
    cfg.dump(p)
    reloaded = Config.load(p)
    assert set(a.lower() for a in reloaded.named_authors) == set(a.lower() for a in cfg.named_authors)
    assert reloaded.core_keywords == cfg.core_keywords
