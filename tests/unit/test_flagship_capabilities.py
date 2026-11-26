"""
Unit tests for the flagship capabilities (BNS-013 capabilities B and C,
BNS-015 flagship track): contracts, verdict ladders, router wiring, and the
flagship certification program.
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.abi import enforce_statistical_warrant, get_capability_abi
from bionexus.annotation_evidence import (
    AnnotationEvidence,
    assess_annotation_evidence,
)
from bionexus.capabilities import get_capability
from bionexus.certification import (
    EXTERNAL_CRITERIA,
    FLAGSHIP_CAPABILITIES,
    CertificationTier,
    certify_capability,
    flagship_program,
)
from bionexus.cli import main as cli_main
from bionexus.intent_router import RoutingStatus, route_scientific_intent
from bionexus.spatial_inference import (
    CANONICAL_ALTERNATIVES,
    ControlResult,
    assess_spatial_inference,
)

# ==============================================================================
# Capability contracts
# ==============================================================================


def test_flagship_contracts_exist():
    for cid in FLAGSHIP_CAPABILITIES:
        cap = get_capability(cid)
        assert cap.preconditions, cid
        assert cap.refusal_conditions, cid
        assert cap.forbidden_claims, cid
        abi = get_capability_abi(cid)
        assert abi.input_contract.required_inputs, cid
        assert abi.evidence_ceiling.without_external_validation


def test_annotation_evidence_ceiling_is_supported():
    assert get_capability_abi("scrna.annotation_evidence").evidence_ceiling.without_external_validation == "SUPPORTED"


def test_spatial_validity_ceiling_is_fragile():
    abi = get_capability_abi("spatial.inference_validity")
    assert abi.evidence_ceiling.without_external_validation == "FRAGILE"
    assert "physical" in abi.input_contract.coordinate_type_allowed


# ==============================================================================
# Flagship B: annotation evidence ladder
# ==============================================================================


def test_annotation_scores_without_empirical_profile_stay_tentative():
    verdict = assess_annotation_evidence(
        "CD8 effector T cell",
        AnnotationEvidence(
            marker_consistency=0.85,
            negative_marker_violation=0.05,
            reference_mapping_score=0.9,
            doublet_rate=0.03,
            ontology_compatible=True,
            cross_method_agreement=0.9,
        ),
    )
    assert verdict.verdict == "TENTATIVE"
    assert verdict.calibration["fallback_used"] is False
    assert any("approved empirical calibration" in item for item in verdict.missing_evidence)


def test_annotation_markers_only_stay_tentative():
    verdict = assess_annotation_evidence(
        "Tpex",
        AnnotationEvidence(marker_consistency=0.8, negative_marker_violation=0.1, doublet_rate=0.05),
    )
    assert verdict.verdict == "TENTATIVE"
    assert any("independent identity source" in m for m in verdict.missing_evidence)


def test_annotation_open_set_abstains():
    verdict = assess_annotation_evidence(
        "Tumor-reactive T cell", AnnotationEvidence(marker_consistency=0.9, open_set_detected=True)
    )
    assert verdict.verdict == "ABSTAIN"
    assert any("open-set" in r.lower() or "unknown" in r.lower() for r in verdict.reasons)


def test_annotation_no_evidence_abstains():
    verdict = assess_annotation_evidence("whatever", AnnotationEvidence())
    assert verdict.verdict == "ABSTAIN"


def test_annotation_contradicting_evidence_is_tentative():
    verdict = assess_annotation_evidence(
        "B cell",
        AnnotationEvidence(marker_consistency=0.2, negative_marker_violation=0.5, reference_mapping_score=0.9),
    )
    assert verdict.verdict == "TENTATIVE"
    assert any("approved empirical calibration" in item for item in verdict.missing_evidence)


# ==============================================================================
# Flagship C: spatial inference validity ladder
# ==============================================================================


def test_spatial_no_controls_abstains():
    verdict = assess_spatial_inference("Gene X enriches toward macrophage-facing membrane", None)
    assert verdict.verdict == "ABSTAIN"


def test_spatial_untested_alternatives_fragile():
    verdict = assess_spatial_inference(
        "Gene X enriches toward macrophage-facing membrane",
        {
            "cell_size": "CONTROLLED",
            "transcript_density": "TESTED",
            "segmentation_uncertainty": "TESTED",
            "nuclear_eccentricity": "UNTESTED",
        },
    )
    assert verdict.verdict == "FRAGILE"
    assert "nuclear_eccentricity" in verdict.untested
    # canonical alternatives not declared count as untested; the permutation
    # null only caps at SUPPORTED when merely absent (see next test)
    assert "spot_composition" in verdict.untested


def _bound_spatial_controls():
    controls = []
    artifacts = {}
    for name in CANONICAL_ALTERNATIVES:
        if name == "sample_level_replication":
            continue
        payload = f"{name} synthetic diagnostic".encode()
        digest = hashlib.sha256(payload).hexdigest()
        artifacts[digest] = payload
        controls.append(ControlResult(name, "TESTED", statistic=1.0, artifact_sha256=digest))
    return controls, artifacts


def test_spatial_all_core_controls_supported_without_null():
    controls, artifacts = _bound_spatial_controls()
    obs = pd.DataFrame({"donor": [1, 2, 3, 4], "condition": ["A", "A", "B", "B"]})
    verdict = assess_spatial_inference(
        "Membrane enrichment", [c for c in controls if c.name != "permutation_null"], obs=obs, artifacts=artifacts,
    )
    assert verdict.verdict == "SUPPORTED"
    assert any("permutation null" in n.lower() for n in verdict.notes)


def test_spatial_full_controls_with_null_robust():
    controls, artifacts = _bound_spatial_controls()
    obs = pd.DataFrame({"donor": [1, 2, 3, 4], "condition": ["A", "A", "B", "B"]})
    verdict = assess_spatial_inference("Membrane enrichment", controls, obs=obs, artifacts=artifacts)
    assert verdict.verdict == "ROBUST"
    assert verdict.samples_per_group == {"A": 2, "B": 2}
    assert verdict.to_dict()["control_evidence"]["cell_size"]["statistic"] == 1.0


def test_spatial_declarations_and_mismatched_artifacts_cap_verdict():
    obs = pd.DataFrame({"section": ["s1", "s2"], "condition": ["A", "A"]})
    results = assess_spatial_inference("Enrichment", dict.fromkeys(CANONICAL_ALTERNATIVES, "TESTED"), obs=obs)
    assert results.verdict == "FRAGILE"
    assert set(results.declared) == set(CANONICAL_ALTERNATIVES) - {"sample_level_replication"}
    controls, artifacts = _bound_spatial_controls()
    artifacts[controls[0].artifact_sha256] = b"changed"
    assert assess_spatial_inference("Enrichment", controls, obs=obs, artifacts=artifacts).declared == [controls[0].name]


def test_spatial_counts_independent_units_and_ignores_replication_declaration():
    controls, artifacts = _bound_spatial_controls()
    controls.append(ControlResult("sample_level_replication", "CONTROLLED", artifact_sha256=controls[0].artifact_sha256))
    verdict = assess_spatial_inference("Enrichment", controls, artifacts=artifacts)
    assert verdict.verdict == "FRAGILE"
    assert "sample_level_replication" in verdict.untested
    obs = pd.DataFrame({"condition": ["A", "A", "B", "B"], "donor_id": [1, 2, 3, 3], "section": [1, 2, 3, 4]})
    verdict = assess_spatial_inference("Enrichment", controls, obs=obs, artifacts=artifacts)
    assert verdict.verdict == "ABSTAIN"
    assert verdict.samples_per_group == {"A": 2, "B": 1}
    only_section = pd.DataFrame({"section_id": ["s1"] * 100})
    assert assess_spatial_inference("Enrichment", controls, obs=only_section, artifacts=artifacts).verdict == "ABSTAIN"


def test_tissue_edge_aliases_are_independent_of_contact_geometry(monkeypatch):
    from bionexus.spatial_inference import ALTERNATIVE_ALIASES
    monkeypatch.setitem(ALTERNATIVE_ALIASES, "tissue_edge", "edge_effect")
    for alias in ("edge_effects", "edge_effect", "tissue_edge"):
        verdict = assess_spatial_inference("Enrichment", {alias: "FAILED", "contact_geometry": "TESTED"})
        assert verdict.failed == ["edge_effects"]
        assert verdict.declared == ["contact_geometry"]


def test_spatial_failed_control_is_conflicted():
    verdict = assess_spatial_inference(
        "Gene X enriches toward macrophage-facing membrane",
        {"cell_size": "FAILED", "transcript_density": "TESTED", "segmentation_uncertainty": "TESTED"},
    )
    assert verdict.verdict == "CONFLICTED"
    assert "cell_size" in verdict.failed


def test_control_result_validates_names_and_statuses():
    import pytest

    with pytest.raises(ValueError):
        ControlResult(name="not_a_control", status="TESTED")
    with pytest.raises(ValueError):
        ControlResult(name="cell_size", status="MAYBE")


# ==============================================================================
# Router wiring for the flagship capabilities
# ==============================================================================


def test_router_annotation_no_evidence_refused():
    decision = route_scientific_intent(
        query="assess the annotation evidence support for the candidate cell-type labels",
        data_metadata={"annotation_evidence_available": False},
    )
    assert decision.status is RoutingStatus.ABSTAIN
    assert decision.matched_capability.id == "scrna.annotation_evidence"
    assert any("BN-F003" in v for v in decision.violations) or "annotation" in " ".join(decision.violations).lower()


def test_router_annotation_open_set_refused():
    decision = route_scientific_intent(
        query="assess the annotation evidence support for the candidate labels",
        data_metadata={"annotation_evidence_available": True, "open_set_detected": True},
    )
    assert decision.status is RoutingStatus.ABSTAIN


def test_router_spatial_validity_no_controls_needs_data():
    decision = route_scientific_intent(
        query="validate the spatial conclusion against alternative explanations",
        data_metadata={"alternative_explanations_tested": False},
    )
    assert decision.status is RoutingStatus.NEEDS_DATA
    assert decision.matched_capability.id == "spatial.inference_validity"
    assert decision.missing_data_requests


def test_router_spatial_validity_ceiling_fragile():
    decision = route_scientific_intent(
        query="test whether the spatial conclusion holds against alternative explanations",
        data_metadata={"untested_alternatives": ["cell_size"], "claimed_maturity": "SUPPORTED"},
    )
    assert decision.status is RoutingStatus.PERMITTED
    assert enforce_statistical_warrant("spatial.inference_validity", "SUPPORTED") == "FRAGILE"


def test_statistical_warrant_fdr_cap():
    """BN-F005: missing FDR caps warrant-level maturities at PRELIMINARY."""
    assert enforce_statistical_warrant("scrna.pseudobulk_de", "SUPPORTED", has_fdr_correction=False) == "PRELIMINARY"
    assert enforce_statistical_warrant("scrna.pseudobulk_de", "REPLICATED", has_fdr_correction=False) == "PRELIMINARY"
    assert enforce_statistical_warrant("scrna.pseudobulk_de", "SUPPORTED", has_fdr_correction=True) == "SUPPORTED"
    # warning states pass through untouched
    assert enforce_statistical_warrant("scrna.pseudobulk_de", "FRAGILE", has_fdr_correction=False) == "FRAGILE"


# ==============================================================================
# Flagship certification track (BNS-015)
# ==============================================================================


def test_flagship_program_structure():
    program = flagship_program()
    assert program["flagship_target_certified"] == 3
    assert set(program["capabilities"]) == set(FLAGSHIP_CAPABILITIES)
    assert program["principle"].startswith("Three CERTIFIED")
    for cid, info in program["capabilities"].items():
        assert info["current_tier"] in ("VALIDATED", "CERTIFIED"), cid
        assert set(info["external_criteria_remaining"]) <= set(EXTERNAL_CRITERIA)
        if info["current_tier"] != "CERTIFIED":
            assert info["external_criteria_remaining"], f"{cid} flagship is external-evidence-driven"


def test_flagship_tiers_computed_not_asserted():
    for cid in FLAGSHIP_CAPABILITIES:
        rec = certify_capability(cid)
        assert rec.tier in (CertificationTier.VALIDATED, CertificationTier.CERTIFIED)
        # external criteria cannot be self-satisfied
        for crit in EXTERNAL_CRITERIA:
            if crit not in rec.blocking_for_certified:
                assert rec.criteria[crit].satisfied and rec.criteria[crit].evidence, (cid, crit)


def test_certification_cli_shows_flagship(capsys):
    assert cli_main(["certification"]) == 0
    out = capsys.readouterr().out
    assert "Flagship Certification Track" in out
    assert "scrna.annotation_evidence" in out
    assert "spatial.inference_validity" in out
    assert "external" in out.lower()
