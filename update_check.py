"""Self-update support for arxiv-digest.

Two pieces, in the spirit of modern CLI tools:

- ``check_for_update()``: a cached (24 h) check of the latest GitHub release
  against the installed version. Used to print a one-line notice on normal
  ``arxiv-digest`` runs; always fails silently (no network in tests, no
  annoyance when GitHub is unreachable).
- ``run_self_upgrade()``: the ``arxiv-digest update`` / ``arxiv-digest upgrade``
  subcommand. Detects the ``uv tool`` install and reinstalls the package from
  the latest release tag on GitHub, so the update works even if the original
  clone is gone.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

REPO_URL = "https://github.com/isaac-tes/arxiv-digest"
GIT_URL = f"{REPO_URL}.git"
LATEST_RELEASE_URL = f"https://api.github.com/repos/isaac-tes/arxiv-digest/releases/latest"

CACHE_PATH = Path("~/.arxiv_scraper/update_check.json").expanduser()
CACHE_TTL = 24 * 3600  # 24 hours


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse ``v1.2.3`` / ``1.2.3`` into a comparable tuple of ints."""
    match = re.search(r"\d+(?:\.\d+)*", v or "")
    if match is None:
        return (0,)
    return tuple(int(x) for x in match.group(0).split("."))


def _current_version() -> str:
    """Installed package version, or "0.0.0" when metadata can't resolve."""
    try:
        return metadata.version("arxiv-digest")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _detect_install_method() -> str | None:
    """Return ``'uv'``, or None if we can't tell."""
    prefix = Path(sys.prefix)
    parts = tuple(p.lower() for p in prefix.parts)
    pairs = list(zip(parts, parts[1:]))

    if ("uv", "tools") in pairs:
        return "uv"

    # Env-var override: only trust it if sys.prefix is actually under it.
    root = os.environ.get("UV_TOOL_DIR")
    if root:
        try:
            if prefix.is_relative_to(Path(root)):
                return "uv"
        except (ValueError, OSError):
            pass
    return None


def _gui_extra() -> str:
    """``'[gui]'`` when Streamlit is installed in this env, ``''`` otherwise.

    Keeps a CLI-only install CLI-only through upgrades.
    """
    return "[gui]" if find_spec("streamlit") is not None else ""


def _read_cache() -> str | None:
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None
    if data.get("fetched_at", 0) + CACHE_TTL < time.time():
        return None
    version = data.get("latest_version")
    return version if isinstance(version, str) else None


def _write_cache(version: str | None) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"fetched_at": int(time.time()), "latest_version": version})
        )
    except OSError:
        pass


def _latest_release() -> str | None:
    """Latest release tag from GitHub (``v0.5.6``), via a 24 h cache.

    Returns None when GitHub is unreachable or has no releases.
    """
    cached = _read_cache()
    if cached is not None:
        return cached
    latest = None
    try:
        req = urllib.request.Request(LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            latest = json.loads(resp.read().decode()).get("tag_name")
            if not isinstance(latest, str):
                latest = None
    except Exception:
        latest = None
    _write_cache(latest)
    return latest


def check_for_update(current_version: str | None = None) -> str | None:
    """Return a one-line update notice if a newer release exists, else None.

    Parameters
    ----------
    current_version : str | None
        Installed version; defaults to the installed package metadata.

    Returns
    -------
    str | None
        Human-readable notice, or None when up to date / offline.
    """
    try:
        current = current_version or _current_version()
        latest = _latest_release()
        if latest and _parse_version(latest) > _parse_version(current):
            method = _detect_install_method()
            if method:
                return (
                    f"A newer version of arxiv-digest is available ({latest}); "
                    f"you are using {current}. Run `arxiv-digest update` to upgrade."
                )
            return (
                f"A newer version of arxiv-digest is available ({latest}); "
                f"you are using {current}. Run `arxiv-digest update` for upgrade "
                "instructions."
            )
        return None
    except Exception:
        return None


def _upgrade_source() -> str:
    """PEP 508 requirement string to reinstall from (latest tag if known)."""
    latest = _latest_release()
    if latest and _parse_version(latest) > _parse_version(_current_version()):
        return f"arxiv-digest{_gui_extra()} @ {GIT_URL}@{latest}"
    return f"arxiv-digest{_gui_extra()} @ {GIT_URL}"


def run_self_upgrade() -> int:
    """Reinstall the tool from GitHub, honoring how it was installed.

    Returns
    -------
    int
        Subprocess exit code, 1 on detection failure, or 2 if the upgrade was
        skipped (Windows executable lock / no package manager found).
    """
    method = _detect_install_method()
    if method is None:
        print(
            "Could not detect the uv tool install (is arxiv-digest on your PATH via uv?).\n"
            f"  sys.prefix:     {sys.prefix}\n"
            f"  sys.executable: {sys.executable}\n"
            "To upgrade manually, run one of:\n"
            f"  uv tool install --reinstall '{_upgrade_source()}'\n"
            f"  git clone {REPO_URL} && (cd arxiv-digest && uv tool install '.[gui]')"
        )
        return 2

    cmd = ["uv", "tool", "install", "--reinstall", _upgrade_source()]

    # Windows: the running entry-point .exe is locked while this process lives,
    # so an in-place upgrade would fail to replace it. Print instead (same
    # approach as other cross-platform CLI tools).
    if sys.platform == "win32":
        print(f"To upgrade arxiv-digest on Windows, run:\n  {' '.join(cmd)}")
        return 2

    try:
        return subprocess.run(cmd, check=False).returncode
    except FileNotFoundError:
        print(
            "Detected a uv tool install, but `uv` is not on PATH. "
            "Run the upgrade manually from a shell where it is available.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run_self_upgrade())
