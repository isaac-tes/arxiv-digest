from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest

import arxiv_digest
from arxiv_digest import (
    AUTO_OUTPUT_SENTINEL,
    Config,
    apply_cli_modifications,
    determine_feed,
    parse_args,
    resolve_report_path,
)


def _ns(**overrides) -> argparse.Namespace:
    """Build an argparse Namespace pre-populated with all CLI fields the code touches."""
    base = dict(
        feed=None,
        top=None,
        config=Path("ignored"),
        no_config=True,
        save_config=False,
        list_config=False,
        sections=None,
        output_json=None,
        output_markdown=None,
        verbose=False,
        timeframe=None,
        add_core=[],
        remove_core=[],
        rename_core=[],
        add_author=[],
        remove_author=[],
        rename_author=[],
        add_low_priority=[],
        remove_low_priority=[],
        rename_low_priority=[],
        add_url=[],
        rename_url=[],
        delete_url=[],
        set_default_feed=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_resolve_report_path_auto_sentinel():
    out = resolve_report_path(AUTO_OUTPUT_SENTINEL, "json", datetime(2026, 5, 6, tzinfo=UTC))
    assert out == Path("reports") / "digest-2026-05-06.json"


def test_resolve_report_path_none_returns_none():
    assert resolve_report_path(None, "json", datetime.now(UTC)) is None


def test_resolve_report_path_explicit_path_passes_through(tmp_path):
    target = tmp_path / "explicit.md"
    out = resolve_report_path(target, "md", datetime.now(UTC))
    assert out == target


def test_determine_feed_pastweek_rewrites_urls():
    cfg = Config()
    args = _ns(timeframe="pastweek")
    urls = determine_feed(cfg, args)
    assert urls
    assert all(u.endswith("/pastweek") for u in urls)


def test_determine_feed_today_rewrites_urls():
    cfg = Config()
    args = _ns(timeframe="today")
    urls = determine_feed(cfg, args)
    assert urls
    assert all(u.endswith("/new") for u in urls)


def test_determine_feed_uses_config_default_when_no_arg_timeframe():
    cfg = Config()
    cfg.timeframe = "today"
    args = _ns()
    urls = determine_feed(cfg, args)
    assert all(u.endswith("/new") for u in urls)


def test_determine_feed_with_named_feed():
    cfg = Config()
    args = _ns(feed=["cond-mat"], timeframe="today")
    urls = determine_feed(cfg, args)
    assert urls == ["https://arxiv.org/list/cond-mat/new"]


def test_determine_feed_with_explicit_url():
    cfg = Config()
    args = _ns(feed=["https://arxiv.org/list/hep-th/new"], timeframe="today")
    urls = determine_feed(cfg, args)
    assert urls == ["https://arxiv.org/list/hep-th/new"]


def test_determine_feed_unknown_name_raises():
    cfg = Config()
    args = _ns(feed=["nope"])
    with pytest.raises(SystemExit):
        determine_feed(cfg, args)


def test_apply_cli_add_core_keyword():
    cfg = Config()
    args = _ns(add_core=["new_keyword"])
    apply_cli_modifications(cfg, args)
    assert "new_keyword" in cfg.core_keywords


def test_apply_cli_remove_author():
    cfg = Config()
    args = _ns(remove_author=["bloch"])
    apply_cli_modifications(cfg, args)
    assert "bloch" not in [a.lower() for a in cfg.named_authors]


def test_apply_cli_add_url_then_set_default():
    cfg = Config()
    args = _ns(
        add_url=["hep-th=https://arxiv.org/list/hep-th/new"],
        set_default_feed=["hep-th"],
    )
    apply_cli_modifications(cfg, args)
    assert "hep-th" in cfg.feeds
    assert cfg.default_feeds == ["hep-th"]


def test_apply_cli_set_default_feed_unknown_raises():
    cfg = Config()
    args = _ns(set_default_feed=["does-not-exist"])
    with pytest.raises(SystemExit):
        apply_cli_modifications(cfg, args)


def test_apply_cli_top_override():
    cfg = Config()
    args = _ns(top=42)
    apply_cli_modifications(cfg, args)
    assert cfg.top_n == 42


def test_parse_args_smoke():
    ns = parse_args(["--top", "10", "--timeframe", "today"])
    assert ns.top == 10
    assert ns.timeframe == "today"


def test_parse_args_repeated_feed_collects():
    ns = parse_args(["--feed", "cond-mat", "--feed", "quant-ph"])
    assert ns.feed == ["cond-mat", "quant-ph"]


def test_main_list_config_exits_zero(monkeypatch, capsys):
    """--list-config + --no-config should print JSON and return 0 without touching network."""
    rc = arxiv_digest.main(["--list-config", "--no-config"])
    captured = capsys.readouterr()
    assert rc == 0
    assert '"weights"' in captured.out
    assert '"core_keyword"' in captured.out
