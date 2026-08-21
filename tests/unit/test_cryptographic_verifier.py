from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bionexus.attestation_authority import (
    generate_attestation_bundle,
    generate_verification_receipt,
    verify_attestation_bundle,
    SIGNING_PUBLIC_KEY_PEM,
)
from bionexus.cryptographic_verifier import verify_study_provenance
from bionexus.independent_pseudobulk import validate_preregistration, verify_negative_result_freeze

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_signature_verification_positive():
    study_id = 'TEST-STUDY-001'
    merkle_root = 'a' * 64
    report_sha256 = 'b' * 64

    bundle = generate_attestation_bundle(study_id, merkle_root, report_sha256)
    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root=merkle_root)
    assert valid is True
    assert len(errors) == 0

    receipt = generate_verification_receipt(study_id, bundle, merkle_root)
    assert receipt['verification_status'] == 'VALID_VERIFIED'
    assert receipt['signature_verified'] is True


def test_tampered_payload_rejected():
    bundle = generate_attestation_bundle('TEST-002', 'c' * 64, 'd' * 64)
    # Tamper the in-toto payload
    payload_raw = base64.b64decode(bundle['dsseEnvelope']['payload']).decode('utf-8')
    tampered_raw = payload_raw.replace('TEST-002', 'TAMPERED-STUDY')
    bundle['dsseEnvelope']['payload'] = base64.b64encode(tampered_raw.encode('utf-8')).decode('ascii')

    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root='c' * 64)
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_tampered_signature_rejected():
    bundle = generate_attestation_bundle('TEST-003', 'e' * 64, 'f' * 64)
    # Corrupt the signature bytes
    sig_raw = bytearray(base64.b64decode(bundle['dsseEnvelope']['signatures'][0]['sig']))
    sig_raw[0] ^= 0xFF
    bundle['dsseEnvelope']['signatures'][0]['sig'] = base64.b64encode(bytes(sig_raw)).decode('ascii')

    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root='e' * 64)
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_wrong_public_key_rejected():
    bundle = generate_attestation_bundle('TEST-004', '1' * 64, '2' * 64)
    # Generate a different arbitrary Ed25519 key
    wrong_key = ed25519.Ed25519PrivateKey.generate()
    wrong_pem = wrong_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')

    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root='1' * 64, public_key_pem=wrong_pem)
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_invalid_or_future_timestamp_rejected():
    # Future timestamp (10 days in the future)
    future_iso = '2036-01-01T00:00:00+00:00'
    bundle = generate_attestation_bundle('TEST-005', '3' * 64, '4' * 64, timestamp_iso=future_iso)

    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root='3' * 64)
    assert valid is False
    assert any('future' in err.lower() for err in errors)


def test_merkle_root_mismatch_rejected():
    bundle = generate_attestation_bundle('TEST-006', '5' * 64, '6' * 64)
    wrong_root = '7' * 64
    valid, errors = verify_attestation_bundle(bundle, expected_merkle_root=wrong_root)
    assert valid is False
    assert any('Merkle root mismatch' in err for err in errors)


def test_bn_pb_iv_004_negative_result_freeze_and_provenance():
    study_dir = REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-004'
    report = verify_study_provenance(study_dir)
    assert report.status == 'PASS_VERIFIED'
    assert len(report.issues) == 0
    assert report.is_tamper_evident is True

    freeze_issues = verify_negative_result_freeze(study_dir / 'NEGATIVE_RESULT_FREEZE.json')
    assert len(freeze_issues) == 0


def test_bn_pb_iv_005_negative_result_freeze_and_provenance():
    study_dir = REPO_ROOT / 'validation' / 'pseudobulk' / 'studies' / 'BN-PB-IV-005'
    prereg_path = study_dir / 'PREREGISTRATION.json'
    lock_path = study_dir / 'PREREGISTRATION_LOCK.json'

    prereg = json.loads(prereg_path.read_text(encoding='utf-8'))
    lock = json.loads(lock_path.read_text(encoding='utf-8'))

    issues = validate_preregistration(prereg, lock, prereg_path)
    assert len(issues) == 0
    assert prereg['predecessor_results']['BN-PB-IV-004']['status'] == 'negative_result'

    report = verify_study_provenance(study_dir)
    assert report.status == 'PASS_VERIFIED'
    assert len(report.issues) == 0

    freeze_issues = verify_negative_result_freeze(study_dir / 'NEGATIVE_RESULT_FREEZE.json')
    assert len(freeze_issues) == 0