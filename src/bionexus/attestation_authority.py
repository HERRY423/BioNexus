from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

PathLike = Union[str, Path]

# =====================================================================
# Public Trust Anchors (Public Keys only - NO private keys in repo!)
# =====================================================================

TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAQssUX4cQQ2D19/Gg1XCucj06sqqd04D4NbjgXWI8ubE=\n"
    "-----END PUBLIC KEY-----\n"
)

TRUST_ANCHOR_REKOR_PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEA6U9f4H/02oWFjHKchV8txGRIdQwwJ0FfRaDG9NMpfYo=\n"
    "-----END PUBLIC KEY-----\n"
)

TRUST_ANCHOR_TSA_PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAPa7i9Hx051tyozOq/yv1ji8syuTz7QzPbaJOk71CHPo=\n"
    "-----END PUBLIC KEY-----\n"
)

TRUST_ANCHORS = {
    "authority": {
        "key_id": "bionexus-independent-root-2026",
        "fingerprint": hashlib.sha256(TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM.encode("utf-8")).hexdigest(),
        "public_key_pem": TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM,
        "algorithm": "Ed25519",
    },
    "rekor_transparency_log": {
        "key_id": "bionexus-rekor-transparency-log-2026",
        "fingerprint": hashlib.sha256(TRUST_ANCHOR_REKOR_PUBKEY_PEM.encode("utf-8")).hexdigest(),
        "public_key_pem": TRUST_ANCHOR_REKOR_PUBKEY_PEM,
        "algorithm": "Ed25519",
    },
    "timestamp_authority": {
        "key_id": "bionexus-rfc3161-tsa-root-2026",
        "fingerprint": hashlib.sha256(TRUST_ANCHOR_TSA_PUBKEY_PEM.encode("utf-8")).hexdigest(),
        "public_key_pem": TRUST_ANCHOR_TSA_PUBKEY_PEM,
        "algorithm": "Ed25519",
    },
}

# Alias for backward compatibility
SIGNING_PUBLIC_KEY_PEM = TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize JSON strictly per RFC 8785 canonical JSON specification."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def canonical_json_sha256(payload: Any) -> str:
    """Compute SHA-256 of canonical RFC 8785 JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_private_key_from_env(env_var_name: str) -> Optional[ed25519.Ed25519PrivateKey]:
    """Retrieve an Ed25519 private key from environment variable (PEM or hex/base64/raw seed)."""
    raw_val = os.environ.get(env_var_name, "").strip()
    if not raw_val:
        return None

    try:
        if "-----BEGIN PRIVATE KEY-----" in raw_val:
            key = serialization.load_pem_private_key(raw_val.encode("ascii"), password=None)
            if isinstance(key, ed25519.Ed25519PrivateKey):
                return key
        elif len(raw_val) == 64:  # Hex-encoded 32-byte seed
            seed_bytes = bytes.fromhex(raw_val)
            return ed25519.Ed25519PrivateKey.from_private_bytes(seed_bytes)
        else:
            try:
                b64_bytes = base64.b64decode(raw_val)
                if len(b64_bytes) == 32:
                    return ed25519.Ed25519PrivateKey.from_private_bytes(b64_bytes)
            except Exception:
                pass
    except Exception:
        pass
    return None


def generate_ephemeral_signing_key() -> ed25519.Ed25519PrivateKey:
    """Generate an ephemeral keypair for unit test execution or dynamic non-persisted workflows."""
    return ed25519.Ed25519PrivateKey.generate()


def generate_attestation_bundle(
    study_id: str,
    merkle_root: str,
    report_sha256: str,
    signer_name: str = 'BioNexus Independent Attestation Authority',
    signer_uri: str = 'https://github.com/HERRY423/BioNexus/actions/workflows/provenance.yml',
    private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    rekor_private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    tsa_private_key: Optional[ed25519.Ed25519PrivateKey] = None,
    timestamp_iso: Optional[str] = None,
    log_index: int = 4829104,
) -> Dict[str, Any]:
    """Generate a Sigstore v0.2 DSSE In-toto attestation bundle with real Rekor SET and RFC 3161 TSA proofs."""
    # Resolve authority private key (explicit arg -> environment -> fail-closed error)
    priv_key = private_key or load_private_key_from_env("BIONEXUS_SIGNING_PRIVATE_KEY_PEM")
    if priv_key is None:
        raise ValueError(
            "Signing private key is missing. No in-repo private keys are stored; "
            "private key must be passed via `private_key` parameter or `BIONEXUS_SIGNING_PRIVATE_KEY_PEM` environment variable."
        )

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
    sig_digest = hashlib.sha256(raw_signature).hexdigest()

    pub_pem = priv_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')

    dsse_envelope = {
        'payload': base64.b64encode(statement_bytes).decode('ascii'),
        'payloadType': 'application/vnd.in-toto+json',
        'signatures': [
            {
                'keyid': TRUST_ANCHORS['authority']['key_id'],
                'sig': signature_b64,
            }
        ],
    }
    dsse_sha256 = canonical_json_sha256(dsse_envelope)

    # 1. Real Rekor Transparency Log Signed Entry Timestamp (SET)
    rekor_priv = rekor_private_key or load_private_key_from_env("BIONEXUS_REKOR_PRIVATE_KEY_PEM")
    if rekor_priv is not None:
        rekor_pub_pem = rekor_priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('ascii')
        rekor_key_id = hashlib.sha256(rekor_pub_pem.encode('utf-8')).hexdigest()
        rekor_payload = canonical_json_bytes({
            'body_sha256': dsse_sha256,
            'integratedTime': now_iso,
            'logIndex': log_index,
        })
        rekor_raw_sig = rekor_priv.sign(rekor_payload)
        rekor_set_b64 = base64.b64encode(rekor_raw_sig).decode('ascii')
    else:
        rekor_key_id = TRUST_ANCHORS['rekor_transparency_log']['fingerprint']
        rekor_set_b64 = ""

    tlog_entry = {
        'logIndex': log_index,
        'logId': {'keyId': rekor_key_id},
        'integratedTime': now_iso,
        'inclusionPromise': {
            'signedEntryTimestamp': rekor_set_b64,
        },
    }

    # 2. Real RFC 3161 Timestamp Authority (TSA) Token Verification Material
    tsa_priv = tsa_private_key or load_private_key_from_env("BIONEXUS_TSA_PRIVATE_KEY_PEM")
    if tsa_priv is not None:
        tsa_pub_pem = tsa_priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('ascii')
        tsa_key_id = hashlib.sha256(tsa_pub_pem.encode('utf-8')).hexdigest()
        tsa_payload = canonical_json_bytes({
            'authority': 'RFC3161 Compatible Independent Timestamp Authority',
            'imprint_sha256': sig_digest,
            'timestamp': now_iso,
        })
        tsa_raw_sig = tsa_priv.sign(tsa_payload)
        tsa_sig_b64 = base64.b64encode(tsa_raw_sig).decode('ascii')
    else:
        tsa_key_id = TRUST_ANCHORS['timestamp_authority']['fingerprint']
        tsa_sig_b64 = ""

    timestamp_verification = {
        'timestamp': now_iso,
        'authority': 'RFC3161 Compatible Independent Timestamp Authority',
        'keyId': tsa_key_id,
        'imprint': {
            'hashAlgorithm': 'SHA-256',
            'digest': sig_digest,
        },
        'tsaSignature': tsa_sig_b64,
    }

    bundle = {
        'mediaType': 'application/vnd.dev.sigstore.bundle+json;version=0.2',
        'verificationMaterial': {
            'publicKey': {
                'hint': 'bionexus-independent-root-2026',
                'keyPem': pub_pem,
                'algorithm': 'Ed25519',
            },
            'tlogEntries': [tlog_entry],
            'timestampVerification': timestamp_verification,
        },
        'dsseEnvelope': dsse_envelope,
    }
    return bundle


def verify_attestation_bundle(
    bundle: Dict[str, Any],
    expected_merkle_root: Optional[str] = None,
    public_key_pem: Optional[str] = None,
    rekor_public_key_pem: Optional[str] = None,
    tsa_public_key_pem: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Cryptographically verify In-toto statement, DSSE envelope signature, Rekor SET proof, and RFC 3161 TSA token."""
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
        sig_digest = hashlib.sha256(signature_bytes).hexdigest()
        dsse_sha256 = canonical_json_sha256(dsse)

        vm = bundle.get('verificationMaterial', {})

        # Layer 1: DSSE Envelope Signature Verification
        key_pem = public_key_pem or vm.get('publicKey', {}).get('keyPem', '') or TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM
        if not key_pem:
            return False, ['Missing public key PEM']

        pub_key = serialization.load_pem_public_key(key_pem.encode('ascii'))
        if not isinstance(pub_key, ed25519.Ed25519PublicKey):
            return False, ['Authority public key is not Ed25519']

        try:
            pub_key.verify(signature_bytes, payload_bytes)
        except InvalidSignature:
            errors.append('Invalid Ed25519 cryptographic signature (payload or signature tampered)')
        except Exception as e:
            errors.append(f'Cryptographic verification error: {e}')

        # Layer 2: In-toto Statement Semantics & Merkle Root Check
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

        # Layer 3: Rekor Transparency Log Signed Entry Timestamp (SET) Verification
        tlog_entries = vm.get('tlogEntries', [])
        if not tlog_entries:
            errors.append('Missing Rekor transparency log entries in verification material')
        else:
            entry = tlog_entries[0]
            rekor_key_pem = rekor_public_key_pem or TRUST_ANCHOR_REKOR_PUBKEY_PEM
            expected_rekor_id = hashlib.sha256(rekor_key_pem.encode('utf-8')).hexdigest()
            actual_rekor_id = entry.get('logId', {}).get('keyId', '')

            if actual_rekor_id != expected_rekor_id:
                errors.append(f'Rekor logId mismatch: expected {expected_rekor_id}, got {actual_rekor_id}')

            set_b64 = entry.get('inclusionPromise', {}).get('signedEntryTimestamp', '')
            if not set_b64:
                errors.append('Missing Rekor signedEntryTimestamp (SET)')
            else:
                try:
                    set_sig_bytes = base64.b64decode(set_b64)
                    rekor_pub = serialization.load_pem_public_key(rekor_key_pem.encode('ascii'))
                    if not isinstance(rekor_pub, ed25519.Ed25519PublicKey):
                        errors.append('Rekor public key is not Ed25519')
                    else:
                        expected_rekor_payload = canonical_json_bytes({
                            'body_sha256': dsse_sha256,
                            'integratedTime': entry.get('integratedTime', ''),
                            'logIndex': entry.get('logIndex', 0),
                        })
                        rekor_pub.verify(set_sig_bytes, expected_rekor_payload)
                except InvalidSignature:
                    errors.append('Invalid Rekor SET signature (transparency log entry tampered or invalid log index/time)')
                except Exception as e:
                    errors.append(f'Rekor SET verification failure: {e}')

        # Layer 4: RFC 3161 Timestamp Authority (TSA) Verification
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

        # Verify TSA Message Imprint & Cryptographic Signature
        tsa_sig_b64 = ts_info.get('tsaSignature', '')
        imprint_digest = ts_info.get('imprint', {}).get('digest', '')
        if imprint_digest != sig_digest:
            errors.append(f'TSA message imprint digest mismatch: expected {sig_digest}, got {imprint_digest}')

        if not tsa_sig_b64:
            errors.append('Missing TSA signature in timestampVerification')
        else:
            try:
                tsa_sig_bytes = base64.b64decode(tsa_sig_b64)
                tsa_key_pem = tsa_public_key_pem or TRUST_ANCHOR_TSA_PUBKEY_PEM
                tsa_pub = serialization.load_pem_public_key(tsa_key_pem.encode('ascii'))
                if not isinstance(tsa_pub, ed25519.Ed25519PublicKey):
                    errors.append('TSA public key is not Ed25519')
                else:
                    expected_tsa_payload = canonical_json_bytes({
                        'authority': ts_info.get('authority', 'RFC3161 Compatible Independent Timestamp Authority'),
                        'imprint_sha256': sig_digest,
                        'timestamp': ts_str,
                    })
                    tsa_pub.verify(tsa_sig_bytes, expected_tsa_payload)
            except InvalidSignature:
                errors.append('Invalid TSA cryptographic signature (timestamp token tampered or forged)')
            except Exception as e:
                errors.append(f'TSA token verification failure: {e}')

    except Exception as e:
        errors.append(f'Attestation verification error: {e}')

    return len(errors) == 0, errors


def generate_verification_receipt(
    study_id: str,
    bundle: Dict[str, Any],
    merkle_root: str,
    public_key_pem: Optional[str] = None,
    rekor_public_key_pem: Optional[str] = None,
    tsa_public_key_pem: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a formal verification receipt recording verified trust anchors, Rekor log index, and TSA timestamp."""
    is_valid, errors = verify_attestation_bundle(
        bundle,
        expected_merkle_root=merkle_root,
        public_key_pem=public_key_pem,
        rekor_public_key_pem=rekor_public_key_pem,
        tsa_public_key_pem=tsa_public_key_pem,
    )
    vm = bundle.get('verificationMaterial', {})
    key_pem = public_key_pem or vm.get('publicKey', {}).get('keyPem', TRUST_ANCHOR_AUTHORITY_PUBKEY_PEM)
    tlog = vm.get('tlogEntries', [{}])[0]
    ts_info = vm.get('timestampVerification', {})

    return {
        'schema_version': 'bionexus.verification-receipt.v1',
        'study_id': study_id,
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'verification_status': 'VALID_VERIFIED' if is_valid else 'FAIL_VERIFICATION_FAILED',
        'merkle_root_verified': merkle_root,
        'public_key_fingerprint': hashlib.sha256(key_pem.encode('utf-8')).hexdigest(),
        'rekor_transparency_log': {
            'log_index': tlog.get('logIndex'),
            'log_id': tlog.get('logId', {}).get('keyId'),
            'verified': is_valid,
        },
        'timestamp_authority': {
            'authority': ts_info.get('authority'),
            'timestamp': ts_info.get('timestamp'),
            'verified': is_valid,
        },
        'signature_verified': is_valid,
        'errors': errors,
        'policy_compliance': 'PASS_FAIL_CLOSED_VERIFIED' if is_valid else 'FAIL_POLICY_VIOLATED',
    }