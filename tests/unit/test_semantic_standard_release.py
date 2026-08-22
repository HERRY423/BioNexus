"""Release-boundary tests for the language-neutral BNS-019 distribution."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bionexus.scientific_semantics import (
    DEFAULT_SEMANTIC_STANDARD_ROOT,
    SEMANTIC_STANDARD_ROOT_ENV,
    ScientificSemanticError,
    ScientificSemanticRegistry,
    SemanticStandardRelease,
    default_scientific_semantic_registry,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_public_distribution_is_verified_and_is_the_python_source() -> None:
    release = SemanticStandardRelease.load(DEFAULT_SEMANTIC_STANDARD_ROOT)
    registry = default_scientific_semantic_registry()
    manifest = json.loads(
        (DEFAULT_SEMANTIC_STANDARD_ROOT / "release-manifest.json").read_text(encoding="utf-8")
    )

    assert release.version == "0.1.0"
    assert len(release.release_digest_sha256) == 64
    assert registry.release == release
    assert registry.inventory()["standard_id"] == "BNS-019"
    assert registry.inventory()["release_digest_sha256"] == release.release_digest_sha256
    assert manifest["attestation_profile"] == {
        "schema_version": "bionexus.evidence-attestation.v1",
        "predicate_type": "standard-release",
        "subject_type": "scientific-semantic-conventions-release",
        "subject_id": "BNS-019",
        "subject_version": "0.1.0",
        "required_claims": {"release_digest_sha256": release.release_digest_sha256},
    }

    assert not (REPOSITORY_ROOT / "src" / "bionexus" / "data" / "scientific_semantic_conventions.yaml").exists()
    assert not (
        REPOSITORY_ROOT / "src" / "bionexus" / "data" / "scientific_semantic_envelope.schema.json"
    ).exists()


def test_normative_contract_files_are_language_neutral() -> None:
    standard_root = DEFAULT_SEMANTIC_STANDARD_ROOT
    normative_paths = [
        standard_root / "registry.json",
        *sorted((standard_root / "schemas").glob("*.json")),
        standard_root / "conformance" / "manifest.json",
        *sorted((standard_root / "conformance" / "valid").glob("*.json")),
        *sorted((standard_root / "conformance" / "invalid").glob("*.json")),
    ]
    assert normative_paths
    for path in normative_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload is not None
        text = path.read_text(encoding="utf-8").lower()
        assert "src/bionexus" not in text
        assert "import bionexus" not in text
        assert ".py" not in text


def test_language_neutral_conformance_cases_match_reference_consumer() -> None:
    registry = ScientificSemanticRegistry.load(DEFAULT_SEMANTIC_STANDARD_ROOT)
    conformance_root = DEFAULT_SEMANTIC_STANDARD_ROOT / "conformance"
    manifest = json.loads((conformance_root / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["standard_version"] == registry.schema_version
    for case in manifest["cases"]:
        fixture = json.loads((conformance_root / case["input"]).read_text(encoding="utf-8"))
        report = registry.validate_attributes(fixture["convention"], fixture["attributes"])
        assert report.valid is case["expected_valid"], case["id"]
        if report.valid:
            assert report.normalized_attributes == case["expected_normalized_attributes"], case["id"]
        else:
            assert case["expected_failure_class"] in report.failure_classes, case["id"]


def test_explicit_external_standard_root_is_supported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    external_root = tmp_path / "semconv"
    shutil.copytree(DEFAULT_SEMANTIC_STANDARD_ROOT, external_root)
    monkeypatch.setenv(SEMANTIC_STANDARD_ROOT_ENV, str(external_root))

    registry = default_scientific_semantic_registry()

    assert registry.release is not None
    assert registry.release.root == external_root.resolve()


def test_missing_or_tampered_external_release_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_root = tmp_path / "missing"
    monkeypatch.setenv(SEMANTIC_STANDARD_ROOT_ENV, str(missing_root))
    with pytest.raises(ScientificSemanticError, match="not found"):
        default_scientific_semantic_registry()

    tampered_root = tmp_path / "tampered"
    shutil.copytree(DEFAULT_SEMANTIC_STANDARD_ROOT, tampered_root)
    registry_path = tampered_root / "registry.json"
    registry_path.write_text(registry_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    monkeypatch.setenv(SEMANTIC_STANDARD_ROOT_ENV, str(tampered_root))
    with pytest.raises(ScientificSemanticError, match="SHA-256 mismatch: registry.json"):
        default_scientific_semantic_registry()


def test_release_zip_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    script = REPOSITORY_ROOT / "scripts" / "build_semantic_standard_release.py"
    command = [sys.executable, str(script), "--output-dir", str(tmp_path)]
    first = subprocess.run(command, cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True)
    archive = tmp_path / "bionexus-scientific-semantic-conventions-0.1.0.zip"
    first_bytes = archive.read_bytes()
    second = subprocess.run(command, cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True)

    assert first.returncode == second.returncode == 0
    assert archive.read_bytes() == first_bytes
    assert archive.with_suffix(".zip.sha256").is_file()
