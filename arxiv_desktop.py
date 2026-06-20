"""Desktop launcher: run the Streamlit GUI inside a native Pake window.

Pake (https://github.com/tw93/pake) wraps a *running* localhost URL into a
lightweight native WebView window. Pake does **not** bundle the Python/Streamlit
server, so this launcher owns the server lifecycle:

    1. start Streamlit headless on a local port,
    2. wait until the port answers,
    3. open the Pake-built app if present, else the system browser,
    4. tear the server down on exit.

Build the native window once with ``scripts/build_desktop.sh`` (uses
``npx pake-cli``); after that the binary points at the same localhost URL this
launcher serves.

Wired to the ``arxiv-desktop`` console script in pyproject.toml.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501
APP_NAME = "arXiv Digest"


def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """True if a TCP connection to host:port succeeds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout: float = 30.0, interval: float = 0.25) -> bool:
    """Poll until host:port accepts connections or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_is_open(host, port):
            return True
        time.sleep(interval)
    return False


def streamlit_command(app: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> list[str]:
    """argv that starts Streamlit headless on the given host/port."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]


def pake_build_command(
    url: str,
    name: str = APP_NAME,
    *,
    hide_title_bar: bool = True,
    width: int = 1280,
    height: int = 800,
) -> list[str]:
    """npx pake-cli argv that wraps ``url`` into a native window.

    Kept pure (no side effects) so it is unit-testable without pake installed.
    """
    cmd = ["npx", "--yes", "pake-cli", url, "--name", name,
           "--width", str(width), "--height", str(height)]
    if hide_title_bar:
        cmd.append("--hide-title-bar")
    return cmd


def _app_path() -> Path:
    return Path(__file__).resolve().parent / "arxiv_gui.py"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    host, port = DEFAULT_HOST, DEFAULT_PORT
    url = f"http://{host}:{port}"

    app = _app_path()
    if not app.exists():
        print(f"GUI app not found: {app}", file=sys.stderr)
        return 1

    try:
        import streamlit  # noqa: F401
    except ImportError:
        print(
            "Streamlit is not installed. Install GUI extras with:\n"
            "  uv sync --group gui        # in a clone\n"
            "  uv tool install '.[gui]'   # from source",
            file=sys.stderr,
        )
        return 1

    print(f"Starting {APP_NAME} server on {url} ...")
    server = subprocess.Popen(streamlit_command(app, host, port))
    try:
        if not wait_for_port(host, port):
            print("Server did not come up in time.", file=sys.stderr)
            return 1
        print(f"Server ready. Opening {url}")
        # The native Pake window, once built, is a standalone app the user
        # launches separately; here we just ensure the server is up and open a
        # window for convenience.
        webbrowser.open(url)
        server.wait()
    except KeyboardInterrupt:
        print("\nShutting down server ...")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
