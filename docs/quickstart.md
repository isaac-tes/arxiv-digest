# Quickstart

Two commands get you the web app: clone the repo, install it as a tool.

## 1. Install uv

Skip this if you already have `uv` (check with `uv --version`).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # macOS / Linux
```

Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, or `brew install uv` on macOS. Restart your terminal afterwards. See the official [uv install docs](https://docs.astral.sh/uv/getting-started/installation/).

## 2. Clone and install

```bash
git clone https://github.com/isaac-tes/arxiv-digest.git
cd arxiv-digest
uv tool install '.[gui]'      # puts arxiv-digest + arxiv-gui on your PATH
```

Python 3.12 or newer is required; `uv` installs it for you if it's missing.

## 3. Run it

```bash
arxiv-gui                     # web app — opens http://localhost:8501 in your browser
arxiv-digest --top 10         # CLI digest, prints ranked papers to stdout
```

In the GUI, hit **Fetch papers** in the sidebar and start reading. Pick a
[starter preset](index.md#starter-presets) under **Profiles** if you'd rather begin from
a prepared topic bundle (e.g. *open quantum systems*). To tune what counts as a
match, edit the **Keywords** / **Authors** / **Scoring** tabs; the Papers tab
re-ranks instantly.

Updating after a while? One command, no clone needed:

```bash
arxiv-digest update    # reinstalls from the latest GitHub release
```

Or from inside the clone (e.g. to track a branch):

```bash
git pull
uv tool install '.[gui]' --reinstall    # rebuilds both commands on PATH
```

To remove: `uv tool uninstall arxiv-digest`.

---

## Alternatives

### Run without installing (uvx)

`uvx` builds and runs the package from your clone on the fly, with nothing to
install or uninstall:

```bash
uvx --from '.[gui]' arxiv-gui               # web app — opens your browser
uvx --from '.[gui]' arxiv-digest --top 10   # CLI
```

Drop the `[gui]` extra for CLI-only runs (`uvx --from . arxiv-digest --top 10`).

### Run from the clone (for development)

If you want to hack on the code or run the test suite:

```bash
uv sync --group dev                      # CLI + GUI + tests + docs
uv run pytest -q                         # full test suite, ~2s, no network
uv run python arxiv_digest.py --top 10   # CLI sanity check
uv run streamlit run arxiv_gui.py        # GUI in browser at localhost:8501
./launch_gui.sh                          # optional: auto-syncs gui group, then runs
```

`uv run` always picks up your latest edits, no reinstall needed.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `streamlit: command not found` after `uv tool install .` | You skipped the `[gui]` extra. Reinstall with `uv tool install '.[gui]' --reinstall`. |
| GUI says "Streamlit is not installed" | You ran `arxiv-gui` from a venv without the `gui` group. Use `uv sync --group gui` or install with the extra. |
| Tests pass locally, CI fails | CI runs `uv sync --group dev` on a clean Python 3.12. Pin your local Python with `uv python pin 3.12`. |
| `arxiv_config.json` not picked up | The CLI reads it from the current working directory. Either `cd` into the repo or pass `--config /path/to/config.json`. |
