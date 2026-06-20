#!/usr/bin/env bash
# Build a native desktop window for the arXiv Digest GUI using Pake.
#
# Pake wraps a RUNNING localhost URL into a native WebView binary; it does not
# bundle the Python server. Workflow:
#   1. In one terminal:  uv run arxiv-desktop        (starts Streamlit on :8501)
#   2. In another:       scripts/build_desktop.sh    (builds the native app)
#   3. Ship the produced binary alongside a way to start the server.
#
# Requires Node (for `npx pake-cli`). No global install needed.
set -euo pipefail

URL="${1:-http://127.0.0.1:8501}"
NAME="${2:-arXiv Digest}"

if ! command -v npx >/dev/null 2>&1; then
  echo "node/npx not found. Install Node 18+ first (e.g. brew install node)." >&2
  exit 1
fi

echo "Building native window for ${URL} (name: ${NAME}) ..."
echo "Note: the target URL must be reachable now — start 'uv run arxiv-desktop' first."

npx --yes pake-cli "${URL}" \
  --name "${NAME}" \
  --width 1280 \
  --height 800 \
  --hide-title-bar

echo "Done. The produced app points at ${URL}; the Streamlit server must be running when it launches."
