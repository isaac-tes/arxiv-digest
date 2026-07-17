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
from dataclasses import asdict, dataclass, field, replace
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
        "eckardt",
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


def _default_feed_weights() -> Dict[str, int]:
    """Default per-feed score bonuses (formerly the hardcoded subject bonuses)."""
    return {
        "cond-mat.quant-gas": 4,
        "cond-mat.mes-hall": 4,
        "quant-ph": 2,
    }


def _hydrate_feed_weights(data: Dict[str, object]) -> Dict[str, int]:
    """Load feed_weights, migrating legacy hardcoded subject bonuses if absent."""
    raw = data.get("feed_weights")
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    # Pre-unification config: rebuild from the old weights.*_subject fields.
    w = data.get("weights")
    w = w if isinstance(w, dict) else {}
    fw = _default_feed_weights()
    for old_key, feed in (
        ("quant_gas_subject", "cond-mat.quant-gas"),
        ("mes_hall_subject", "cond-mat.mes-hall"),
        ("quant_ph_subject", "quant-ph"),
    ):
        if old_key in w:
            fw[feed] = int(w[old_key])
    return fw


@dataclass
class ScoringWeights:
    core_keyword: int = 6
    named_author: int = 6
    low_priority_penalty: int = -5
    long_abstract_bonus: int = 1
    long_abstract_threshold: int = 200

    @classmethod
    def from_json(cls, raw: Dict[str, object] | None) -> "ScoringWeights":
        if not raw:
            return cls()
        defaults = cls()
        return cls(
            core_keyword=int(raw.get("core_keyword", defaults.core_keyword)),
            named_author=int(raw.get("named_author", defaults.named_author)),
            low_priority_penalty=int(raw.get("low_priority_penalty", defaults.low_priority_penalty)),
            long_abstract_bonus=int(raw.get("long_abstract_bonus", defaults.long_abstract_bonus)),
            long_abstract_threshold=int(raw.get("long_abstract_threshold", defaults.long_abstract_threshold)),
        )


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
    include_replacements: bool = False  # keep arXiv 'Replacement submissions' (today feed)
    # Per-feed score bonus: feed name -> points, added when the feed name appears
    # in a paper's subjects. Single source of truth for subject scoring (the old
    # hardcoded quant-gas/mes-hall/quant-ph bonuses are just default entries).
    feed_weights: Dict[str, int] = field(default_factory=_default_feed_weights)
    # Match keywords/authors/low-priority as whole tokens rather than raw
    # substrings, so 'mpo' no longer scores 'temporal' and author 'bloch' no
    # longer scores 'Blochwitz' (arxiv_scraper_cli-28n). Subjects/feed_weights
    # stay substring so a parent feed 'cond-mat' still matches 'cond-mat.quant-gas'.
    # Set False for the legacy substring behavior.
    word_boundary_matching: bool = True
    # GUI display prefs: hover-highlight matched terms.
    highlight_authors: bool = True
    highlight_terms_title: bool = True
    highlight_terms_abstract: bool = True
    weights: ScoringWeights = field(default_factory=ScoringWeights)

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

        weights_raw = data.get("weights")
        weights = ScoringWeights.from_json(weights_raw if isinstance(weights_raw, dict) else None)

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
            top_n=int(data.get("top_n") or 20),
            timeframe=str(data.get("timeframe") or "pastweek"),
            include_replacements=bool(data.get("include_replacements", False)),
            word_boundary_matching=bool(data.get("word_boundary_matching", True)),
            feed_weights=_hydrate_feed_weights(data),
            highlight_authors=bool(data.get("highlight_authors", True)),
            highlight_terms_title=bool(data.get("highlight_terms_title", True)),
            highlight_terms_abstract=bool(data.get("highlight_terms_abstract", True)),
            weights=weights,
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


# ─────────────────────────── Starter presets ───────────────────────────
#
# Read-only, built-in research-topic bundles a new user can pick as a starting
# point instead of the generic cond-mat default. Grounded in the TU Berlin
# AG Eckardt (quantum nonequilibrium dynamics) research profile. Presets are
# NEVER written to disk on their own — Load/Add only mutate the in-memory
# Config; the user's arxiv_config.json and ~/.arxiv_scraper profiles are
# untouched unless they explicitly Save / --save-config.
#
# Each preset defines keywords + authors + feeds/feed_weights; scalar prefs
# (weights, top_n, timeframe, flags) stay at Config defaults. Authors always
# include eckardt + petiziol, plus famous *distinctive* surnames per field
# (short/common ones like 'wu'/'link'/'ma' are omitted — they over-match even
# with whole-word matching), capped at 10.


def _feeds_map(*categories: str) -> Dict[str, str]:
    """arXiv listing URL per category (the /new suffix is timeframe-rewritten)."""
    return {c: f"https://arxiv.org/list/{c}/new" for c in categories}


PRESETS: Dict[str, Dict[str, object]] = {
    "open-quantum-systems": {
        "description": "Lindbladian dynamics, dissipation, driven-dissipative & non-Markovian systems.",
        "core_keywords": [
            "lindblad", "lindbladian", "open quantum system", "master equation",
            "dissipative", "dissipation", "driven-dissipative", "non-markovian",
            "decoherence", "quantum trajectory", "steady state", "bath engineering",
            "quantum reservoir", "dephasing",
        ],
        "named_authors": [
            "eckardt", "petiziol", "schnell", "zoller", "cirac",
            "plenio", "breuer", "diehl",
        ],
        "feeds": _feeds_map("quant-ph", "cond-mat.stat-mech", "cond-mat.quant-gas"),
        "default_feeds": ["quant-ph", "cond-mat.stat-mech", "cond-mat.quant-gas"],
        "feed_weights": {"quant-ph": 3, "cond-mat.stat-mech": 3, "cond-mat.quant-gas": 2},
    },
    "quantum-many-body": {
        "description": "Thermalization, many-body localization, tensor networks & strongly correlated systems.",
        "core_keywords": [
            "many-body localization", "thermalization", "prethermal",
            "eigenstate thermalization", "entanglement entropy", "tensor network",
            "matrix product state", "dmrg", "quench dynamics", "hubbard model",
            "spin chain", "strongly correlated", "quantum quench", "ergodicity",
        ],
        "named_authors": [
            "eckardt", "petiziol", "eisert", "cirac", "abanin",
            "huse", "altman", "bloch",
        ],
        "feeds": _feeds_map(
            "cond-mat.str-el", "cond-mat.quant-gas", "cond-mat.stat-mech", "quant-ph"
        ),
        "default_feeds": ["cond-mat.str-el", "cond-mat.quant-gas", "cond-mat.stat-mech", "quant-ph"],
        "feed_weights": {
            "cond-mat.str-el": 4, "cond-mat.quant-gas": 3,
            "cond-mat.stat-mech": 2, "quant-ph": 2,
        },
    },
    "floquet-topological": {
        "description": "Floquet engineering, periodically driven systems & topological matter (group signature).",
        "core_keywords": [
            "floquet", "periodically driven", "topological insulator", "chern number",
            "fractional chern", "anomalous floquet", "berry curvature", "optical lattice",
            "ultracold atoms", "shortcuts to adiabaticity", "anyons", "lattice gauge",
            "bose-einstein condensate", "topological invariant",
        ],
        "named_authors": [
            "eckardt", "petiziol", "cooper", "goldman", "aidelsburger",
            "bloch", "refael", "lindner", "rudner",
        ],
        "feeds": _feeds_map("cond-mat.quant-gas", "cond-mat.mes-hall", "quant-ph"),
        "default_feeds": ["cond-mat.quant-gas", "cond-mat.mes-hall", "quant-ph"],
        "feed_weights": {"cond-mat.quant-gas": 4, "cond-mat.mes-hall": 4, "quant-ph": 2},
    },
}


def preset_names() -> List[str]:
    """Names of the built-in starter presets."""
    return list(PRESETS)


def preset_description(name: str) -> str:
    return str(PRESETS[name].get("description", ""))


def preset_config(name: str) -> Config:
    """Full Config for a preset: its content fields, Config defaults elsewhere.

    'Load' in the GUI (and `--preset` on the CLI) replaces the working config
    with this. Raises KeyError for an unknown name.
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Available: {', '.join(preset_names())}")
    spec = PRESETS[name]
    return Config(
        feeds=dict(spec["feeds"]),  # type: ignore[arg-type]
        default_feeds=list(spec["default_feeds"]),  # type: ignore[arg-type]
        core_keywords=list(spec["core_keywords"]),  # type: ignore[arg-type]
        named_authors=list(spec["named_authors"]),  # type: ignore[arg-type]
        feed_weights=dict(spec["feed_weights"]),  # type: ignore[arg-type]
    )


def _union_preserve(base: List[str], extra: List[str]) -> List[str]:
    """base + items of extra not already present (case-insensitive), order kept."""
    seen = {x.lower() for x in base}
    out = list(base)
    for item in extra:
        if item.lower() not in seen:
            out.append(item)
            seen.add(item.lower())
    return out


def merge_preset(cfg: Config, name: str) -> Config:
    """Return a copy of `cfg` with preset `name`'s content unioned in.

    'Add' in the GUI (and `--add-preset` on the CLI): keywords/authors/feeds/
    default_feeds/feed_weights are merged; scalar prefs (weights, top_n,
    timeframe, flags) are kept from `cfg`. `cfg` is not mutated.
    """
    spec = PRESETS[name] if name in PRESETS else None
    if spec is None:
        raise KeyError(f"Unknown preset '{name}'. Available: {', '.join(preset_names())}")
    merged_feeds = {**cfg.feeds, **spec["feeds"]}  # type: ignore[dict-item]
    merged_feed_weights = {**cfg.feed_weights, **spec["feed_weights"]}  # type: ignore[dict-item]
    return replace(
        cfg,
        core_keywords=_union_preserve(cfg.core_keywords, list(spec["core_keywords"])),  # type: ignore[arg-type]
        named_authors=_union_preserve(cfg.named_authors, list(spec["named_authors"])),  # type: ignore[arg-type]
        low_priority_kw=list(cfg.low_priority_kw),
        feeds=merged_feeds,
        default_feeds=_union_preserve(cfg.default_feeds, list(spec["default_feeds"])),  # type: ignore[arg-type]
        feed_weights=merged_feed_weights,
    )


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


# ── Submission-type / day filtering ──────────────────────────────────────────
#
# arXiv /new pages group entries under h3 headers: "New submissions (...)",
# "Cross submissions (...)", "Replacement submissions (...)". /pastweek groups
# by day: "Fri, 19 Jun 2026 (showing 88 of 88 entries )". fetch_feed stores that
# header in paper["section"], so we can filter without re-fetching.

_DAY_LABEL_RE = re.compile(r"^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4}")


def section_category(section: str) -> str:
    """Classify an arXiv list section header → new | cross | replacement | other.

    Date sections (pastweek) and anything unrecognised return 'other'.
    """
    s = (section or "").lower()
    if "replacement" in s:
        return "replacement"
    if "cross" in s:
        return "cross"
    if "new submission" in s:
        return "new"
    return "other"


def section_day_label(section: str) -> str | None:
    """Extract the date label from a pastweek day section, else None.

    'Fri, 19 Jun 2026 (showing 88 of 88 entries )' -> 'Fri, 19 Jun 2026'
    """
    m = _DAY_LABEL_RE.match(section or "")
    return m.group(0) if m else None


def available_day_labels(papers: List[dict]) -> List[str]:
    """Distinct day labels present in papers, sorted chronologically."""
    labels = {lbl for p in papers if (lbl := section_day_label(p.get("section", "")))}

    def _key(lbl: str):
        try:
            return datetime.strptime(lbl, "%a, %d %b %Y")
        except ValueError:
            return datetime.max

    return sorted(labels, key=_key)


def filter_papers(
    papers: List[dict],
    *,
    include_replacements: bool = False,
    days: Sequence[str] | None = None,
) -> List[dict]:
    """Drop replacement submissions (unless asked to keep) and restrict to days.

    `days` is a list of day labels (see section_day_label); None = all days.
    Cross submissions and new submissions are always kept.
    """
    out: List[dict] = []
    for p in papers:
        section = p.get("section", "")
        if not include_replacements and section_category(section) == "replacement":
            continue
        if days is not None and section_day_label(section) not in set(days):
            continue
        out.append(p)
    return out


def term_pattern(term: str, *, word_boundary: bool = True) -> "re.Pattern[str] | None":
    """Compile a case-insensitive matcher for a keyword/author/low-priority term.

    With `word_boundary` (default) the term must be a whole token: the
    lookarounds `(?<!\\w)`/`(?!\\w)` reject matches flanked by another word
    character, so 'mpo' matches 'MPO' / 'MPO-based' / 'the mpo,' but not
    'temporal' or 'fqhe'. Punctuation, spaces, and string edges all count as
    boundaries. `re.escape` keeps user terms literal (no regex injection).

    Without `word_boundary` it degrades to a plain substring search — the
    legacy behavior. Returns None for blank terms.
    """
    term = term.strip()
    if not term:
        return None
    body = re.escape(term)
    if word_boundary:
        body = r"(?<!\w)" + body + r"(?!\w)"
    return re.compile(body, re.IGNORECASE)


def term_matches(term: str, text: str, *, word_boundary: bool = True) -> bool:
    """True if `term` occurs in `text` (whole-token unless word_boundary=False)."""
    pat = term_pattern(term, word_boundary=word_boundary)
    return bool(pat and pat.search(text))


def explain_score(paper: dict, cfg: Config) -> dict:
    """Return a per-rule breakdown of how `score_paper` arrived at its total.

    Returned dict has shape:
        {
            "keywords": [(kw, weight), ...],     # matched core keywords
            "authors":  [(author, weight), ...], # matched named authors
            "subjects": {name: weight, ...},     # only included subjects that matched
            "low_priority_hits": [kw, ...],      # matched low-priority terms
            "low_priority_penalty": int,         # applied once if any hit, else 0
            "abstract_bonus": int,               # weights.long_abstract_bonus or 0
            "total": int,                        # sum of all contributions
        }
    """
    weights = cfg.weights
    txt = " ".join(
        [
            paper.get("title", ""),
            paper.get("abstract", ""),
            paper.get("authors", ""),
            paper.get("subjects", ""),
        ]
    ).lower()
    subjects = paper.get("subjects", "").lower()
    # Named authors must match the actual author list only — not the title or
    # abstract. Otherwise "Bloch theorem" in an abstract awards author points
    # though no author is named Bloch (arxiv_scraper_cli-8tz).
    authors_txt = paper.get("authors", "").lower()

    wb = cfg.word_boundary_matching
    matched_keywords = [kw for kw in cfg.core_keywords if term_matches(kw, txt, word_boundary=wb)]
    matched_authors = [a for a in cfg.named_authors if term_matches(a, authors_txt, word_boundary=wb)]
    matched_low = [k for k in cfg.low_priority_kw if term_matches(k, txt, word_boundary=wb)]

    # Subject scoring is fully driven by per-feed bonuses: each feed whose name
    # appears in the paper's subjects contributes its configured weight.
    subject_hits: Dict[str, int] = {}
    for name, w in (cfg.feed_weights or {}).items():
        if w and name.lower() in subjects:
            subject_hits[name] = w

    penalty = weights.low_priority_penalty if matched_low else 0
    abstract_bonus = (
        weights.long_abstract_bonus
        if len(paper.get("abstract", "")) > weights.long_abstract_threshold
        else 0
    )

    total = (
        len(matched_keywords) * weights.core_keyword
        + len(matched_authors) * weights.named_author
        + sum(subject_hits.values())
        + penalty
        + abstract_bonus
    )

    return {
        "keywords": [(kw, weights.core_keyword) for kw in matched_keywords],
        "authors": [(a, weights.named_author) for a in matched_authors],
        "subjects": subject_hits,
        "low_priority_hits": matched_low,
        "low_priority_penalty": penalty,
        "abstract_bonus": abstract_bonus,
        "total": total,
    }


def score_paper(paper: dict, cfg: Config) -> int:
    return explain_score(paper, cfg)["total"]


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
    parser.add_argument(
        "--preset",
        choices=list(PRESETS),
        help="Start from a built-in starter preset (replaces the config's content). See --list-presets.",
    )
    parser.add_argument(
        "--add-preset",
        action="append",
        default=[],
        choices=list(PRESETS),
        metavar="NAME",
        help="Union a starter preset's keywords/authors/feeds onto the current config (repeatable).",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List the built-in starter presets and exit.",
    )
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
    parser.add_argument(
        "--include-replacements",
        action="store_true",
        help="Keep arXiv 'Replacement submissions' (hidden by default; only present in the 'today' feed)",
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

    if args.list_presets:
        for name in preset_names():
            print(f"{name}\n    {preset_description(name)}")
        return 0

    cfg_path = args.config if not args.no_config else None
    # --preset picks a built-in starting point instead of the config file;
    # --add-preset unions presets onto whatever base we have. Neither writes to
    # disk unless the user also passes --save-config.
    cfg = preset_config(args.preset) if args.preset else Config.load(cfg_path)
    for name in args.add_preset:
        cfg = merge_preset(cfg, name)
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

    if args.include_replacements:
        cfg.include_replacements = True
    fetched_count = len(papers)
    papers = filter_papers(papers, include_replacements=cfg.include_replacements)
    hidden_replacements = fetched_count - len(papers)

    generated_at = datetime.now(UTC)
    top_limit = args.top if args.top is not None else cfg.top_n
    entries = build_ranked_entries(papers, cfg, top_n=top_limit)
    digest = format_digest(entries, len(papers), top_limit)
    print(digest)
    if hidden_replacements:
        print(
            f"\nNote: hid {hidden_replacements} replacement submission(s). "
            f"Pass --include-replacements to keep them."
        )

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
