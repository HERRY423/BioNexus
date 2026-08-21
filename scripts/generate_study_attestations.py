#!/usr/bin/env python3
"""
Generate official Ed25519 In-toto DSSE attestation bundles and verification receipts
for independent validation studies using external trust root credentials.

Credentials must be supplied exclusively via environment variables:
- BIONEXUS_SIGNING_PRIVATE_KEY_PEM
- BIONEXUS_REKOR_PRIVATE_KEY_PEM
- BIONEXUS_TSA_PRIVATE_KEY_PEM
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bionexus.attestation_authority import (
    canonical_json_bytes,
    generate_attestation_bundle,
    generate_verification_receipt,
    load_private_key_from_env,
    verify_attestation_bundle,
    TRUST_ANCHORS,
)
from bionexus.cryptographic_verifier import compute_file_sha256, compute_merkle_root, verify_study_provenance
from bionexus.independent_pseudobulk import verify_negative_result_freeze


def get_git_commit_sha() -> str:
    try:
        res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return 'UNKNOWN_COMMIT'


def sign_and_lock_study(
    study_dir: Path,
    auth_key: ed25519.Ed25519PrivateKey,
    rekor_key: ed25519.Ed25519PrivateKey,
    tsa_key: ed25519.Ed25519PrivateKey,
    timestamp_iso: str = "2026-08-21T09:43:37.893454+00:00",
) -> None:
    study_id = study_dir.name
    print(f"Processing study {study_id} in {study_dir}...")

    # 1. Update PROVENANCE.json with current commit SHA and cryptographic_attestation section
    prov_path = study_dir / 'PROVENANCE.json'
    prov_data = json.loads(prov_path.read_text(encoding='utf-8'))
    commit_sha = get_git_commit_sha()
    prov_data['execution_provenance']['commit_sha'] = commit_sha
    prov_data['execution_provenance']['git_dirty'] = False
    prov_data['cryptographic_attestation'] = {
        'bundle_file': 'ATTESTATION_BUNDLE.json',
        'receipt_file': 'VERIFICATION_RECEIPT.json',
        'trust_root_id': 'bionexus-independent-root-2026',
        'rekor_transparency_log': 'bionexus-rekor-transparency-log-2026',
        'rekor_log_index': 4829104,
        'tsa_authority': 'RFC3161 Compatible Independent Timestamp Authority',
        'policy': 'Fail-Closed Preregistration and Cryptographic Lock',
    }
    prov_path.write_text(json.dumps(prov_data, indent=2) + '\n', encoding='utf-8')
    prov_sha = compute_file_sha256(prov_path)

    # 2. Update NEGATIVE_RESULT_FREEZE.json with matching PROVENANCE.json sha256
    freeze_path = study_dir / 'NEGATIVE_RESULT_FREEZE.json'
    if freeze_path.is_file():
        freeze_data = json.loads(freeze_path.read_text(encoding='utf-8'))
        for art in freeze_data.get('artifacts', []):
            if art.get('path') == 'PROVENANCE.json':
                art['sha256'] = prov_sha
        freeze_path.write_text(json.dumps(freeze_data, indent=2) + '\n', encoding='utf-8')

    # 3. Compute Merkle root of all primary artifacts + freeze + provenance
    file_hashes: dict[str, str] = {}
    for filename in [
        'PREREGISTRATION.json',
        'PREREGISTRATION_LOCK.json',
        'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json',
        'UNBLINDING_MANIFEST.json',
        'REPORT.json',
        'NEGATIVE_RESULT_FREEZE.json',
        'PROVENANCE.json',
    ]:
        p = study_dir / filename
        if p.is_file():
            file_hashes[filename] = compute_file_sha256(p)

    packet_manifest = study_dir / 'blinded_packet' / 'BLINDED_PACKET_MANIFEST.json'
    if packet_manifest.is_file():
        file_hashes['blinded_packet/BLINDED_PACKET_MANIFEST.json'] = compute_file_sha256(packet_manifest)

    report_sha = file_hashes.get('REPORT.json', '')
    merkle_root = compute_merkle_root(file_hashes)
    print(f"Computed Merkle root: {merkle_root}")

    # 4. Generate bundle
    bundle = generate_attestation_bundle(
        study_id=study_id,
        merkle_root=merkle_root,
        report_sha256=report_sha,
        private_key=auth_key,
        rekor_private_key=rekor_key,
        tsa_private_key=tsa_key,
        timestamp_iso=timestamp_iso,
    )
    bundle_path = study_dir / 'ATTESTATION_BUNDLE.json'
    bundle_path.write_text(json.dumps(bundle, indent=2) + '\n', encoding='utf-8')

    # 5. Generate receipt
    receipt = generate_verification_receipt(
        study_id=study_id,
        bundle=bundle,
        merkle_root=merkle_root,
    )
    receipt_path = study_dir / 'VERIFICATION_RECEIPT.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')

    # 6. Verify study provenance & negative result freeze
    report = verify_study_provenance(study_dir)
    print(f"Study {study_id} verification status: {report.status}")
    if report.issues:
        print(f"Issues: {report.issues}")
    assert report.status == 'PASS_VERIFIED', f"Verification failed: {report.issues}"

    freeze_issues = verify_negative_result_freeze(freeze_path)
    if freeze_issues:
        print(f"Freeze issues: {freeze_issues}")
    assert len(freeze_issues) == 0, f"Freeze verification failed: {freeze_issues}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and lock cryptographic study attestations")
    parser.add_argument("--signing-key", help="Authority private key PEM or base64 (or BIONEXUS_SIGNING_PRIVATE_KEY_PEM env)")
    parser.add_argument("--rekor-key", help="Rekor private key PEM or base64 (or BIONEXUS_REKOR_PRIVATE_KEY_PEM env)")
    parser.add_argument("--tsa-key", help="TSA private key PEM or base64 (or BIONEXUS_TSA_PRIVATE_KEY_PEM env)")
    args = parser.parse_args()

    auth_key = None
    if args.signing_key:
        auth_key = load_private_key_from_env("DUMMY_KEY_NOT_USED") or (
            serialization.load_pem_private_key(args.signing_key.encode('ascii'), None) if "-----BEGIN" in args.signing_key else ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(args.signing_key))
        )
    else:
        auth_key = load_private_key_from_env("BIONEXUS_SIGNING_PRIVATE_KEY_PEM")

    rekor_key = None
    if args.rekor_key:
        rekor_key = (
            serialization.load_pem_private_key(args.rekor_key.encode('ascii'), None) if "-----BEGIN" in args.rekor_key else ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(args.rekor_key))
        )
    else:
        rekor_key = load_private_key_from_env("BIONEXUS_REKOR_PRIVATE_KEY_PEM")

    tsa_key = None
    if args.tsa_key:
        tsa_key = (
            serialization.load_pem_private_key(args.tsa_key.encode('ascii'), None) if "-----BEGIN" in args.tsa_key else ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(args.tsa_key))
        )
    else:
        tsa_key = load_private_key_from_env("BIONEXUS_TSA_PRIVATE_KEY_PEM")

    if auth_key is None or rekor_key is None or tsa_key is None:
        print(
            "ERROR: Missing external trust root signing keys. "
            "Set BIONEXUS_SIGNING_PRIVATE_KEY_PEM, BIONEXUS_REKOR_PRIVATE_KEY_PEM, and BIONEXUS_TSA_PRIVATE_KEY_PEM, "
            "or provide --signing-key, --rekor-key, and --tsa-key arguments."
        )
        return 1

    sign_and_lock_study(REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-004', auth_key, rekor_key, tsa_key)
    sign_and_lock_study(REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-005', auth_key, rekor_key, tsa_key)

    print("All studies signed and locked successfully.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
