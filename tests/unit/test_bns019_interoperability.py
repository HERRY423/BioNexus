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


def test_scanpy_adapter_contract_is_uns_only_and_nfcore_is_not_counted_without_nextflow() -> None:
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


def test_scoreboard_cannot_claim_public_success_without_external_submission() -> None:
    scoreboard = json.loads((INTEROP_ROOT / "trial" / "results" / "scoreboard.json").read_text(encoding="utf-8"))
    assert scoreboard["accepted_external_submissions"] == []
    assert scoreboard["public_success_gate"] == "NOT_MET"
    assert scoreboard["publication_status"] == "open_on_publication"


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
