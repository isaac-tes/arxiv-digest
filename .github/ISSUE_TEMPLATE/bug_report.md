---
name: Bug report
about: Something is broken or behaves unexpectedly
title: "[Bug] "
labels: bug
assignees: ''
---

## Description

A clear description of the bug.

## Steps to reproduce

```bash
# Minimal command(s) that trigger the bug, e.g.
uv run python arxiv_digest.py --timeframe today --top 10
```

## Expected behaviour

What you expected to happen.

## Actual behaviour

What actually happens (include the full traceback if applicable).

## Environment

- arxiv-digest version: <!-- e.g. 0.2.0 — see pyproject.toml -->
- Python version: <!-- e.g. 3.12.4 -->
- OS: <!-- e.g. macOS 14, Ubuntu 24.04 -->
- Streamlit version (if GUI bug): <!-- `uv run streamlit --version` -->

## Additional context

Any other context, screenshots, the relevant `arxiv_config.json` (with personal preferences redacted), or the `reports/` output that helps reproduce the issue.
