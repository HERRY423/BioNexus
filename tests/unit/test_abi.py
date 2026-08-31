"""
Unit tests for the Biological Capability ABI (BNS-001 §5, ABI v1.0).

Validates:
1. ABI projection completeness & single-source-of-truth from canonical contracts.
2. Input contract semantics (matrix states, coordinate types).
3. Forbidden-claim catalog normativity and claim audits.
4. Evidence-ceiling clamping (BNS-CC-013 / BNS-EM-006).
5. Routing-time forbidden-claim interception (BNS-AD-009).
6. CLI 'bionexus abi' surface.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.abi import (
    ABI_VERSION,
    FORBIDDEN_CLAIM_CATALOG,
    audit_claims_against_abi,
    capability_abis,
    detect_forbidden_claims_in_query,
    enforce_evidence_ceiling,
    get_capability_abi,
)
from bionexus.capabilities import CANONICAL_CAPABILITIES
from bionexus.cli import main as cli_main
from bionexus.intent_router import route_scientific_intent


def test_abi_projection_covers_all_capabilities():
    """Every canonical capability MUST project to a complete ABI record (BNS-CC-010)."""
    abis = capability_abis()
    assert set(abis.keys()) == set(CANONICAL_CAPABILITIES.keys())
    for cid, abi in abis.items():
        assert abi.capability_id == cid
        assert abi.abi_version == ABI_VERSION
        assert abi.contract_version == CANONICAL_CAPABILITIES[cid].version
        assert len(abi.forbidden_claims) > 0
        assert abi.evidence_ceiling.without_external_validation in (
            "PRELIMINARY",
            "SUPPORTED",
            "ROBUST",
        ) or abi.evidence_ceiling.without_external_validation == "FRAGILE"
        assert abi.provenance.dataset_hash == "required"
        assert abi.provenance.package_versions == "required"
        assert abi.provenance.parameters == "required"


def test_abi_serializes_to_canonical_shape():
    """The ABI record MUST serialize to the canonical YAML shape (BNS-001 §5)."""
    d = get_capability_abi("spatial.morans_svg").to_dict()
    assert d["capability"]["id"] == "spatial.morans_svg"
    assert d["capability"]["abi_version"] == "1.0"
    ic = d["input_contract"]
    assert "normalized_expression" in ic["matrix_state_allowed"]
    assert ic["coordinates_required"] is True
    assert set(ic["coordinate_type_allowed"]) == {"physical", "justified_spatial_embedding"}
    assert "causal_interaction" in d["forbidden_claims"]
    assert "cell_cell_communication" in d["forbidden_claims"]
    assert d["execution"]["reference_backend"] == "squidpy"
    assert d["execution"]["reference_algorithm"] == "spatial_autocorr"
    assert d["validation"]["multiple_testing"] == "required"
    assert d["evidence_ceiling"]["without_external_validation"] == "FRAGILE"
    assert d["provenance"]["dataset_hash"] == "required"


def test_abi_single_source_of_truth_no_drift():
    """ABI forbidden claims and ceiling MUST mirror the contract, not enrichment."""
    for cid, contract in CANONICAL_CAPABILITIES.items():
        abi = get_capability_abi(cid)
        assert abi.forbidden_claims == contract.forbidden_claims, cid
        assert (
            abi.evidence_ceiling.without_external_validation
            == contract.evidence_ceiling_without_external_validation
        ), cid
        required = [n for n, s in contract.inputs.items() if s.required]
        assert abi.input_contract.required_inputs == required, cid


def test_count_model_abis_require_raw_counts():
    """Negative-binomial capabilities MUST restrict matrix state to raw counts (BNS-II-002)."""
    assert get_capability_abi("scrna.pseudobulk_de").input_contract.matrix_state_allowed == ["raw_counts"]
    assert get_capability_abi("scvi.probabilistic_vae").input_contract.matrix_state_allowed == ["raw_counts"]


def test_forbidden_claim_catalog_normative():
    """All catalog entries MUST have detection patterns; contract claims MUST come from the catalog."""
    for claim_id, claim in FORBIDDEN_CLAIM_CATALOG.items():
        assert claim.claim_id == claim_id
        assert claim.description
        assert len(claim.detection_patterns) > 0
    for cid, abi in capability_abis().items():
        for claim_id in abi.forbidden_claims:
            assert claim_id in FORBIDDEN_CLAIM_CATALOG, f"{cid} -> unknown claim {claim_id}"


def test_claim_audit_catches_and_clears():
    """Claim audit MUST flag forbidden claims and MUST pass honest phrasing (BNS-CC-012)."""
    bad = audit_claims_against_abi(
        "spatial.morans_svg",
        [
            "Gene X exhibits significant spatial autocorrelation (Moran's I = 0.42)",
            "This proves cell-cell communication between neighborhoods.",
        ],
    )
    assert bad.passed is False
    assert any(v["claim_id"] == "cell_cell_communication" for v in bad.violations)

    good = audit_claims_against_abi(
        "spatial.morans_svg",
        ["Gene X ranks among the top spatially autocorrelated genes at FDR < 0.05."],
    )
    assert good.passed is True


def test_evidence_ceiling_clamping():
    """Ceiling clamps over-warranted claims; external validation unlocks (BNS-EM-006)."""
    # Spatial: SUPPORTED -> FRAGILE without external validation
    assert enforce_evidence_ceiling("spatial.morans_svg", "SUPPORTED") == "FRAGILE"
    assert enforce_evidence_ceiling("spatial.morans_svg", "REPLICATED") == "FRAGILE"
    # Exploratory clustering: ROBUST -> PRELIMINARY
    assert enforce_evidence_ceiling("scrna.exploratory_clustering", "ROBUST") == "PRELIMINARY"
    # Pseudobulk: REPLICATED -> SUPPORTED without an external cohort
    assert enforce_evidence_ceiling("scrna.pseudobulk_de", "REPLICATED") == "SUPPORTED"
    # Claims at or below the ceiling are untouched
    assert enforce_evidence_ceiling("scrna.pseudobulk_de", "SUPPORTED") == "SUPPORTED"
    assert enforce_evidence_ceiling("spatial.morans_svg", "FRAGILE") == "FRAGILE"
    # External validation removes the clamp (ACMG + ClinVar truth set -> REPLICATED)
    assert (
        enforce_evidence_ceiling("variant.acmg_classification", "REPLICATED", has_external_validation=True)
        == "REPLICATED"
    )
    # ABSTAIN/low claims are never inflated by the clamp
    assert enforce_evidence_ceiling("spatial.morans_svg", "ABSTAIN") == "ABSTAIN"


def test_router_blocks_forbidden_claim_requests():
    """Router MUST refuse requests that ask a capability for a forbidden claim (BNS-AD-009)."""
    blocked = route_scientific_intent(
        "Use Moran's I spatial autocorrelation to prove cell-cell communication "
        "and causal interaction between ligand-receptor pairs"
    )
    assert blocked.status.value == "ABSTAIN"
    assert any("forbidden claim" in v.lower() for v in blocked.violations)

    clinical = route_scientific_intent(
        "Kaplan-Meier survival analysis to confirm the patient has disease and recommend therapy"
    )
    assert clinical.status.value == "ABSTAIN"

    celltype = route_scientific_intent(
        "Leiden clustering of my single-cell data, then state that cluster 0 are T cells without reference"
    )
    assert celltype.status.value == "ABSTAIN"


def test_router_preserves_legitimate_requests(canonical_backends_available):
    """Forbidden-claim screening MUST NOT block legitimate requests (no false positives)."""
    ok_spatial = route_scientific_intent(
        "Compute Moran's I spatial autocorrelation on my Visium spatial transcriptomics data",
        data_metadata={"n_spatial_spots": 500},
    )
    assert ok_spatial.status.value == "PERMITTED"

    ok_cluster = route_scientific_intent(
        "Look at my scRNA clusters 0, 1, 2. Tell me which one is CD8+ T cell, B cell, and NK cell."
    )
    assert ok_cluster.status.value == "PERMITTED"

    assert detect_forbidden_claims_in_query("spatial.morans_svg", "identify spatially variable genes") == []


def test_abi_cli_surface(capsys):
    """CLI exposes the ABI: list / show / audit-claims / conformance."""
    assert cli_main(["abi", "conformance"]) == 0
    assert cli_main(["abi", "show", "spatial.morans_svg"]) == 0
    assert cli_main(["abi", "list"]) == 0
    out = capsys.readouterr()
    assert "CONFORMANT" in out.out

    rc = cli_main(
        ["abi", "audit-claims", "spatial.morans_svg", "--claims", "Morans I proves cell-cell communication"]
    )
    assert rc == 1  # violations detected
    captured = capsys.readouterr()
    assert "VIOLATIONS DETECTED" in captured.out

    assert cli_main(["abi", "audit-claims", "spatial.morans_svg", "--claims", "SVG ranking table"]) == 0
