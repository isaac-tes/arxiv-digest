# Scoring

Every paper is reduced to a single integer score. The CLI and GUI both rank by this score and slice to `top_n`. Scoring is fully transparent: the GUI's *Why this score?* expander shows the per-rule contribution.

## Defaults

| Rule | Default weight |
|------|---------------|
| Per matched core keyword | **+6** |
| Per matched named author | **+6** (matched against the author list only) |
| Per-feed subject bonus | **per feed**: e.g. `cond-mat.quant-gas` +4, `cond-mat.mes-hall` +4, `quant-ph` +2 |
| Any low-priority term matches (applied once) | **−5** |
| Abstract longer than 200 chars | **+1** |

Scalar weights live in the `ScoringWeights` dataclass; **subject scoring is fully driven by `feed_weights`**, one bonus per configured feed, added when the feed name appears in a paper's subjects. Edit both in `arxiv_config.json` or the GUI's Scoring tab (a field per feed under *Per-feed subject bonuses*).

## `weights` + `feed_weights` in `arxiv_config.json`

```json
{
  "weights": {
    "core_keyword": 6,
    "named_author": 6,
    "low_priority_penalty": -5,
    "long_abstract_bonus": 1,
    "long_abstract_threshold": 200
  },
  "feed_weights": {
    "cond-mat.quant-gas": 4,
    "cond-mat.mes-hall": 4,
    "quant-ph": 2
  }
}
```

Missing `weights` keys fall back to defaults. Configs written before unification (with `quant_gas_subject` etc. under `weights`) are **migrated automatically** into `feed_weights` on load.

## Why the low-priority penalty fires only once

Multiple low-priority hits don't compound. A paper with three "growth" / "film" / "annealing" hits gets `−5`, not `−15`. This stops the heuristic from over-punishing legitimate work that happens to mention thin films in one sentence.

## Designing custom weights

A useful mental model: a single keyword is worth roughly two `quant-ph` subject bonuses, and a single low-priority hit cancels one keyword match. Tune from there.

Common patterns:

- **Subject-only ranking**: zero out keywords/authors, raise subject bonuses to e.g. +10.
- **Author-driven**: drop keywords to +1, raise `named_author` to +10. Useful when tracking specific groups.
- **Aggressive filtering**: `low_priority_penalty: -20` makes any film/growth hit drop a paper out of the top N entirely.

## `explain_score`

Programmatic introspection:

```python
from arxiv_digest import Config, explain_score

cfg = Config.load()
breakdown = explain_score(paper, cfg)
# {
#   "keywords": [("topological", 6), ("dmrg", 6)],
#   "authors": [("bloch", 6)],
#   "subjects": {"cond-mat.quant-gas": 4},
#   "low_priority_hits": [],
#   "low_priority_penalty": 0,
#   "abstract_bonus": 1,
#   "total": 23,
# }
```

`score_paper(paper, cfg)` is a thin wrapper that returns `breakdown["total"]`. The two functions can never drift: `score_paper` calls `explain_score` internally.
