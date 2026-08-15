"""Doctor gate and MCP role annotations."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from local_mcp_server import TOOLS_SCHEMA

from bio_research.doctor import run_doctor
from bio_research.inventory import core_skills


def test_doctor_reports_tier_and_forbids_clia():
    report = run_doctor()
    assert report["tier"] in {"full", "degraded", "refuse"}
    assert "scverse_ready" in report["ready"]
    assert "scvi_ready" in report["ready"]
    assert "spatial_ready" in report["ready"]
    assert "celltypepilot" not in report["flags"]
    assert "CLIA/CAP diagnostic interpretation" in report["forbidden_claims"]
    assert any("scrna_pipeline" in a or "scverse" in a for a in report["allowed_next_actions"])
    assert "single-cell-rna-qc" in report["core_skills"]
    names = {s["name"] for s in core_skills()}
    assert names == {
        "single-cell-rna-qc",
        "scvi-tools",
        "nextflow-development",
        "spatial-transcriptomics",
    }
    assert "spatial-transcriptomics" in report["default_skills"]
    assert "biologics-design" in report["legacy_skills"]


def test_mcp_marks_hosted_tools_as_fallback():
    by_name = {t["name"]: t for t in TOOLS_SCHEMA}
    pubmed = by_name["search_pubmed"]
    assert pubmed["annotations"]["bionexus_role"] == "hosted_fallback"
    assert pubmed["description"].startswith("[local fallback")
    uniprot = by_name["search_uniprot"]
    assert uniprot["annotations"]["bionexus_role"] == "local_unique"
    cosmic = by_name["search_cosmic"]
    assert "COSMIC API" in cosmic["description"] or "not the COSMIC" in cosmic["description"].lower() or "Not the COSMIC" in cosmic["description"]
