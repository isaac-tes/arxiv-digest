"""Unit tests for the desktop launcher helpers (no server/network needed)."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import arxiv_desktop as dt


def test_streamlit_command_is_headless_on_requested_port():
    cmd = dt.streamlit_command(Path("arxiv_gui.py"), host="127.0.0.1", port=9999)
    assert cmd[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert "arxiv_gui.py" in cmd[4]
    assert cmd[cmd.index("--server.port") + 1] == "9999"
    assert cmd[cmd.index("--server.address") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--server.headless") + 1] == "true"


def test_pake_build_command_defaults():
    cmd = dt.pake_build_command("http://127.0.0.1:8501")
    assert cmd[:3] == ["npx", "--yes", "pake-cli"]
    assert "http://127.0.0.1:8501" in cmd
    assert cmd[cmd.index("--name") + 1] == dt.APP_NAME
    assert "--hide-title-bar" in cmd


def test_pake_build_command_no_title_bar_flag_toggle():
    cmd = dt.pake_build_command("http://x", hide_title_bar=False)
    assert "--hide-title-bar" not in cmd


def test_port_is_open_detects_listening_socket():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert dt.port_is_open("127.0.0.1", port) is True
    finally:
        srv.close()
    # closed socket -> not open
    assert dt.port_is_open("127.0.0.1", port) is False


def test_wait_for_port_times_out_fast_on_dead_port():
    # Unused high port; should return False quickly, not hang.
    assert dt.wait_for_port("127.0.0.1", 1, timeout=0.5, interval=0.1) is False


# ───────────── Frozen / PyInstaller bundling (arxiv_scraper_cli-7k9) ─────────────

def test_is_frozen_false_under_normal_python():
    assert dt.is_frozen() is False


def test_resource_path_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert dt.resource_path("arxiv_gui.py") == tmp_path / "arxiv_gui.py"


def test_resource_path_falls_back_to_source_dir(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    p = dt.resource_path("arxiv_gui.py")
    assert p.name == "arxiv_gui.py"
    assert p.parent == Path(dt.__file__).resolve().parent


def test_pyinstaller_spec_exists_and_handles_streamlit_gotchas():
    spec = Path(__file__).resolve().parent.parent / "packaging" / "arxiv_digest_desktop.spec"
    assert spec.exists(), "PyInstaller spec missing"
    text = spec.read_text()
    # The two Streamlit freezing gotchas must be addressed.
    assert 'copy_metadata("streamlit")' in text
    assert "collect_all" in text
    assert "arxiv_gui.py" in text
