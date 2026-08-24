# Troubleshooting

Common issues when running the CLI or the Streamlit GUI.

## GUI

### "My changes don't save" / a widget looks stuck

Older builds had a bug where **Reset to defaults**, **Apply weights**, **Load
profile**, and **Import** updated the underlying config but left the on-screen
widgets showing their old values. This was a Streamlit footgun: once a widget is
given an explicit `key`, Streamlit ignores the `value=`/`default=` argument on
every rerun because `st.session_state[key]` already holds a value.

This is fixed: those handlers now clear the affected widget state before
rerunning (`_reset_widget_state` in `arxiv_gui.py`) so the widgets re-read from
the active config. If you still see stale values:

- Use the in-app buttons (**Reset to defaults**, **Apply weights**) rather than
  expecting an edit to apply automatically. List and weight edits commit on
  **Save** / **Apply**.
- Hard-refresh the browser tab, or restart `streamlit run arxiv_gui.py`.

### Running inside the VS Code integrated browser

Launch with `uv run streamlit run arxiv_gui.py` and open the printed
`http://localhost:8501` URL. Streamlit keeps per-session state in the browser
tab; if you reload the Simple Browser tab the session resets (papers and unsaved
config are cleared). Save a **Profile** (Profiles tab) to persist config across
sessions, or **Write project config** to feed the CLI.

### "Fetched 0 papers"

- The selected timeframe may genuinely have no new listings (`today` = arXiv
  `/new`, `pastweek` = `/pastweek`).
- A feed URL may be wrong. Feeds are edited on the **Feeds** tab and must point
  at an arXiv listing page, e.g. `https://arxiv.org/list/cond-mat/new`.
- arXiv may be rate-limiting; click **Clear fetch cache** and retry.

## CLI

### Flag names

Use `--timeframe {today,pastweek}`. There are no `--today` / `--pastweek` /
`--days` flags despite some older docs. Confirm with `--help`.

### Inspecting defaults

```bash
uv run python arxiv_digest.py --list-config --no-config
```

shows the built-in defaults without reading `arxiv_config.json`.
