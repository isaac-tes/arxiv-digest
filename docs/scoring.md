# Scoring

Every paper is reduced to a single integer score. The CLI and GUI both rank by this score and slice to `top_n`. Scoring is fully transparent — the GUI's *Why this score?* expander shows the per-rule contribution.

## Defaults

| Rule | Default weight |
|------|---------------|
| Per matched core keyword | **+6** |
| Per matched named author | **+6** (matched against the author list only) |
| Subject contains `cond-mat.quant-gas` | **+4** |
| Subject contains `cond-mat.mes-hall` | **+4** |
| Subject contains `quant-ph` | **+2** |
| Per-feed bonus (any extra feed) | **configurable** — set per feed in the Scoring tab |
| Any low-priority term matches (applied once) | **−5** |
| Abstract longer than 200 chars | **+1** |

All values live in the `ScoringWeights` dataclass and are configurable via `weights` in `arxiv_config.json` or the GUI's Scoring tab.

## `weights` block in `arxiv_config.json`

```json
{
  "weights": {
    "core_keyword": 6,
    "named_author": 6,
    "quant_gas_subject": 4,
    "mes_hall_subject": 4,
    "quant_ph_subject": 2,
    "low_priority_penalty": -5,
    "long_abstract_bonus": 1,
    "long_abstract_threshold": 200
  }
}
```

Missing keys fall back to the defaults above, so partial blocks are valid.

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

`score_paper(paper, cfg)` is a thin wrapper that returns `breakdown["total"]`. The two functions can never drift — `score_paper` calls `explain_score` internally.
