#!/usr/bin/env bash
# Update arXiv digest to the latest version.
#
# Pulls the newest code and rebuilds the installed `arxiv-digest` / `arxiv-gui`
# tools. Run it from anywhere inside your clone:
#
#     ./scripts/update.sh
#
# (uv tool installs run in an isolated env that does NOT auto-track the clone,
#  so a plain `git pull` is not enough — the --reinstall rebuilds it.)
set -euo pipefail

# Move to the repo root (parent of this script's dir).
cd "$(dirname "$0")/.."

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "✗ Not a git clone — re-run from inside the arxiv-digest repository." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "✗ uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "→ Pulling latest code…"
git pull --ff-only

echo "→ Reinstalling the arxiv-digest / arxiv-gui tools…"
uv tool install '.[gui]' --reinstall

echo
echo "✓ Updated to $(git describe --tags --always 2>/dev/null || git rev-parse --short HEAD)."
echo "  Run 'arxiv-gui' or 'arxiv-digest --help'."
