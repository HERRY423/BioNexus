"""
Unit tests for ValidationArtifact and related artifact-generation utilities
added to evals/flagship_validation.py (BNS-015 artifact track).

Tests cover:
- ValidationArtifact serialization / deserialization round-trip
- SHA-256 checksum computation on temporary files
- JSON schema completeness (all required fields present)
- --output-dir CLI argument propagation
- Metric pass/fail determination logic
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from evals.flagship_validation import (
    ValidationArtifact,
    _capability_to_subdir,
    _determine_status,
    build_arg_parser,
    compute_file_checksum,
    generate_validation_report,
)

# ---------------------------------------------------------------------------
# Fixtures — use workspace-local temp dir to avoid Windows system-temp issues
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Override pytest's tmp_path to use a workspace-local directory."""
    base = _REPO_ROOT / ".pytest_tmp" / "test_validation_artifacts"
    base.mkdir(parents=True, exist_ok=True)
    p = Path(tempfile.mkdtemp(dir=str(base), prefix="run_"))
    yield p
    shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_artifact() -> ValidationArtifact:
    """A fully-populated ValidationArtifact for round-trip tests."""
    return ValidationArtifact(
        capability="scrna.pseudobulk_de",
        dataset={
            "name": "kang2018_pbmc_ifnb",
            "version": "1.0",
            "accession": "GEO GSE96583",
            "checksum_sha256": {"pbmc_ifnb_counts.h5ad": "deadbeef" * 8},
        },
        pipeline={
            "version": "0.4.0",
            "backend_identity": {"state": "CONFORMANT"},
        },
        metrics=[
            {"name": "top100_overlap", "expected": ">=0.5", "observed": "0.72", "result": "pass"},
        ],
        limitations=["No parameter sweep audit yet"],
        timestamp="2026-08-18T12:00:00+00:00",
        evidence_files=["validation/pseudobulk/kang2018_pbmc_ifnb_validation.json"],
        status="pass",
    )


@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    """Create a temporary file with known content for checksum tests."""
    p = tmp_path / "testfile.bin"
    p.write_bytes(b"bionexus-validation-artifact-test")
    return p


# ---------------------------------------------------------------------------
# Tests: ValidationArtifact serialization / deserialization
# ---------------------------------------------------------------------------

class TestValidationArtifactSerialization:
    """ValidationArtifact must round-trip through dict and JSON."""

    def test_to_dict_contains_all_fields(self, sample_artifact: ValidationArtifact) -> None:
        d = sample_artifact.to_dict()
        expected_keys = {
            "capability", "dataset", "pipeline", "metrics",
            "limitations", "timestamp", "evidence_files", "status",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_round_trip_dict(self, sample_artifact: ValidationArtifact) -> None:
        d = sample_artifact.to_dict()
        restored = ValidationArtifact.from_dict(d)
        assert restored.capability == sample_artifact.capability
        assert restored.dataset == sample_artifact.dataset
        assert restored.pipeline == sample_artifact.pipeline
        assert restored.metrics == sample_artifact.metrics
        assert restored.limitations == sample_artifact.limitations
        assert restored.timestamp == sample_artifact.timestamp
        assert restored.evidence_files == sample_artifact.evidence_files
        assert restored.status == sample_artifact.status

    def test_to_json_is_valid_json(self, sample_artifact: ValidationArtifact) -> None:
        json_str = sample_artifact.to_json()
        parsed = json.loads(json_str)
        assert parsed["capability"] == "scrna.pseudobulk_de"
        assert parsed["status"] == "pass"

    def test_json_round_trip(self, sample_artifact: ValidationArtifact) -> None:
        json_str = sample_artifact.to_json()
        parsed = json.loads(json_str)
        restored = ValidationArtifact.from_dict(parsed)
        assert restored.capability == sample_artifact.capability
        assert restored.status == sample_artifact.status


# ---------------------------------------------------------------------------
# Tests: compute_file_checksum
# ---------------------------------------------------------------------------

class TestComputeFileChecksum:
    """SHA-256 checksum computation must be correct."""

    def test_sha256_known_value(self, tmp_file: Path) -> None:
        expected = hashlib.sha256(b"bionexus-validation-artifact-test").hexdigest()
        assert compute_file_checksum(tmp_file) == expected

    def test_sha256_empty_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.bin"
        empty.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_file_checksum(empty) == expected

    def test_sha256_large_file(self, tmp_path: Path) -> None:
        """File larger than the 8192-byte read chunk to exercise the loop."""
        large = tmp_path / "large.bin"
        data = b"x" * 20000
        large.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_checksum(large) == expected

    def test_md5_algorithm(self, tmp_file: Path) -> None:
        expected = hashlib.md5(b"bionexus-validation-artifact-test").hexdigest()
        assert compute_file_checksum(tmp_file, algorithm="md5") == expected


# ---------------------------------------------------------------------------
# Tests: JSON schema completeness
# ---------------------------------------------------------------------------

class TestReportSchemaCompleteness:
    """Generated report JSON must contain all required top-level fields."""

    REQUIRED_FIELDS = {
        "capability", "dataset", "pipeline", "metrics",
        "limitations", "timestamp", "evidence_files", "status",
    }

    def test_dataset_fields(self, sample_artifact: ValidationArtifact) -> None:
        ds = sample_artifact.to_dict()["dataset"]
        for key in ("name", "version", "accession", "checksum_sha256"):
            assert key in ds, f"dataset missing key: {key}"

    def test_pipeline_fields(self, sample_artifact: ValidationArtifact) -> None:
        pl = sample_artifact.to_dict()["pipeline"]
        for key in ("version", "backend_identity"):
            assert key in pl, f"pipeline missing key: {key}"

    def test_metric_record_fields(self, sample_artifact: ValidationArtifact) -> None:
        for m in sample_artifact.to_dict()["metrics"]:
            for key in ("name", "expected", "observed", "result"):
                assert key in m, f"metric record missing key: {key}"

    def test_all_required_top_level_fields(self, sample_artifact: ValidationArtifact) -> None:
        d = sample_artifact.to_dict()
        assert self.REQUIRED_FIELDS.issubset(set(d.keys()))

    def test_generate_validation_report_schema(self, tmp_path: Path) -> None:
        """generate_validation_report returns an artifact with all fields."""
        run_result = {"actual_status": "PERMITTED", "skipped": False}
        artifact = generate_validation_report(
            capability="scrna.annotation_evidence",
            dataset_id="citeseq_pbmc_sorted",
            run_result=run_result,
            metrics=[{"name": "distrust_check", "expected": "not SUPPORTED", "observed": "ABSTAIN", "result": "pass"}],
            limitations=["no public atlas vendored"],
            evidence_files=[],
            output_dir=tmp_path,
        )
        d = artifact.to_dict()
        assert self.REQUIRED_FIELDS.issubset(set(d.keys()))
        assert d["status"] == "pass"
        assert d["capability"] == "scrna.annotation_evidence"


# ---------------------------------------------------------------------------
# Tests: --output-dir CLI argument
# ---------------------------------------------------------------------------

class TestOutputDirCLI:
    """--output-dir must be correctly parsed and propagated."""

    def test_default_output_dir(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args([])
        # Default should end with "validation"
        assert args.output_dir.name == "validation"

    def test_custom_output_dir(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(["--output-dir", "/tmp/my_reports"])
        assert args.output_dir == Path("/tmp/my_reports")

    def test_output_dir_used_in_report(self, tmp_path: Path) -> None:
        """Report file is written under the specified output_dir."""
        run_result = {"actual_status": "PERMITTED", "skipped": False}
        generate_validation_report(
            capability="spatial.inference_validity",
            dataset_id="xenium_spatial_truth",
            run_result=run_result,
            output_dir=tmp_path,
        )
        expected_subdir = tmp_path / "spatial"
        assert expected_subdir.is_dir()
        json_files = list(expected_subdir.glob("*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["capability"] == "spatial.inference_validity"


# ---------------------------------------------------------------------------
# Tests: metric pass/fail determination logic
# ---------------------------------------------------------------------------

class TestDetermineStatus:
    """_determine_status must correctly map run results to pass/fail/skipped."""

    def test_permitted_is_pass(self) -> None:
        assert _determine_status({"actual_status": "PERMITTED", "skipped": False}) == "pass"

    def test_outcome_mismatch_is_fail(self) -> None:
        assert _determine_status({"actual_status": "OUTCOME_MISMATCH", "skipped": False}) == "fail"

    def test_execution_failure_is_fail(self) -> None:
        assert _determine_status({"actual_status": "EXECUTION_FAILURE", "skipped": False}) == "fail"

    def test_blocked_backend_is_fail(self) -> None:
        assert _determine_status({"actual_status": "BLOCKED_BACKEND_IDENTITY", "skipped": False}) == "fail"

    def test_skipped_no_dataset(self) -> None:
        result = {"actual_status": "SKIPPED_NO_BACKEND", "skipped": True, "skip_reason": "dataset absent"}
        assert _determine_status(result) == "skipped"

    def test_explicit_skipped_flag(self) -> None:
        assert _determine_status({"actual_status": "WHATEVER", "skipped": True}) == "skipped"

    def test_unknown_status_is_fail(self) -> None:
        assert _determine_status({"actual_status": "SOMETHING_ELSE", "skipped": False}) == "fail"

    def test_empty_result_is_fail(self) -> None:
        assert _determine_status({}) == "fail"


# ---------------------------------------------------------------------------
# Tests: _capability_to_subdir mapping
# ---------------------------------------------------------------------------

class TestCapabilityToSubdir:
    """Capability id -> output sub-directory mapping."""

    def test_pseudobulk(self) -> None:
        assert _capability_to_subdir("scrna.pseudobulk_de") == "pseudobulk"

    def test_annotation(self) -> None:
        assert _capability_to_subdir("scrna.annotation_evidence") == "annotation"

    def test_spatial(self) -> None:
        assert _capability_to_subdir("spatial.inference_validity") == "spatial"

    def test_unknown_capability_fallback(self) -> None:
        result = _capability_to_subdir("custom.some_capability")
        assert result == "custom_some_capability"


# ---------------------------------------------------------------------------
# Tests: CERTIFICATION.json bundle completeness
# ---------------------------------------------------------------------------

_VALIDATION_ROOT = _REPO_ROOT / "validation"

# Map from capability id to its validation sub-directory name.
_FLAGSHIP_CERT_FILES: Dict[str, Path] = {
    "scrna.pseudobulk_de": _VALIDATION_ROOT / "pseudobulk" / "CERTIFICATION.json",
    "scrna.annotation_evidence": _VALIDATION_ROOT / "annotation" / "CERTIFICATION.json",
    "spatial.inference_validity": _VALIDATION_ROOT / "spatial" / "CERTIFICATION.json",
}

_CERTIFICATION_REQUIRED_KEYS = {
    "schema_version", "capability_id", "certification_level",
    "assessment_date", "project_version", "standards",
    "summary", "evidence_bundle",
}

_STANDARD_REQUIRED_KEYS = {"standard_id", "satisfied", "evidence", "notes"}


class TestCertificationBundles:
    """CERTIFICATION.json files must exist and be schema-complete."""

    def test_all_flagship_certifications_exist(self) -> None:
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            assert path.is_file(), f"Missing CERTIFICATION.json for {cid} at {path}"

    def test_certification_schema_completeness(self) -> None:
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            missing = _CERTIFICATION_REQUIRED_KEYS - set(data.keys())
            assert not missing, f"{cid} CERTIFICATION.json missing keys: {missing}"

    def test_certification_has_14_standards(self) -> None:
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            assert len(data["standards"]) == 14, f"{cid} has {len(data['standards'])} standards, expected 14"
            for std in data["standards"]:
                missing = _STANDARD_REQUIRED_KEYS - set(std.keys())
                assert not missing, f"{cid} standard {std.get('standard_id', '?')} missing keys: {missing}"

    def test_certification_level_matches_compute_tier(self) -> None:
        """CERTIFICATION.json level must match what compute_tier computes from _EVIDENCE."""
        from bionexus.certification import certify_capability
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            rec = certify_capability(cid)
            assert data["certification_level"] == rec.tier.value, (
                f"{cid}: CERTIFICATION.json says {data['certification_level']} "
                f"but compute_tier says {rec.tier.value}"
            )

    def test_summary_counts_match_standards(self) -> None:
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            satisfied = [s for s in data["standards"] if s["satisfied"]]
            unsatisfied = [s for s in data["standards"] if not s["satisfied"]]
            summary = data["summary"]
            assert summary["total_standards"] == 14
            assert summary["satisfied"] == len(satisfied)
            assert summary["unsatisfied"] == len(unsatisfied)
            assert set(summary["unsatisfied_list"]) == {s["standard_id"] for s in unsatisfied}

    def test_evidence_bundle_references_exist(self) -> None:
        """Files referenced in evidence_bundle must exist on disk."""
        for cid, path in _FLAGSHIP_CERT_FILES.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            bundle = data["evidence_bundle"]
            for key, ref_path in bundle.items():
                if not isinstance(ref_path, str) or not ref_path:
                    continue
                # Skip non-file references (e.g. certification_source)
                if key == "certification_source":
                    continue
                full = _REPO_ROOT / ref_path
                assert full.is_file(), (
                    f"{cid} evidence_bundle.{key} references {ref_path} which does not exist"
                )

    def test_pseudobulk_is_validated(self) -> None:
        """pseudobulk should be VALIDATED (9/14, all core + adversarial + IGT + provenance)."""
        data = json.loads(_FLAGSHIP_CERT_FILES["scrna.pseudobulk_de"].read_text(encoding="utf-8"))
        assert data["certification_level"] == "VALIDATED"
        assert data["summary"]["satisfied"] == 9

    def test_annotation_is_validated(self) -> None:
        data = json.loads(_FLAGSHIP_CERT_FILES["scrna.annotation_evidence"].read_text(encoding="utf-8"))
        assert data["certification_level"] == "VALIDATED"
        assert data["summary"]["satisfied"] == 6

    def test_spatial_is_validated(self) -> None:
        data = json.loads(_FLAGSHIP_CERT_FILES["spatial.inference_validity"].read_text(encoding="utf-8"))
        assert data["certification_level"] == "VALIDATED"
        assert data["summary"]["satisfied"] == 6
