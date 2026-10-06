"""Generate the iOS demo-mode fixture from the real scoring engine.

Every score and breakdown in the demo comes from `arxiv_digest.explain_score`
with the demo config below, so the demo shows exactly what the digest service
would return for these papers. All papers and author names are invented.

    uv run python ios/scripts/make_demo_fixture.py

writes ios/Sources/ArxivDigestCore/Demo/DemoFixture.swift.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import arxiv_digest as ad  # noqa: E402

FEEDS = ["cond-mat.quant-gas", "cond-mat.mes-hall", "quant-ph", "cond-mat.str-el"]

CONFIG = ad.Config(
    feeds={f: ad.feed_url(f"https://arxiv.org/list/{f}/new", "today") for f in FEEDS},
    default_feeds=["cond-mat.quant-gas", "cond-mat.mes-hall", "quant-ph"],
    core_keywords=[
        "floquet", "topological", "anyons", "chern number", "lindblad",
        "open quantum system", "tensor network", "optical lattice",
        "many-body localization", "bose-hubbard",
    ],
    named_authors=["Mira Castellanos", "Jonas Albrecht", "okafor"],
    low_priority_kw=["photonic", "machine learning", "review"],
    feed_weights={"cond-mat.quant-gas": 4, "cond-mat.mes-hall": 4, "quant-ph": 2},
    top_n=10,
)

DAYS = ["Mon, 28 Sep 2026", "Tue, 29 Sep 2026", "Wed, 30 Sep 2026", "Thu, 01 Oct 2026", "Fri, 02 Oct 2026"]

# (id, day index, title, authors, subjects, abstract)
PAPERS = [
    ("2609.21407", 4, "Anomalous Floquet Anyons in Driven Optical Lattices",
     "Mira L. Castellanos, Tomas Reinholt, Aiko Senda",
     "cond-mat.quant-gas, quant-ph",
     "We show that periodic driving of an interacting optical lattice stabilises anyons with a "
     "statistical phase set by the Floquet frequency. The anomalous Floquet phase hosts chiral "
     "edge modes although every Floquet band has zero Chern number. Exact diagonalisation and "
     "tensor network simulations of a Bose-Hubbard ladder show that the braiding phase survives "
     "heating times well beyond current experiments."),
    ("2609.21188", 3, "Lindblad Engineering of Topological Steady States",
     "Jonas Albrecht, Leila Haddad",
     "quant-ph, cond-mat.mes-hall",
     "Engineered dissipation can prepare topological phases as the unique steady state of a "
     "Lindblad master equation. We classify which jump operators preserve a non-zero Chern number "
     "and derive a gap condition that bounds the preparation time in an open quantum system of "
     "fermions on a lattice."),
    ("2609.20954", 2, "Chern Number Tomography from Quench Dynamics",
     "Ruth Okafor, Daniel Meyrink, Sana Qureshi",
     "cond-mat.quant-gas",
     "We propose a protocol that reads out the Chern number of an optical lattice band from the "
     "time-of-flight images after a sudden quench. The method needs no adiabatic loading and is "
     "robust to a finite temperature and to weak interactions."),
    ("2609.20711", 1, "Tensor Network Study of the Bose-Hubbard Model at Fractional Filling",
     "Pieter van Loon, Hana Kobayashi",
     "cond-mat.str-el, cond-mat.quant-gas",
     "Using an infinite tensor network ansatz we map the ground-state phase diagram of the "
     "two-dimensional Bose-Hubbard model at filling one half with nearest-neighbour repulsion, "
     "finding a supersolid region bounded by first-order transitions."),
    ("2609.21530", 4, "Many-Body Localization in Quasiperiodic Floquet Chains",
     "Elena Varga, Marco Pellizzari",
     "cond-mat.dis-nn, quant-ph",
     "We study many-body localization in a quasiperiodic spin chain under periodic kicks. The "
     "Floquet eigenstates stay area-law entangled up to a critical drive amplitude, beyond which "
     "the system heats to infinite temperature."),
    ("2609.20333", 0, "Edge States of Higher-Order Topological Insulators in Moire Bilayers",
     "Chen Wei, Ingrid Solberg, Tomas Reinholt",
     "cond-mat.mes-hall",
     "Twisted bilayers with a moire potential host corner modes protected by crystalline "
     "symmetry. We compute the quadrupole moment and show how the corner charge responds to an "
     "applied displacement field."),
    ("2609.20877", 2, "Photonic Realization of Floquet Topological Insulators: A Review",
     "Amara Diallo",
     "physics.optics, quant-ph",
     "We review photonic waveguide arrays and coupled resonators as platforms for Floquet "
     "topological insulators, summarising experiments on anomalous edge transport and the "
     "measurement of winding numbers in synthetic dimensions."),
    ("2609.21002", 3, "Dissipative Preparation of Spin Liquids with Rydberg Arrays",
     "Ruth Okafor, Felix Brandt",
     "quant-ph, cond-mat.str-el",
     "Rydberg tweezer arrays with engineered decay realise an open quantum system whose steady "
     "state is a resonating valence bond liquid. We give the fidelity as a function of array "
     "size and decay rate."),
    ("2609.20519", 1, "Machine Learning Phase Boundaries of Driven Bose Gases",
     "Kenji Arakawa, Lucia Romero",
     "cond-mat.quant-gas, cs.LG",
     "A convolutional network trained on snapshots of a driven Bose gas in an optical lattice "
     "locates the superfluid to Mott transition within two percent of quantum Monte Carlo."),
    ("2609.20166", 0, "Thermal Transport in Kitaev Magnets",
     "Ingrid Solberg, Rafael Mendes",
     "cond-mat.str-el",
     "We compute the thermal Hall conductivity of a Kitaev magnet in a tilted field with a "
     "self-consistent spin-wave theory and compare with recent measurements."),
    ("2609.21455", 4, "Interferometric Detection of Non-Abelian Anyons in Quantum Hall Bilayers",
     "Sana Qureshi, Jonas Albrecht, Leon Hartmann",
     "cond-mat.mes-hall",
     "We propose a Fabry-Perot interferometer that distinguishes non-Abelian anyons in a quantum "
     "Hall bilayer by the parity of the enclosed quasiparticle number."),
    ("2609.20640", 1, "Quantum Error Mitigation for Variational Eigensolvers",
     "Grace Whitfield, Omar Saleh",
     "quant-ph",
     "We benchmark zero-noise extrapolation and probabilistic error cancellation for variational "
     "eigensolvers on twelve superconducting qubits."),
    ("2609.20288", 0, "Spin Squeezing in Cavity-Coupled Atomic Ensembles",
     "Helena Novak",
     "quant-ph, physics.atom-ph",
     "Collective coupling to an optical cavity generates spin squeezing of ten decibels in an "
     "ensemble of strontium atoms."),
    ("2609.20999", 2, "Superconducting Diode Effect in Twisted Trilayer Graphene",
     "Marco Pellizzari, Chen Wei",
     "cond-mat.supr-con, cond-mat.mes-hall",
     "We report a nonreciprocal critical current in twisted trilayer graphene and relate it to "
     "valley polarisation."),
]


def _paper(pid, day, title, authors, subjects, abstract, section):
    return {
        "id": pid,
        "title": title,
        "authors": authors,
        "link": f"https://arxiv.org/abs/{pid}",
        "subjects": subjects,
        "abstract": abstract,
        "section": section,
    }


def _scored(p: dict) -> dict:
    breakdown = ad.explain_score(p, CONFIG)
    return {
        **p,
        "rank": 0,  # assigned when the demo backend ranks
        "summary": ad.summarize(p["abstract"]),
        "score": breakdown["total"],
        "breakdown": {"signals": {"keyword": breakdown}, "total": breakdown["total"]},
    }


def build() -> dict:
    pastweek = [_scored(_paper(pid, d, t, a, s, ab, DAYS[d])) for pid, d, t, a, s, ab in PAPERS]
    # "today" = the latest day's /new listing: new + cross submissions, plus one
    # replacement (hidden unless include_replacements).
    today = []
    for pid, d, t, a, s, ab in PAPERS:
        if d != len(DAYS) - 1:
            continue
        kind = "Cross submissions" if s.split(",")[0].strip() not in FEEDS else "New submissions"
        today.append(_scored(_paper(pid, d, t, a, s, ab, f"{kind} (showing 1 of 1 entries)")))
    pid, d, t, a, s, ab = PAPERS[1]
    today.append(_scored(_paper(pid, d, t, a, s, ab, "Replacement submissions (showing 1 of 1 entries)")))

    presets = {
        name: {"description": ad.preset_description(name), "config": asdict(ad.preset_config(name))}
        for name in ad.preset_names()
    }
    return {
        "config": asdict(CONFIG),
        "pastweek": pastweek,
        "today": today,
        "days": DAYS,
        "presets": presets,
    }


def main() -> None:
    data = json.dumps(build(), indent=1, ensure_ascii=True, sort_keys=True)
    out = ROOT / "ios" / "Sources" / "ArxivDigestCore" / "Demo" / "DemoFixture.swift"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "// Generated by ios/scripts/make_demo_fixture.py. Do not edit by hand.\n"
        "// Scores/breakdowns come from arxiv_digest.explain_score; papers and names are invented.\n\n"
        "enum DemoFixture {\n"
        '    static let json = #"""\n'
        f"{data}\n"
        '"""#\n'
        "}\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
