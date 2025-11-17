"""One-stop cond-mat-quant-ph arXiv scraper + relevance filter.

This script combines fetching the latest cond-mat-quant-ph submissions and ranking them
according to researcher-defined heuristics. It can be run as-is, imported, or
pasted into ChatGPT / Code Interpreter. Configuration may be tweaked via CLI
flags without hand-editing the file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Sequence

import requests
from bs4 import BeautifulSoup

DEFAULT_FEED = "cond-mat"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("arxiv_config.json")


def _default_core_keywords() -> List[str]:
    return [
        "geometry",
        "geom",
        "quantum geometry",
        "quantum geom",
        "topological",
        "topolog",
        "anyon",
        "1d",
        "one-dimensional",
        "scar",
        "boson",
        "bosonic BdG",
        "Krylov",
        "Thouless",
        "pumping",
        "pumping",
        "gauge field",
        "gauge potential",
        "Peierls phases",
        "topological phase transition",
        "topological order",
        "Chern",
        "Hopf",
        "Hofstadter",
        "Harper",
        "Hatsugai",
        "chain",
        "lattice",
        "mps",
        "dmrg",
        "matrix product",
        "tensor",
        "tensor network",
        "purification",
        "tebd",
        "lindblad",
        "dissipative",
        "open quantum",
        "reservoir",
        "reservoir engineering",
        "quantum gas",
        "ladder",
        "bosonic",
        "mott",
        "doublon",
        "holon",
        "hubbard",
        "supersolid",
        "chiral",
        "spin chain",
        "kitaev",
        "ising",
        "heisenberg",
        "frustrat",
        "entanglement",
        "mpo",
    ]


def _default_named_authors() -> List[str]:
    return [
        "mera",
        "slager",
        "ozawa",
        "carusotto",
        "goldman",
        "eckardt",
        "pollmann",
        "verresen",
        "barbiero",
        "lewenstein",
        "törmä",
        "bukov",
        "tarruell",
        "celi",
        "aidelsburger",
        "cooper",
        "dalibard",
        "bloch",
        "cirac",
        "jaksch",
        "demler",
        "lukin",
        "moessner",
        "senthil",
        "fradkin",
        "pelster",
        # "giamarchi",
        # "chepiga",
    ]


def _default_low_priority_kw() -> List[str]:
    return [
        "film",
        "heterostructure",
        "photoemission",
        "device",
        "junction",
        "transport",
        "measurement",
        "spectroscopy",
        "microscopy",
        "epitaxial",
        "mbe",
        "growth",
        "fabrication",
        "stm",
        "arpes",
        "rixs",
    ]


@dataclass
class Config:
    feeds: Dict[str, str] = field(
        default_factory=lambda: {
            "cond-mat.quant-gas": "https://arxiv.org/list/cond-mat.quant-gas/recent",
            "cond-mat.mes-hall": "https://arxiv.org/list/cond-mat.mes-hall/recent",
            "quant-ph": "https://arxiv.org/archive/quant-ph/new",
            "cond-mat": "https://arxiv.org/list/cond-mat/new",
        }
    )
    default_feed: str = DEFAULT_FEED
    core_keywords: List[str] = field(default_factory=_default_core_keywords)
    named_authors: List[str] = field(default_factory=_default_named_authors)
    low_priority_kw: List[str] = field(default_factory=_default_low_priority_kw)
    top_n: int = 15

    @classmethod
    def from_json(cls, raw: Dict[str, object]) -> "Config":
        data = {**raw}
        feeds = data.get("feeds") or {}
        default_feed = data.get("default_feed") or DEFAULT_FEED
        cfg = cls(
            feeds={k: str(v) for k, v in feeds.items()},
            default_feed=str(default_feed),
            core_keywords=list(data.get("core_keywords") or _default_core_keywords()),
            named_authors=list(data.get("named_authors") or _default_named_authors()),
            low_priority_kw=list(data.get("low_priority_kw") or _default_low_priority_kw()),
            top_n=int(data.get("top_n") or 15),
        )
        if cfg.default_feed not in cfg.feeds:
            cfg.default_feed = next(iter(cfg.feeds), DEFAULT_FEED)
        return cfg

    @classmethod
    def load(cls, path: Path | None) -> "Config":
        if path and path.exists():
            with path.open("r", encoding="utf-8") as fh:
                return cls.from_json(json.load(fh))
        return cls()

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_rename_arg(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("Rename arguments must look like OLD:NEW")
    old, new = value.split(":", 1)
    return old.strip(), new.strip()


def _parse_add_url(arg: str) -> tuple[str, str]:
    if "=" not in arg:
        raise ValueError("Add-url arguments must look like NAME=https://...")
    name, url = arg.split("=", 1)
    return name.strip(), url.strip()


def _find_index_casefold(seq: Sequence[str], needle: str) -> int | None:
    target = needle.casefold()
    for idx, item in enumerate(seq):
        if item.casefold() == target:
            return idx
    return None


def modify_list(seq: List[str], additions: List[str], removals: List[str], renames: List[str]) -> None:
    for value in additions:
        candidate = value.strip()
        if candidate and _find_index_casefold(seq, candidate) is None:
            seq.append(candidate)
    for value in removals:
        idx = _find_index_casefold(seq, value)
        if idx is not None:
            seq.pop(idx)
    for item in renames:
        old, new = _parse_rename_arg(item)
        idx = _find_index_casefold(seq, old)
        if idx is not None:
            seq[idx] = new


def apply_cli_modifications(cfg: Config, args: argparse.Namespace) -> None:
    modify_list(cfg.core_keywords, args.add_core, args.remove_core, args.rename_core)
    modify_list(cfg.named_authors, args.add_author, args.remove_author, args.rename_author)
    modify_list(
        cfg.low_priority_kw,
        args.add_low_priority,
        args.remove_low_priority,
        args.rename_low_priority,
    )

    for payload in args.add_url:
        name, url = _parse_add_url(payload)
        cfg.feeds[name] = url
        if args.verbose:
            print(f"Added feed '{name}' -> {url}")
    for payload in args.rename_url:
        old, new = _parse_rename_arg(payload)
        if old in cfg.feeds:
            cfg.feeds[new] = cfg.feeds.pop(old)
            if cfg.default_feed == old:
                cfg.default_feed = new
    for name in args.delete_url:
        if name in cfg.feeds:
            cfg.feeds.pop(name)
            if cfg.default_feed == name:
                cfg.default_feed = next(iter(cfg.feeds), DEFAULT_FEED)
    if args.set_default_feed:
        if args.set_default_feed not in cfg.feeds:
            raise SystemExit(f"Unknown feed '{args.set_default_feed}'. Add it first with --add-url")
        cfg.default_feed = args.set_default_feed

    if args.top is not None:
        cfg.top_n = args.top


def fetch_feed(url: str, sections: List[str] | None = None) -> List[dict]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tracked = sections or ["New submissions", "Cross", "Replacements"]
    allowed = []
    for h3 in soup.find_all("h3"):
        title = h3.get_text(strip=True)
        if any(key in title for key in tracked):
            allowed.append((title, h3))

    papers: List[dict] = []
    for sec_name, h3 in allowed:
        stop = h3.find_next("h3")
        node = h3.next_sibling
        section_nodes = []
        while node and node is not stop:
            if getattr(node, "name", None) in {"dt", "dd"}:
                section_nodes.append(node)
            node = node.next_sibling
        dts = [node for node in section_nodes if node.name == "dt"]
        dds = [node for node in section_nodes if node.name == "dd"]
        for dt, dd in zip(dts, dds):
            a_abs = dt.find("a", title="Abstract")
            if not a_abs:
                continue
            link = f"https://arxiv.org{a_abs['href']}"
            arx_id = a_abs.get_text(strip=True)
            title_div = dd.find("div", class_="list-title")
            title = (
                title_div.get_text(" ", strip=True).replace("Title:", "").strip()
                if title_div
                else ""
            )
            authors_div = dd.find("div", class_="list-authors")
            authors = (
                authors_div.get_text(" ", strip=True).replace("Authors:", "").strip()
                if authors_div
                else ""
            )
            subj_div = dd.find("div", class_="list-subjects")
            subjects = (
                subj_div.get_text(" ", strip=True).replace("Subjects:", "").strip()
                if subj_div
                else ""
            )
            abstract_p = dd.find("p", class_="mathjax")
            abstract = (
                abstract_p.get_text(" ", strip=True).replace("Abstract:", "").strip()
                if abstract_p
                else ""
            )
            papers.append(
                {
                    "id": arx_id,
                    "title": title,
                    "authors": authors,
                    "link": link,
                    "subjects": subjects,
                    "abstract": abstract,
                    "section": sec_name,
                }
            )
    return papers


def fetch_feeds(urls: List[str], sections: List[str] | None = None) -> List[dict]:
    """Fetch multiple feeds and concatenate results, deduplicating by arXiv id."""
    all_papers: List[dict] = []
    seen_ids = set()
    for u in urls:
        try:
            papers = fetch_feed(u, sections=sections)
        except Exception:
            # propagate outer exception later — but continue gathering what's available
            raise
        for p in papers:
            pid = p.get("id")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_papers.append(p)
    return all_papers


def score_paper(paper: dict, cfg: Config) -> int:
    txt = " ".join(
        [
            paper.get("title", ""),
            paper.get("abstract", ""),
            paper.get("authors", ""),
            paper.get("subjects", ""),
        ]
    ).lower()
    score = 0
    for kw in cfg.core_keywords:
        if kw.lower() in txt:
            score += 6
    for author in cfg.named_authors:
        if author.lower() in txt:
            score += 6
    subjects = paper.get("subjects", "").lower()
    if "cond-mat.quant-gas" in subjects:
        score += 4
    if "cond-mat.mes-hall" in subjects:
        score += 4
    if "quant-ph" in subjects:
        score += 2
    if any(token.lower() in txt for token in cfg.low_priority_kw):
        score -= 5
    if len(paper.get("abstract", "")) > 200:
        score += 1
    return score


def summarize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return "(No abstract available.)"
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(sentences[:2])


def build_ranked_entries(papers: List[dict], cfg: Config, top_n: int | None = None) -> List[dict]:
    limit = max(top_n or cfg.top_n, 1)
    scored = []
    for paper in papers:
        scored.append(
            {
                **paper,
                "score": score_paper(paper, cfg),
            }
        )
    scored.sort(key=lambda item: (-item["score"], item.get("title", "")))
    entries: List[dict] = []
    for idx, paper in enumerate(scored[:limit], start=1):
        title = (paper.get("title", "") or "").strip() or "(Untitled)"
        authors = (paper.get("authors", "") or "").strip() or "(No authors listed)"
        entry = {
            "rank": idx,
            "id": paper.get("id", ""),
            "title": title,
            "authors": authors,
            "link": (paper.get("link", "") or "").strip(),
            "subjects": (paper.get("subjects", "") or "").strip(),
            "section": (paper.get("section", "") or "").strip(),
            "summary": summarize(paper.get("abstract", "")),
            "score": paper["score"],
        }
        entries.append(entry)
    return entries


def format_digest(entries: List[dict], total_papers: int, requested_top: int) -> str:
    lines = [
        "Daily arXiv cond-mat digest — (real papers)",
        f"Total papers fetched: {total_papers}. Showing top {min(requested_top, total_papers)} by relevance.",
        "",
    ]
    for entry in entries:
        lines.append(f"{entry['rank']}. {entry['title']}")
        lines.append(f"   {entry['authors']}")
        if entry.get("section"):
            lines.append(f"   Section: {entry['section']}")
        if entry.get("link"):
            lines.append(f"   {entry['link']}")
        lines.append(f"   {entry['summary']}")
        lines.append("")
    return "\n".join(lines).strip()


def determine_feed(cfg: Config, args: argparse.Namespace) -> str:
    # This function is kept for backward compatibility but main now supports
    # multiple feeds via --feed (action=append). If args.feed is provided it
    # may be a list of names/URLs; return a list of URLs.
    if args.feed:
        urls: List[str] = []
        for key in args.feed:
            if key in cfg.feeds:
                urls.append(cfg.feeds[key])
                continue
            if key.startswith("http"):
                urls.append(key)
                continue
            raise SystemExit(f"Unknown feed '{key}'. Add it first with --add-url")
        return urls

    default_url = cfg.feeds.get(cfg.default_feed)
    if not default_url:
        raise SystemExit("No feeds configured. Use --add-url NAME=https://... to add one.")
    return [default_url]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch + rank cond-mat arXiv papers")
    parser.add_argument(
        "--feed",
        action="append",
        help=(
            "Feed name from config or explicit URL. May be provided multiple times to "
            "fetch from several named feeds (e.g. --feed cond-mat --feed quant-ph)"
        ),
        default=None,
    )
    parser.add_argument("--top", type=int, help="Override number of entries to print")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Optional config JSON path")
    parser.add_argument("--no-config", action="store_true", help="Ignore config file even if present")
    parser.add_argument("--save-config", action="store_true", help="Persist modified config back to --config path")
    parser.add_argument("--list-config", action="store_true", help="Print current config and exit")
    parser.add_argument("--sections", nargs="*", help="Limit scraping to specific section titles")
    parser.add_argument("--output-json", type=Path, help="Also write digest entries to JSON")
    parser.add_argument("--verbose", action="store_true")

    parser.add_argument("--add-core", action="append", default=[], help="Add a core keyword")
    parser.add_argument("--remove-core", action="append", default=[], help="Remove a core keyword")
    parser.add_argument("--rename-core", action="append", default=[], metavar="OLD:NEW", help="Rename a core keyword")

    parser.add_argument("--add-author", action="append", default=[], help="Add a highlighted author")
    parser.add_argument("--remove-author", action="append", default=[], help="Remove a highlighted author")
    parser.add_argument(
        "--rename-author",
        action="append",
        default=[],
        metavar="OLD:NEW",
        help="Rename a highlighted author",
    )

    parser.add_argument(
        "--add-low-priority",
        action="append",
        default=[],
        help="Add a low-priority keyword (subtracts score)",
    )
    parser.add_argument("--remove-low-priority", action="append", default=[], help="Remove a low-priority keyword")
    parser.add_argument(
        "--rename-low-priority",
        action="append",
        default=[],
        metavar="OLD:NEW",
        help="Rename a low-priority keyword",
    )

    parser.add_argument("--add-url", action="append", default=[], metavar="NAME=URL", help="Add a named feed")
    parser.add_argument("--rename-url", action="append", default=[], metavar="OLD:NEW", help="Rename a feed")
    parser.add_argument("--delete-url", action="append", default=[], metavar="NAME", help="Delete a feed")
    parser.add_argument(
        "--set-default-feed",
        help="Set the default feed name to use when --feed is omitted",
    )

    # enable shell completion if argcomplete is installed
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except Exception:
        # argcomplete is optional; ignore failures
        pass

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    cfg_path = args.config if not args.no_config else None
    cfg = Config.load(cfg_path)
    apply_cli_modifications(cfg, args)

    if args.list_config:
        print(json.dumps(asdict(cfg), indent=2, ensure_ascii=False))
        if not args.save_config:
            return 0

    if args.save_config and cfg_path:
        cfg.dump(cfg_path)

    feed_urls = determine_feed(cfg, args)
    try:
        papers = fetch_feeds(feed_urls, sections=args.sections)
    except requests.RequestException as exc:
        # show a helpful combined message
        raise SystemExit(f"Failed to fetch feeds {feed_urls}: {exc}") from exc

    top_limit = args.top if args.top is not None else cfg.top_n
    entries = build_ranked_entries(papers, cfg, top_n=top_limit)
    digest = format_digest(entries, len(papers), top_limit)
    print(digest)

    if args.output_json:
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "feed_urls": feed_urls,
            "sections": args.sections or [],
            "top_n": top_limit,
            "total_papers": len(papers),
            "entries": entries,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if args.verbose:
            print(f"Saved digest JSON to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
