"""
Unit tests for BioNexus Rule Calibration & Scientific Challenge Network (BNS-018).

Validates:
1. Loading development rule propositions with explicit trust-reset states.
2. Scientific proposition verification and theoretical framework tracking.
3. Empty production calibration and endorsement surfaces.
5. Known counterexample boundary mitigations.
6. Sensitivity analysis and cliff-edge transition risk tracking.
7. Challenge Network lifecycle: submission, peer voting, and consensus adjudication.
8. CLI command handlers: 'rule list', 'rule show', 'rule challenge', 'rule list-challenges'.
"""

import json
import sys
from pathlib import Path

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.cli import main as cli_main
from bionexus.rule_calibration import (
    ChallengeNetwork,
    ChallengeStatus,
    ChallengeType,
)
from bionexus.rule_classification import EpistemicKind


def test_challenge_network_loads_calibrated_rules():
    """Production registry retains propositions but removes unverifiable endorsements."""
    network = ChallengeNetwork()
    assert len(network.rules) >= 8

    # Verify missing_replicates (BN-F001)
    rep_rule = network.get_rule("missing_replicates")
    assert rep_rule is not None
    assert rep_rule.epistemic_kind == EpistemicKind.WARRANT_CONSTRAINT
    assert "pseudoreplication" in rep_rule.aliases

    # Proposition
    assert "Biological replication" in rep_rule.proposition.statement
    assert "Var_pop" in rep_rule.proposition.formal_predicate
    assert len(rep_rule.proposition.underlying_assumptions) >= 2

    # Regimes
    assert len(rep_rule.applicable_regimes) >= 2
    reg_ids = [r.regime_id for r in rep_rule.applicable_regimes]
    assert "droplet_scrna_primary_tissue" in reg_ids

    assert network.registry_metadata["registry_status"] == "DEVELOPMENT_UNVERIFIED"
    assert network.registry_metadata["external_validation_claimed"] is False
    assert rep_rule.platform_calibrations == []
    assert rep_rule.dataset_calibrations == []
    assert rep_rule.sensitivity_analysis == []

    # Counterexamples
    assert len(rep_rule.known_counterexamples) >= 1
    ce = rep_rule.known_counterexamples[0]
    assert ce.counterexample_id == "isogenic_cloned_cell_line"
    assert "SAMPLE_SPECIFIC" in ce.mitigation_strategy

    assert rep_rule.reviewers == []
    assert rep_rule.metadata["evidence_status"] == "UNVERIFIED_DEVELOPMENT"
    assert rep_rule.metadata["review_status"] == "NOT_ASSESSED"


def test_regime_applicability_evaluation():
    """Verify checking whether an experimental setup matches declared regimes."""
    network = ChallengeNetwork()

    # Valid regime setup: 10x Chromium with 4 samples
    is_app, msg = network.is_applicable_to_regime(
        "missing_replicates",
        platform="10x_chromium_v3",
        sample_count=4,
        design="unpaired",
    )
    assert is_app is True
    assert "droplet_scrna_primary_tissue" in msg

    # Invalid regime setup: Insufficient samples for population inference
    is_app_low, msg_low = network.is_applicable_to_regime(
        "missing_replicates",
        platform="10x_chromium_v3",
        sample_count=1,
        design="unpaired",
    )
    assert is_app_low is False
    assert "does not match declared applicable regimes" in msg_low


def test_platform_calibration_resolution():
    """Production lookup refuses removed, unverifiable platform thresholds."""
    network = ChallengeNetwork()

    visium_hd = network.get_platform_calibration("spatial_coords_present", "visium_hd")
    assert visium_hd is None

    visium_55 = network.get_platform_calibration("spatial_coords_present", "visium_55um")
    assert visium_55 is None


def test_challenge_network_submission_and_consensus_lifecycle(tmp_path):
    """Verify full challenge lifecycle: submit -> vote -> consensus adjudication."""
    temp_reg = tmp_path / "test_registry.json"
    network = ChallengeNetwork()
    network.save(temp_reg)

    # Initialize fresh network on temp registry
    verified_ids = {"att:test:review-1", "att:test:review-2", "att:test:review-3"}
    test_net = ChallengeNetwork(temp_reg, verified_attestation_ids=verified_ids)

    # 1. Submit a challenge
    challenge = test_net.submit_challenge(
        target_rule_id="missing_replicates",
        challenger_identity="orcid:0000-0004-9999-0000",
        challenge_type=ChallengeType.PARAMETER_DRIFT,
        title="High-depth single-nucleus RNA-seq achieves power with n=2 in homogenous cortex",
        description="Empirical benchmark across 50 snRNA-seq brains shows stable dispersion at n=2.",
        empirical_evidence_refs=["doi:10.1038/s41586-023-00000-x"],
        reproduction_script="import scanpy as sc; print('reproduce')",
    )

    assert challenge.status == ChallengeStatus.PROPOSED
    assert challenge.target_rule_id == "missing_replicates"
    assert challenge.reproduction_script_sha256 != ""

    # 2. Reviewer 1 votes
    s1 = test_net.adjudicate_challenge(
        challenge_id=challenge.challenge_id,
        reviewer_id="orcid:0000-0002-1825-0097",
        vote="ACCEPT_AMENDMENT",
        review_note="Data looks valid for snRNA-seq cortex.",
        review_attestation_id="att:test:review-1",
    )
    assert s1 == ChallengeStatus.UNDER_REVIEW

    # 3. Reviewer 2 votes
    s2 = test_net.adjudicate_challenge(
        challenge_id=challenge.challenge_id,
        reviewer_id="orcid:0000-0001-8356-4210",
        vote="ACCEPT_AMENDMENT",
        review_note="Agreed, cortex has lower between-donor dispersion.",
        review_attestation_id="att:test:review-2",
    )
    assert s2 == ChallengeStatus.UNDER_REVIEW

    # 4. Reviewer 3 votes -> Consensus threshold reached!
    s3 = test_net.adjudicate_challenge(
        challenge_id=challenge.challenge_id,
        reviewer_id="orcid:0000-0003-4567-8901",
        vote="ACCEPT_AMENDMENT",
        review_note="Ratified for snRNA-seq sub-regime.",
        review_attestation_id="att:test:review-3",
    )
    assert s3 == ChallengeStatus.ACCEPTED_AMENDMENT
    assert "Challenge accepted by peer consensus" in test_net.challenges[challenge.challenge_id].resolution_notes


def test_unverified_challenge_votes_never_change_consensus(tmp_path):
    temp_reg = tmp_path / "test_registry.json"
    network = ChallengeNetwork()
    network.save(temp_reg)
    test_net = ChallengeNetwork(temp_reg)
    challenge = test_net.submit_challenge(
        target_rule_id="missing_replicates",
        challenger_identity="test-only",
        challenge_type=ChallengeType.PARAMETER_DRIFT,
        title="test challenge",
        description="test-only development fixture",
    )
    for index in range(3):
        status = test_net.adjudicate_challenge(
            challenge.challenge_id,
            reviewer_id=f"reviewer-{index}",
            vote="ACCEPT_AMENDMENT",
            review_note="unverified test vote",
        )
    assert status == ChallengeStatus.UNDER_REVIEW
    assert "excluded from consensus" in challenge.resolution_notes


def test_cli_rule_subcommands(capsys):
    """Verify CLI subcommands for BNS-018: rule list, show, list-challenges."""
    # Test 'rule list'
    rc_list = cli_main(["rule", "list"])
    assert rc_list == 0
    out_list = capsys.readouterr().out
    assert "BioNexus Development Rule Registry" in out_list
    assert "missing_replicates" in out_list
    assert "normalized_matrix_only" in out_list

    # Test 'rule show'
    rc_show = cli_main(["rule", "show", "missing_replicates"])
    assert rc_show == 0
    out_show = capsys.readouterr().out
    assert "BioNexus Rule Proposition: missing_replicates" in out_show
    assert "Scientific Proposition" in out_show
    assert "Evidence Status:      UNVERIFIED_DEVELOPMENT" in out_show
    assert "Verified External Attestations] 0" in out_show

    # Test 'rule show --json'
    rc_json = cli_main(["rule", "show", "missing_replicates", "--json"])
    assert rc_json == 0
    out_json = capsys.readouterr().out
    data = json.loads(out_json)
    assert data["rule_id"] == "missing_replicates"
    assert data["proposition"]["statement"] != ""
    assert data["dataset_calibrations"] == []
    assert data["reviewers"] == []

    # Test 'rule list-challenges'
    rc_chal = cli_main(["rule", "list-challenges"])
    assert rc_chal == 0
    out_chal = capsys.readouterr().out
    assert "Scientific Challenge Network Ledger" in out_chal
