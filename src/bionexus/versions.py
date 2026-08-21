"""Pinned library versions and agent-facing API pitfalls.

Single source of truth. Skills should point here instead of restating pins.
"""

from __future__ import annotations

from typing import Dict, List, TypedDict

from .provenance import package_version

VERSION = "1.0.0-rc.2"
PLUGIN_VERSION = VERSION


class VersionPin(TypedDict):
    name: str
    recommend: str
    notes: str


PINS: List[VersionPin] = [
    {
        "name": "scanpy",
        "recommend": "1.10+",
        "notes": (
            "1.10 moved Scrublet to sc.pp.scrublet. "
            "1.12 needs Python >=3.12 and deprecates per-plot save=. "
            "rank_genes_groups is exploratory; condition DE needs pseudobulk."
        ),
    },
    {
        "name": "anndata",
        "recommend": "0.10+",
        "notes": "Keep raw counts in .layers['counts'] before normalize/log1p.",
    },
    {
        "name": "scvi-tools",
        "recommend": "1.1+",
        "notes": "Train only on raw counts. Do not log-transform before setup_anndata.",
    },
    {
        "name": "leidenalg",
        "recommend": "0.10+",
        "notes": "Required for sc.tl.leiden via python-igraph. Missing → KMeans fallback, not Leiden.",
    },
    {
        "name": "lifelines",
        "recommend": "0.27+",
        "notes": "Only backend allowed to emit hazard_ratio. Otherwise event_rate_ratio.",
    },
    {
        "name": "squidpy",
        "recommend": "1.3+",
        "notes": "Preferred Moran / spatial graph. Use spatial_neighbors_knn when present.",
    },
    {
        "name": "pydeseq2",
        "recommend": "0.4+",
        "notes": "Only backend allowed to emit Wald DE on pseudobulk counts.",
    },
]


PITFALLS: List[str] = [
    "Do not treat rank_genes_groups p-values as sample-level differential expression.",
    "Do not log-normalize before scVI / scANVI training.",
    "Do not call BLOSUM or PWM scores ACMG PP3/PVS1.",
    "Do not call kNN majority vote BayesSpace or ExtraTrees SCENIC+.",
    "This plugin does not assign cell-type identity; clusters remain numeric.",
    "Prefer hosted PubMed/ChEMBL/Open Targets/ClinicalTrials MCP when connected.",
]


def installed_vs_recommended() -> List[Dict[str, str]]:
    rows = []
    for pin in PINS:
        rows.append(
            {
                "name": pin["name"],
                "recommend": pin["recommend"],
                "installed": package_version(pin["name"]) or "not installed",
                "notes": pin["notes"],
            }
        )
    return rows
