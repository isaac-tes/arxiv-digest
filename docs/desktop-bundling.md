# Desktop app & self-contained distributable

Two ways to ship the Streamlit GUI as a desktop app. Both reuse the same
`arxiv_desktop.py` launcher.

## Background: what Pake does (and doesn't)

[Pake](https://github.com/tw93/pake) wraps a **running** URL into a native
WebView window (Rust/Tauri under the hood). It is tiny and fast, but it does
**not** bundle the Python/Streamlit server. So a Pake binary on its own assumes
something is already serving `http://127.0.0.1:8501`.

## Path (a) — dev / personal desktop shortcut

The lightweight option (PR #2).

```bash
uv run arxiv-desktop          # starts Streamlit headless on :8501, opens a window
scripts/build_desktop.sh      # one-time: build a native Pake window over that URL
```

The user (or a login item) keeps the server running; the Pake window is just a
chromeless browser. Good for a single machine; **not** a redistributable app.

## Path (b) — self-contained distributable

Goal: a binary an end user runs with **no Python install**. Embed the
interpreter + Streamlit server with PyInstaller.

### Architecture

```
┌─────────────────────────────┐
│ arxiv-digest-desktop (PyInstaller one-folder)        │
│  • embedded CPython + Streamlit + pandas             │
│  • arxiv_gui.py / arxiv_digest.py shipped as datas   │
│  • arxiv_desktop.main():                             │
│      is_frozen() -> run server in-process via        │
│      streamlit.web.bootstrap, open window when ready │
└─────────────────────────────┘
        (optional) Pake window points at the same :8501
```

`arxiv_desktop.py` is frozen-aware:

- `is_frozen()` / `resource_path()` resolve bundled files via `sys._MEIPASS`.
- When frozen there is no `streamlit` console script, so the server is started
  in-process through `streamlit.web.bootstrap.run`.

### Build

```bash
uv run --group bundle pyinstaller packaging/arxiv_digest_desktop.spec
# or
scripts/build_bundle.sh
# -> dist/arxiv-digest-desktop/arxiv-digest-desktop
```

### Streamlit freezing gotchas (handled in the spec)

| Gotcha | Fix |
| --- | --- |
| Frontend assets (`static/index.html`) missing → blank page | `collect_all("streamlit")` |
| `importlib.metadata` version lookup crashes on boot | `copy_metadata("streamlit")` |
| App scripts not in bundle | shipped as `datas`, resolved via `resource_path()` |
| `streamlit run` CLI absent when frozen | `streamlit.web.bootstrap.run(...)` in-process |

### Trade-offs & open items

- **Size:** one-folder bundle is ~300–500 MB (CPython + pandas/pyarrow). A
  `--onefile` build is smaller to ship but slower to start (unpacks to a temp).
- **Native window:** path (b) still pairs with Pake for the chromeless window,
  or graduate to a full **Tauri sidecar** (Tauri app + the frozen server as a
  sidecar process) for a single installable `.app`/`.msi`. Heavier (Rust
  toolchain) — deferred.
- **CI:** the freeze is minutes-long and platform-specific (macOS/Windows/Linux
  each need their own runner). Build in release CI, not the test loop.
- **Code signing / notarization** (macOS) and Windows SmartScreen are required
  before public distribution — not yet set up.

Tracked in `arxiv_scraper_cli-7k9` (depends on the Pake slice `f8e`).
