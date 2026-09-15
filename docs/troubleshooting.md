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

### arXiv is rate-limiting or blocking you

Symptom: a `pastweek` fetch hangs for a long time, or the log shows repeated
`API 429; retrying...` / `Rate exceeded` / `ReadTimeout`.

What's happening: the `pastweek` timeframe uses arXiv's **export API**
(`export.arxiv.org`), which throttles bursts by returning HTTP `429` — sometimes
blocking your IP for **minutes up to ~1 hour**. It trips on paginating a big
feed (e.g. `cond-mat`), fetching many feeds back-to-back, or refetching often.

What the app does about it:

- Paces requests ~3s apart, retries a `429`/timeout a few times with capped
  backoff, and gives up within a ~30s budget instead of grinding for minutes.
- Falls back to arXiv's HTML `/pastweek` listing (a different, more tolerant
  host) when the API stays blocked, and shows a warning saying so. Results may
  then cover fewer than seven days.
- **Caches results per day** so a normal re-open doesn't re-hit arXiv at all
  (see [Caching](gui-guide.md#caching)).

What you can do:

- **Wait a few minutes to ~1 hour** without fetching; the block clears on its
  own once you stop hitting the API.
- Rely on the cache: re-selecting the same feeds the same day is served from
  disk with no network call.
- Fetch fewer feeds at once, and avoid clicking **Fetch papers** repeatedly.

## CLI

### Flag names

Use `--timeframe {today,pastweek}`. There are no `--today` / `--pastweek` /
`--days` flags despite some older docs. Confirm with `--help`.

### Inspecting defaults

```bash
uv run python arxiv_digest.py --list-config --no-config
```

shows the built-in defaults without reading `arxiv_config.json`.
