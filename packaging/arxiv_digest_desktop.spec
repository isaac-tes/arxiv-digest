# PyInstaller spec for the self-contained arXiv Digest desktop server.
#
# Builds a one-folder bundle that embeds the Python runtime + Streamlit server,
# so end users need no Python install. Build with:
#
#     uv run --group bundle pyinstaller packaging/arxiv_digest_desktop.spec
#
# Notes / gotchas handled here:
#   * collect_all('streamlit') pulls the compiled frontend under static/.
#   * copy_metadata('streamlit') — Streamlit reads its own version via
#     importlib.metadata at runtime; without metadata it crashes on boot.
#   * arxiv_gui.py / arxiv_digest.py are shipped as datas and resolved at
#     runtime through arxiv_desktop.resource_path() (sys._MEIPASS).
import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

# PyInstaller resolves spec-relative paths from the spec's own directory, so
# anchor everything on the repo root (parent of packaging/).
ROOT = os.path.dirname(SPECPATH)  # noqa: F821 -- SPECPATH injected by PyInstaller

datas, binaries, hiddenimports = [], [], []
for pkg in ("streamlit", "pandas", "altair", "pyarrow"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass  # optional deps; skip if absent

datas += copy_metadata("streamlit")
datas += [
    (os.path.join(ROOT, "arxiv_gui.py"), "."),
    (os.path.join(ROOT, "arxiv_digest.py"), "."),
    (os.path.join(ROOT, ".streamlit", "config.toml"), ".streamlit"),
]

hiddenimports += [
    "streamlit.runtime.scriptrunner.magic_funcs",
    "arxiv_gui",
    "arxiv_digest",
]

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "arxiv_desktop.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "langchain", "tkinter"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="arxiv-digest-desktop",
    console=True,  # keep a console for the server log; flip to False for a silent app
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="arxiv-digest-desktop",
)
