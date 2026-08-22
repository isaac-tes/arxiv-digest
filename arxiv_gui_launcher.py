"""Console-script entry that launches the Streamlit GUI.

Wired to ``arxiv-gui`` via ``[project.scripts]`` in pyproject.toml so that
``uv tool install '.[gui]'`` produces a working ``arxiv-gui`` executable.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print(
            "Streamlit is not installed. Install GUI extras with:\n"
            "  uv tool install '.[gui]'   # if installing from source\n"
            "  uv sync --group gui        # if working in a clone",
            file=sys.stderr,
        )
        return 1
    app = Path(__file__).resolve().parent / "arxiv_gui.py"
    # Auto-open the browser so the GUI pops up without manually pasting the
    # localhost URL. Streamlit's server.headless defaults to false (open the
    # browser), but when launched through the `uv tool` wrapper it can miss the
    # interactive context and stay headless. Force it unless the user passes an
    # explicit --server.headless override.
    if not any(a.startswith("--server.headless") for a in sys.argv[1:]):
        sys.argv = ["streamlit", "run", str(app), "--server.headless", "false", *sys.argv[1:]]
    else:
        sys.argv = ["streamlit", "run", str(app), *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
