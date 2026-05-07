#!/usr/bin/env bash
# Optional convenience launcher for the Streamlit GUI.
# The canonical command is `uv run streamlit run arxiv_gui.py`; this wrapper
# also auto-syncs the gui dependency group so a fresh clone works in one shot.
set -euo pipefail
cd "$(dirname "$0")"
uv sync --group gui --quiet
exec uv run streamlit run arxiv_gui.py "$@"
