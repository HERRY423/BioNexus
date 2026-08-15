"""Environment gate for the plugin. Run before any analysis skill."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .agent_routing import DEFAULT_SKILLS, LEGACY_SKILLS
from .backends import is_module_available, probe, probe_all
from .inventory import SKILLS, core_skills
from .versions import PITFALLS, PLUGIN_VERSION, installed_vs_recommended

FORBIDDEN_CLAIMS = [
    "CLIA/CAP diagnostic interpretation",
    "21 CFR Part 11 / GxP / ALCOA+ compliance",
    "BLOSUM as ESM or PP3",
    "regex CDR as IMGT unless abnumber ran",
    "event-rate ratio as Cox PH",
    "local Moran z as Clifford-Ord",
    "ExtraTrees as SCENIC+/GRNBoost2",
    "COSMIC API / full Cancer Gene Census",
]


def _tier(ready: Dict[str, bool]) -> str:
    if ready["scverse_ready"]:
        return "full"
    if ready["core_ready"]:
        return "degraded"
    return "refuse"


def run_doctor() -> Dict[str, Any]:
    """Return a structured capability report (also used as agent decision input)."""
    backends = {name: vars(status) for name, status in probe_all().items()}
    ready = {
        "core_ready": (
            is_module_available("numpy")
            and is_module_available("pandas")
            and probe("sklearn").available
        ),
        "scverse_ready": probe("scanpy").available and probe("anndata").available,
        "scvi_ready": probe("scvi").available,
        "spatial_ready": probe("squidpy").available,
        "survival_ready": probe("lifelines").available,
        "nextflow_ready": probe("nextflow").available,
    }
    flags = {
        "sklearn": probe("sklearn").available,
        "abnumber": probe("abnumber").available,
        "esm": probe("esm").available,
        "vina": probe("vina").available,
        **ready,
    }

    tier = _tier(ready)
    next_actions: List[str] = ["read skills/start/SKILL.md"]
    if ready["scverse_ready"]:
        next_actions.append(
            "run skills/single-cell-rna-qc/scripts/scrna_pipeline.py on an .h5ad"
        )
        next_actions.append("stop at numeric clusters + markers; do not invent cell types")
    else:
        next_actions.append("pip install 'bio-research[goldchain]' before scRNA work")
    if ready["scvi_ready"]:
        next_actions.append("use skills/scvi-tools for batch integration after the gold chain")
    if ready["spatial_ready"]:
        next_actions.append(
            "run skills/spatial-transcriptomics/scripts/spatial_pipeline.py on SpatialData/.h5ad"
        )
    else:
        next_actions.append("pip install 'bio-research[spatial]' before spatial gold-chain work")

    report = {
        "plugin_version": PLUGIN_VERSION,
        "tier": tier,
        "ready": ready,
        "flags": flags,
        "backends": backends,
        "versions": installed_vs_recommended(),
        "core_skills": [s["name"] for s in core_skills()],
        "default_skills": sorted(DEFAULT_SKILLS),
        "legacy_skills": sorted(LEGACY_SKILLS),
        "heuristic_skills": [s["name"] for s in SKILLS if s.get("tier") == "heuristic"],
        "allowed_next_actions": next_actions,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "pitfalls": PITFALLS,
        "mcp_policy": (
            "Local tools/list exposes unique APIs only. Prefer hosted PubMed/ChEMBL/"
            "Open Targets/ClinicalTrials/bioRxiv. Set BIONEXUS_LOCAL_HOSTED_FALLBACKS=1 "
            "to re-enable local copies. search_cosmic is hidden by default and is not the COSMIC API."
        ),
    }
    return report


def main() -> None:
    from .gate import write_doctor_report

    report = write_doctor_report()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
