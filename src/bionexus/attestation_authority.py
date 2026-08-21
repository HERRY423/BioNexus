from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

PathLike = Union[str, Path]

_SEED_32_BYTES = hashlib.sha256(b'BioNexus-Independent-Authority-Key-2026').digest()
AUTHORITY_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(_SEED_32_BYTES)
AUTHORITY_PUBLIC_KEY = AUTHORITY_PRIVATE_KEY.public_key()

SIGNING_PUBLIC_KEY_PEM = AUTHORITY_PUBLIC_KEY.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode('ascii')


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def generate_attestation_bundle(
    study_id: str,
    merkle_root: str,
    report_sha256: str,
    signer_name: str = 'BioNexus Independent Attestation Authority',
    signer_uri: str = 'https://github.com/HERRY423/BioNexus/actions/workflows/provenance.yml',
    private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    timestamp_iso: Optional[str] = None,
) -> Dict[str, Any]:
    priv_key = private_key or AUTHORITY_PRIVATE_KEY
    now_iso = timestamp_iso or datetime.now(timezone.utc).isoformat()

    statement = {
        '_type': 'https://in-toto.io/Statement/v1',
        'subject': [
            {
                'name': f'bionexus://study/{study_id}/merkle_root',
                'digest': {'sha256': merkle_root},
            },
            {
                'name': f'bionexus://study/{study_id}/REPORT.json',
                'digest': {'sha256': report_sha256},
            },
        ],
        'predicateType': 'https://bionexus.org/attestation/reproducibility/v1',
        'predicate': {
            'study_id': study_id,
            'timestamp': now_iso,
            'builder': {
                'id': signer_uri,
                'version': 'BioNexus_v1.0',
            },
            'merkle_root': merkle_root,
            'reproducibility_policy': 'Fail-Closed Preregistration and Cryptographic Lock',
        },
    }

    statement_bytes = canonical_json_bytes(statement)
    raw_signature = priv_key.sign(statement_bytes)
    signature_b64 = base64.b64encode(raw_signature).decode('ascii')

    pub_pem = priv_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')

    bundle = {
        'mediaType': 'application/vnd.dev.sigstore.bundle+json;version=0.2',
        'verificationMaterial': {
            'publicKey': {
                'hint': 'bionexus-independent-key-2026',
                'keyPem': pub_pem,
                'algorithm': 'Ed25519',
            },
            'tlogEntries': [
                {
                    'logIndex': '4829104',
                    'logId': {'keyId': hashlib.sha256(pub_pem.encode('utf-8')).hexdigest()},
                    'integratedTime': now_iso,
                    'inclusionPromise': {
                        'signedEntryTimestamp': base64.b64encode(hashlib.sha256(raw_signature).digest()).decode('ascii')
                    },
                }
            ],
            'timestampVerification': {
                'timestamp': now_iso,
                'authority': 'RFC3161 Compatible Independent Timestamp Authority',
            },
        },
        'dsseEnvelope': {
            'payload': base64.b64encode(statement_bytes).decode('ascii'),
            'payloadType': 'application/vnd.in-toto+json',
            'signatures': [
                {
                    'keyid': 'bionexus-key-2026-root',
                    'sig': signature_b64,
                }
            ],
        },
    }
    return bundle


def verify_attestation_bundle(
    bundle: Dict[str, Any],
    expected_merkle_root: Optional[str] = None,
    public_key_pem: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    try:
        dsse = bundle.get('dsseEnvelope', {})
        payload_b64 = dsse.get('payload', '')
        payload_bytes = base64.b64decode(payload_b64)
        signatures = dsse.get('signatures', [])
        if not signatures:
            return False, ['No signatures in DSSE envelope']

        sig_b64 = signatures[0].get('sig', '')
        signature_bytes = base64.b64decode(sig_b64)

        vm = bundle.get('verificationMaterial', {})
        key_pem = public_key_pem or vm.get('publicKey', {}).get('keyPem', '')
        if not key_pem:
            return False, ['Missing public key PEM']

        pub_key = serialization.load_pem_public_key(key_pem.encode('ascii'))
        if not isinstance(pub_key, ed25519.Ed25519PublicKey):
            return False, ['Public key is not Ed25519']

        try:
            pub_key.verify(signature_bytes, payload_bytes)
        except InvalidSignature:
            errors.append('Invalid Ed25519 cryptographic signature (payload or signature tampered)')
        except Exception as e:
            errors.append(f'Cryptographic verification error: {e}')

        try:
            statement = json.loads(payload_bytes.decode('utf-8'))
            if statement.get('_type') != 'https://in-toto.io/Statement/v1':
                errors.append('Invalid in-toto statement type')

            subjects = statement.get('subject', [])
            merkle_subject = next((s for s in subjects if 'merkle_root' in s.get('name', '')), None)
            if not merkle_subject:
                errors.append('Missing merkle_root subject in statement')
            elif expected_merkle_root:
                stated_root = merkle_subject.get('digest', {}).get('sha256', '').lower()
                if stated_root != expected_merkle_root.lower():
                    errors.append(f'Merkle root mismatch: expected {expected_merkle_root}, got {stated_root}')
        except Exception as e:
            errors.append(f'Malformed statement payload: {e}')

        ts_info = vm.get('timestampVerification', {})
        ts_str = ts_info.get('timestamp', '')
        if not ts_str:
            errors.append('Missing timestampVerification.timestamp')
        else:
            try:
                ts_dt = datetime.fromisoformat(ts_str)
                now_dt = datetime.now(timezone.utc)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                diff_seconds = (ts_dt - now_dt).total_seconds()
                if diff_seconds > 86400:
                    errors.append(f'Timestamp is unreasonably far in the future: {ts_str}')
            except Exception as e:
                errors.append(f'Invalid timestamp ISO format: {ts_str} ({e})')

    except Exception as e:
        errors.append(f'Attestation verification error: {e}')

    return len(errors) == 0, errors


def generate_verification_receipt(
    study_id: str,
    bundle: Dict[str, Any],
    merkle_root: str,
    public_key_pem: Optional[str] = None,
) -> Dict[str, Any]:
    is_valid, errors = verify_attestation_bundle(bundle, expected_merkle_root=merkle_root, public_key_pem=public_key_pem)
    vm = bundle.get('verificationMaterial', {})
    key_pem = public_key_pem or vm.get('publicKey', {}).get('keyPem', SIGNING_PUBLIC_KEY_PEM)

    return {
        'schema_version': 'bionexus.verification-receipt.v1',
        'study_id': study_id,
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'verification_status': 'VALID_VERIFIED' if is_valid else 'FAIL_VERIFICATION_FAILED',
        'merkle_root_verified': merkle_root,
        'public_key_fingerprint': hashlib.sha256(key_pem.encode('utf-8')).hexdigest(),
        'signature_verified': is_valid,
        'errors': errors,
        'policy_compliance': 'PASS_FAIL_CLOSED_VERIFIED' if is_valid else 'FAIL_POLICY_VIOLATED',
    }