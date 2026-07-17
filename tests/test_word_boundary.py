"""Word-boundary matching for keywords/authors/low-priority (arxiv_scraper_cli-28n).

Substring matching made short terms bleed into unrelated words: 'mpo' scored
'temporal', author 'ma' scored 'Mao', 'bloch' scored 'Blochwitz'. Matching is
now whole-token by default (config flag `word_boundary_matching`, default ON).
Subjects (feed_weights) intentionally stay substring so a parent category like
'cond-mat' still matches 'cond-mat.quant-gas'.
"""
from __future__ import annotations

import json

from arxiv_digest import Config, explain_score, score_paper, term_matches


# --- the helper -------------------------------------------------------------

def test_term_matches_whole_token_only():
    assert term_matches("mpo", "matrix product operator (mpo) ansatz")
    assert term_matches("mpo", "an MPO-based method")          # hyphen = boundary
    assert term_matches("mpo", "the mpo, truncated")            # comma = boundary
    assert not term_matches("mpo", "temporal composition")     # inside word
    assert not term_matches("qhe", "fqhe physics")             # inside longer token


def test_term_matches_handles_punctuation_terms():
    assert term_matches("u(1)", "a U(1) gauge theory")
    assert term_matches("spin-1/2", "a spin-1/2 chain")


def test_term_matches_substring_mode_when_boundary_off():
    assert term_matches("mpo", "temporal", word_boundary=False)
    assert not term_matches("mpo", "temporal", word_boundary=True)


# --- scoring: keywords ------------------------------------------------------

def test_keyword_no_false_positive_inside_word(make_paper):
    cfg = Config(core_keywords=["mpo"], named_authors=[], low_priority_kw=[], feed_weights={})
    p = make_paper(abstract="We study temporal composition of channels.")
    assert score_paper(p, cfg) == 0


def test_keyword_true_positive_whole_token(make_paper):
    cfg = Config(core_keywords=["mpo"], named_authors=[], low_priority_kw=[], feed_weights={})
    for txt in ("an MPO ansatz", "MPO-based tensor network", "the mpo, then"):
        p = make_paper(abstract=txt)
        assert score_paper(p, cfg) == cfg.weights.core_keyword, txt


# --- scoring: authors -------------------------------------------------------

def test_author_no_false_positive_substring(make_paper):
    cfg = Config(core_keywords=[], named_authors=["ma", "bloch"], low_priority_kw=[], feed_weights={})
    p = make_paper(authors="Yun Mao, Anna Blochwitz")
    assert score_paper(p, cfg) == 0


def test_author_true_positive_whole_token(make_paper):
    cfg = Config(core_keywords=[], named_authors=["bloch"], low_priority_kw=[], feed_weights={})
    p = make_paper(authors="Immanuel Bloch, et al.")
    assert score_paper(p, cfg) == cfg.weights.named_author


# --- scoring: low priority --------------------------------------------------

def test_low_priority_whole_word_only(make_paper):
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=["film"], feed_weights={})
    hit = make_paper(abstract="a thin film sample")
    miss = make_paper(abstract="a study of filmography")
    assert score_paper(hit, cfg) == cfg.weights.low_priority_penalty
    assert score_paper(miss, cfg) == 0


# --- subjects stay substring ------------------------------------------------

def test_subjects_remain_substring_parent_category(make_paper):
    """Boundary matching must NOT touch subjects: parent feed 'cond-mat' should
    still score a paper whose subject is 'cond-mat.quant-gas'."""
    cfg = Config(core_keywords=[], named_authors=[], low_priority_kw=[],
                 feed_weights={"cond-mat": 3})
    p = make_paper(subjects="Condensed Matter (cond-mat.quant-gas)")
    assert score_paper(p, cfg) == 3


# --- flag plumbing ----------------------------------------------------------

def test_flag_defaults_on():
    assert Config().word_boundary_matching is True


def test_flag_off_restores_substring(make_paper):
    cfg = Config(core_keywords=["mpo"], named_authors=[], low_priority_kw=[],
                 feed_weights={}, word_boundary_matching=False)
    p = make_paper(abstract="temporal composition")
    assert score_paper(p, cfg) == cfg.weights.core_keyword


def test_config_roundtrip_preserves_flag(tmp_path):
    cfg = Config(word_boundary_matching=False)
    path = tmp_path / "c.json"
    cfg.dump(path)
    assert json.loads(path.read_text())["word_boundary_matching"] is False
    assert Config.load(path).word_boundary_matching is False


def test_explain_score_total_matches_score_paper_boundary(make_paper):
    cfg = Config(core_keywords=["mpo"], named_authors=["bloch"], low_priority_kw=["film"])
    p = make_paper(title="MPO methods", authors="Immanuel Bloch", abstract="thin film " + "x" * 300)
    assert score_paper(p, cfg) == explain_score(p, cfg)["total"]
