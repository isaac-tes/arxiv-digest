"""Pluggable scoring signals (ADR 0004).

Each signal contributes a score and an explanation. The
pipeline sums signals; adding a signal later is additive and does not break the
API or the app.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Signal(Protocol):
    """A single scoring dimension in the pipeline."""

    name: str

    def score(self, paper: dict, cfg) -> int: ...

    def explain(self, paper: dict, cfg) -> dict: ...

