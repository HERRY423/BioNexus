from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import pytest

from bionexus.cryptographic_verifier import (
    compute_file_sha256,
    verify_study_provenance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# =====================================================================
# 1. Zero Private Key & Secret Leakage Auditing
# =====================================================================

FORBIDDEN_KEY_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"-----BEGIN RSA PRIVATE KEY-----"),
    re.compile(r"-----BEGIN EC PRIVATE KEY-----"),
    re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"),
    re.compile(r"Secret-Material", re.IGNORECASE),
    re.compile(r"BioNexus-Independent-Authority-Key", re.IGNORECASE),
    re.compile(r"BioNexus-Authority-Root-2026-Secret", re.IGNORECASE),
    re.compile(r"BioNexus-Rekor-Log-Root-2026-Secret", re.IGNORECASE),
    re.compile(r"BioNexus-TSA-Authority-Root-2026-Secret", re.IGNORECASE),
]

IGNORED_SCAN_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    "venv",
    ".venv",
    "node_modules",
}


def test_zero_private_keys_or_secret_seeds_in_repository():
    """Verify that NO private keys, seeds, or hardcoded secrets exist in tracked files."""
    violations: List[str] = []

    for file_path in REPO_ROOT.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in file_path.parts for part in IGNORED_SCAN_PARTS):
            continue
        # Only inspect code, config, documentation, and data manifests
        if file_path.suffix not in (".py", ".json", ".md", ".yaml", ".yml", ".txt", ".toml", ".sh", ".ps1"):
            continue

        # Skip this test file itself for the pattern literal definitions
        if file_path.name == "test_security_audit.py":
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pat in FORBIDDEN_KEY_PATTERNS:
            if pat.search(content):
                violations.append(f"Secret / private key pattern '{pat.pattern}' detected in {file_path.relative_to(REPO_ROOT)}")

    assert len(violations) == 0, "Secret leaks detected in repository:\n" + "\n".join(violations)


# =====================================================================
# 2. Provenance & Study Artifact Deep Hash Consistency
# =====================================================================

@pytest.mark.parametrize("study_id", ["BN-PB-IV-004", "BN-PB-IV-005"])
def test_study_internal_hash_consistency(study_id: str):
    """Verify exact internal SHA-256 consistency across all study artifacts and sidecars."""
    study_dir = REPO_ROOT / "validation" / "pseudobulk" / "studies" / study_id
    assert study_dir.is_dir(), f"Study directory missing: {study_dir}"

    prereg_path = study_dir / "PREREGISTRATION.json"
    lock_path = study_dir / "PREREGISTRATION_LOCK.json"
    report_path = study_dir / "REPORT.json"
    freeze_path = study_dir / "NEGATIVE_RESULT_FREEZE.json"
    attestation_path = study_dir / "INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json"
    unblind_path = study_dir / "UNBLINDING_MANIFEST.json"
    prov_path = study_dir / "PROVENANCE.json"
    bundle_path = study_dir / "ATTESTATION_BUNDLE.json"
    receipt_path = study_dir / "VERIFICATION_RECEIPT.json"

    # 1. Preregistration Lock Consistency
    assert prereg_path.is_file() and lock_path.is_file()
    prereg_sha = compute_file_sha256(prereg_path)
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock_data.get("preregistration_sha256") == prereg_sha

    # 2. Blinded Packet Manifest Consistency
    packet_dir = study_dir / "blinded_packet"
    packet_manifest_path = packet_dir / "BLINDED_PACKET_MANIFEST.json"
    packet_manifest_sha = None
    if packet_manifest_path.is_file():
        packet_manifest_sha = compute_file_sha256(packet_manifest_path)
        packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
        for entry in packet_manifest.get("files", []):
            rel_file = packet_dir / entry.get("file")
            if rel_file.is_file():
                assert compute_file_sha256(rel_file) == entry.get("sha256")

    # 3. Biostatistician Attestation Consistency
    assert attestation_path.is_file()
    att_sha = compute_file_sha256(attestation_path)
    att_data = json.loads(attestation_path.read_text(encoding="utf-8"))
    assert att_data.get("status") == "SIGNED_COMPLETE"
    assert att_data.get("materials", {}).get("preregistration_sha256") == prereg_sha
    if packet_manifest_sha:
        assert att_data.get("materials", {}).get("blinded_packet_sha256") == packet_manifest_sha

    # 4. Unblinding Manifest Consistency
    assert unblind_path.is_file()
    unb_data = json.loads(unblind_path.read_text(encoding="utf-8"))
    assert unb_data.get("biostatistician_attestation_sha256") == att_sha

    # 5. Study Report Consistency
    assert report_path.is_file()
    rep_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert rep_data.get("preregistration", {}).get("sha256") == prereg_sha
    assert rep_data.get("biostatistician_review", {}).get("sha256") == att_sha

    # 6. Negative Result Freeze Integrity
    assert freeze_path.is_file()
    freeze_data = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze_data.get("result", {}).get("run_status") == "negative_result"
    assert freeze_data.get("result", {}).get("conclusion_maturity") == "FRAGILE"
    assert freeze_data.get("result", {}).get("independent_biological_validation") == "not_supported"
    for art in freeze_data.get("artifacts", []):
        art_path = study_dir / art.get("path")
        assert art_path.is_file(), f"Frozen artifact {art.get('path')} missing"
        assert compute_file_sha256(art_path) == art.get("sha256"), f"Frozen artifact SHA mismatch for {art.get('path')}"

    # 7. Provenance Sidecar Consistency
    assert prov_path.is_file()
    prov_data = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov_data.get("execution_provenance", {}).get("git_dirty") is False
    for in_entry in prov_data.get("input_files", []):
        p = Path(in_entry.get("path", ""))
        if not p.is_file():
            p = study_dir / in_entry.get("file_name", "")
        if not p.is_file():
            p = study_dir / "blinded_packet" / in_entry.get("file_name", "")
        assert p.is_file(), f"Declared input file missing: {in_entry.get('file_name')}"
        assert compute_file_sha256(p) == in_entry.get("sha256")

    for out_entry in prov_data.get("output_files", []):
        p = Path(out_entry.get("path", ""))
        if not p.is_file():
            p = study_dir / out_entry.get("file_name", "")
        if not p.is_file():
            p = study_dir / "evidence" / out_entry.get("file_name", "")
        assert p.is_file(), f"Declared output file missing: {out_entry.get('file_name')}"
        assert compute_file_sha256(p) == out_entry.get("sha256")

    crypto_att = prov_data.get("cryptographic_attestation", {})
    assert crypto_att.get("trust_root_id") == "bionexus-independent-root-2026"
    assert crypto_att.get("bundle_file") == "ATTESTATION_BUNDLE.json"
    assert crypto_att.get("receipt_file") == "VERIFICATION_RECEIPT.json"
    assert bundle_path.is_file(), f"Attestation bundle missing: {bundle_path}"
    assert receipt_path.is_file(), f"Verification receipt missing: {receipt_path}"

    # 8. Overall Study Verification Pass
    report = verify_study_provenance(study_dir)
    assert report.status == "PASS_VERIFIED"
    assert len(report.issues) == 0
    assert report.is_tamper_evident is True


# =====================================================================
# 3. Negative Result Scientific Integrity Permanence
# =====================================================================

def test_scientific_freeze_permanence():
    """Verify that failed endpoints are permanently retained and cannot be overwritten."""
    for study_id, expected_p in [("BN-PB-IV-004", 0.2209), ("BN-PB-IV-005", 0.3872)]:
        study_dir = REPO_ROOT / "validation" / "pseudobulk" / "studies" / study_id
        freeze_data = json.loads((study_dir / "NEGATIVE_RESULT_FREEZE.json").read_text(encoding="utf-8"))
        report_data = json.loads((study_dir / "REPORT.json").read_text(encoding="utf-8"))

        # Strict immutability checks
        assert freeze_data["policy"]["overwrite_prohibited"] is True
        assert freeze_data["policy"]["reinterpret_as_pass_prohibited"] is True
        assert freeze_data["result"]["run_status"] == "negative_result"
        assert freeze_data["result"]["conclusion_maturity"] == "FRAGILE"
        assert freeze_data["result"]["independent_biological_validation"] == "not_supported"

        assert report_data["status"]["run_status"] == "negative_result"
        assert report_data["status"]["conclusion_maturity"] == "FRAGILE"
        assert report_data["status"]["independent_biological_validation"] == "not_supported"
        assert report_data["endpoints"]["negative_control"]["empirical_p_value"] > 0.05


# =====================================================================
# 4. Tamper Resistance & Negative Testing
# =====================================================================

def test_tamper_detection_in_study_artifacts(tmp_path):
    """Verify that tampering with any primary artifact or provenance record fails verification."""
    import shutil
    src_study = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-004"
    dest_study = tmp_path / "BN-PB-IV-004"
    shutil.copytree(src_study, dest_study)

    # Initial state must pass
    assert verify_study_provenance(dest_study).status == "PASS_VERIFIED"

    # Tamper 1: Modify REPORT.json
    report_file = dest_study / "REPORT.json"
    rep = json.loads(report_file.read_text(encoding="utf-8"))
    rep["conclusion_maturity"] = "SUPPORTED"  # Fraudulent promotion
    report_file.write_text(json.dumps(rep, indent=2), encoding="utf-8")

    tampered_result = verify_study_provenance(dest_study)
    assert tampered_result.status == "FAIL_TAMPER_DETECTED"
    assert any("Merkle root mismatch" in issue or "signature" in issue for issue in tampered_result.issues)
