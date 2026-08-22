"""Contracts for the three-platform Spatial Empirical Gold Program.

All manifests and observations constructed here are software fixtures. They do
not represent real Xenium, CosMx, or MERSCOPE evidence and are never packaged
as calibration profiles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bionexus.empirical_warrant import (
    CalibrationProfile,
    CalibrationReviewStatus,
    ComparisonDirection,
    ReviewerApproval,
)
from bionexus.spatial_empirical_gold import (
    DEFAULT_SPATIAL_GOLD_ROOT,
    SPATIAL_CONTROL_METRICS,
    SPATIAL_GOLD_PLATFORMS,
    ImagingSpatialPlatform,
    SpatialGoldError,
    SpatialGoldObservationSet,
    SpatialGoldProgram,
    SpatialGoldRuntimeEvidence,
    SpatialGoldStudyManifest,
    fit_spatial_candidate_profile,
    verify_spatial_gold_artifacts,
)
from bionexus.spatial_gold_cli import main as spatial_gold_cli_main
from bionexus.trust_evidence import (
    EvidenceSubject,
    TrustKey,
    TrustRegistry,
    create_attestation,
    create_revocation,
    public_key_id,
    sha256_file,
)

METRIC = SPATIAL_CONTROL_METRICS["segmentation_uncertainty"]


def _study_document(platform: str = "xenium") -> dict[str, object]:
    return {
        "schema_version": "bionexus.spatial-empirical-gold-study.v1",
        "study_id": f"fixture-{platform}-segmentation-001",
        "platform": platform,
        "platform_release": "fixture-release-v1",
        "tissue": "fixture-tissue",
        "species": "human",
        "panel_id": "fixture-panel-v1",
        "task": "contact_expression_enrichment",
        "reference": "independent-boundary-adjudication-v1",
        "data_provenance": "REAL_PLATFORM_EXPORT",
        "dataset_artifacts": [{"uri": "fixture://vendor-export", "sha256": "a" * 64, "media_type": "application/zarr"}],
        "calibration_donor_ids": ["donor-cal"],
        "validation_donor_ids": ["donor-val"],
        "calibration_fov_ids": ["fov-cal"],
        "validation_fov_ids": ["fov-val"],
        "segmentation_revision_ids": ["vendor-seg-v1", "independent-seg-v1"],
        "leakage_model_ids": [],
        "metrics": [METRIC],
        "evidence_sources": {METRIC: "fixture-segmentation-adjudicator-v1"},
        "preregistration_artifact": {
            "uri": "fixture://preregistration",
            "sha256": "b" * 64,
            "media_type": "application/json",
        },
        "adjudication_protocol_artifact": {
            "uri": "fixture://adjudication-protocol",
            "sha256": "c" * 64,
            "media_type": "application/json",
        },
        "independent_adjudicator_ids": ["fixture-independent-reviewer"],
        "outcome_definition": "fixture-only independently adjudicated preservation of the declared effect",
    }


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "fixture://vendor-export": tmp_path / "vendor-export.bin",
        "fixture://preregistration": tmp_path / "preregistration.json",
        "fixture://adjudication-protocol": tmp_path / "adjudication-protocol.json",
    }
    for uri, path in paths.items():
        if not path.exists():
            path.write_bytes(f"software fixture bytes for {uri}".encode("utf-8"))
    return paths


def _write_study(tmp_path: Path, document: dict[str, object]) -> SpatialGoldStudyManifest:
    artifact_paths = _artifact_paths(tmp_path)
    document["dataset_artifacts"][0]["sha256"] = hashlib.sha256(
        artifact_paths["fixture://vendor-export"].read_bytes()
    ).hexdigest()
    document["preregistration_artifact"]["sha256"] = hashlib.sha256(
        artifact_paths["fixture://preregistration"].read_bytes()
    ).hexdigest()
    document["adjudication_protocol_artifact"]["sha256"] = hashlib.sha256(
        artifact_paths["fixture://adjudication-protocol"].read_bytes()
    ).hexdigest()
    path = tmp_path / "study.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return SpatialGoldStudyManifest.load(path)


def _write_observations(
    tmp_path: Path,
    manifest: SpatialGoldStudyManifest,
) -> tuple[SpatialGoldObservationSet, dict[str, Path]]:
    records: list[dict[str, object]] = []
    record_artifact_paths: dict[str, Path] = {}

    def add_record(
        *,
        record_id: str,
        score: float,
        outcome_supported: bool,
        partition: str,
        donor_id: str,
        fov_id: str,
    ) -> None:
        battery_path = tmp_path / f"{record_id}.battery.json"
        adjudication_path = tmp_path / f"{record_id}.adjudication.json"
        battery_path.write_text(
            json.dumps(
                {
                    "schema_version": "bionexus.spatial-gold-battery-record.v1",
                    "record_id": record_id,
                    "study_id": manifest.study_id,
                    "platform": manifest.platform.value,
                    "metric": METRIC,
                    "donor_id": donor_id,
                    "fov_id": fov_id,
                    "partition": partition,
                    "score": score,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        adjudication_path.write_text(
            json.dumps(
                {
                    "schema_version": "bionexus.spatial-gold-adjudication-record.v1",
                    "record_id": record_id,
                    "study_id": manifest.study_id,
                    "platform": manifest.platform.value,
                    "metric": METRIC,
                    "donor_id": donor_id,
                    "fov_id": fov_id,
                    "partition": partition,
                    "outcome_supported": outcome_supported,
                    "adjudicator_id": manifest.independent_adjudicator_ids[0],
                    "protocol_sha256": manifest.adjudication_protocol_artifact.sha256,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        record_artifact_paths[f"{record_id}:battery_run"] = battery_path
        record_artifact_paths[f"{record_id}:adjudication_record"] = adjudication_path
        records.append(
            {
                "record_id": record_id,
                "study_id": manifest.study_id,
                "platform": manifest.platform.value,
                "metric": METRIC,
                "score": score,
                "outcome_supported": outcome_supported,
                "partition": partition,
                "donor_id": donor_id,
                "fov_id": fov_id,
                "battery_run_sha256": hashlib.sha256(battery_path.read_bytes()).hexdigest(),
                "adjudication_record_sha256": hashlib.sha256(adjudication_path.read_bytes()).hexdigest(),
            }
        )

    for index in range(20):
        add_record(
            record_id=f"cal-positive-{index}",
            score=0.80 + index * 0.005,
            outcome_supported=True,
            partition="calibration",
            donor_id="donor-cal",
            fov_id="fov-cal",
        )
    for index in range(10):
        add_record(
            record_id=f"cal-negative-{index}",
            score=0.10 + index * 0.02,
            outcome_supported=False,
            partition="calibration",
            donor_id="donor-cal",
            fov_id="fov-cal",
        )
    for index in range(10):
        add_record(
            record_id=f"val-positive-{index}",
            score=0.82 + index * 0.01,
            outcome_supported=True,
            partition="validation",
            donor_id="donor-val",
            fov_id="fov-val",
        )
    for index in range(5):
        add_record(
            record_id=f"val-negative-{index}",
            score=0.10 + index * 0.02,
            outcome_supported=False,
            partition="validation",
            donor_id="donor-val",
            fov_id="fov-val",
        )
    document = {
        "schema_version": "bionexus.spatial-empirical-gold-observations.v1",
        "study_manifest_sha256": manifest.source_sha256,
        "records": records,
    }
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return SpatialGoldObservationSet.load(path, manifest), record_artifact_paths


def _template(manifest: SpatialGoldStudyManifest) -> CalibrationProfile:
    return CalibrationProfile(
        profile_id=f"candidate.spatial.{manifest.platform.value}.segmentation.fixture",
        version="0.1.0",
        metric=METRIC,
        direction=ComparisonDirection.AT_LEAST,
        threshold=0.5,
        tissues=(manifest.tissue,),
        platforms=(manifest.platform.value,),
        references=(manifest.reference,),
        tasks=(manifest.task,),
        evidence_sources=(manifest.evidence_sources[METRIC],),
        review_status=CalibrationReviewStatus.CANDIDATE,
        metadata={"fixture_only": True, "scientific_claim": "none"},
    )


def _approved_runtime_fixture(
    tmp_path: Path,
) -> tuple[CalibrationProfile, SpatialGoldRuntimeEvidence, Ed25519PrivateKey, str]:
    manifest = _write_study(tmp_path, _study_document())
    observations, record_artifact_paths = _write_observations(tmp_path, manifest)
    artifact_verification = verify_spatial_gold_artifacts(
        manifest,
        _artifact_paths(tmp_path),
        observation_set=observations,
        record_artifact_paths=record_artifact_paths,
    )
    candidate, _ = fit_spatial_candidate_profile(
        manifest=manifest,
        observation_set=observations,
        artifact_verification=artifact_verification,
        metric=METRIC,
        profile_template=_template(manifest),
        target_precision_lower_bound=0.75,
        confidence_level=0.95,
        minimum_selected=10,
    )
    approved = replace(
        candidate,
        review_status=CalibrationReviewStatus.APPROVED,
        approvals=(
            ReviewerApproval(
                reviewer_id="fixture-independent-reviewer",
                reviewed_at="2026-08-21T00:00:00+00:00",
                decision="APPROVE",
                scope="software-contract authorization fixture only",
                attestation_sha256="d" * 64,
            ),
        ),
    )
    profile_path = tmp_path / "approved-profile.json"
    profile_path.write_text(json.dumps(approved.to_dict(), indent=2) + "\n", encoding="utf-8")
    profile_artifact_uri = "fixture://approved-profile"
    attestation_id = "att:spatial-gold:test:001"
    study_binding = approved.metadata["spatial_gold_study_bindings"][0]

    program_document = json.loads((DEFAULT_SPATIAL_GOLD_ROOT / "program.json").read_text(encoding="utf-8"))
    program_document["status"] = "externally_validated"
    program_document["studies"] = [
        {
            "study_id": manifest.study_id,
            "platform": manifest.platform.value,
            "manifest_uri": "fixture://study-manifest",
            "manifest_sha256": manifest.source_sha256,
            "status": "BYTE_VERIFIED",
        }
    ]
    program_document["approved_profiles"] = [
        {
            "profile_id": approved.profile_id,
            "version": approved.version,
            "profile_sha256": approved.fingerprint_sha256,
            "profile_artifact_uri": profile_artifact_uri,
            "profile_artifact_sha256": sha256_file(profile_path),
            "platform": manifest.platform.value,
            "metric": METRIC,
            "study_bindings": [study_binding],
            "approval_attestation_id": attestation_id,
            "status": "ACTIVE",
        }
    ]
    program_document["platform_programs"]["xenium"] = {
        "status": "EXTERNALLY_VALIDATED",
        "study_ids": [manifest.study_id],
        "approved_profile_ids": [approved.profile_id],
    }
    program_path = tmp_path / "program.json"
    program_path.write_text(json.dumps(program_document, indent=2) + "\n", encoding="utf-8")
    program = SpatialGoldProgram(
        program_document,
        root=DEFAULT_SPATIAL_GOLD_ROOT,
        source_uri=str(program_path),
        source_sha256=sha256_file(program_path),
    )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    key_id = public_key_id(public_key)
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    signer_id = "fixture-spatial-gold-council"
    trust_registry = TrustRegistry(
        keys={
            key_id: TrustKey(
                key_id=key_id,
                signer_id=signer_id,
                public_key_pem=public_pem,
                valid_from="2026-01-01T00:00:00+00:00",
                valid_until="2027-01-01T00:00:00+00:00",
                allowed_predicates=("spatial-gold-profile-approval", "revocation"),
            )
        },
        status="TEST_FIXTURE",
    )
    attestation = create_attestation(
        attestation_id=attestation_id,
        predicate_type="spatial-gold-profile-approval",
        subject=EvidenceSubject(
            subject_type="spatial-calibration-profile",
            subject_id=approved.profile_id,
            version=approved.version,
            artifact_uri=profile_artifact_uri,
            artifact_sha256=sha256_file(profile_path),
        ),
        scope={
            "program_version": program.program_version,
            "program_sha256": program.program_sha256,
            "platform": manifest.platform.value,
            "metric": METRIC,
        },
        claims={
            "review_status": "APPROVED",
            "profile_sha256": approved.fingerprint_sha256,
            "study_bindings": [study_binding],
            "record_artifact_bytes_verified": True,
        },
        issued_at="2026-08-21T00:00:00+00:00",
        expires_at="2026-12-31T00:00:00+00:00",
        signer_id=signer_id,
        key_id=key_id,
        private_key=private_key,
    )
    runtime = SpatialGoldRuntimeEvidence(
        program=program,
        trust_registry=trust_registry,
        profile_artifact_paths={f"{approved.profile_id}@{approved.version}": profile_path},
        approval_attestations={attestation_id: attestation},
        study_manifest_paths={manifest.study_id: manifest.source_uri},
        at_time=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    return approved, runtime, private_key, attestation_id


def test_program_is_zero_threshold_and_reports_all_three_platform_gaps() -> None:
    program = SpatialGoldProgram.load(DEFAULT_SPATIAL_GOLD_ROOT)
    inventory = program.inventory()

    assert tuple(inventory["supported_platforms"]) == SPATIAL_GOLD_PLATFORMS
    assert inventory["status"] == "incomplete_not_claim_ready"
    assert inventory["study_count"] == 0
    assert inventory["approved_profile_count"] == 0
    assert inventory["coverage_gap_count"] == 3 * len(SPATIAL_CONTROL_METRICS)
    assert inventory["claim_ready"] is False
    assert '"threshold"' not in (DEFAULT_SPATIAL_GOLD_ROOT / "program.json").read_text(encoding="utf-8")


def test_inventory_cli_reports_incomplete_without_promoting_claims(capsys: pytest.CaptureFixture[str]) -> None:
    assert spatial_gold_cli_main(["inventory"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["coverage_gap_count"] == 36
    assert output["approved_profile_count"] == 0
    assert output["claim_ready"] is False


@pytest.mark.parametrize("platform", ["xenium", "cosmx", "merscope"])
def test_each_admitted_platform_can_load_a_strict_study_contract(tmp_path: Path, platform: str) -> None:
    manifest = _write_study(tmp_path, _study_document(platform))

    assert manifest.platform == ImagingSpatialPlatform(platform)
    assert len(manifest.source_sha256) == 64
    assert manifest.context_for(METRIC).platform == platform


def test_synthetic_provenance_and_partition_overlap_fail_closed(tmp_path: Path) -> None:
    synthetic = _study_document()
    synthetic["data_provenance"] = "SYNTHETIC"
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(synthetic), encoding="utf-8")
    with pytest.raises(SpatialGoldError, match="schema violation"):
        SpatialGoldStudyManifest.load(path)

    overlap = _study_document()
    overlap["validation_donor_ids"] = ["donor-cal"]
    overlap["validation_fov_ids"] = ["fov-cal"]
    with pytest.raises(SpatialGoldError, match="donors overlap"):
        _write_study(tmp_path, overlap)


def test_observation_set_binds_manifest_and_enforces_partition_membership(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, _ = _write_observations(tmp_path, manifest)
    assert len(observations.records) == 45

    observation_path = Path(observations.source_uri)
    document = json.loads(observation_path.read_text(encoding="utf-8"))
    document["records"][0]["donor_id"] = "donor-val"
    observation_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SpatialGoldError, match="outside calibration partition"):
        SpatialGoldObservationSet.load(observation_path, manifest)


def test_platform_specific_fit_can_only_create_candidate(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, record_artifact_paths = _write_observations(tmp_path, manifest)
    artifact_verification = verify_spatial_gold_artifacts(
        manifest,
        _artifact_paths(tmp_path),
        observation_set=observations,
        record_artifact_paths=record_artifact_paths,
    )

    candidate, receipt = fit_spatial_candidate_profile(
        manifest=manifest,
        observation_set=observations,
        artifact_verification=artifact_verification,
        metric=METRIC,
        profile_template=_template(manifest),
        target_precision_lower_bound=0.75,
        confidence_level=0.95,
        minimum_selected=10,
    )

    assert candidate.review_status == CalibrationReviewStatus.CANDIDATE
    assert candidate.approvals == ()
    assert candidate.platforms == ("xenium",)
    assert candidate.metadata["platform_pooling"] is False
    assert candidate.metadata["approval_eligible"] is False
    assert receipt.approval_eligible is False
    assert receipt.calibration_donor_ids == ("donor-cal",)
    assert receipt.validation_donor_ids == ("donor-val",)
    assert candidate.metadata["artifact_verification_receipt_sha256"] == artifact_verification.receipt_sha256
    assert candidate.metadata["record_artifact_bytes_verified"] is True


def test_candidate_fit_requires_actual_artifact_bytes(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    paths = _artifact_paths(tmp_path)
    paths["fixture://vendor-export"].write_text("tampered", encoding="utf-8")

    with pytest.raises(SpatialGoldError, match="SHA-256 mismatch"):
        verify_spatial_gold_artifacts(manifest, paths)


def test_candidate_fit_rejects_study_only_receipt(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, _ = _write_observations(tmp_path, manifest)
    study_only = verify_spatial_gold_artifacts(manifest, _artifact_paths(tmp_path))

    assert study_only.verified is False
    with pytest.raises(SpatialGoldError, match="battery-run, and adjudication artifacts"):
        fit_spatial_candidate_profile(
            manifest=manifest,
            observation_set=observations,
            artifact_verification=study_only,
            metric=METRIC,
            profile_template=_template(manifest),
            target_precision_lower_bound=0.75,
            confidence_level=0.95,
            minimum_selected=10,
        )


def test_record_artifact_bytes_are_required_and_tamper_detected(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, record_artifact_paths = _write_observations(tmp_path, manifest)
    first_key = sorted(record_artifact_paths)[0]
    record_artifact_paths[first_key].write_text("tampered", encoding="utf-8")

    with pytest.raises(SpatialGoldError, match="record artifact SHA-256 mismatch"):
        verify_spatial_gold_artifacts(
            manifest,
            _artifact_paths(tmp_path),
            observation_set=observations,
            record_artifact_paths=record_artifact_paths,
        )


def test_record_artifact_bytes_must_semantically_match_observation(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, record_artifact_paths = _write_observations(tmp_path, manifest)
    first_key = sorted(key for key in record_artifact_paths if key.endswith(":battery_run"))[0]
    battery_path = record_artifact_paths[first_key]
    battery_document = json.loads(battery_path.read_text(encoding="utf-8"))
    battery_document["score"] = 0.999
    battery_path.write_text(json.dumps(battery_document, sort_keys=True), encoding="utf-8")

    observation_path = Path(observations.source_uri)
    observation_document = json.loads(observation_path.read_text(encoding="utf-8"))
    record_id = first_key.rsplit(":", 1)[0]
    for item in observation_document["records"]:
        if item["record_id"] == record_id:
            item["battery_run_sha256"] = hashlib.sha256(battery_path.read_bytes()).hexdigest()
            break
    observation_path.write_text(json.dumps(observation_document, indent=2) + "\n", encoding="utf-8")
    rebound_observations = SpatialGoldObservationSet.load(observation_path, manifest)

    with pytest.raises(SpatialGoldError, match="record artifact semantic mismatch.*score"):
        verify_spatial_gold_artifacts(
            manifest,
            _artifact_paths(tmp_path),
            observation_set=rebound_observations,
            record_artifact_paths=record_artifact_paths,
        )


def test_runtime_authorization_requires_trusted_unrevoked_profile_and_study_bytes(tmp_path: Path) -> None:
    approved, runtime, private_key, attestation_id = _approved_runtime_fixture(tmp_path)

    authorization = runtime.authorize(approved)
    assert authorization.authorized is True
    assert authorization.trust_decision == "VERIFIED"
    assert authorization.study_ids == ("fixture-xenium-segmentation-001",)

    program_path = Path(runtime.program.source_uri)
    original_program_bytes = program_path.read_bytes()
    program_path.write_bytes(original_program_bytes + b" ")
    tampered_program = runtime.authorize(approved)
    assert tampered_program.authorized is False
    assert tampered_program.status == "GOLD_PROGRAM_BINDING_MISMATCH"
    program_path.write_bytes(original_program_bytes)

    candidate_only_document = json.loads(original_program_bytes.decode("utf-8"))
    candidate_only_document["status"] = "candidate_only"
    candidate_only_path = tmp_path / "candidate-only-program.json"
    candidate_only_path.write_text(json.dumps(candidate_only_document, indent=2) + "\n", encoding="utf-8")
    candidate_only_program = SpatialGoldProgram(
        candidate_only_document,
        root=DEFAULT_SPATIAL_GOLD_ROOT,
        source_uri=str(candidate_only_path),
        source_sha256=sha256_file(candidate_only_path),
    )
    candidate_only = replace(runtime, program=candidate_only_program).authorize(approved)
    assert candidate_only.authorized is False
    assert candidate_only.status == "GOLD_PROGRAM_NOT_EXTERNALLY_VALIDATED"

    legacy_id_only_runtime = replace(
        runtime,
        profile_artifact_paths={approved.profile_id: next(iter(runtime.profile_artifact_paths.values()))},
    )
    legacy_id_only = legacy_id_only_runtime.authorize(approved)
    assert legacy_id_only.authorized is False
    assert legacy_id_only.status == "PROFILE_ARTIFACT_BYTES_REQUIRED"

    attestation = runtime.approval_attestations[attestation_id]
    runtime.trust_registry.revocations.append(
        create_revocation(
            revocation_id="rev:spatial-gold:test:001",
            target_type="attestation",
            target_id=attestation_id,
            reason="fixture withdrawal",
            revoked_at="2026-08-22T01:00:00+00:00",
            signer_id=attestation.signer_id,
            key_id=attestation.key_id,
            private_key=private_key,
        )
    )
    revoked_runtime = replace(runtime, at_time=datetime(2026, 8, 23, tzinfo=timezone.utc))
    revoked = revoked_runtime.authorize(approved)
    assert revoked.authorized is False
    assert revoked.status == "APPROVAL_ATTESTATION_NOT_TRUSTED"
    assert revoked.trust_decision == "REVOKED"


def test_profile_cannot_pool_or_change_platform(tmp_path: Path) -> None:
    manifest = _write_study(tmp_path, _study_document())
    observations, record_artifact_paths = _write_observations(tmp_path, manifest)
    artifact_verification = verify_spatial_gold_artifacts(
        manifest,
        _artifact_paths(tmp_path),
        observation_set=observations,
        record_artifact_paths=record_artifact_paths,
    )
    pooled = replace(_template(manifest), platforms=("xenium", "cosmx"))

    with pytest.raises(SpatialGoldError, match="platforms must exactly match"):
        fit_spatial_candidate_profile(
            manifest=manifest,
            observation_set=observations,
            artifact_verification=artifact_verification,
            metric=METRIC,
            profile_template=pooled,
            target_precision_lower_bound=0.75,
            confidence_level=0.95,
            minimum_selected=10,
        )
