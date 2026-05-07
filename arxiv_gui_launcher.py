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
    sys.argv = ["streamlit", "run", str(app), *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
