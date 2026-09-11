"""Tests for update_check: version parsing, release check, and self-upgrade."""
from __future__ import annotations

import json
import sys
import types

import pytest

import update_check


# ── _parse_version ────────────────────────────────────────────────────────────


def test_parse_version_strips_v_prefix():
    assert update_check._parse_version("v0.5.6") == (0, 5, 6)


def test_parse_version_plain():
    assert update_check._parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_garbage_is_zero():
    assert update_check._parse_version("no-version-here") == (0,)


def test_parse_version_comparison():
    assert update_check._parse_version("v0.6.0") > update_check._parse_version("0.5.6")
    assert update_check._parse_version("v0.5.6") == update_check._parse_version("0.5.6")


# ── check_for_update ──────────────────────────────────────────────────────────


def test_check_for_update_newer_release(monkeypatch):
    monkeypatch.setattr(update_check, "_latest_release", lambda: "v99.0.0")
    notice = update_check.check_for_update("0.5.6")
    assert notice is not None
    assert "99.0.0" in notice
    assert "arxiv-digest update" in notice


def test_check_for_update_up_to_date(monkeypatch):
    monkeypatch.setattr(update_check, "_latest_release", lambda: "v0.5.6")
    assert update_check.check_for_update("0.5.6") is None


def test_check_for_update_no_release(monkeypatch):
    monkeypatch.setattr(update_check, "_latest_release", lambda: None)
    assert update_check.check_for_update("0.5.6") is None


def test_check_for_update_swallows_errors(monkeypatch):
    def boom():
        raise OSError("offline")

    monkeypatch.setattr(update_check, "_latest_release", boom)
    assert update_check.check_for_update("0.5.6") is None


# ── _latest_release (cache + HTTP) ────────────────────────────────────────────


def test_latest_release_reads_fresh_cache(monkeypatch, tmp_path):
    cache = tmp_path / "update_check.json"
    cache.write_text(json.dumps({"fetched_at": update_check.time.time(), "latest_version": "v1.0.0"}))
    monkeypatch.setattr(update_check, "CACHE_PATH", cache)
    assert update_check._latest_release() == "v1.0.0"


def test_latest_release_ignores_stale_cache(monkeypatch, tmp_path):
    cache = tmp_path / "update_check.json"
    stale = update_check.time.time() - update_check.CACHE_TTL - 10
    cache.write_text(json.dumps({"fetched_at": stale, "latest_version": "v1.0.0"}))
    monkeypatch.setattr(update_check, "CACHE_PATH", cache)
    monkeypatch.setattr(update_check, "_write_cache", lambda v: None)

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"tag_name": "v2.0.0"}).encode()

    def fake_urlopen(req, timeout):
        return FakeResp()

    monkeypatch.setattr(update_check.urllib.request, "urlopen", fake_urlopen)
    assert update_check._latest_release() == "v2.0.0"


def test_latest_release_offline_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(update_check, "CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(update_check, "_write_cache", lambda v: None)

    def fake_urlopen(req, timeout):
        raise OSError("offline")

    monkeypatch.setattr(update_check.urllib.request, "urlopen", fake_urlopen)
    assert update_check._latest_release() is None


# ── install-method detection ──────────────────────────────────────────────────


def test_detect_install_method_via_env(monkeypatch, tmp_path):
    tool_root = tmp_path / "tools"
    monkeypatch.setattr(sys, "prefix", str(tool_root / "arxiv-digest"))
    monkeypatch.setenv("UV_TOOL_DIR", str(tool_root))
    assert update_check._detect_install_method() == "uv"


def test_detect_install_method_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "somewhere-else"))
    monkeypatch.delenv("UV_TOOL_DIR", raising=False)
    assert update_check._detect_install_method() is None


# ── upgrade source & run_self_upgrade ─────────────────────────────────────────


def test_upgrade_source_pins_newer_tag(monkeypatch):
    monkeypatch.setattr(update_check, "_latest_release", lambda: "v99.0.0")
    monkeypatch.setattr(update_check, "_current_version", lambda: "0.5.6")
    monkeypatch.setattr(update_check, "_gui_extra", lambda: "")
    assert update_check._upgrade_source() == f"arxiv-digest @ {update_check.GIT_URL}@v99.0.0"


def test_upgrade_source_falls_back_to_head(monkeypatch):
    monkeypatch.setattr(update_check, "_latest_release", lambda: None)
    monkeypatch.setattr(update_check, "_gui_extra", lambda: "[gui]")
    assert update_check._upgrade_source() == f"arxiv-digest[gui] @ {update_check.GIT_URL}"


def test_run_self_upgrade_unknown_method_prints_instructions(monkeypatch, capsys):
    monkeypatch.setattr(update_check, "_detect_install_method", lambda: None)
    assert update_check.run_self_upgrade() == 2
    out = capsys.readouterr().out
    assert "uv tool install --reinstall" in out


def test_run_self_upgrade_windows_prints_command(monkeypatch, capsys):
    monkeypatch.setattr(update_check, "_detect_install_method", lambda: "uv")
    monkeypatch.setattr(update_check, "_gui_extra", lambda: "[gui]")
    monkeypatch.setattr(update_check, "_upgrade_source", lambda: "arxiv-digest[gui] @ url")
    monkeypatch.setattr(sys, "platform", "win32")
    assert update_check.run_self_upgrade() == 2
    assert "To upgrade arxiv-digest on Windows" in capsys.readouterr().out


def test_run_self_upgrade_runs_uv(monkeypatch):
    monkeypatch.setattr(update_check, "_detect_install_method", lambda: "uv")
    monkeypatch.setattr(update_check, "_gui_extra", lambda: "")
    monkeypatch.setattr(update_check, "_upgrade_source", lambda: "arxiv-digest @ url")
    monkeypatch.setattr(sys, "platform", "linux")
    seen = types.SimpleNamespace(cmd=None)

    def fake_run(cmd, check):
        seen.cmd = cmd
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(update_check.subprocess, "run", fake_run)
    assert update_check.run_self_upgrade() == 0
    assert seen.cmd == ["uv", "tool", "install", "--reinstall", "arxiv-digest @ url"]


def test_run_self_upgrade_missing_binary(monkeypatch, capsys):
    monkeypatch.setattr(update_check, "_detect_install_method", lambda: "uv")
    monkeypatch.setattr(update_check, "_gui_extra", lambda: "")
    monkeypatch.setattr(update_check, "_upgrade_source", lambda: "arxiv-digest @ url")
    monkeypatch.setattr(sys, "platform", "linux")

    def fake_run(cmd, check):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(update_check.subprocess, "run", fake_run)
    assert update_check.run_self_upgrade() == 1
    assert "not on PATH" in capsys.readouterr().err


# ── CLI wiring ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flag", ["update", "upgrade"])
def test_cli_dispatch_uses_installed_module(monkeypatch, flag):
    # main() imports update_check by module name; make sure that resolves to
    # the same module we monkeypatch here.
    import arxiv_digest

    monkeypatch.setattr(sys.modules["update_check"], "run_self_upgrade", lambda: 0)
    assert arxiv_digest.main([flag]) == 0
