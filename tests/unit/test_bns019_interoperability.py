"""Focused contract tests for the public BNS-019 interoperability kit."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INTEROP_ROOT = REPOSITORY_ROOT / "interoperability" / "bns019"
STANDARD_ROOT = REPOSITORY_ROOT / "standards" / "scientific-semantic-conventions"


def load_python_validator():
    path = INTEROP_ROOT / "python" / "bns019_validator.py"
    spec = importlib.util.spec_from_file_location("bns019_test_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trial_is_bound_to_the_exact_verified_release() -> None:
    validator = load_python_validator()
    release, _ = validator.load_verified_release(STANDARD_ROOT)
    trial = json.loads((INTEROP_ROOT / "trial" / "trial-manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((INTEROP_ROOT / "trial" / "schemas" / "trial-manifest.schema.json").read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(trial)
    conformance_path = STANDARD_ROOT / "conformance" / "manifest.json"
    assert trial["standard"] == {
        "id": "BNS-019",
        "version": release["version"],
        "release_digest_sha256": release["release_digest_sha256"],
        "conformance_manifest_sha256": validator.sha256_file(conformance_path),
    }
    assert trial["publication_status"] == "open_on_publication"
    assert trial["opened_on"] is None


def test_implementations_do_not_embed_a_registry_copy_or_import_product_runtime() -> None:
    assert not list(INTEROP_ROOT.rglob("registry.json"))
    python_source = (INTEROP_ROOT / "python" / "bns019_validator.py").read_text(encoding="utf-8")
    r_source = (INTEROP_ROOT / "r" / "bns019_validator.R").read_text(encoding="utf-8")
    assert "import bionexus" not in python_source.lower()
    assert "bionexus::" not in r_source.lower()
    assert "reticulate" not in r_source.lower()


def test_python_independent_validator_passes_all_published_cases() -> None:
    result = load_python_validator().run_conformance_suite(STANDARD_ROOT)

    assert result["status"] == "PASS"
    assert result["implementation"]["track"] == "independent_validator"
    assert len(result["case_results"]) == 5
    assert {case["status"] for case in result["case_results"]} == {"PASS"}


def test_r_independent_validator_agrees_when_runtime_is_available(tmp_path: Path) -> None:
    rscript = shutil.which("Rscript")
    if not rscript:
        pytest.skip("Rscript is unavailable")
    preflight = subprocess.run(
        [
            rscript,
            "-e",
            "cat(requireNamespace('jsonlite',quietly=TRUE) && requireNamespace('digest',quietly=TRUE))",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if preflight.returncode != 0 or not preflight.stdout.strip().endswith("TRUE"):
        pytest.skip("R jsonlite/digest dependencies are unavailable")

    output = tmp_path / "r-result.json"
    completed = subprocess.run(
        [
            rscript,
            str(INTEROP_ROOT / "r" / "bns019_validator.R"),
            "--standard-root",
            str(STANDARD_ROOT),
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    r_result = json.loads(output.read_text(encoding="utf-8"))
    python_result = load_python_validator().run_conformance_suite(STANDARD_ROOT)
    assert r_result["standard"] == python_result["standard"]
    assert r_result["case_results"] == python_result["case_results"]


def test_scanpy_adapter_contract_and_historical_nextflow_fixture_boundaries() -> None:
    scanpy_source = (INTEROP_ROOT / "scanpy" / "bns019_scanpy_adapter.py").read_text(encoding="utf-8")
    seurat_source = (INTEROP_ROOT / "seurat" / "bns019_seurat_adapter.R").read_text(encoding="utf-8")
    nextflow_source = (INTEROP_ROOT / "nf-core" / "modules" / "local" / "bns019_semconv" / "main.nf").read_text(
        encoding="utf-8"
    )

    assert "adata.uns[HOST_KEY]" in scanpy_source
    assert ".X" not in scanpy_source
    assert ".obs" not in scanpy_source
    assert "object@misc[[HOST_KEY]]" in seurat_source
    assert "@assays" not in seurat_source
    assert "process BNS019_SEMCONV" in nextflow_source
    assert "Historical standalone trial fixture" in nextflow_source
    assert "versions.yml" in nextflow_source


def test_nfcore_adapter_core_binds_release_digest(tmp_path: Path) -> None:
    output = tmp_path / "record.bns019.json"
    versions = tmp_path / "versions.yml"
    completed = subprocess.run(
        [
            sys.executable,
            str(INTEROP_ROOT / "nf-core" / "bin" / "bns019_nfcore_adapter.py"),
            "--validator",
            str(INTEROP_ROOT / "python" / "bns019_validator.py"),
            "--standard-root",
            str(STANDARD_ROOT),
            "--record",
            str(INTEROP_ROOT / "trial" / "fixtures" / "workflow-record.json"),
            "--semantics",
            str(STANDARD_ROOT / "conformance" / "valid" / "observation.json"),
            "--output",
            str(output),
            "--versions",
            str(versions),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    release = json.loads((STANDARD_ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert payload["standard"]["release_digest_sha256"] == release["release_digest_sha256"]
    assert len(payload["scientific_semantics"]["semantic_fingerprint_sha256"]) == 64
    assert release["release_digest_sha256"] in versions.read_text(encoding="utf-8")


def test_zero_touch_rocrate_adapter_is_artifact_addressable_and_non_mutating(tmp_path: Path) -> None:
    adapter = INTEROP_ROOT / "ro-crate" / "bns019_artifact_annotator.py"
    crate = INTEROP_ROOT / "ro-crate" / "fixtures" / "minimal-crate" / "ro-crate-metadata.json"
    declarations = INTEROP_ROOT / "ro-crate" / "fixtures" / "artifact-semantics.json"
    output = tmp_path / "annotations.json"
    before = crate.read_bytes()
    completed = subprocess.run(
        [
            sys.executable,
            str(adapter),
            "--validator",
            str(INTEROP_ROOT / "python" / "bns019_validator.py"),
            "--standard-root",
            str(STANDARD_ROOT),
            "--crate",
            str(crate),
            "--declarations",
            str(declarations),
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert crate.read_bytes() == before
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["provenance_container"]["mutated"] is False
    assert result["inference_policy"] == "EXPLICIT_ONLY_NO_FILENAME_CONTENT_OR_WORKFLOW_SHAPE_INFERENCE"
    assert [item["entity_id"] for item in result["annotations"]] == [
        "artifacts/gene_counts.tsv",
        "artifacts/log_expression.tsv",
    ]
    assert result["annotations"][0]["semantic_envelope"]["attributes"] == {
        "biological.unit": "sample",
        "matrix.state": "raw_counts",
    }
    assert result["annotations"][1]["semantic_envelope"]["attributes"]["matrix.state"] == "log_normalized"
    assert "artifacts/report.html" in result["unannotated_entities_observed"]


def test_zero_touch_rocrate_adapter_refuses_hash_mismatch_and_run_level_semantics(tmp_path: Path) -> None:
    source = json.loads(
        (INTEROP_ROOT / "ro-crate" / "fixtures" / "artifact-semantics.json").read_text(encoding="utf-8")
    )
    source["annotations"][0]["expected_sha256"] = "0" * 64
    source["attributes"] = {"biological.unit": "sample"}
    declarations = tmp_path / "bad-declarations.json"
    declarations.write_text(json.dumps(source), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(INTEROP_ROOT / "ro-crate" / "bns019_artifact_annotator.py"),
            "--validator",
            str(INTEROP_ROOT / "python" / "bns019_validator.py"),
            "--standard-root",
            str(STANDARD_ROOT),
            "--crate",
            str(INTEROP_ROOT / "ro-crate" / "fixtures" / "minimal-crate" / "ro-crate-metadata.json"),
            "--declarations",
            str(declarations),
            "--output",
            str(tmp_path / "out.json"),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 2
    assert "run-level attributes are forbidden" in completed.stderr


def test_zero_touch_adapter_contains_no_pipeline_shape_or_samplesheet_logic() -> None:
    source = (INTEROP_ROOT / "ro-crate" / "bns019_artifact_annotator.py").read_text(encoding="utf-8")
    executable_source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith('"'))
    assert "parse_samplesheet" not in executable_source
    assert "nextflow run" not in executable_source.lower()
    assert "evidence_maturity" not in executable_source


def test_hosted_interoperability_gate_exercises_zero_touch_surface_only() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "bns019-interoperability.yml").read_text(
        encoding="utf-8"
    )
    assert "zero-touch-rocrate:" in workflow
    assert "bns019_artifact_annotator.py" in workflow
    assert "nf-core/setup-nextflow" not in workflow
    assert "nextflow run" not in workflow
    assert "--confcutdir=tests/unit" in workflow


def test_scoreboard_cannot_claim_public_success_without_external_submission() -> None:
    scoreboard = json.loads((INTEROP_ROOT / "trial" / "results" / "scoreboard.json").read_text(encoding="utf-8"))
    assert scoreboard["accepted_external_submissions"] == []
    assert scoreboard["public_success_gate"] == "NOT_MET"
    assert scoreboard["publication_status"] == "open_on_publication"


def test_external_engagement_registry_cannot_self_promote_private_feedback() -> None:
    root = REPOSITORY_ROOT / "standards" / "external-engagement"
    registry = json.loads((root / "EXTERNAL_ENGAGEMENT_REGISTRY.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (root / "schemas" / "external-engagement-registry.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(registry)
    assert registry["records"] == []
    derived = {state: 0 for state in registry["state_definitions"]}
    for record in registry["records"]:
        derived[record["state"]] += 1
    assert registry["observed_counts"] == derived
    assert all(count == 0 for count in registry["observed_counts"].values())


def test_result_and_future_submission_contracts_are_machine_enforced() -> None:
    trial_root = INTEROP_ROOT / "trial"
    result_schema = json.loads((trial_root / "schemas" / "trial-run-result.schema.json").read_text(encoding="utf-8"))
    submission_schema = json.loads((trial_root / "schemas" / "submission.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(result_schema)
    Draft202012Validator.check_schema(submission_schema)

    local_result = json.loads((trial_root / "results" / "local-maintainer-run.json").read_text(encoding="utf-8"))
    Draft202012Validator(result_schema).validate(local_result)
    assert local_result["overall_status"] == "INCOMPLETE"
    assert (
        next(item for item in local_result["tracks"] if item["id"] == "nfcore-nextflow-adapter")["status"] == "NOT_RUN"
    )

    for submission in (trial_root / "submissions").glob("*/submission.json"):
        payload = json.loads(submission.read_text(encoding="utf-8"))
        Draft202012Validator(submission_schema).validate(payload)
        artifact = trial_root / payload["result_artifact"]["path"]
        assert artifact.is_file()
        assert load_python_validator().sha256_file(artifact) == payload["result_artifact"]["sha256"]
