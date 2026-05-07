# Quickstart

Three install paths depending on what you want.

## Path 1 — clone and run (recommended for tinkering)

```bash
git clone https://github.com/isaac-tes/arxiv-digest.git
cd arxiv-digest
uv sync --group dev                      # CLI + GUI + tests + docs
uv run pytest -q                         # 74-test suite, ~1s
uv run python arxiv_digest.py --top 10   # CLI sanity check
uv run streamlit run arxiv_gui.py        # GUI in browser at localhost:8501
```

The GUI also ships an optional convenience launcher:

```bash
./launch_gui.sh                          # auto-syncs gui group, then runs
```

## Path 2 — install as a tool (recommended for daily CLI use)

```bash
uv tool install '.[gui]'                 # from inside a clone
arxiv-digest --top 10                    # CLI command on PATH
arxiv-gui                                # GUI command on PATH
```

`uv tool install` puts the executables on your PATH in their own isolated environment, so they survive across clones and venvs. To upgrade after a `git pull`:

```bash
uv tool install '.[gui]' --reinstall
```

To uninstall:

```bash
uv tool uninstall arxiv-digest
```

## Path 3 — paste into ChatGPT

`arxiv_digest.py` is intentionally a single file with only `requests` + `beautifulsoup4` as runtime deps. Paste the file into Code Interpreter / Advanced Data Analysis and run `python arxiv_digest.py --top 10`.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Python 3.12 or newer (uv installs it for you if missing)

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `streamlit: command not found` after `uv tool install .` | You skipped the `[gui]` extra. Reinstall with `uv tool install '.[gui]' --reinstall`. |
| GUI says "Streamlit is not installed" | You ran `arxiv-gui` from a venv without the `gui` group. Use `uv sync --group gui` or install with the extra. |
| Tests pass locally, CI fails | CI runs `uv sync --group dev` on a clean Python 3.12. Pin your local Python with `uv python pin 3.12`. |
| `arxiv_config.json` not picked up | The CLI reads it from the current working directory. Either `cd` into the repo or pass `--config /path/to/config.json`. |
