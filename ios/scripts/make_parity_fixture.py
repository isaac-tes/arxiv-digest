"""Generate the Swift scorer's parity fixture from the real scoring engine.

Each case is a paper, a config and the breakdown `arxiv_digest.explain_score`
returns for them. The Swift `Scorer` must reproduce every breakdown exactly, so
a scoring change in Python fails the Swift tests until the port follows
(ADR 0009). Papers and author names are invented.

    uv run python ios/scripts/make_parity_fixture.py

writes ios/Tests/ArxivDigestCoreTests/ScoringParityFixture.swift and
FetchParityFixture.swift (an invented export-API Atom page and the paper
dicts `_paper_from_api_entry` builds from it).
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import arxiv_digest as ad  # noqa: E402

INVENTED_AUTHORS = ["Mira Castellanos", "okafor", "Jonas Albrecht", "Søren Ødegård", "li"]

BASE = ad.Config(named_authors=INVENTED_AUTHORS)

CONFIGS = {
    # Engine defaults, apart from the (real) default author names.
    "defaults": BASE,
    "substring": replace(BASE, word_boundary_matching=False),
    "custom-weights": replace(
        BASE,
        weights=ad.ScoringWeights(
            core_keyword=3, named_author=10, low_priority_penalty=-2,
            long_abstract_bonus=4, long_abstract_threshold=80,
        ),
    ),
    # Parent feed 'cond-mat' matches every cond-mat.* subject; a zero bonus never hits.
    "parent-feed": replace(
        BASE, feed_weights={"cond-mat": 3, "quant-ph": 0, "physics.optics": -1, "CS.LG": 2},
    ),
    "empty-lists": replace(BASE, core_keywords=[], named_authors=[], low_priority_kw=[], feed_weights={}),
    "tricky-terms": replace(
        BASE,
        core_keywords=["mpo", "Floquet", "  anyons ", "", "c++", "bose-hubbard", "chern number", "ünal"],
        named_authors=["Ada Lovelace", "ma", "Castellanos", "Ødegård", " "],
        low_priority_kw=["review", "machine learning", "dé"],
    ),
}

PAPERS = [
    {
        "id": "2609.30001",
        "title": "Anomalous Floquet Anyons in Driven Optical Lattices",
        "authors": "Mira L. Castellanos, Tomas Reinholt, Aiko Senda",
        "subjects": "Quantum Gases (cond-mat.quant-gas); Quantum Physics (quant-ph)",
        "abstract": (
            "We show that periodic driving of an interacting optical lattice stabilises anyons "
            "with a statistical phase set by the Floquet frequency. Tensor network simulations "
            "of a Bose-Hubbard ladder confirm a non-zero Chern number in transport measurements."
        ),
    },
    {
        "id": "2609.30002",
        "title": "Temporal MPO compression for c++ solvers: a review",
        "authors": "Ruth Okafor, Y. Mao, Jonas K. Albrecht",
        "subjects": "Strongly Correlated Electrons (cond-mat.str-el); Machine Learning (cs.LG)",
        "abstract": "We review MPO-based methods. Machine learning helps.",
    },
    {
        "id": "2609.30003",
        "title": "Photonic waveguides",
        "authors": "Søren Ødegård, Wei Li, Ada Example",
        "subjects": "Optics (physics.optics)",
        "abstract": "Short.",
    },
    {
        "id": "2609.30004",
        "title": "Bob Ada and Charlie Lovelace on transport",
        "authors": "Bob Ada, Charlie Lovelace, Elif Ünal",
        "subjects": "Mesoscale and Nanoscale Physics (cond-mat.mes-hall)",
        "abstract": "Dé-coherence in a film device. " * 12,
    },
    {
        "id": "2609.30005",
        "title": "",
        "authors": "",
        "subjects": "",
        "abstract": "",
    },
]


def build() -> list[dict]:
    cases = []
    for cfg_name, cfg in CONFIGS.items():
        for paper in PAPERS:
            b = ad.explain_score(paper, cfg)
            cases.append({
                "name": f"{cfg_name}/{paper['id']}",
                "config": asdict(cfg),
                "paper": paper,
                "expected": {**b, "keywords": [list(t) for t in b["keywords"]],
                             "authors": [list(t) for t in b["authors"]]},
            })
    return cases


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <id>https://arxiv.org/api/invented</id>
  <title>arXiv Query: invented</title>
  <updated>2026-10-07T00:00:00Z</updated>
  <opensearch:totalResults>1203</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>500</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2610.01234v2</id>
    <updated>2026-10-06T17:59:59Z</updated>
    <published>2026-10-05T23:30:00Z</published>
    <title>Anomalous Floquet Anyons
  in Driven Optical Lattices</title>
    <summary>  We show that periodic driving stabilises anyons.
Exact diagonalisation confirms it &amp; more.
</summary>
    <author>
      <name>Mira L. Castellanos</name>
      <arxiv:affiliation>Invented Institute</arxiv:affiliation>
    </author>
    <author>
      <name> Søren Ødegård </name>
    </author>
    <arxiv:comment>12 pages</arxiv:comment>
    <link href="http://arxiv.org/abs/2610.01234v2" rel="alternate" type="text/html"/>
    <arxiv:primary_category term="cond-mat.quant-gas"/>
    <category term="cond-mat.quant-gas" scheme="http://arxiv.org/schemas/atom"/>
    <category term="quant-ph" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/cond-mat/0601001v1</id>
    <published>2026-10-01T09:00:00Z</published>
    <title>Old-style identifier</title>
    <summary>Short.</summary>
    <author><name>Ruth Okafor</name></author>
    <category term="cond-mat.str-el" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2610.05555v11</id>
    <published>2026-10-07T00:00:01Z</published>
    <title>No abstract</title>
    <summary></summary>
    <category term="quant-ph" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


def build_fetch() -> dict:
    root = ET.fromstring(ATOM.encode())
    total = int(root.find(f"{ad._API_OPENSEARCH}totalResults").text)
    papers = [ad._paper_from_api_entry(e) for e in root.findall(f"{ad._API_ATOM}entry")]
    return {"atom": ATOM, "total": total, "papers": papers}


def write(name: str, source: str, value) -> None:
    data = json.dumps(value, indent=1, ensure_ascii=True, sort_keys=True)
    out = ROOT / "ios" / "Tests" / "ArxivDigestCoreTests" / f"{name}.swift"
    out.write_text(
        "// Generated by ios/scripts/make_parity_fixture.py. Do not edit by hand.\n"
        f"// Expected values come from {source}; papers and names are invented.\n\n"
        f"enum {name} {{\n"
        '    static let json = #"""\n'
        f"{data}\n"
        '"""#\n'
        "}\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")


QP = "https://arxiv.org/list/quant-ph/new"
LG = "https://arxiv.org/list/cs.LG/new"

# Config blobs as the app PUTs them -> asdict(Config.from_json(blob)), the
# server's `_hydrate`. Every blob names invented authors, so no default
# (real) author list appears in the fixture.
HYDRATE = [
    {"named_authors": INVENTED_AUTHORS},
    {"core_keywords": [], "named_authors": [], "low_priority_kw": []},
    {"feeds": {"quant-ph": QP, "cs.LG": LG}, "default_feeds": ["quant-ph", "unknown"], "named_authors": ["okafor"]},
    {"feeds": {"quant-ph": QP}, "default_feeds": [], "named_authors": ["okafor"]},
    {"feeds": {"quant-ph": QP, "cs.LG": LG}, "default_feed": "cs.LG", "named_authors": ["okafor"],
     "weights": {"quant_gas_subject": 9, "core_keyword": "7", "named_author": 2.0}},
    {"named_authors": ["okafor"], "top_n": 0, "timeframe": "", "include_replacements": "false",
     "word_boundary_matching": 0, "highlight_authors": None, "color_keyword": "#000000", "weights": {},
     "feed_weights": {"quant-ph": 2.0, "cond-mat": "3"}, "unknown_key": 1},
    {"named_authors": ["okafor"], "top_n": "7", "core_keywords": ["Floquet", 5, True]},
]
HYDRATE_ERRORS = [{"top_n": "abc"}, {"feeds": ["quant-ph"]}, {"weights": {"core_keyword": None}}]


def build_config() -> dict:
    hydrate = [{"input": blob, "expected": asdict(ad.Config.from_json(blob))} for blob in HYDRATE]
    for blob in HYDRATE_ERRORS:
        try:
            ad.Config.from_json(blob)
        except (TypeError, ValueError, AttributeError):
            continue
        raise AssertionError(f"expected {blob} to be invalid")
    base = ad.Config.from_json({"named_authors": ["okafor"], "core_keywords": ["Lindblad", "anyons"],
                                "feed_weights": {"quant-ph": 9}})
    merge = [{"base": asdict(base), "preset": name, "expected": asdict(ad.merge_preset(base, name))}
             for name in ad.preset_names()]
    return {"hydrate": hydrate, "invalid": HYDRATE_ERRORS, "merge": merge}


def write_defaults() -> None:
    """The engine's defaults and starter presets, Standalone mode's first-run
    config (the same defaults the CLI, GUI and server start from)."""
    value = {
        "defaults": asdict(ad.Config()),
        "presets": {
            name: {"description": ad.preset_description(name), "config": asdict(ad.preset_config(name))}
            for name in ad.preset_names()
        },
    }
    data = json.dumps(value, indent=1, ensure_ascii=True, sort_keys=True)
    out = ROOT / "ios" / "Sources" / "ArxivDigestCore" / "Local" / "EngineDefaults.swift"
    out.write_text(
        "// Generated by ios/scripts/make_parity_fixture.py. Do not edit by hand.\n"
        "// arxiv_digest.Config() and the starter presets (PRESETS), as the engine defines them.\n\n"
        "enum EngineDefaults {\n"
        '    static let json = #"""\n'
        f"{data}\n"
        '"""#\n'
        "}\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")


def main() -> None:
    write("ScoringParityFixture", "arxiv_digest.explain_score", build())
    write("FetchParityFixture", "arxiv_digest._paper_from_api_entry", build_fetch())
    write("ConfigParityFixture", "arxiv_digest.Config.from_json / merge_preset", build_config())
    write_defaults()


if __name__ == "__main__":
    main()
