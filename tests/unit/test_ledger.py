"""
Unit tests for the Claim–Evidence Ledger (BNS-012).

Validates:
1. Closed vocabularies and record shape (BNS-CL-002..004).
2. Fail-closed status resolution incl. the CLAIM-017 reference scenario (BNS-CL-005..007).
3. Ceiling interplay: aggregation never manufactures warrant.
4. JSON round-trip and PROV-O JSON-LD projection (BNS-CL-008..009).
5. Append-only semantics: duplicate IDs rejected.
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef


def _reference_ledger() -> ClaimLedger:
    """The CLAIM-017 interferon-response scenario from BNS-012 §1."""
    ledger = ClaimLedger()
    for ref in [
        EvidenceRef("DE-102", "statistical_result", "IFN-stimulated genes enriched in cluster 3", maturity="PRELIMINARY"),
        EvidenceRef("GSEA-021", "statistical_result", "Interferon response pathway ES=0.58, FDR q=0.11", maturity="FRAGILE"),
        EvidenceRef("SCVI-DE-014", "cross_method", "scVI latent DE does not separate IFN program", maturity="PRELIMINARY"),
        EvidenceRef("QC-004", "transformation", "MAD-based QC, 8% cells removed", maturity="SUPPORTED"),
        EvidenceRef("NORMALIZATION-003", "transformation", "CPM + log1p", maturity="SUPPORTED"),
        EvidenceRef("CLUSTERING-007", "method_run", "Leiden res=1.0, ARI stability 0.74", maturity="FRAGILE"),
    ]:
        ledger.add_evidence(ref)
    return ledger


def test_evidence_kind_vocabulary_is_closed():
    with pytest.raises(ValueError):
        EvidenceRef("X-1", "vibes", "not a real kind")
    with pytest.raises(ValueError):
        EvidenceRef("X-2", "dataset", "bad maturity", maturity="SUPER_CONFIDENT")


def test_claim_017_reference_scenario():
    """Contradicted claims MUST resolve CONFLICTED (fail-closed, BNS-CL-005)."""
    ledger = _reference_ledger()
    claim = ClaimRecord(
        claim_id="CLAIM-017",
        statement="Cluster 3 exhibits interferon-response activation",
        capability_id="scrna.exploratory_clustering",
        supported_by=["DE-102", "GSEA-021"],
        contradicted_by=["SCVI-DE-014"],
        depends_on=["DATASET-SHA256:deadbeef", "QC-004", "NORMALIZATION-003", "CLUSTERING-007"],
    )
    ledger.add_claim(claim)
    assert claim.evidence_status == "CONFLICTED"


def test_min_maturity_and_ceiling_clamp():
    """Uncontradicted claims inherit the weakest support rank, clamped by the ABI ceiling."""
    ledger = _reference_ledger()
    claim = ClaimRecord(
        claim_id="CLAIM-018",
        statement="Cluster 3 shows IFN marker enrichment",
        capability_id="scrna.exploratory_clustering",
        supported_by=["DE-102", "GSEA-021"],  # PRELIMINARY (rank 1) + FRAGILE (rank 2)
        depends_on=["QC-004"],
    )
    ledger.add_claim(claim)
    # Weakest warrant dominates (rank 1); ceiling PRELIMINARY leaves it unchanged
    assert claim.evidence_status == "PRELIMINARY"

    # Strong support dragged down by one FRAGILE member -> warning state preserved
    ledger.add_evidence(EvidenceRef("ATLAS-MATCH-8", "database", "marker concordance with atlas", maturity="SUPPORTED"))
    mixed = ClaimRecord(
        claim_id="CLAIM-019",
        statement="Cluster 3 marker program matches atlas",
        capability_id="scrna.exploratory_clustering",
        supported_by=["ATLAS-MATCH-8", "GSEA-021"],
    )
    ledger.add_claim(mixed)
    assert mixed.evidence_status == "FRAGILE"

    # No capability context: inherits exactly
    cap = ClaimRecord(
        claim_id="CLAIM-020",
        statement="Cluster 3 shows IFN marker enrichment",
        capability_id=None,
        supported_by=["DE-102"],
    )
    ledger.add_claim(cap)
    assert cap.evidence_status == "PRELIMINARY"


def test_claims_need_evidence():
    ledger = _reference_ledger()
    empty = ClaimRecord("CLAIM-030", "Something happened", supported_by=[])
    ledger.add_claim(empty)
    assert empty.evidence_status == "ABSTAIN"


def test_database_retrieval_does_not_unlock_external_validation_ceiling():
    ledger = _reference_ledger()
    ledger.add_evidence(EvidenceRef("PBMC-ATLAS-9", "database", "CITE-seq atlas IFN module concordance", maturity="REPLICATED"))
    claim = ClaimRecord(
        claim_id="CLAIM-021",
        statement="Cluster 3 is an IFN-active population",
        capability_id="variant.acmg_classification",
        supported_by=["PBMC-ATLAS-9"],
    )
    ledger.add_claim(claim)
    assert claim.evidence_status != "REPLICATED"


def test_qualified_independent_validation_unlocks_ceiling():
    ledger = _reference_ledger()
    ledger.add_evidence(
        EvidenceRef(
            "PBMC-ATLAS-10",
            "cross_method",
            "Held-out cohort assessment",
            maturity="REPLICATED",
            validation_role="external_validation",
            provenance={
                "independence_basis": "held_out_cohort",
                "validation_target_sha256": "a" * 64,
                "validation_evidence_sha256": "b" * 64,
                "review_status": "approved",
                "reviewer_id": "reviewer:external-01",
                "review_receipt_sha256": "c" * 64,
            },
        )
    )
    claim = ClaimRecord(
        claim_id="CLAIM-022",
        statement="Gene X is associated with response Y",
        capability_id="variant.acmg_classification",
        supported_by=["PBMC-ATLAS-10"],
    )
    ledger.add_claim(claim)
    assert claim.evidence_status == "REPLICATED"


def test_external_validation_role_requires_independence_hashes_and_human_review():
    with pytest.raises(ValueError, match="review_status='approved'"):
        EvidenceRef(
            "EXT-BAD-1",
            "cross_method",
            validation_role="external_validation",
            provenance={"independence_basis": "held_out_cohort"},
        )

    with pytest.raises(ValueError, match="cannot validate an artifact against itself"):
        EvidenceRef(
            "EXT-BAD-2",
            "cross_method",
            validation_role="external_validation",
            provenance={
                "independence_basis": "held_out_cohort",
                "validation_target_sha256": "a" * 64,
                "validation_evidence_sha256": "a" * 64,
                "review_status": "approved",
                "reviewer_id": "reviewer:external-01",
                "review_receipt_sha256": "c" * 64,
            },
        )


def test_external_validation_qualification_is_rechecked_after_mutation():
    ref = EvidenceRef(
        "EXT-MUTABLE-1",
        "cross_method",
        validation_role="external_validation",
        provenance={
            "independence_basis": "orthogonal_assay",
            "validation_target_sha256": "a" * 64,
            "validation_evidence_sha256": "b" * 64,
            "review_status": "approved",
            "reviewer_id": "reviewer:external-02",
            "review_receipt_sha256": "c" * 64,
        },
    )
    assert ref.qualifies_as_external_validation is True

    ref.provenance["review_status"] = "pending"

    assert ref.qualifies_as_external_validation is False


def test_unknown_references_rejected_and_duplicates_refused():
    ledger = _reference_ledger()
    with pytest.raises(KeyError):
        ledger.add_claim(ClaimRecord("CLAIM-X", "dangling", supported_by=["NOPE-1"]))
    with pytest.raises(ValueError):
        ledger.add_evidence(EvidenceRef("DE-102", "statistical_result", "duplicate evidence id"))
    ledger.add_claim(ClaimRecord("CLAIM-Y", "first", supported_by=["QC-004"]))
    with pytest.raises(ValueError):
        ledger.add_claim(ClaimRecord("CLAIM-Y", "duplicate claim id", supported_by=["QC-004"]))


def test_json_round_trip(tmp_path):
    ledger = _reference_ledger()
    ledger.add_claim(
        ClaimRecord(
            "CLAIM-017",
            "Cluster 3 exhibits interferon-response activation",
            capability_id="scrna.exploratory_clustering",
            supported_by=["DE-102", "GSEA-021"],
            contradicted_by=["SCVI-DE-014"],
            depends_on=["DATASET-SHA256:deadbeef"],
        )
    )
    p = ledger.save(tmp_path / "ledger.json")
    assert p.exists()
    loaded = ClaimLedger.load(p)
    assert loaded.to_dict() == ledger.to_dict()
    assert loaded.claims["CLAIM-017"].evidence_status == "CONFLICTED"


def test_jsonld_projection():
    ledger = _reference_ledger()
    ledger.add_claim(
        ClaimRecord(
            "CLAIM-017",
            "Cluster 3 exhibits interferon-response activation",
            capability_id="scrna.exploratory_clustering",
            supported_by=["DE-102"],
            depends_on=["QC-004"],
            contradicted_by=["SCVI-DE-014"],
        )
    )
    doc = ledger.to_jsonld()
    assert doc["@context"]["prov"] == "http://www.w3.org/ns/prov#"
    nodes = {n["@id"]: n for n in doc["@graph"]}
    claim = nodes["bns:CLAIM-017"]
    assert "prov:Entity" in claim["@type"]
    assert claim["prov:wasDerivedFrom"] == ["bns:DE-102", "bns:QC-004"]
    assert claim["prov:wasGeneratedBy"] == "bns:capability/scrna.exploratory_clustering"
    assert claim["bns:contradictedBy"] == ["bns:SCVI-DE-014"]
    # Must be valid JSON (no graph store needed to consume)
    json.dumps(doc)
