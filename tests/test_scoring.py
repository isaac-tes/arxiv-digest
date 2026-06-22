from __future__ import annotations

import random

from arxiv_digest import Config, ScoringWeights, build_ranked_entries, explain_score, score_paper


def test_empty_paper_empty_cfg_scores_zero(empty_cfg, make_paper):
    assert score_paper(make_paper(), empty_cfg) == 0


def test_single_keyword_match_uses_core_keyword_weight(make_paper):
    cfg = Config(core_keywords=["topological"], named_authors=[], low_priority_kw=[])
    p = make_paper(title="Topological insulator")
    assert score_paper(p, cfg) == cfg.weights.core_keyword


def test_single_author_match_uses_named_author_weight(make_paper):
    cfg = Config(core_keywords=[], named_authors=["bloch"], low_priority_kw=[])
    p = make_paper(authors="Immanuel Bloch et al")
    assert score_paper(p, cfg) == cfg.weights.named_author


def test_named_author_does_not_match_abstract_or_title(make_paper):
    """Regression (arxiv_scraper_cli-8tz): 'Bloch theorem' in the abstract must
    not award author points when no author named Bloch is present."""
    cfg = Config(core_keywords=[], named_authors=["bloch"], low_priority_kw=[])
    p = make_paper(
        title="On the Bloch theorem",
        abstract="We revisit the Bloch theorem for periodic systems.",
        authors="Alice Smith, Bob Jones",
    )
    assert score_paper(p, cfg) == 0
    assert explain_score(p, cfg)["authors"] == []


def test_named_author_still_matches_in_author_field(make_paper):
    cfg = Config(core_keywords=[], named_authors=["bloch"], low_priority_kw=[])
    p = make_paper(title="Bloch theorem revisited", authors="Immanuel Bloch")
    assert score_paper(p, cfg) == cfg.weights.named_author


def test_feed_weight_adds_bonus_when_subject_matches(make_paper):
    """Per-feed weight (arxiv_scraper_cli-9i8): bonus when feed name is in subjects."""
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=[])
    cfg.feed_weights = {"hep-th": 7}
    p = make_paper(subjects="hep-th (primary)")
    assert score_paper(p, cfg) == 7
    assert explain_score(p, cfg)["subjects"]["hep-th"] == 7


def test_feed_weight_no_effect_when_unmatched_or_zero(make_paper):
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=[])
    cfg.feed_weights = {"hep-th": 7, "math.AG": 0}
    p = make_paper(subjects="quant-ph")  # only builtin quant-ph applies
    assert score_paper(p, cfg) == cfg.weights.quant_ph_subject


def test_feed_weight_does_not_double_count_builtin_subject(make_paper):
    """If a feed name equals a builtin subject key, don't add twice."""
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=[])
    cfg.feed_weights = {"quant-ph": 5}
    p = make_paper(subjects="quant-ph")
    assert score_paper(p, cfg) == cfg.weights.quant_ph_subject  # builtin only


def test_feed_weight_roundtrips_through_json(make_paper):
    from arxiv_digest import Config
    cfg = Config()
    cfg.feed_weights = {"hep-th": 3}
    import json as _json
    from dataclasses import asdict
    restored = Config.from_json(_json.loads(_json.dumps(asdict(cfg))))
    assert restored.feed_weights == {"hep-th": 3}


def test_quant_gas_subject_bonus(empty_cfg, make_paper):
    p = make_paper(subjects="cond-mat.quant-gas (primary)")
    assert score_paper(p, empty_cfg) == empty_cfg.weights.quant_gas_subject


def test_mes_hall_subject_bonus(empty_cfg, make_paper):
    p = make_paper(subjects="cond-mat.mes-hall")
    assert score_paper(p, empty_cfg) == empty_cfg.weights.mes_hall_subject


def test_quant_ph_subject_bonus(empty_cfg, make_paper):
    p = make_paper(subjects="quant-ph")
    assert score_paper(p, empty_cfg) == empty_cfg.weights.quant_ph_subject


def test_low_priority_penalty_applied_once_not_per_hit(make_paper):
    """One penalty regardless of how many low-priority terms match."""
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=["film", "growth"])
    p_one = make_paper(abstract="thin film")
    p_two = make_paper(abstract="thin film growth")
    assert score_paper(p_one, cfg) == cfg.weights.low_priority_penalty
    assert score_paper(p_two, cfg) == cfg.weights.low_priority_penalty


def test_long_abstract_bonus(empty_cfg, make_paper):
    p_short = make_paper(abstract="x" * empty_cfg.weights.long_abstract_threshold)
    p_long = make_paper(abstract="x" * (empty_cfg.weights.long_abstract_threshold + 1))
    assert score_paper(p_short, empty_cfg) == 0
    assert score_paper(p_long, empty_cfg) == empty_cfg.weights.long_abstract_bonus


def test_combined_score_sums_all_rules(make_paper):
    cfg = Config(
        core_keywords=["topological"],
        named_authors=["bloch"],
        low_priority_kw=["growth"],
    )
    p = make_paper(
        title="topological flat band",
        authors="Bloch et al",
        subjects="cond-mat.quant-gas, quant-ph",
        abstract="x" * 250 + " growth",
    )
    w = cfg.weights
    expected = (
        w.core_keyword
        + w.named_author
        + w.quant_gas_subject
        + w.quant_ph_subject
        + w.low_priority_penalty
        + w.long_abstract_bonus
    )
    assert score_paper(p, cfg) == expected


def test_explain_score_total_matches_score_paper(make_paper):
    cfg = Config()
    rng = random.Random(42)
    samples = [
        make_paper(title=cfg.core_keywords[rng.randrange(len(cfg.core_keywords))]),
        make_paper(authors=cfg.named_authors[rng.randrange(len(cfg.named_authors))]),
        make_paper(subjects="cond-mat.quant-gas"),
        make_paper(abstract="x" * 300 + " " + cfg.low_priority_kw[0]),
        make_paper(),
    ]
    for p in samples:
        assert score_paper(p, cfg) == explain_score(p, cfg)["total"]


def test_explain_score_breakdown_structure(make_paper):
    cfg = Config(core_keywords=["topological"], named_authors=["bloch"], low_priority_kw=["film"])
    p = make_paper(title="Topological", authors="Bloch", abstract="thin film")
    breakdown = explain_score(p, cfg)
    assert ("topological", cfg.weights.core_keyword) in breakdown["keywords"]
    assert ("bloch", cfg.weights.named_author) in breakdown["authors"]
    assert breakdown["low_priority_hits"] == ["film"]
    assert breakdown["low_priority_penalty"] == cfg.weights.low_priority_penalty


def test_custom_weights_change_scoring(make_paper):
    cfg = Config(
        core_keywords=["topological"],
        named_authors=[],
        low_priority_kw=[],
        weights=ScoringWeights(core_keyword=100),
    )
    p = make_paper(title="Topological")
    assert score_paper(p, cfg) == 100


def test_build_ranked_entries_sorts_by_score_descending(make_paper):
    cfg = Config(core_keywords=["x"], named_authors=[], low_priority_kw=[])
    papers = [
        make_paper(id="a", title="no match"),
        make_paper(id="b", title="x match"),
    ]
    out = build_ranked_entries(papers, cfg, top_n=10)
    assert out[0]["id"] == "b"
    assert out[0]["score"] > out[1]["score"]
    assert out[0]["rank"] == 1


def test_build_ranked_entries_respects_top_n(make_paper):
    cfg = Config()
    papers = [make_paper(id=str(i), title=f"paper {i}") for i in range(50)]
    out = build_ranked_entries(papers, cfg, top_n=10)
    assert len(out) == 10
    assert [e["rank"] for e in out] == list(range(1, 11))


def test_build_ranked_entries_handles_top_n_larger_than_inputs(make_paper):
    cfg = Config()
    papers = [make_paper(id=str(i)) for i in range(3)]
    out = build_ranked_entries(papers, cfg, top_n=10)
    assert len(out) == 3
