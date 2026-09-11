"""No synthetic expert identity or local hash confers scientific approval."""
from copy import deepcopy

import pytest

from bionexus.de_audit import audit_differential_expression
from bionexus.de_pilot import demo_inputs, write_bundle
from bionexus.rule_calibration import ChallengeNetwork, ChallengeStatus, ChallengeType
from bionexus.rule_impact import assess_rule_change


def challenge(tmp_path):
    registry = tmp_path / "registry.json"
    ChallengeNetwork().save(registry)
    net = ChallengeNetwork(registry, verified_attestation_ids={"t1", "t2", "t3", "t4"})
    item = net.submit_challenge("missing_replicates", "test", ChallengeType.PARAMETER_DRIFT,
                                "test only", "test counterexample")
    return net, item


def test_vote_revision_retains_dissent_and_drops_stale_authentication(tmp_path):
    net, item = challenge(tmp_path)
    for index in range(1, 4):
        net.adjudicate_challenge(item.challenge_id, f"reviewer{index}", "ACCEPT_AMENDMENT", "test", f"t{index}")
    assert item.status == ChallengeStatus.ACCEPTED_AMENDMENT
    net.adjudicate_challenge(item.challenge_id, "reviewer1", "REJECT_CHALLENGE", "new evidence")
    assert item.status == ChallengeStatus.UNDER_REVIEW
    assert "reviewer1" not in item.reviewer_attestation_ids
    assert len(item.review_history) == 4
    assert item.review_history[-1]["previous_vote"] == "ACCEPT_AMENDMENT"
    assert item.review_history[-1]["note"] == "new evidence"
    net.adjudicate_challenge(item.challenge_id, "reviewer1", "REJECT_CHALLENGE", "bound new evidence", "t4")
    assert item.status == ChallengeStatus.UNDER_REVIEW
    assert "disagreement" in item.resolution_notes
    net.save()
    restored = ChallengeNetwork(net.registry_file)
    assert restored.challenges[item.challenge_id].review_history == item.review_history


def test_invalid_and_reused_attestation_votes_do_not_mutate(tmp_path):
    net, item = challenge(tmp_path)
    net.adjudicate_challenge(item.challenge_id, "reviewer1", "ACCEPT_AMENDMENT", "test", "t1")
    before = deepcopy(item.to_dict())
    for reviewer, vote, attestation in [("reviewer1", "BAD", None),
                                        ("reviewer2", "ACCEPT_AMENDMENT", "t1"),
                                        ("reviewer1", "REJECT_CHALLENGE", "t1")]:
        with pytest.raises(ValueError):
            net.adjudicate_challenge(item.challenge_id, reviewer, vote, "test", attestation)
        assert item.to_dict() == before


def test_scope_requires_all_declared_dimensions():
    net = ChallengeNetwork()
    args = dict(platform="10x_chromium_v3", sample_count=4, design="unpaired", feature_count=1000, tissue="blood")
    assert net.is_applicable_to_regime("missing_replicates", **args)[0]
    for override in ({"platform": "10x"}, {"platform": None}, {"feature_count": None},
                     {"feature_count": 3}, {"tissue": None}, {"tissue": "unsupported"}):
        assert not net.is_applicable_to_regime("missing_replicates", **{**args, **override})[0]
    net.rules["missing_replicates"].applicable_regimes = []
    assert not net.is_applicable_to_regime("missing_replicates", **args)[0]


def test_impact_keeps_old_bytes_and_unknown_rule_application(tmp_path):
    result = audit_differential_expression(**demo_inputs())
    bundle = write_bundle(result, tmp_path / "bundle", inputs={}, claim=None, synthetic=True)
    old_bytes = {p.name: p.read_bytes() for p in bundle.iterdir()}
    rid = result.to_dict()["findings"][0]["rule_id"]
    before = {"rules": {"canonical": {"aliases": [rid], "applicable_regimes": []}}}
    after = deepcopy(before)
    after["rules"]["canonical"]["note"] = "test revision"
    report = assess_rule_change(before, after, [bundle])
    assert report["cases"][0]["impact"] == "REASSESS_REQUIRED"
    assert report["cases"][0]["human_decision"] == "PENDING"
    assert report["scientific_authorization"] == "NONE"
    assert old_bytes == {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert assess_rule_change(before, before, [bundle])["cases"][0]["impact"] == "NO_REGISTRY_CHANGE"
    report = assess_rule_change({"rules": {}}, {"rules": {"new-rule": {}}}, [bundle])
    assert report["cases"][0]["impact"] == "RULE_APPLICATION_UNRECORDED"
    (bundle / "REVIEW.md").write_text("tampered", encoding="utf-8")
    assert assess_rule_change(before, after, [bundle])["cases"][0]["impact"] == "INTEGRITY_BLOCKED"


def test_rule_removal_retains_old_scope():
    old = {"rules": {"old-rule": {"applicable_regimes": [{"regime_id": "old-context"}]}}}
    report = assess_rule_change(old, {"rules": {}}, [])
    assert report["changes"][0]["change"] == "REMOVED"
    assert report["changes"][0]["before_scope"] == [{"regime_id": "old-context"}]
