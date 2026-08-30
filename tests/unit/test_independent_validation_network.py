"""Unit tests for the Independent Validation Network (BNS-023).

Covers:
1. Fail-closed quota counting: >= 3 independent datasets x >= 2 external labs
   x >= 1 non-author reviewer per flagship capability.
2. Independence rules: author-associated datasets, unverified frameworks and
   slots, hash drift, and author-roster overlap never count.
3. Annotation cross-disease / cross-tissue / cross-technology coverage.
4. Spatial independent pathology/segmentation truth requirement.
5. Calibration freeze on held-out contexts (fail-closed authorization gate).
6. OPEN_QUESTIONS alignment: the four blockers stay open on the seeded
   registry, and certification output is unchanged while quotas are unmet.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
for _path in (str(_REPO_ROOT), str(_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bionexus import certification  # noqa: E402
from bionexus import ivn as ivn_mod
from bionexus.calibration_freeze import (  # noqa: E402
    CalibrationFreezeError,
    CalibrationFreezeRecord,
    FreezeDecision,
    HeldOutContext,
    authorize_context,
    freeze_profile,
    profile_from_payload,
    verify_freeze,
)
from bionexus.empirical_warrant import (  # noqa: E402
    CalibrationProfile,
    CalibrationReviewStatus,
    ComparisonDirection,
    EmpiricalEvidence,
    ReviewerApproval,
)
from bionexus.ivn import (  # noqa: E402
    CapabilityRequirements,
    DatasetTruthProvenance,
    ExternalLabStudy,
    IndependenceDeclaration,
    IVNDataset,
    IVNError,
    IVNRegistry,
    NonAuthorReview,
    default_registry_path,
    evaluate_capability,
    evaluate_network,
    load_registry,
    verify_registry_integrity,
)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(tmp_path: Path, name: str, content: str = "artifact") -> tuple:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path, _sha(path)


def _dataset(tmp_path: Path, **overrides) -> IVNDataset:
    pre_path, pre_sha = _write(tmp_path, "studies/d1/PREREGISTRATION.json")
    rep_path, rep_sha = _write(tmp_path, "studies/d1/REPORT.json")
    fields = dict(
        dataset_id="d1",
        capability_id="scrna.pseudobulk_de",
        title="Independent donor cohort",
        source_uri="GEO",
        disease="systemic_lupus_erythematosus",
        tissue="PBMC_blood",
        technology="10x_chromium_3prime_droplet",
        author_associated=False,
        donor_aware=True,
        preregistration_path=str(pre_path.relative_to(tmp_path)),
        preregistration_sha256=pre_sha,
        report_path=str(rep_path.relative_to(tmp_path)),
        report_sha256=rep_sha,
        status="VERIFIED",
    )
    fields.update(overrides)
    return IVNDataset(**fields)


def _lab(tmp_path: Path, **overrides) -> ExternalLabStudy:
    cap_path, cap_sha = _write(tmp_path, "labs/L1/REPORT.json")
    fields = dict(
        study_id="L1",
        lab_id="lab-1",
        lab_name="External Lab One",
        institution="University of Somewhere",
        country="US",
        capability_id="scrna.pseudobulk_de",
        dataset_id="d1",
        host="codex",
        independence=IndependenceDeclaration(True, "PI One"),
        capsule_path=str(cap_path.relative_to(tmp_path)),
        capsule_sha256=cap_sha,
        status="VERIFIED",
    )
    fields.update(overrides)
    return ExternalLabStudy(**fields)


def _review(tmp_path: Path, **overrides) -> NonAuthorReview:
    rev_path, rev_sha = _write(tmp_path, "reviews/R1/REVIEW.json")
    fields = dict(
        review_id="R1",
        capability_id="scrna.pseudobulk_de",
        subject_id="d1",
        reviewer_id="0000-0001-2222-3333",
        reviewer_name="External Reviewer",
        affiliation="Institute Elsewhere",
        verdict="ENDORSED_WITH_LIMITS",
        blinded=True,
        declared_non_author=True,
        attestation_id="att-1",
        review_path=str(rev_path.relative_to(tmp_path)),
        review_sha256=rev_sha,
        status="VERIFIED",
    )
    fields.update(overrides)
    return NonAuthorReview(**fields)


def _registry(tmp_path: Path, datasets=(), labs=(), reviews=(), roster=(("author", ("author@bio.example",)),)):
    return IVNRegistry(
        author_roster=tuple({"name": name, "identifiers": list(ids)} for name, ids in roster),
        datasets=tuple(datasets),
        lab_studies=tuple(labs),
        reviews=tuple(reviews),
    )


def _counts(assessment):
    return (
        len(assessment.counted_datasets),
        len(assessment.counted_lab_studies),
        len(assessment.counted_reviews),
    )


def _check(assessment, requirement):
    return {check.requirement: check for check in assessment.checks}[requirement]


# ------------------------------------------------------------------------------
# 1. Alignment with the certification & verifier flagship tuples
# ------------------------------------------------------------------------------


def test_flagship_tuple_alignment_across_modules():
    from bionexus.validation_verifier import FLAGSHIP_CAPABILITIES as VERIFIER_TUPLE

    assert ivn_mod.FLAGSHIP_CAPABILITIES == certification.FLAGSHIP_CAPABILITIES
    assert ivn_mod.FLAGSHIP_CAPABILITIES == VERIFIER_TUPLE


# ------------------------------------------------------------------------------
# 2. Seeded registry honesty (post-rc3 state)
# ------------------------------------------------------------------------------


def test_seed_registry_network_is_incomplete_and_honest():
    registry = load_registry(default_registry_path(_REPO_ROOT))
    network = evaluate_network(registry, repo_root=_REPO_ROOT)
    assert network["network_status"] == "INCOMPLETE"

    pseudobulk = network["capabilities"]["scrna.pseudobulk_de"]
    assert len(pseudobulk["counted_datasets"]) == 3  # frozen negative results count as executed evidence
    assert pseudobulk["counted_lab_studies"] == []
    assert pseudobulk["counted_reviews"] == []

    annotation = network["capabilities"]["scrna.annotation_evidence"]
    assert len(annotation["counted_datasets"]) == 2
    by_req = {check["requirement"]: check for check in annotation["checks"]}
    assert by_req["cross_disease"]["satisfied"] is False
    assert by_req["cross_tissue"]["satisfied"] is False
    assert by_req["cross_technology"]["satisfied"] is True

    spatial = network["capabilities"]["spatial.inference_validity"]
    assert spatial["counted_datasets"] == []
    assert any("truth" in item["reason"] for item in spatial["excluded_datasets"])


def test_seed_open_questions_blockers_all_still_open():
    registry = load_registry(default_registry_path(_REPO_ROOT))
    network = evaluate_network(registry, repo_root=_REPO_ROOT)
    blockers = network["open_questions"]["blockers"]
    assert set(blockers) == set(ivn_mod.OPEN_QUESTION_BLOCKERS)
    assert all(blocker["still_open"] for blocker in blockers.values())
    assert network["open_questions"]["all_still_open_as_assessed"] is True


def test_certification_output_unchanged_while_ivn_quotas_unmet():
    record = certification.certify_capability("scrna.pseudobulk_de")
    assert record.tier.value == "VALIDATED"
    assert record.criteria["cross_host_test"].satisfied is False
    assert record.criteria["external_reviewer"].satisfied is False


# ------------------------------------------------------------------------------
# 3. Fail-closed dataset counting
# ------------------------------------------------------------------------------


def test_empty_registry_satisfies_nothing(tmp_path):
    network = evaluate_network(_registry(tmp_path), repo_root=tmp_path)
    assert network["network_status"] == "INCOMPLETE"
    for assessment in network["capabilities"].values():
        assert assessment["complete"] is False


def test_author_associated_dataset_never_counts(tmp_path):
    assessment = evaluate_capability(
        "scrna.pseudobulk_de",
        _registry(tmp_path, datasets=(_dataset(tmp_path, author_associated=True),)),
        repo_root=tmp_path,
    )
    assert _counts(assessment) == (0, 0, 0)
    assert "author_associated" in assessment.excluded_datasets[0]["reason"]


def test_unverified_dataset_does_not_count(tmp_path):
    assessment = evaluate_capability(
        "scrna.pseudobulk_de",
        _registry(tmp_path, datasets=(_dataset(tmp_path, status="REGISTERED"),)),
        repo_root=tmp_path,
    )
    assert _counts(assessment) == (0, 0, 0)
    assert "frameworks" not in assessment.excluded_datasets[0]["reason"]
    assert "not VERIFIED" in assessment.excluded_datasets[0]["reason"]


def test_hash_drift_excludes_dataset(tmp_path):
    dataset = _dataset(tmp_path)
    (tmp_path / dataset.report_path).write_text("tampered", encoding="utf-8")
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,)), repo_root=tmp_path
    )
    assert _counts(assessment) == (0, 0, 0)
    assert "SHA-256" in assessment.excluded_datasets[0]["reason"]


def test_donors_required_only_where_capability_requires_them(tmp_path):
    not_donor_aware = _dataset(tmp_path, donor_aware=False)
    pseudobulk = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(not_donor_aware,)), repo_root=tmp_path
    )
    assert pseudobulk.counted_datasets == ()

    annotation_copy = not_donor_aware
    object.__setattr__(annotation_copy, "capability_id", "scrna.annotation_evidence")
    annotation = evaluate_capability(
        "scrna.annotation_evidence", _registry(tmp_path, datasets=(annotation_copy,)), repo_root=tmp_path
    )
    assert annotation.counted_datasets == ("d1",)


def test_missing_artifacts_excluded_fail_closed(tmp_path):
    fields = dict(_dataset(tmp_path).__dict__)
    fields["preregistration_path"] = "studies/none/PREREGISTRATION.json"
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(IVNDataset(**fields),)), repo_root=tmp_path
    )
    assert _counts(assessment) == (0, 0, 0)


# ------------------------------------------------------------------------------
# 4. Annotation coverage matrix
# ------------------------------------------------------------------------------


def test_annotation_coverage_gaps_across_disease_and_tissue(tmp_path):
    datasets = (
        _dataset(tmp_path, dataset_id="d1", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="healthy_donor_control", tissue="PBMC_blood", technology="CITE-seq_10x_protein_v3"),
        _dataset(tmp_path, dataset_id="d2", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="healthy_donor_control", tissue="PBMC_blood", technology="azimuth_reference_mapping_10x"),
        _dataset(tmp_path, dataset_id="d3", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="healthy_donor_control", tissue="PBMC_blood", technology="smartseq2_plate"),
    )
    assessment = evaluate_capability(
        "scrna.annotation_evidence", _registry(tmp_path, datasets=datasets), repo_root=tmp_path
    )
    assert len(assessment.counted_datasets) == 3
    assert _check(assessment, "independent_datasets").satisfied is True
    assert _check(assessment, "cross_technology").satisfied is True
    assert _check(assessment, "cross_disease").satisfied is False
    assert _check(assessment, "cross_tissue").satisfied is False
    assert assessment.complete is False


def test_annotation_coverage_satisfied_with_diverse_datasets(tmp_path):
    datasets = (
        _dataset(tmp_path, dataset_id="d1", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="healthy_donor_control", tissue="PBMC_blood", technology="CITE-seq_10x_protein_v3"),
        _dataset(tmp_path, dataset_id="d2", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="type_1_diabetes", tissue="pancreas", technology="CITE-seq_10x_protein_v3"),
        _dataset(tmp_path, dataset_id="d3", capability_id="scrna.annotation_evidence", donor_aware=False,
                 disease="healthy_donor_control", tissue="PBMC_blood", technology="merfish_imaging"),
    )
    assessment = evaluate_capability(
        "scrna.annotation_evidence", _registry(tmp_path, datasets=datasets), repo_root=tmp_path
    )
    assert _check(assessment, "cross_disease").satisfied is True
    assert _check(assessment, "cross_tissue").satisfied is True
    assert _check(assessment, "cross_technology").satisfied is True


def test_pseudobulk_has_no_coverage_matrix_requirement(tmp_path):
    datasets = tuple(
        _dataset(tmp_path, dataset_id=f"d{i}") for i in range(1, 4)
    )
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=datasets), repo_root=tmp_path
    )
    requirements = {check.requirement for check in assessment.checks}
    assert "cross_disease" not in requirements
    assert "independent_truth" not in requirements


# ------------------------------------------------------------------------------
# 5. Spatial independent truth
# ------------------------------------------------------------------------------


def test_spatial_dataset_without_independent_truth_excluded(tmp_path):
    base = dict(capability_id="spatial.inference_validity", donor_aware=False)
    pipeline_derived = _dataset(
        tmp_path, dataset_id="s1",
        truth_provenance=DatasetTruthProvenance(
            kind="pipeline_derived", provider="self", independent_of_authors=True,
            blinded_to_system_outputs=True,
        ),
        **base,
    )
    unblinded = _dataset(
        tmp_path, dataset_id="s2",
        truth_provenance=DatasetTruthProvenance(
            kind="pathology_annotation", provider="Pathology Lab",
            independent_of_authors=True, blinded_to_system_outputs=False,
        ),
        **base,
    )
    none_declared = _dataset(tmp_path, dataset_id="s3", **base)
    assessment = evaluate_capability(
        "spatial.inference_validity",
        _registry(tmp_path, datasets=(pipeline_derived, unblinded, none_declared)),
        repo_root=tmp_path,
    )
    assert _counts(assessment) == (0, 0, 0)
    assert _check(assessment, "independent_truth").satisfied is False


def test_spatial_dataset_with_independent_blinded_truth_counts(tmp_path):
    dataset = _dataset(
        tmp_path,
        capability_id="spatial.inference_validity",
        donor_aware=False,
        truth_provenance=DatasetTruthProvenance(
            kind="segmentation_truth",
            provider="Independent Digital Pathology Core",
            independent_of_authors=True,
            blinded_to_system_outputs=True,
        ),
    )
    assessment = evaluate_capability(
        "spatial.inference_validity", _registry(tmp_path, datasets=(dataset,)), repo_root=tmp_path
    )
    assert assessment.counted_datasets == ("d1",)
    assert _check(assessment, "independent_truth").satisfied is True


# ------------------------------------------------------------------------------
# 6. External lab studies: frameworks and slots never count
# ------------------------------------------------------------------------------


def test_registered_lab_study_is_not_completed_evidence(tmp_path):
    dataset = _dataset(tmp_path)
    lab = _lab(tmp_path, status="REGISTERED")
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,), labs=(lab,)), repo_root=tmp_path
    )
    assert assessment.counted_lab_studies == ()
    assert "never count" in assessment.excluded_lab_studies[0]["reason"]


def test_lab_study_on_non_counted_dataset_does_not_count(tmp_path):
    dataset = _dataset(tmp_path, status="EVIDENCE_SUBMITTED")
    lab = _lab(tmp_path)
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,), labs=(lab,)), repo_root=tmp_path
    )
    assert assessment.counted_lab_studies == ()
    assert "does not itself count" in assessment.excluded_lab_studies[0]["reason"]


def test_two_labs_same_institution_do_not_satisfy_quota(tmp_path):
    datasets = tuple(_dataset(tmp_path, dataset_id=f"d{i}") for i in range(1, 4))
    labs = (
        _lab(tmp_path, study_id="L1", lab_id="lab-1", institution="Same University"),
        _lab(tmp_path, study_id="L2", lab_id="lab-2", institution="Same University", dataset_id="d2"),
    )
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=datasets, labs=labs), repo_root=tmp_path
    )
    assert len(assessment.counted_lab_studies) == 2
    assert _check(assessment, "external_labs").satisfied is False


def test_unsigned_independence_declaration_refuses_lab(tmp_path):
    dataset = _dataset(tmp_path)
    lab = _lab(tmp_path, independence=IndependenceDeclaration(False, ""))
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,), labs=(lab,)), repo_root=tmp_path
    )
    assert assessment.counted_lab_studies == ()
    assert "independence declaration not signed" in assessment.excluded_lab_studies[0]["reason"]


# ------------------------------------------------------------------------------
# 7. Non-author reviews
# ------------------------------------------------------------------------------


def test_review_by_author_roster_member_does_not_count(tmp_path):
    dataset = _dataset(tmp_path)
    review = _review(tmp_path, reviewer_name="author", reviewer_id="author@bio.example")
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,), reviews=(review,)), repo_root=tmp_path
    )
    assert assessment.counted_reviews == ()
    assert "author roster" in assessment.excluded_reviews[0]["reason"]


def test_empty_author_roster_fails_closed_for_reviews(tmp_path):
    dataset = _dataset(tmp_path)
    review = _review(tmp_path)
    assessment = evaluate_capability(
        "scrna.pseudobulk_de",
        _registry(tmp_path, datasets=(dataset,), reviews=(review,), roster=()),
        repo_root=tmp_path,
    )
    assert assessment.counted_reviews == ()
    assert "roster is empty" in assessment.excluded_reviews[0]["reason"]


def test_unblinded_or_unattested_review_does_not_count(tmp_path):
    dataset = _dataset(tmp_path)
    unblinded = _review(tmp_path, review_id="R1", blinded=False)
    unattested = _review(tmp_path, review_id="R2", attestation_id="")
    assessment = evaluate_capability(
        "scrna.pseudobulk_de",
        _registry(tmp_path, datasets=(dataset,), reviews=(unblinded, unattested)),
        repo_root=tmp_path,
    )
    assert assessment.counted_reviews == ()
    reasons = {item["review_id"]: item["reason"] for item in assessment.excluded_reviews}
    assert "not blinded" in reasons["R1"]
    assert "attestation" in reasons["R2"]


def test_valid_non_author_review_counts(tmp_path):
    dataset = _dataset(tmp_path)
    review = _review(tmp_path)
    assessment = evaluate_capability(
        "scrna.pseudobulk_de", _registry(tmp_path, datasets=(dataset,), reviews=(review,)), repo_root=tmp_path
    )
    assert assessment.counted_reviews == ("R1",)
    assert _check(assessment, "non_author_reviewers").satisfied is True


# ------------------------------------------------------------------------------
# 8. Positive end-to-end path: pseudobulk quota completion
# ------------------------------------------------------------------------------


def test_pseudobulk_capability_can_complete_with_full_evidence(tmp_path):
    datasets = tuple(_dataset(tmp_path, dataset_id=f"d{i}") for i in range(1, 4))
    labs = (
        _lab(tmp_path, study_id="L1", lab_id="lab-1", institution="University A", host="codex"),
        _lab(tmp_path, study_id="L2", lab_id="lab-2", institution="University B", host="claude-code", dataset_id="d2"),
    )
    review = _review(tmp_path)
    assessment = evaluate_capability(
        "scrna.pseudobulk_de",
        _registry(tmp_path, datasets=datasets, labs=labs, reviews=(review,)),
        repo_root=tmp_path,
    )
    assert assessment.complete is True
    assert assessment.blocking_gaps == ()


def test_network_still_incomplete_when_only_one_capability_completes(tmp_path):
    datasets = tuple(_dataset(tmp_path, dataset_id=f"d{i}") for i in range(1, 4))
    labs = (
        _lab(tmp_path, study_id="L1", lab_id="lab-1", institution="University A"),
        _lab(tmp_path, study_id="L2", lab_id="lab-2", institution="University B", dataset_id="d2"),
    )
    review = _review(tmp_path)
    network = evaluate_network(
        _registry(tmp_path, datasets=datasets, labs=labs, reviews=(review,)), repo_root=tmp_path
    )
    assert network["network_status"] == "INCOMPLETE"
    assert network["capabilities"]["scrna.pseudobulk_de"]["complete"] is True
    assert network["capabilities"]["spatial.inference_validity"]["complete"] is False


# ------------------------------------------------------------------------------
# 9. Registry schema fail-closed behavior
# ------------------------------------------------------------------------------


def test_registry_rejects_unknown_capability_and_duplicates(tmp_path):
    with pytest.raises(IVNError):
        _dataset(tmp_path, capability_id="scrna.exploratory_clustering")
    good = _dataset(tmp_path)
    with pytest.raises(IVNError):
        _registry(tmp_path, datasets=(good, good))


def test_registry_rejects_wrong_schema_version():
    with pytest.raises(IVNError):
        IVNRegistry(schema_version="bionexus.ivn.registry.v0")


def test_verify_registry_integrity_detects_drift(tmp_path):
    dataset = _dataset(tmp_path)
    (tmp_path / dataset.report_path).write_text("tampered", encoding="utf-8")
    report = verify_registry_integrity(_registry(tmp_path, datasets=(dataset,)), repo_root=tmp_path)
    assert report["integrity"] == "FAIL"
    assert report["drift"][0]["problem"] == "sha256_mismatch"


def test_requirements_override_must_target_flagship(tmp_path):
    with pytest.raises(IVNError):
        _registry(tmp_path)
        IVNRegistry(
            requirements={"survival.kaplan_meier": CapabilityRequirements()},
        )


# ------------------------------------------------------------------------------
# 10. Calibration freeze on held-out contexts
# ------------------------------------------------------------------------------


def _approved_profile(**overrides):
    evidence = EmpiricalEvidence(
        evidence_id="emp.marker:v1:held_out",
        dataset_id="holdout_cohort",
        source_uri="https://example.org/holdout",
        source_sha256="a" * 64,
        sample_size=200,
        positive_outcomes=180,
        negative_outcomes=20,
        outcome_definition="annotation supported by orthogonal evidence",
        estimator="wilson_lower_bound",
        validation_partition="validation",
        independent_validation=True,
        observed_precision=0.90,
        precision_interval=(0.85, 0.94),
    )
    approval = ReviewerApproval(
        reviewer_id="reviewer-1",
        reviewed_at="2026-01-01T00:00:00+00:00",
        decision="APPROVE",
        scope="emp.marker:v1",
        attestation_sha256="b" * 64,
    )
    fields = dict(
        profile_id="emp.marker",
        version="v1",
        metric="marker_consistency",
        direction=ComparisonDirection.AT_LEAST,
        threshold=0.62,
        tissues=("PBMC_blood",),
        platforms=("10x_chromium_3prime_droplet",),
        references=("*",),
        tasks=("annotation_evidence",),
        evidence_sources=("*",),
        review_status=CalibrationReviewStatus.APPROVED,
        evidence=(evidence,),
        approvals=(approval,),
    )
    fields.update(overrides)
    return CalibrationProfile(**fields)


def _context(**overrides):
    fields = dict(
        dataset_id="holdout_cohort",
        dataset_sha256="c" * 64,
        disease="systemic_lupus_erythematosus",
        tissue="PBMC_blood",
        platform="10x_chromium_3prime_droplet",
        technology="CITE-seq_10x_protein_v3",
    )
    fields.update(overrides)
    return HeldOutContext(**fields)


def test_freeze_refuses_unapproved_profile():
    candidate = _approved_profile(review_status=CalibrationReviewStatus.CANDIDATE)
    with pytest.raises(CalibrationFreezeError, match="APPROVED"):
        freeze_profile(candidate, [_context()], freeze_id="F1", frozen_by="governance")


def test_freeze_refuses_approved_profile_with_validation_issues():
    broken = _approved_profile(approvals=())
    with pytest.raises(CalibrationFreezeError, match="validation issues"):
        freeze_profile(broken, [_context()], freeze_id="F1", frozen_by="governance")


def test_freeze_requires_held_out_validation_contexts():
    with pytest.raises(CalibrationFreezeError, match="held-out context"):
        freeze_profile(_approved_profile(), [], freeze_id="F1", frozen_by="governance")
    with pytest.raises(CalibrationFreezeError, match="validation"):
        freeze_profile(
            _approved_profile(),
            [_context(partition="calibration")],
            freeze_id="F1",
            frozen_by="governance",
        )


def test_frozen_record_verifies_and_detects_profile_drift():
    profile = _approved_profile()
    record = freeze_profile(profile, [_context()], freeze_id="F1", frozen_by="governance")
    ok, reasons = verify_freeze(record, profile)
    assert ok is True, reasons

    drifted = _approved_profile(threshold=0.7)
    ok, reasons = verify_freeze(record, drifted)
    assert ok is False
    assert any("hash changed" in reason for reason in reasons)


def test_authorize_gate_fail_closed_paths():
    profile = _approved_profile()
    record = freeze_profile(profile, [_context()], freeze_id="F1", frozen_by="governance")

    candidate = _approved_profile(review_status=CalibrationReviewStatus.CANDIDATE)
    assert authorize_context(candidate, [record], _context())["decision"] == (
        FreezeDecision.PROFILE_NOT_APPROVED.value
    )
    assert authorize_context(profile, [], _context())["decision"] == FreezeDecision.FREEZE_REQUIRED.value

    other_context = _context(disease="type_1_diabetes", tissue="pancreas")
    assert authorize_context(profile, [record], other_context)["decision"] == (
        FreezeDecision.CONTEXT_NOT_COVERED.value
    )

    drifted = _approved_profile(threshold=0.7)
    assert authorize_context(drifted, [record], _context())["decision"] == (
        FreezeDecision.FREEZE_MISMATCH.value
    )

    authorized = authorize_context(profile, [record], _context())
    assert authorized["decision"] == FreezeDecision.AUTHORIZED.value
    assert authorized["authorizing"] is True


def test_freeze_record_round_trips_through_dict():
    profile = _approved_profile()
    record = freeze_profile(
        profile, [_context()], freeze_id="F1", frozen_by="governance", notes="rc3+ freeze"
    )
    restored = CalibrationFreezeRecord.from_dict(json.loads(json.dumps(record.to_dict())))
    assert restored == record


def test_profile_from_payload_round_trip():
    profile = _approved_profile()
    payload = json.loads(json.dumps(profile.to_dict()))
    restored = profile_from_payload(payload)
    assert restored == profile


def test_seed_registry_has_zero_frozen_calibrations():
    registry = load_registry(default_registry_path(_REPO_ROOT))
    state = ivn_mod._calibration_freeze_state(registry)
    assert state["approved_frozen_profiles"] == []
    assert state["approved_unfrozen_profiles"] == []
    assert state["frozen_profile_records"] == 0


# ------------------------------------------------------------------------------
# 11. CLI surface
# ------------------------------------------------------------------------------


def _run_cli(capsys, *argv):
    from bionexus.cli import main

    code = main(list(argv))
    return code, capsys.readouterr().out


def test_cli_ivn_status_json(tmp_path, capsys):
    code, out = _run_cli(
        capsys, "ivn", "status", "--json", "--repo-root", str(_REPO_ROOT)
    )
    assert code == 0
    network = json.loads(out)
    assert network["network_status"] == "INCOMPLETE"
    assert set(network["capabilities"]) == set(ivn_mod.FLAGSHIP_CAPABILITIES)
    assert network["open_questions"]["all_still_open_as_assessed"] is True


def test_cli_ivn_verify(tmp_path, capsys):
    code, out = _run_cli(capsys, "ivn", "verify", "--repo-root", str(_REPO_ROOT))
    assert code == 0
    assert "PASS" in out


def test_cli_register_review_refuses_author_roster_overlap(tmp_path, capsys):
    payload = tmp_path / "review.json"
    review = _review(tmp_path, reviewer_name="author", reviewer_id="author@bio.example")
    payload.write_text(json.dumps(review.to_dict()), encoding="utf-8")
    code, out = _run_cli(
        capsys,
        "ivn", "register-review",
        "--payload", str(payload),
        "--registry", str(tmp_path / "REGISTRY.json"),
        "--repo-root", str(tmp_path),
    )
    assert code == 2
    assert "author roster" in out


def test_cli_freeze_profile_end_to_end(tmp_path, capsys):
    profile_path = tmp_path / "profile.json"
    contexts_path = tmp_path / "contexts.json"
    registry_path = tmp_path / "REGISTRY.json"
    profile_path.write_text(json.dumps(_approved_profile().to_dict()), encoding="utf-8")
    contexts_path.write_text(json.dumps([_context().to_dict()]), encoding="utf-8")

    code, out = _run_cli(
        capsys,
        "ivn", "freeze-profile",
        "--profile-json", str(profile_path),
        "--held-out-json", str(contexts_path),
        "--freeze-id", "F-001",
        "--frozen-by", "release-governance",
        "--registry", str(registry_path),
        "--repo-root", str(tmp_path),
        "--json",
    )
    assert code == 0
    record = json.loads(out)
    assert record["profile_id"] == "emp.marker"

    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(_context().to_dict()), encoding="utf-8")
    code, out = _run_cli(
        capsys,
        "ivn", "authorize",
        "--profile-json", str(profile_path),
        "--context-json", str(context_path),
        "--registry", str(registry_path),
        "--repo-root", str(tmp_path),
    )
    assert code == 0
    assert "AUTHORIZED" in out
