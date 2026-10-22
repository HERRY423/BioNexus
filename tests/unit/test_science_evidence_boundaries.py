"""Adversarial boundaries: calculations must not manufacture scientific authority."""
import json
from dataclasses import replace

import numpy as np
import pytest

from bionexus.annotation_calibration_audit import (
    compute_calibration_metrics,
    compute_wilson_lower_bound,
    evaluate_facs_physical_ground_truth_benchmark,
    evaluate_selective_abstention_curve,
)
from bionexus.cross_lab_protocol import build_cross_host_dossier, capture_host_fingerprint
from bionexus.de_scientific_reliability import (
    audit_multi_cohort_de_replication,
    compute_decision_curve_analysis,
    evaluate_de_hard_truth_calibration,
    evaluate_empirical_null_uniformity,
)
from bionexus.rules.definitions import get_canonical_rule_objects
from bionexus.rules.dual_track import RuleEvaluationTruthPair, compute_empirical_metrics
from bionexus.rules.holdout_evaluator import RuleHoldoutEvaluator, evaluate_single_case
from bionexus.rules.ladder_comparison import run_ladder_vs_static_comparison
from bionexus.scientific_review_dossier import generate_certified_scientific_review
from bionexus.spatial_pathology_benchmark import (
    evaluate_pathology_domain_concordance,
    run_spatial_pathology_validation_suite,
)


def de_metrics(n=100, false_calls=6):
    names = [f"g{i}" for i in range(n)]
    return evaluate_de_hard_truth_calibration(
        gene_names=names, padj_values=[.01] * n, log2fc_values=[1.] * n,
        ground_truth_positives=set(names[:n-false_calls]),
        ground_truth_negatives=set(names[n-false_calls:]), nominal_fdr=.05,
    )


def test_exact_fdp_threshold_cannot_be_relaxed():
    result = de_metrics()
    assert result.empirical_fdr == .06
    assert result.observed_fdp_within_nominal is False
    assert result.fdr_controlled is None
    assert result.to_dict()["fdr_control_status"] == "NOT_ESTABLISHED"


def test_empty_de_denominators_are_not_perfect_performance():
    result = de_metrics(0, 0)
    assert result.empirical_fdr is None
    assert result.precision is None and result.specificity is None and result.sensitivity is None
    dca = compute_decision_curve_analysis(audited_metrics=result, naive_metrics=result)
    assert dca.estimation_status == "NOT_ESTIMABLE"
    assert dca.mean_net_benefit_gain is None and not dca.audited_strictly_superior
    json.dumps(dca.to_dict(), allow_nan=False)


def test_ties_and_empty_decision_curve_never_establish_superiority():
    metrics = de_metrics()
    tie = compute_decision_curve_analysis(audited_metrics=metrics, naive_metrics=metrics)
    assert tie.mean_net_benefit_gain == 0
    assert not tie.audited_strictly_superior
    empty = compute_decision_curve_analysis(audited_metrics=metrics, naive_metrics=metrics, threshold_probabilities=[])
    assert empty.estimation_status == "NOT_ESTIMABLE"
    assert not empty.audited_strictly_superior
    with pytest.raises(ValueError, match="same reference population"):
        compute_decision_curve_analysis(audited_metrics=metrics, naive_metrics=de_metrics(99))
    with pytest.raises(ValueError, match="inconsistent"):
        compute_decision_curve_analysis(audited_metrics=replace(metrics, tp=500), naive_metrics=metrics)


@pytest.mark.parametrize("bad", [float("nan"), -1., 2., float("inf")])
def test_invalid_pvalues_are_not_silently_filtered(bad):
    with pytest.raises(ValueError):
        evaluate_empirical_null_uniformity(null_p_values=[.5, bad])
    with pytest.raises(ValueError):
        evaluate_de_hard_truth_calibration(gene_names=["x"], padj_values=[bad], log2fc_values=[1.],
                                         ground_truth_positives={"x"}, ground_truth_negatives=set())


def test_null_raw_rejection_rate_is_not_fwer():
    result = evaluate_empirical_null_uniformity(null_p_values=[.001, .9, .8, .7])
    assert result.per_test_rejection_rate == .25
    assert result.empirical_fwer is None
    assert result.null_uniform is None
    assert result.fwer_status == "NOT_ESTIMABLE"


def test_duplicate_and_conflicting_gene_labels_rejected():
    with pytest.raises(ValueError, match="unique"):
        evaluate_de_hard_truth_calibration(gene_names=["x", "x"], padj_values=[.01, .01],
            log2fc_values=[1., 1.], ground_truth_positives={"x"}, ground_truth_negatives=set())
    with pytest.raises(ValueError, match="disjoint"):
        evaluate_de_hard_truth_calibration(gene_names=["x"], padj_values=[.01], log2fc_values=[1.],
                                         ground_truth_positives={"x"}, ground_truth_negatives={"x"})


def test_no_significant_cohort_genes_does_not_change_endpoint():
    result = audit_multi_cohort_de_replication(cohort_a_name="a", cohort_b_name="b",
        genes_a=["x", "y"], genes_b=["x", "y"], log2fc_a=[1., 2.], log2fc_b=[1., 2.],
        padj_a=[.9, .9], padj_b=[.9, .9], min_shared_genes=2)
    assert result.n_shared_genes == 0
    assert result.estimation_status == "NOT_ESTIMABLE"
    assert result.replication_pass is False


def test_missing_reference_labels_and_predictions_are_not_accuracy_one():
    curve = evaluate_selective_abstention_curve(warrant_verdicts=[], predictions=[], ground_truth_labels=[])
    assert all(p.coverage_fraction is None and p.accuracy_on_accepted is None and p.abstention_effective is None for p in curve)
    curve = evaluate_selective_abstention_curve(warrant_verdicts=["ABSTAIN"], predictions=["T"], ground_truth_labels=["T"])
    assert curve[-1].n_accepted == 0 and curve[-1].accuracy_on_accepted is None
    with pytest.raises(ValueError):
        compute_wilson_lower_bound(2, 1)
    assert compute_wilson_lower_bound(9, 10, .99) < compute_wilson_lower_bound(9, 10, .90)


@pytest.mark.parametrize("probs,labels", [
    ([[.8, .8]], [0]), ([[float('nan'), .5]], [0]), ([[-.2, 1.2]], [0]),
    ([[.5, .5]], [-1]), ([[.5, .5]], [2]), ([[.5, .5]], []),
])
def test_annotation_rejects_invalid_probabilities_and_reference_indices(probs, labels):
    with pytest.raises(ValueError):
        compute_calibration_metrics(probabilities=np.array(probs), ground_truth_indices=np.array(labels))


def test_hash_match_is_integrity_only_even_with_perfect_predictions():
    import hashlib
    labels = ["A", "B"] * 200
    counts = np.tile(np.array([[10., 0.], [0., 10.]]), (200, 1))
    result = evaluate_facs_physical_ground_truth_benchmark(dataset_name="fixture",
        raw_counts_matrix=counts, gene_names=["a", "b"], physical_ground_truth=labels,
        marker_modules={"A": ["a"], "B": ["b"]},
        blinded_key_hash=hashlib.sha256(",".join(labels).encode()).hexdigest())
    assert result.overall_accuracy == 1.
    assert result.reference_hash_matches
    assert not result.blinding_verified
    assert not result.positive_candidate_promoted
    assert result.calibration.is_well_calibrated is None


def test_predicted_only_spatial_domains_are_penalized_not_omitted():
    domains = evaluate_pathology_domain_concordance(inferred_domain_labels=["A", "HALLUCINATED"], pathologist_ground_truth=["A", "A"])
    extra = next(d for d in domains if d.domain_name == "HALLUCINATED")
    assert extra.dice_coefficient == 0 and extra.n_ground_truth_cells == 0
    assert extra.boundary_precision is None  # Membership overlap is not boundary geometry.
    assert not extra.domain_validated


def test_perfect_spatial_labels_without_controls_never_promote():
    result = run_spatial_pathology_validation_suite(cohort_name="fixture", tissue_type="unknown",
        coords=np.zeros((2, 2)), expression_matrix=np.ones((2, 1)), gene_names=["x"],
        inferred_domains=["A", "B"], pathologist_ground_truth=["A", "B"])
    assert result.mean_dice_coefficient == 1
    assert result.reference_concordance_threshold_met
    assert not result.biological_validity_promoted
    assert all(t.system_verdict == "NOT_EVALUATED" and t.raw_spatial_statistic is None for t in result.discrimination_tests)


def test_empty_spatial_evaluation_has_no_overlap_estimate():
    result = run_spatial_pathology_validation_suite(cohort_name="fixture", tissue_type="unknown",
        coords=np.empty((0, 2)), expression_matrix=np.empty((0, 0)), gene_names=[],
        inferred_domains=[], pathologist_ground_truth=[])
    assert result.mean_dice_coefficient is None
    assert not result.pathology_concordance_pass and not result.biological_validity_promoted


def test_empty_external_evidence_never_creates_authority(tmp_path):
    review = generate_certified_scientific_review(tmp_path)
    assert not list(tmp_path.iterdir())
    assert review.reviewers == [] and review.case_reviews == [] and not review.standard_14_satisfied
    cross = build_cross_host_dossier(repo_root=tmp_path, studies_to_compare=[])
    assert cross.overall_agreement_rate is None and not cross.standard_13_satisfied
    assert capture_host_fingerprint("local", tmp_path).repo_commit_sha == ""


def test_missing_primary_report_is_retained_as_missing(tmp_path):
    missing = tmp_path / "absent.json"
    cross = build_cross_host_dossier(repo_root=tmp_path, studies_to_compare=[("cap", "study", missing)])
    assert len(cross.comparisons) == 1
    assert cross.comparisons[0].primary_checksum == ""
    assert cross.comparisons[0].replication_checksum == ""
    assert cross.comparisons[0].warrants_identical is None and not cross.comparisons[0].verified


def test_single_class_rule_metrics_do_not_invent_denominators_or_kappa():
    pair = RuleEvaluationTruthPair("x", "BFA-001", True, "BLOCKER", None, True, "fixture", "unverified")
    metrics = compute_empirical_metrics([pair])
    assert metrics.false_positive_rate is None
    assert metrics.false_negative_rate == 0.
    assert metrics.cohens_kappa is None
    assert metrics.expected_calibration_error is None
    empty = compute_empirical_metrics([])
    assert empty.expert_concordance is None and empty.false_negative_rate is None
    missing = compute_empirical_metrics([replace(pair, expert_confirmed_flaw=None)])
    assert missing.n_labeled_cases == 0 and missing.expert_concordance is None
    json.dumps(missing.to_dict(), allow_nan=False)


def test_fixture_evaluator_does_not_fabricate_probabilities_or_calibrate_global_rules():
    result = RuleHoldoutEvaluator().run_evaluation()
    assert all(p.rule_confidence is None and p.adjudication_status == "UNVERIFIED_CALLER_LABEL" for p in result.rule_pairs)
    assert result.overall_metrics.expected_calibration_error is None
    assert all(r.empirical_metrics is None for r in get_canonical_rule_objects().values())
    assert result.to_dict()["production_audit_executed"] is False
    comparison = run_ladder_vs_static_comparison().to_dict()
    assert comparison["superiority_established"] is False
    assert comparison["evidence_kind"] == "DEVELOPER_CASE_FIXTURE"


def test_unknown_rule_or_missing_truth_does_not_default_to_verified_pass():
    with pytest.raises(ValueError, match="Unsupported"):
        evaluate_single_case({"case_id": "x", "target_rule_id": "FAKE"})
    pair = evaluate_single_case({"case_id": "x", "target_rule_id": "BFA-001"})
    assert pair.expert_confirmed_flaw is None
    assert pair.rule_confidence is None


def test_de_report_does_not_call_synthetic_comparators(monkeypatch, tmp_path):
    from evals import de_hard_truth_benchmark as benchmark
    source = tmp_path / "de.csv"
    source.write_text("gene,mean,log2FoldChange,se,stat,p,padj\nISG15,5,2,.1,5,.001,.002\nCD3D,5,0,.1,0,.8,.9\n", encoding="utf-8")
    monkeypatch.setattr(benchmark, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(benchmark, "DE_FULL_CSV", source)
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic output must not feed the report")
    monkeypatch.setattr(benchmark, "simulate_naive_pseudoreplication", forbidden)
    monkeypatch.setattr(benchmark, "generate_mock_null_pvalues", forbidden)
    report = benchmark.run_benchmark(write=False)
    assert report["audited_pipeline_performance"]["tp"] == 1
    assert report["naive_pipeline_performance"]["estimation_status"] == "NOT_RUN"
    assert report["scientific_conclusions"]["scientific_net_benefit_positive"] is None
    assert report["dataset"]["n_confirmed_null_genes"] == 0
    assert not (tmp_path / "validation").exists()


def test_spatial_legacy_label_fabricator_is_disabled():
    from evals.spatial_biological_validity import load_spatial_cells_and_pathology_annotations
    with pytest.raises(ValueError, match="unavailable"):
        load_spatial_cells_and_pathology_annotations()


def test_missing_adjusted_pvalue_is_not_counted_as_true_negative(tmp_path):
    from evals.de_hard_truth_benchmark import load_real_de_results
    source = tmp_path / "missing.csv"
    source.write_text("gene,log2FoldChange,padj\nIFIT1,2,.01\nCD3D,0,\nCD19,0,nan\n", encoding="utf-8")
    genes, effects, pvalues = load_real_de_results(source)
    assert genes == ["IFIT1"]
    assert effects == [2.]
    assert pvalues == [.01]
