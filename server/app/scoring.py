"""Scoring pipeline (ADR 0004).

Loads the shared ``arxiv_digest`` core from the repo root and runs the configured
signals over a paper, merging their scores and explanations.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .settings import REPO_ROOT

# Make the shared arxiv_digest.py importable from the repo root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arxiv_digest import Config  # noqa: E402

from .signals.keyword import KeywordSignal  # noqa: E402

# Ordered list of active signals. v1 ships only the keyword signal; later
# signals (embedding, author-affinity, veto) are appended here additively.
ACTIVE_SIGNALS: list[Any] = [KeywordSignal()]


def config_from_dict(data: dict[str, Any]) -> Config:
    """Build an arxiv_digest.Config from a JSON dict (the stored config blob)."""
    return Config.from_json(data)


def load_user_config(db, user) -> Config:
    """Load a user's stored config, or fall back to a default config file, or
    the built-in defaults.

    Shared by the digest/score/config routers so config loading lives in one
    place. `db` is a SQLAlchemy session; `user` is a models.User. When the user
    has no stored config, `DIGEST_DEFAULT_CONFIG_PATH` (a saved GUI profile,
    e.g. topology-mode.json) is used if set, so the mobile app scores with the
    same preferences as the web GUI.
    """
    import json

    from .models import Config as ConfigModel
    from .settings import get_settings

    row = db.query(ConfigModel).filter(ConfigModel.user_id == user.id).first()
    if row and row.data:
        return config_from_dict(json.loads(row.data))

    default_path = get_settings().default_config_path
    if default_path:
        path = Path(default_path).expanduser()
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                return config_from_dict(json.load(fh))

    return Config()


def score_paper(paper: dict, cfg: Config) -> int:
    """Total score across all active signals."""
    return sum(sig.score(paper, cfg) for sig in ACTIVE_SIGNALS)


def explain_paper(paper: dict, cfg: Config) -> dict[str, Any]:
    """Per-signal breakdown of a paper's score."""
    breakdown: dict[str, Any] = {"signals": {}, "total": 0}
    for sig in ACTIVE_SIGNALS:
        sig_explain = sig.explain(paper, cfg)
        breakdown["signals"][sig.name] = sig_explain
        breakdown["total"] += sig_explain.get("total", 0)
    return breakdown


def highlight_paper(paper: dict, cfg: Config) -> dict[str, Any]:
    """Matched terms per aspect for the UI to highlight."""
    merged: dict[str, Any] = {}
    for sig in ACTIVE_SIGNALS:
        for aspect, terms in sig.highlight(paper, cfg).items():
            merged.setdefault(aspect, []).extend(terms)
    return merged
