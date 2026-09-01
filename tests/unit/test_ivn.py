"""Unit tests for BioNexus Independent Validation Network (IVN / BNS-023) and Public Ledger.

Tests:
1. Loading and validating the canonical registry.
2. Honest fail-closed evaluation of capability quotas.
3. Non-author roster verification invariants.
4. Artifact integrity and drift detection.
5. Standalone public ledger HTML generation and structure.
6. Merkle root determinism.
7. CLI commands (status, verify, build-ledger).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from bionexus.ivn import (
    FLAGSHIP_CAPABILITIES,
    IVNRegistry,
    NonAuthorReview,
    default_registry_path,
    evaluate_network,
    generate_merkle_root,
    load_registry,
    render_public_ledger_html,
    verify_registry_integrity,
)


@pytest.fixture
def canonical_registry() -> IVNRegistry:
    """Load the canonical packaged IVN registry."""
    path = default_registry_path(_REPO_ROOT)
    assert path.is_file(), f"Canonical registry not found at {path}"
    return load_registry(path)


class TestIVNRegistryBasics:
    """Core schema and loading verification."""

    def test_canonical_registry_loads_cleanly(self, canonical_registry: IVNRegistry):
        assert canonical_registry.schema_version == "bionexus.ivn.registry.v1"
        assert len(canonical_registry.datasets) >= 6
        assert len(canonical_registry.author_roster) >= 1
        assert isinstance(canonical_registry.lab_studies, tuple)
        assert isinstance(canonical_registry.reviews, tuple)
        assert isinstance(canonical_registry.calibration_freezes, tuple)

    def test_canonical_registry_has_no_hash_drift(self, canonical_registry: IVNRegistry):
        report = verify_registry_integrity(canonical_registry, repo_root=_REPO_ROOT)
        assert report["integrity"] == "PASS", f"Integrity drift detected: {report['drift']}"
        assert report["checked_entities"] >= 6
        assert len(report["drift"]) == 0

    def test_merkle_root_is_deterministic(self, canonical_registry: IVNRegistry):
        root1 = generate_merkle_root(canonical_registry)
        root2 = generate_merkle_root(canonical_registry)
        assert len(root1) == 64
        assert root1 == root2


class TestIVNNetworkAssessment:
    """Fail-closed quota evaluation tests."""

    def test_network_evaluation_honest_post_rc3_state(self, canonical_registry: IVNRegistry):
        network = evaluate_network(canonical_registry, repo_root=_REPO_ROOT)
        assert network["network_status"] == "INCOMPLETE"
        assert set(network["capabilities"].keys()) == set(FLAGSHIP_CAPABILITIES)

        # 1. scrna.pseudobulk_de: 3 datasets (negative results), 0 labs, 0 reviews
        pb = network["capabilities"]["scrna.pseudobulk_de"]
        assert len(pb["counted_datasets"]) == 3
        assert len(pb["counted_lab_studies"]) == 0
        assert len(pb["counted_reviews"]) == 0
        assert pb["complete"] is False

        # 2. scrna.annotation_evidence: 2 datasets counted, gaps in cross-disease / tissue
        ann = network["capabilities"]["scrna.annotation_evidence"]
        assert len(ann["counted_datasets"]) == 2
        assert ann["complete"] is False
        assert any("cross_disease" in g for g in ann["blocking_gaps"])

        # 3. spatial.inference_validity: 0 counted (tiny kidney has no independent truth yet)
        sp = network["capabilities"]["spatial.inference_validity"]
        assert len(sp["counted_datasets"]) == 0
        assert sp["complete"] is False
        assert any("independent_truth" in g for g in sp["blocking_gaps"])

    def test_all_four_open_blockers_remain_open(self, canonical_registry: IVNRegistry):
        network = evaluate_network(canonical_registry, repo_root=_REPO_ROOT)
        oq = network["open_questions"]
        assert oq["all_still_open_as_assessed"] is True
        for b_id, b_data in oq["blockers"].items():
            assert b_data["still_open"] is True, f"Blocker {b_id} unexpectedly resolved"

    def test_author_roster_rejection(self, canonical_registry: IVNRegistry):
        # Pick an author name from roster
        author_name = canonical_registry.author_roster[0]["name"]
        review = NonAuthorReview(
            review_id="BN-REV-TEST-001",
            capability_id="scrna.pseudobulk_de",
            subject_id="BN-PB-IV-002",
            reviewer_id="rev-01",
            reviewer_name=author_name,
            affiliation="Test Affil",
            verdict="ENDORSED",
            blinded=True,
            declared_non_author=True,
        )
        assert canonical_registry.reviewer_is_author(review) is True

    def test_empty_author_roster_fails_closed(self):
        empty_reg = IVNRegistry(author_roster=())
        review = NonAuthorReview(
            review_id="BN-REV-TEST-002",
            capability_id="scrna.pseudobulk_de",
            subject_id="BN-PB-IV-002",
            reviewer_id="ext-reviewer",
            reviewer_name="Dr. External Scientist",
            affiliation="External Institute",
            verdict="ENDORSED",
            blinded=True,
            declared_non_author=True,
        )
        # Empty roster cannot prove non-authorship -> fail closed
        assert empty_reg.reviewer_is_author(review) is True


class TestPublicLedgerHTMLGeneration:
    """Public ledger page generation tests."""

    def test_render_public_ledger_html_structure(self, canonical_registry: IVNRegistry):
        html_out = render_public_ledger_html(canonical_registry, repo_root=_REPO_ROOT)
        assert "<!DOCTYPE html>" in html_out
        assert "BioNexus IVN" in html_out
        assert "The Only Moat That" in html_out
        assert "Automatically Deepens" in html_out

        # Must display Merkle root
        merkle = generate_merkle_root(canonical_registry)
        assert merkle in html_out

        # Must display all flagship capabilities
        for cap in FLAGSHIP_CAPABILITIES:
            assert cap in html_out

        # Must display registered dataset IDs
        for ds in canonical_registry.datasets:
            assert ds.dataset_id in html_out

        # Must contain recruitment tracks and RFV section
        assert "Request for Validation (RFV)" in html_out
        assert "Track 01" in html_out
        assert "Track 02" in html_out
        assert "Track 03" in html_out
        assert "Track 04" in html_out

        # Must contain interactive verifier and search
        assert "Live In-Browser Ledger Verifier" in html_out
        assert "verifyHashOnline" in html_out
        assert "filterLedger" in html_out

    def test_cli_build_ledger_execution(self, tmp_path: Path):
        from bionexus.cli import main as cli_main

        out_html = tmp_path / "ledger.html"
        ret = cli_main(["ivn", "build-ledger", "-o", str(out_html), "--repo-root", str(_REPO_ROOT)])
        assert ret == 0
        assert out_html.is_file()
        content = out_html.read_text(encoding="utf-8")
        assert len(content) > 10000
        assert "BioNexus IVN" in content
