from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from bionexus.attestation_authority import (
    generate_attestation_bundle,
    generate_ephemeral_signing_key,
    generate_rekor_transparency_proof,
    generate_tsa_timestamp_token,
    generate_verification_receipt,
    verify_attestation_bundle,
    verify_rekor_transparency_proof,
    verify_tsa_timestamp_token,
)
from bionexus.cryptographic_verifier import verify_study_provenance
from bionexus.independent_pseudobulk import validate_preregistration, verify_negative_result_freeze

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def test_keys():
    auth_key = generate_ephemeral_signing_key()
    rekor_key = generate_ephemeral_signing_key()
    tsa_key = generate_ephemeral_signing_key()
    return {
        'auth': auth_key,
        'rekor': rekor_key,
        'tsa': tsa_key,
        'auth_pem': auth_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii'),
        'rekor_pem': rekor_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii'),
        'tsa_pem': tsa_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii'),
    }


def test_signature_verification_positive(test_keys):
    study_id = 'TEST-STUDY-001'
    merkle_root = 'a' * 64
    report_sha256 = 'b' * 64

    bundle = generate_attestation_bundle(
        study_id,
        merkle_root,
        report_sha256,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root=merkle_root,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is True
    assert len(errors) == 0

    receipt = generate_verification_receipt(
        study_id,
        bundle,
        merkle_root,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert receipt['verification_status'] == 'VALID_VERIFIED'
    assert receipt['signature_verified'] is True
    assert receipt['rekor_transparency_log']['verified'] is True
    assert receipt['timestamp_authority']['verified'] is True


def test_tampered_payload_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-002',
        'c' * 64,
        'd' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Tamper the in-toto payload
    payload_raw = base64.b64decode(bundle['dsseEnvelope']['payload']).decode('utf-8')
    tampered_raw = payload_raw.replace('TEST-002', 'TAMPERED-STUDY')
    bundle['dsseEnvelope']['payload'] = base64.b64encode(tampered_raw.encode('utf-8')).decode('ascii')

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='c' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_tampered_signature_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-003',
        'e' * 64,
        'f' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Corrupt the signature bytes
    sig_raw = bytearray(base64.b64decode(bundle['dsseEnvelope']['signatures'][0]['sig']))
    sig_raw[0] ^= 0xFF
    bundle['dsseEnvelope']['signatures'][0]['sig'] = base64.b64encode(bytes(sig_raw)).decode('ascii')

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='e' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_wrong_public_key_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-004',
        '1' * 64,
        '2' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Generate a different arbitrary Ed25519 key
    wrong_key = generate_ephemeral_signing_key()
    wrong_pem = wrong_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='1' * 64,
        public_key_pem=wrong_pem,
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid Ed25519 cryptographic signature' in err for err in errors)


def test_rekor_set_tampering_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-REKOR-001',
        'a' * 64,
        'b' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Corrupt SET signature
    raw_set = bytearray(base64.b64decode(bundle['verificationMaterial']['tlogEntries'][0]['inclusionPromise']['signedEntryTimestamp']))
    raw_set[0] ^= 0xFF
    bundle['verificationMaterial']['tlogEntries'][0]['inclusionPromise']['signedEntryTimestamp'] = base64.b64encode(bytes(raw_set)).decode('ascii')

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='a' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid Rekor SET signature' in err for err in errors)


def test_rekor_untrusted_log_id_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-REKOR-002',
        'a' * 64,
        'b' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Change Rekor logId to untrusted key
    bundle['verificationMaterial']['tlogEntries'][0]['logId']['keyId'] = '0' * 64

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='a' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Rekor logId mismatch' in err for err in errors)


def test_tsa_signature_tampering_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-TSA-001',
        'a' * 64,
        'b' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Corrupt TSA signature
    raw_tsa = bytearray(base64.b64decode(bundle['verificationMaterial']['timestampVerification']['tsaSignature']))
    raw_tsa[0] ^= 0xFF
    bundle['verificationMaterial']['timestampVerification']['tsaSignature'] = base64.b64encode(bytes(raw_tsa)).decode('ascii')

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='a' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid TSA cryptographic signature' in err for err in errors)


def test_tsa_imprint_mismatch_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-TSA-002',
        'a' * 64,
        'b' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    # Alter TSA message imprint
    bundle['verificationMaterial']['timestampVerification']['imprint']['digest'] = 'f' * 64

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='a' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('TSA message imprint digest mismatch' in err for err in errors)


def test_invalid_or_future_timestamp_rejected(test_keys):
    future_iso = '2036-01-01T00:00:00+00:00'
    bundle = generate_attestation_bundle(
        'TEST-005',
        '3' * 64,
        '4' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
        timestamp_iso=future_iso,
    )

    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root='3' * 64,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('future' in err.lower() for err in errors)


def test_merkle_root_mismatch_rejected(test_keys):
    bundle = generate_attestation_bundle(
        'TEST-006',
        '5' * 64,
        '6' * 64,
        private_key=test_keys['auth'],
        rekor_private_key=test_keys['rekor'],
        tsa_private_key=test_keys['tsa'],
    )
    wrong_root = '7' * 64
    valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root=wrong_root,
        public_key_pem=test_keys['auth_pem'],
        rekor_public_key_pem=test_keys['rekor_pem'],
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Merkle root mismatch' in err for err in errors)


def test_missing_attestation_bundle_rejected(tmp_path):
    study_dir = tmp_path / 'study'
    study_dir.mkdir()
    (study_dir / 'PREREGISTRATION.json').write_text(json.dumps({'study_id': 'MOCK-001'}), encoding='utf-8')
    (study_dir / 'PREREGISTRATION_LOCK.json').write_text(json.dumps({'preregistration_sha256': 'mock'}), encoding='utf-8')
    (study_dir / 'REPORT.json').write_text(json.dumps({'run_status': 'negative_result'}), encoding='utf-8')
    (study_dir / 'NEGATIVE_RESULT_FREEZE.json').write_text(json.dumps({'policy': 'lock'}), encoding='utf-8')
    (study_dir / 'PROVENANCE.json').write_text(json.dumps({'execution_provenance': {'git_dirty': False}}), encoding='utf-8')

    report = verify_study_provenance(study_dir)
    assert report.status == 'FAIL_TAMPER_DETECTED'
    assert any('missing ATTESTATION_BUNDLE.json' in issue for issue in report.issues)


def test_provenance_dirty_tree_rejected(tmp_path):
    study_dir = tmp_path / 'study'
    study_dir.mkdir()
    (study_dir / 'PREREGISTRATION.json').write_text(json.dumps({'study_id': 'MOCK-002'}), encoding='utf-8')
    (study_dir / 'PREREGISTRATION_LOCK.json').write_text(json.dumps({'preregistration_sha256': 'mock'}), encoding='utf-8')
    (study_dir / 'REPORT.json').write_text(json.dumps({'run_status': 'negative_result'}), encoding='utf-8')
    (study_dir / 'NEGATIVE_RESULT_FREEZE.json').write_text(json.dumps({'policy': 'lock'}), encoding='utf-8')
    (study_dir / 'ATTESTATION_BUNDLE.json').write_text(json.dumps({}), encoding='utf-8')
    (study_dir / 'VERIFICATION_RECEIPT.json').write_text(json.dumps({'verification_status': 'VALID_VERIFIED', 'signature_verified': True}), encoding='utf-8')
    (study_dir / 'PROVENANCE.json').write_text(json.dumps({'execution_provenance': {'git_dirty': True}}), encoding='utf-8')

    report = verify_study_provenance(study_dir)
    assert report.status == 'FAIL_TAMPER_DETECTED'
    assert any('git_dirty=True' in issue for issue in report.issues)


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


def test_rekor_transparency_proof_standalone_positive(test_keys):
    dsse_env = {'payload': 'dGVzdA==', 'payloadType': 'application/vnd.in-toto+json'}
    proof = generate_rekor_transparency_proof(
        study_id='BN-PB-IV-004',
        dsse_envelope=dsse_env,
        rekor_private_key=test_keys['rekor'],
        log_index=4829104,
    )
    valid, errors = verify_rekor_transparency_proof(
        proof=proof,
        dsse_envelope=dsse_env,
        rekor_public_key_pem=test_keys['rekor_pem'],
    )
    assert valid is True
    assert len(errors) == 0


def test_rekor_transparency_proof_standalone_tampered_rejected(test_keys):
    dsse_env = {'payload': 'dGVzdA==', 'payloadType': 'application/vnd.in-toto+json'}
    proof = generate_rekor_transparency_proof(
        study_id='BN-PB-IV-004',
        dsse_envelope=dsse_env,
        rekor_private_key=test_keys['rekor'],
        log_index=4829104,
    )
    # Tamper logIndex
    proof['log_index'] = 9999999
    valid, errors = verify_rekor_transparency_proof(
        proof=proof,
        dsse_envelope=dsse_env,
        rekor_public_key_pem=test_keys['rekor_pem'],
    )
    assert valid is False
    assert any('Invalid Rekor SET signature' in e for e in errors)


def test_tsa_timestamp_token_standalone_positive(test_keys):
    raw_sig = b"test_signature_bytes_12345678901234567890"
    token = generate_tsa_timestamp_token(
        study_id='BN-PB-IV-004',
        raw_signature=raw_sig,
        tsa_private_key=test_keys['tsa'],
    )
    valid, errors = verify_tsa_timestamp_token(
        token=token,
        raw_signature=raw_sig,
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is True
    assert len(errors) == 0


def test_tsa_timestamp_token_standalone_tampered_rejected(test_keys):
    raw_sig = b"test_signature_bytes_12345678901234567890"
    token = generate_tsa_timestamp_token(
        study_id='BN-PB-IV-004',
        raw_signature=raw_sig,
        tsa_private_key=test_keys['tsa'],
    )
    # Tamper timestamp
    token['timestamp'] = "2030-01-01T00:00:00+00:00"
    valid, errors = verify_tsa_timestamp_token(
        token=token,
        raw_signature=raw_sig,
        tsa_public_key_pem=test_keys['tsa_pem'],
    )
    assert valid is False
    assert any('Invalid TSA signature' in e for e in errors)
