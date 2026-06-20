#!/usr/bin/env bash
# Build the self-contained desktop server (PyInstaller one-folder bundle).
#
# Produces dist/arxiv-digest-desktop/ — a portable folder that runs the
# Streamlit server with no system Python. Wrap it in a native window with Pake
# (see scripts/build_desktop.sh) or ship as-is.
#
# Heavy build (minutes, ~300-500 MB output) — intended for release/CI, not the
# fast test loop.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Building self-contained desktop bundle with PyInstaller ..."
uv run --group bundle pyinstaller \
  --clean --noconfirm \
  packaging/arxiv_digest_desktop.spec

echo
echo "Built: dist/arxiv-digest-desktop/"
echo "Run:   ./dist/arxiv-digest-desktop/arxiv-digest-desktop"
echo "Then:  scripts/build_desktop.sh   # optional native Pake window over the same URL"
