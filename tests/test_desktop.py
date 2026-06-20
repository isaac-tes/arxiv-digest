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
