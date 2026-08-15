"""
Unit tests for Experiment Design Agent suite:
Entity extraction, skill router, 5-phase research planner, multi-modal evidence synthesizer,
and research monograph compiler.
"""

import sys
from pathlib import Path

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "experiment-design-agent" / "scripts"))

from evidence_synthesizer import synthesize_multimodal_evidence
from report_compiler import compile_research_monograph
from research_planner import create_preclinical_research_plan
from skill_router import extract_biological_entities, route_scientific_query


def test_entity_extraction_and_skill_routing():
    """Test extraction of genes, variants, and disease keywords with intelligent routing."""
    query = "Evaluate KRAS G12D mutation and binding pockets in pancreatic adenocarcinoma"
    entities = extract_biological_entities(query)
    assert "KRAS" in entities["genes"]
    assert len(entities["variants"]) >= 1
    assert "adenocarcinoma" in entities["diseases"]

    routed = route_scientific_query(query)
    assert "recommended_execution_plan" in routed
    assert len(routed["recommended_execution_plan"]) >= 2


def test_5_phase_research_plan_generation():
    """Test generation of structured 5-phase preclinical master plan."""
    plan = create_preclinical_research_plan(
        target_gene="BRAF",
        disease_indication="Melanoma",
        modality="Kinase Inhibitor"
    )
    assert plan["target_gene"] == "BRAF"
    assert plan["total_phases"] == 5
    assert len(plan["phases"]) == 5
    assert plan["phases"][0]["phase_number"] == 1
    assert "Druggability" in plan["phases"][0]["phase_title"]
    assert "risk_assessment" in plan


def test_multimodal_evidence_synthesis():
    """Test multi-omics Bayesian target validation decision engine."""
    # Strong convergent evidence -> GO
    ev_strong = synthesize_multimodal_evidence(
        target_gene="EGFR",
        disease_indication="Lung Cancer",
        genetic_association_score=0.90,
        druggability_score=0.85,
        has_potent_ligands=True
    )
    assert "GO" in ev_strong["recommendation"]
    assert ev_strong["bayesian_posterior_success"] > 0.60

    # Weak evidence -> NO-GO
    ev_weak = synthesize_multimodal_evidence(
        target_gene="UNKNOWN_GENE",
        disease_indication="Rare Disease",
        genetic_association_score=0.10,
        druggability_score=0.20,
        has_potent_ligands=False,
        single_cell_enriched=False
    )
    assert "NO-GO" in ev_weak["recommendation"]


def test_research_monograph_compiler():
    """Test Markdown research monograph compilation."""
    plan = create_preclinical_research_plan(target_gene="TP53", disease_indication="Colorectal Cancer")
    evidence = synthesize_multimodal_evidence(target_gene="TP53", disease_indication="Colorectal Cancer")
    monograph = compile_research_monograph(plan, evidence)
    assert "# Preclinical Investigation & Translational Strategy: TP53 in Colorectal Cancer" in monograph
    assert "Executive Summary & Milestone Decision" in monograph
    assert "5-Phase Preclinical Investigation Roadmap" in monograph
    assert "FAIR Data & Computational Provenance" in monograph
