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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Sequence

import requests
from bs4 import BeautifulSoup

DEFAULT_FEEDS = [
    "cond-mat.quant-gas",
    "cond-mat.mes-hall",
    "quant-ph",
    "cond-mat",
]
# legacy helper for configs that still reference a single feed string
DEFAULT_FEED = DEFAULT_FEEDS[-1]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("arxiv_config.json")
AUTO_OUTPUT_SENTINEL = Path("__AUTO__")
DEFAULT_REPORTS_DIR = Path("reports")


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
        "Berry curvature",
        "Berry phase",
        "flat band",
        "Chern band",
        "fractional",
        "fractional quantum hall",
        "quantum hall",
        "quantum hall effect",
        "fqhe",
        "fqh",
        "haldane",
        "landau level",
        "ll",
        "scars",
        "many-body localization",
        "mbl",
        "localization",
        "syk",
        "chaos",
        "Sachdev-Ye-Kitaev",
        "fracton",
        "synthetic dimension",
        "synthetic dim",
        "synthetic gauge",
        "synthetic field",
        "synthetic potential",
        "floquet",
        "floquet engineering",
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
        "palumbo",
        "Bzdušek",
        "ozawa",
        "carusotto",
        "goldman",
        
        "pollmann",
        "verresen",
        "barbiero",
        "lewenstein",
        "törmä",
        "bukov",
        "tarruell",
        "celi",
        "haegeman",
        "verstraete",
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
        "stammer",
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
            "cond-mat.quant-gas": "https://arxiv.org/list/cond-mat.quant-gas/new",
            "cond-mat.mes-hall": "https://arxiv.org/list/cond-mat.mes-hall/new",
            "quant-ph": "https://arxiv.org/list/quant-ph/new",
            "cond-mat": "https://arxiv.org/list/cond-mat/new",
        }
    )
    default_feeds: List[str] = field(default_factory=lambda: list(DEFAULT_FEEDS))
    core_keywords: List[str] = field(default_factory=_default_core_keywords)
    named_authors: List[str] = field(default_factory=_default_named_authors)
    low_priority_kw: List[str] = field(default_factory=_default_low_priority_kw)
    top_n: int = 20
    timeframe: str = "pastweek"  # 'today' or 'pastweek'

    @classmethod
    def from_json(cls, raw: Dict[str, object]) -> "Config":
        data = {**raw}
        feeds = data.get("feeds") or {}
        hydrated_feeds = {k: str(v) for k, v in feeds.items()}

        loaded_default_feeds = data.get("default_feeds")
        if isinstance(loaded_default_feeds, list):
            default_feeds = [str(name) for name in loaded_default_feeds if str(name) in hydrated_feeds]
        else:
            legacy_default = data.get("default_feed")
            if legacy_default and str(legacy_default) in hydrated_feeds:
                default_feeds = [str(legacy_default)]
            else:
                # fallback to all known feeds if nothing was configured
                default_feeds = list(hydrated_feeds) or list(DEFAULT_FEEDS)

        cfg = cls(
            feeds=hydrated_feeds or {
                "cond-mat.quant-gas": "https://arxiv.org/list/cond-mat.quant-gas/new",
                "cond-mat.mes-hall": "https://arxiv.org/list/cond-mat.mes-hall/new",
                "quant-ph": "https://arxiv.org/list/quant-ph/new",
                "cond-mat": "https://arxiv.org/list/cond-mat/new",
            },
            default_feeds=default_feeds or list(DEFAULT_FEEDS),
            core_keywords=list(data.get("core_keywords") or _default_core_keywords()),
            named_authors=list(data.get("named_authors") or _default_named_authors()),
            low_priority_kw=list(data.get("low_priority_kw") or _default_low_priority_kw()),
            top_n=int(data.get("top_n") or 15),
            timeframe=str(data.get("timeframe") or "today"),
        )
        return cfg

    @classmethod
    def load(cls, path: Path | None) -> "Config":
        if path and path.exists():
            with path.open("r", encoding="utf-8") as fh:
                return cls.from_json(json.load(fh))
        return cls()

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_report_path(candidate: Path | None, suffix: str, generated_at: datetime) -> Path | None:
    """Convert argparse output flag values into concrete report paths."""
    if candidate is None:
        return None
    if candidate == AUTO_OUTPUT_SENTINEL:
        date_slug = generated_at.strftime("%Y-%m-%d")
        return DEFAULT_REPORTS_DIR / f"digest-{date_slug}.{suffix}"
    return candidate


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
            cfg.default_feeds = [new if name == old else name for name in cfg.default_feeds]
    for name in args.delete_url:
        if name in cfg.feeds:
            cfg.feeds.pop(name)
            cfg.default_feeds = [feed for feed in cfg.default_feeds if feed != name]
    if args.set_default_feed:
        targets = args.set_default_feed
        if isinstance(targets, str):
            targets = [targets]
        new_defaults: List[str] = []
        for feed_name in targets:
            if feed_name not in cfg.feeds:
                raise SystemExit(f"Unknown feed '{feed_name}'. Add it first with --add-url")
            new_defaults.append(feed_name)
        cfg.default_feeds = new_defaults

    if args.top is not None:
        cfg.top_n = args.top


def fetch_abstract(arxiv_id: str, verbose: bool = False) -> str:
    """Fetch abstract from individual paper page."""
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        resp = requests.get(abs_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        abstract_block = soup.find("blockquote", class_="abstract")
        if abstract_block:
            return abstract_block.get_text(" ", strip=True).replace("Abstract:", "").strip()
    except Exception as e:
        if verbose:
            print(f"  Warning: Failed to fetch abstract for {arxiv_id}: {e}")
    return ""


def fetch_feed(url: str, sections: List[str] | None = None, verbose: bool = False) -> List[dict]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # The new structure uses date-based h3 headers (e.g., "Thu, 4 Dec 2025")
    # We'll collect all papers after any h3 tag until the next h3 or end
    papers: List[dict] = []
    
    # Find all h3 tags (which mark date sections)
    h3_tags = soup.find_all("h3")
    
    for h3 in h3_tags:
        section_name = h3.get_text(strip=True)
        
        # Find the next h3 to know where this section ends
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
            
            # Try multiple ways to find the abstract
            abstract = ""
            # First try: look for p with class mathjax
            abstract_p = dd.find("p", class_="mathjax")
            if abstract_p:
                abstract = abstract_p.get_text(" ", strip=True)
            else:
                # Second try: look for any p tag after the subjects
                all_p = dd.find_all("p")
                for p in all_p:
                    text = p.get_text(" ", strip=True)
                    # Skip empty paragraphs and very short ones
                    if text and len(text) > 20:
                        abstract = text
                        break
            
            abstract = abstract.replace("Abstract:", "").strip()
            
            papers.append(
                {
                    "id": arx_id,
                    "title": title,
                    "authors": authors,
                    "link": link,
                    "subjects": subjects,
                    "abstract": abstract,
                    "section": section_name,
                }
            )
    
    # Batch fetch missing abstracts in parallel for speed
    papers_missing_abstract = [p for p in papers if not p["abstract"]]
    if papers_missing_abstract:
        if verbose:
            print(f"  Fetching {len(papers_missing_abstract)} abstracts in parallel...")
        
        # Use ThreadPoolExecutor to fetch abstracts concurrently
        # Limit to 10 concurrent requests to be respectful to arXiv servers
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_paper = {executor.submit(fetch_abstract, p["id"], verbose): p for p in papers_missing_abstract}
            
            for future in as_completed(future_to_paper):
                paper = future_to_paper[future]
                try:
                    abstract = future.result()
                    paper["abstract"] = abstract
                except Exception as e:
                    if verbose:
                        print(f"  Warning: Failed to fetch abstract for {paper['id']}: {e}")
    
    if verbose:
        print(f"  Found {len(papers)} papers")
    
    return papers


def fetch_feeds(urls: List[str], sections: List[str] | None = None, verbose: bool = False) -> List[dict]:
    """Fetch multiple feeds and concatenate results, deduplicating by arXiv id."""
    all_papers: List[dict] = []
    seen_ids = set()
    for u in urls:
        if verbose:
            print(f"Fetching {u}...")
        try:
            papers = fetch_feed(u, sections=sections, verbose=verbose)
        except Exception:
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


def format_markdown(entries: List[dict], total_papers: int, requested_top: int) -> str:
    lines = [
        "# Daily arXiv cond-mat/quant-ph digest",
        "",
        f"Total papers fetched: {total_papers}. Showing top {min(requested_top, total_papers)} by relevance.",
        "",
    ]
    for entry in entries:
        lines.append(f"## {entry['rank']}. {entry['title']}")
        lines.append(f"- **Authors:** {entry['authors']}")
        if entry.get("section"):
            lines.append(f"- **Section:** {entry['section']}")
        if entry.get("subjects"):
            lines.append(f"- **Subjects:** {entry['subjects']}")
        if entry.get("link"):
            lines.append(f"- **Link:** {entry['link']}")
        lines.append("")
        lines.append(entry.get("summary", ""))
        lines.append("")
    return "\n".join(lines).strip()


def determine_feed(cfg: Config, args: argparse.Namespace) -> List[str]:
    # This function is kept for backward compatibility but main now supports
    # multiple feeds via --feed (action=append). If args.feed is provided it
    # may be a list of names/URLs; return a list of URLs.
    
    # Determine timeframe to use
    timeframe = args.timeframe if args.timeframe else cfg.timeframe
    timeframe_suffix = "new" if timeframe == "today" else "pastweek"
    
    if args.feed:
        urls: List[str] = []
        for key in args.feed:
            if key in cfg.feeds:
                # Replace the timeframe suffix in the URL
                base_url = cfg.feeds[key]
                url = base_url.replace("/new", f"/{timeframe_suffix}").replace("/recent", f"/{timeframe_suffix}").replace("/pastweek", f"/{timeframe_suffix}")
                urls.append(url)
                continue
            if key.startswith("http"):
                urls.append(key)
                continue
            raise SystemExit(f"Unknown feed '{key}'. Add it first with --add-url")
        return urls

    urls: List[str] = []
    for feed_name in cfg.default_feeds:
        if feed_name in cfg.feeds:
            # Replace the timeframe suffix in the URL
            base_url = cfg.feeds[feed_name]
            url = base_url.replace("/new", f"/{timeframe_suffix}").replace("/recent", f"/{timeframe_suffix}").replace("/pastweek", f"/{timeframe_suffix}")
            urls.append(url)
    if urls:
        return urls

    raise SystemExit("No feeds configured. Use --add-url NAME=https://... to add one.")


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
    parser.add_argument(
        "--output-json",
        nargs="?",
        const=AUTO_OUTPUT_SENTINEL,
        type=Path,
        help="Write digest entries to JSON (defaults to reports/digest-YYYY-MM-DD.json)",
    )
    parser.add_argument(
        "--output-markdown",
        nargs="?",
        const=AUTO_OUTPUT_SENTINEL,
        type=Path,
        help="Write digest entries to Markdown (defaults to reports/digest-YYYY-MM-DD.md)",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--timeframe",
        choices=["today", "pastweek"],
        help="Select timeframe: 'today' for /new feeds (today's papers only), 'pastweek' for /pastweek feeds (last ~5 days)",
    )

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
        action="append",
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
        papers = fetch_feeds(feed_urls, sections=args.sections, verbose=args.verbose)
    except requests.RequestException as exc:
        raise SystemExit(f"Failed to fetch feeds {feed_urls}: {exc}") from exc
    
    if args.verbose:
        print(f"\nTotal papers collected: {len(papers)}")

    generated_at = datetime.now(UTC)
    top_limit = args.top if args.top is not None else cfg.top_n
    entries = build_ranked_entries(papers, cfg, top_n=top_limit)
    digest = format_digest(entries, len(papers), top_limit)
    print(digest)

    json_path = resolve_report_path(args.output_json, "json", generated_at)
    markdown_path = resolve_report_path(args.output_markdown, "md", generated_at)

    if json_path:
        payload = {
            "generated_at": generated_at.isoformat(),
            "feed_urls": feed_urls,
            "sections": args.sections or [],
            "top_n": top_limit,
            "total_papers": len(papers),
            "entries": entries,
        }
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if args.verbose:
            print(f"Saved digest JSON to {json_path}")

    if markdown_path:
        markdown = format_markdown(entries, len(papers), top_limit)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
        if args.verbose:
            print(f"Saved digest Markdown to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
