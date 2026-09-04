"""Cross-entry negative controls: declarations and forged summaries cannot promote claims."""

from copy import deepcopy

import pytest

from bionexus.abi import enforce_evidence_ceiling, enforce_statistical_warrant
from bionexus.annotation_evidence import AnnotationEvidence, assess_annotation_evidence, assess_annotation_metadata
from bionexus.clustering_stability import assess_clustering_stability
from bionexus.intent_router import route_scientific_intent


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"annotation_evidence_available": True, "negative_markers_tested": False}, "TENTATIVE"),
        ({}, "ABSTAIN"),
        ({"annotation_evidence_available": "true"}, "ABSTAIN"),
        ({"annotation_evidence": {"reference_mapping_score": 0.99, "marker_consistency": 0.99}}, "TENTATIVE"),
        ({"annotation_evidence": {"reference_mapping_score": 0.99, "open_set_detected": True}}, "ABSTAIN"),
        ({"annotation_evidence": {"reference_mapping_score": 0.99, "protein_concordant": False}}, "CONFLICTED"),
        ({"negative_markers_tested": False, "annotation_evidence": {"negative_marker_violation": 0.01}}, "ABSTAIN"),
        ({"annotation_evidence_available": True, "annotation_assessment": {"verdict": "ROBUST"}}, "TENTATIVE"),
    ],
)
def test_annotation_entrypoints_agree(metadata, expected):
    assessment = assess_annotation_metadata(metadata)
    assert assessment.warrant_ceiling == expected
    assert (
        enforce_evidence_ceiling("scrna.annotation_evidence", "ROBUST", True, annotation_metadata=metadata) == expected
    )
    assert (
        enforce_statistical_warrant("scrna.annotation_evidence", "SUPPORTED", annotation_metadata=metadata) == expected
    )
    decision = route_scientific_intent("Assess annotation evidence for candidate labels", data_metadata=metadata)
    card = decision.evidence_card_template
    assert card.details["annotation_assessment"] == assessment.to_dict()
    assert card.evidence_ceiling == expected
    assert card.details["warrant_assessment"]["evidence_ceiling"] == expected
    assert card.details["evidence_assessment"]["evidence_maturity"] == expected
    if expected == "TENTATIVE":
        assert any("negative" in gap for gap in decision.remedies)
        assert card.blocked_claims


def test_direct_annotation_sources_do_not_invent_scores():
    assessment = assess_annotation_evidence("candidate", AnnotationEvidence(sources_declared=True))
    assert assessment.verdict == "TENTATIVE"
    assert assessment.calibration["metric_assessments"] == {}
    assert assessment.evidence["reference_mapping_score"] is None


def test_annotation_refusal_cannot_be_overridden():
    decision = route_scientific_intent(
        "Assess annotation evidence",
        data_metadata={"annotation_evidence_available": False, "claimed_maturity": "ROBUST"},
        research_purpose="screening",
        lab_policy="shadow_audit",
        override_justification="explore",
    )
    assert decision.status.value == "ABSTAIN"
    assert decision.evidence_card_template.details["clamped_claim"] == "ABSTAIN"


def partitions():
    return {
        "dataset_sha256": "a" * 64,
        "declared_min_ari": 0.8,
        "runs": [
            {
                "run_id": "a",
                "perturbation": "resolution=0.4",
                "cell_ids": ["a", "b", "c", "d", "e", "f"],
                "labels": ["0", "0", "0", "1", "1", "1"],
            },
            {
                "run_id": "b",
                "perturbation": "resolution=0.8",
                "cell_ids": ["f", "e", "d", "c", "b", "a"],
                "labels": ["y", "y", "y", "x", "x", "x"],
            },
        ],
    }


def test_stability_aligns_ids_and_is_label_permutation_invariant():
    result = assess_clustering_stability(partitions(), dataset_sha256="a" * 64)
    assert result["criterion_met"] is True
    assert result["min_ari"] == 1
    assert result["biological_identity"] == "NOT_ASSESSED"
    assert result["independent_validation"] == "NOT_ESTABLISHED"


def test_stability_recomputes_instead_of_trusting_summary():
    packet = partitions()
    packet["criterion_met"] = True
    packet["mean_ari"] = 1.0
    packet["runs"][1]["labels"] = ["x", "y", "x", "y", "x", "y"]
    result = assess_clustering_stability(packet, dataset_sha256="a" * 64)
    assert result["criterion_met"] is False
    assert result["status"] == "BELOW_DECLARED_CRITERION"


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_cell",
        "missing_label",
        "one_cluster",
        "all_singletons",
        "no_overlap",
        "duplicate_run",
        "same_perturbation",
        "nan_threshold",
        "wrong_dataset",
    ],
)
def test_invalid_stability_cannot_grant_support(change):
    packet = deepcopy(partitions())
    run = packet["runs"][1]
    if change == "duplicate_cell":
        run["cell_ids"][0] = run["cell_ids"][1]
    elif change == "missing_label":
        run["labels"].pop()
    elif change == "one_cluster":
        run["labels"] = ["x"] * 6
    elif change == "all_singletons":
        run["labels"] = list("123456")
    elif change == "no_overlap":
        run["cell_ids"] = list("123456")
    elif change == "duplicate_run":
        run["run_id"] = "a"
    elif change == "same_perturbation":
        run["perturbation"] = packet["runs"][0]["perturbation"]
    elif change == "nan_threshold":
        packet["declared_min_ari"] = float("nan")
    else:
        packet["dataset_sha256"] = "b" * 64
    result = assess_clustering_stability(packet, dataset_sha256="a" * 64)
    assert result["status"] == "INVALID"
    assert not result["criterion_met"]


def test_no_implicit_stability_threshold():
    packet = partitions()
    del packet["declared_min_ari"]
    result = assess_clustering_stability(packet, dataset_sha256="a" * 64)
    assert result["status"] == "MEASURED_NO_CRITERION"
    assert not result["criterion_met"]


@pytest.mark.parametrize("n_cells", [30, 30000])
def test_stability_advisory_is_evidence_based_not_cell_cutoff(n_cells, canonical_backends_available):
    result = route_scientific_intent(
        "Cluster cells and report stable populations", data_metadata={"n_cells": n_cells, "stability_verified": True}
    )
    assert result.status.value == "DEGRADED_ADVISORY"
    assert result.evidence_card_template.evidence_ceiling == "FRAGILE"
    assert result.evidence_card_template.details["clustering_stability"]["status"] == "NOT_ASSESSED"


def test_small_exploratory_clustering_does_not_get_arbitrary_refusal(canonical_backends_available):
    result = route_scientific_intent("Cluster 30 cells for exploration", data_metadata={"n_cells": 30})
    assert result.status.value == "PERMITTED"


def test_stability_advisory_does_not_bypass_backend_refusal(monkeypatch):
    from bionexus.backends import BackendStatus

    monkeypatch.setattr(
        "bionexus.capabilities.probe", lambda name: BackendStatus(name, False, name, "goldchain", "absent")
    )
    result = route_scientific_intent("Cluster 30 cells and report stable populations", data_metadata={"n_cells": 30})
    assert result.status.value == "ABSTAIN"
