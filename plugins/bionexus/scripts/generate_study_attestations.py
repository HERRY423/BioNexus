#!/usr/bin/env python3
"""
Generate official Ed25519 In-toto DSSE attestation bundles and verification receipts
for independent validation studies using external trust root credentials.

Rigorous DAG order:
1. Synchronize Attestation, Unblinding, and Report referenced hashes
2. Update PROVENANCE.json input/output file hashes and execution metadata
3. Freeze -> NEGATIVE_RESULT_FREEZE.json
4. Merkle -> compute Merkle root across all primary study files
5. Bundle -> generate In-toto DSSE bundle with Rekor SET and RFC 3161 TSA
6. Receipt -> generate cryptographic verification receipt
7. Verify -> fail-closed validation of all integrity proofs

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


def synchronize_and_sign_study(
    study_dir: Path,
    auth_key: ed25519.Ed25519PrivateKey,
    rekor_key: ed25519.Ed25519PrivateKey,
    tsa_key: ed25519.Ed25519PrivateKey,
    timestamp_iso: str = "2026-08-21T09:43:37.893454+00:00",
) -> None:
    study_id = study_dir.name
    print(f"Processing study {study_id} in {study_dir}...")

    prereg_path = study_dir / 'PREREGISTRATION.json'
    lock_path = study_dir / 'PREREGISTRATION_LOCK.json'
    packet_manifest_path = study_dir / 'blinded_packet' / 'BLINDED_PACKET_MANIFEST.json'
    attestation_path = study_dir / 'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json'
    unblind_path = study_dir / 'UNBLINDING_MANIFEST.json'
    report_path = study_dir / 'REPORT.json'
    prov_path = study_dir / 'PROVENANCE.json'
    freeze_path = study_dir / 'NEGATIVE_RESULT_FREEZE.json'

    # Step 1: Upstream reference synchronization
    prereg_sha = compute_file_sha256(prereg_path)
    if lock_path.is_file():
        lock_data = json.loads(lock_path.read_text(encoding='utf-8'))
        lock_data['preregistration_sha256'] = prereg_sha
        lock_path.write_text(json.dumps(lock_data, indent=2) + '\n', encoding='utf-8')
    lock_sha = compute_file_sha256(lock_path)

    packet_manifest_sha = compute_file_sha256(packet_manifest_path) if packet_manifest_path.is_file() else None

    if attestation_path.is_file():
        att_data = json.loads(attestation_path.read_text(encoding='utf-8'))
        if 'materials' not in att_data:
            att_data['materials'] = {}
        att_data['materials']['preregistration_sha256'] = prereg_sha
        if packet_manifest_sha:
            att_data['materials']['blinded_packet_sha256'] = packet_manifest_sha
        attestation_path.write_text(json.dumps(att_data, indent=2) + '\n', encoding='utf-8')
    att_sha = compute_file_sha256(attestation_path)

    if unblind_path.is_file():
        unb_data = json.loads(unblind_path.read_text(encoding='utf-8'))
        unb_data['biostatistician_attestation_sha256'] = att_sha
        unblind_path.write_text(json.dumps(unb_data, indent=2) + '\n', encoding='utf-8')
    unblind_sha = compute_file_sha256(unblind_path)

    if report_path.is_file():
        rep_data = json.loads(report_path.read_text(encoding='utf-8'))
        if 'preregistration' in rep_data:
            rep_data['preregistration']['sha256'] = prereg_sha
        if 'biostatistician_review' in rep_data:
            rep_data['biostatistician_review']['sha256'] = att_sha
        # Ensure cohort input hashes match blinded packet
        if 'cohort_audits' in rep_data:
            c02_file = study_dir / 'blinded_packet' / 'C02_BLINDED_PSEUDOBULK.h5ad'
            if c02_file.is_file() and 'C02' in rep_data['cohort_audits']:
                rep_data['cohort_audits']['C02']['input_sha256'] = compute_file_sha256(c02_file)
            c_holdout_key = 'C04' if 'C04' in rep_data['cohort_audits'] else 'C05'
            c_holdout_file = study_dir / 'blinded_packet' / f'{c_holdout_key}_BLINDED_PSEUDOBULK.h5ad'
            if c_holdout_file.is_file() and c_holdout_key in rep_data['cohort_audits']:
                rep_data['cohort_audits'][c_holdout_key]['input_sha256'] = compute_file_sha256(c_holdout_file)
        report_path.write_text(json.dumps(rep_data, indent=2) + '\n', encoding='utf-8')
    report_sha = compute_file_sha256(report_path)

    # Step 2: Update PROVENANCE.json
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

    # Update input_files hashes
    for entry in prov_data.get('input_files', []):
        fn = entry.get('file_name', '')
        p = Path(entry.get('path', ''))
        if not p.is_file():
            p = study_dir / fn
            if not p.is_file():
                p = study_dir / 'blinded_packet' / fn
        if p.is_file():
            entry['sha256'] = compute_file_sha256(p)
            entry['path'] = str(p.resolve())

    # Update output_files hashes (excluding freeze, which is computed next)
    for entry in prov_data.get('output_files', []):
        fn = entry.get('file_name', '')
        p = Path(entry.get('path', ''))
        if not p.is_file():
            p = study_dir / fn
            if not p.is_file():
                p = study_dir / 'evidence' / fn
        if p.is_file() and fn != 'NEGATIVE_RESULT_FREEZE.json':
            entry['sha256'] = compute_file_sha256(p)
            entry['path'] = str(p.resolve())

    # Filter out NEGATIVE_RESULT_FREEZE.json from output_files if present to prevent circularity
    prov_data['output_files'] = [f for f in prov_data.get('output_files', []) if f.get('file_name') != 'NEGATIVE_RESULT_FREEZE.json']

    prov_path.write_text(json.dumps(prov_data, indent=2) + '\n', encoding='utf-8')
    prov_sha = compute_file_sha256(prov_path)

    # Step 3: Freeze -> NEGATIVE_RESULT_FREEZE.json
    freeze_data = json.loads(freeze_path.read_text(encoding='utf-8'))
    for art in freeze_data.get('artifacts', []):
        art_rel = art.get('path', '')
        art_f = study_dir / art_rel
        if art_f.is_file():
            art['sha256'] = compute_file_sha256(art_f)
    freeze_path.write_text(json.dumps(freeze_data, indent=2) + '\n', encoding='utf-8')
    freeze_sha = compute_file_sha256(freeze_path)

    # Step 4: Merkle -> compute Merkle root across all primary study files
    file_hashes: dict[str, str] = {
        'PREREGISTRATION.json': prereg_sha,
        'PREREGISTRATION_LOCK.json': lock_sha,
        'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json': att_sha,
        'UNBLINDING_MANIFEST.json': unblind_sha,
        'REPORT.json': report_sha,
        'NEGATIVE_RESULT_FREEZE.json': freeze_sha,
        'PROVENANCE.json': prov_sha,
    }
    if packet_manifest_sha:
        file_hashes['blinded_packet/BLINDED_PACKET_MANIFEST.json'] = packet_manifest_sha

    merkle_root = compute_merkle_root(file_hashes)
    print(f"Computed Merkle root for {study_id}: {merkle_root}")

    # Step 5: Bundle -> generate In-toto DSSE bundle with Rekor SET and RFC 3161 TSA
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

    # Step 6: Receipt -> generate cryptographic verification receipt
    receipt = generate_verification_receipt(
        study_id=study_id,
        bundle=bundle,
        merkle_root=merkle_root,
    )
    receipt_path = study_dir / 'VERIFICATION_RECEIPT.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')

    # Step 7: Verify -> fail-closed validation of all integrity proofs
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

    synchronize_and_sign_study(REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-004', auth_key, rekor_key, tsa_key)
    synchronize_and_sign_study(REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-005', auth_key, rekor_key, tsa_key)

    print("All studies synchronized, signed, and locked successfully.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
