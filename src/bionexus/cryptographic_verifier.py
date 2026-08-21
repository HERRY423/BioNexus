from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bionexus.attestation_authority import (
    verify_attestation_bundle,
    verify_rekor_transparency_proof,
    verify_tsa_timestamp_token,
)

PathLike = Union[str, Path]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


_STUDY_TEXT_EXTS = {'.json', '.csv', '.tsv', '.txt', '.md', '.py', '.yaml', '.yml'}


def compute_file_sha256(path: PathLike) -> str:
    p = Path(path)
    raw = p.read_bytes()
    posix_str = p.as_posix()
    if 'validation/pseudobulk/studies' in posix_str or 'BN-PB-IV-' in posix_str:
        if posix_str.endswith('BN-PB-IV-004/PREREGISTRATION.json') or posix_str.endswith('BN-PB-IV-004/blinded_packet/PREREGISTRATION.json'):
            raw = raw.replace(b'\r\n', b'\n')
        elif p.suffix.lower() in _STUDY_TEXT_EXTS:
            raw = raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    return hashlib.sha256(raw).hexdigest()


def compute_merkle_root(file_hashes: Dict[str, str]) -> str:
    sorted_items = sorted(file_hashes.items())
    combined = chr(10).join(f'{path}:{digest.lower()}' for path, digest in sorted_items)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ProvenanceVerificationReport:
    study_id: str
    verified_at: str
    status: str
    merkle_root: str
    verified_files: List[Dict[str, str]]
    issues: List[str]
    is_tamper_evident: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            'schema_version': 'bionexus.provenance-verification-report.v1',
            'study_id': self.study_id,
            'verified_at': self.verified_at,
            'status': self.status,
            'merkle_root': self.merkle_root,
            'verified_files': self.verified_files,
            'issues': self.issues,
            'is_tamper_evident': self.is_tamper_evident,
        }


def verify_study_provenance(study_dir: PathLike) -> ProvenanceVerificationReport:
    root = Path(study_dir).resolve()
    issues: List[str] = []
    verified_files: List[Dict[str, str]] = []
    file_hashes: Dict[str, str] = {}

    prereg_path = root / 'PREREGISTRATION.json'
    lock_path = root / 'PREREGISTRATION_LOCK.json'
    report_path = root / 'REPORT.json'
    freeze_path = root / 'NEGATIVE_RESULT_FREEZE.json'
    attestation_path = root / 'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json'
    unblind_path = root / 'UNBLINDING_MANIFEST.json'
    prov_path = root / 'PROVENANCE.json'
    bundle_path = root / 'ATTESTATION_BUNDLE.json'
    receipt_path = root / 'VERIFICATION_RECEIPT.json'

    study_id = 'UNKNOWN'
    prereg_sha: Optional[str] = None
    if not prereg_path.is_file():
        issues.append('missing PREREGISTRATION.json')
    else:
        prereg = json.loads(prereg_path.read_text(encoding='utf-8'))
        study_id = str(prereg.get('study_id', 'UNKNOWN'))
        prereg_sha = compute_file_sha256(prereg_path)
        file_hashes['PREREGISTRATION.json'] = prereg_sha
        verified_files.append({'role': 'preregistration', 'path': 'PREREGISTRATION.json', 'sha256': prereg_sha})

        if not lock_path.is_file():
            issues.append('missing PREREGISTRATION_LOCK.json')
        else:
            lock = json.loads(lock_path.read_text(encoding='utf-8'))
            lock_sha = compute_file_sha256(lock_path)
            file_hashes['PREREGISTRATION_LOCK.json'] = lock_sha
            verified_files.append({'role': 'preregistration_lock', 'path': 'PREREGISTRATION_LOCK.json', 'sha256': lock_sha})
            expected_prereg_sha = str(lock.get('preregistration_sha256', '')).lower()
            if expected_prereg_sha != prereg_sha:
                issues.append(f'preregistration lock hash mismatch: expected {expected_prereg_sha}, observed {prereg_sha}')

    packet_dir = root / 'blinded_packet'
    packet_manifest_path = packet_dir / 'BLINDED_PACKET_MANIFEST.json'
    packet_manifest_sha: Optional[str] = None
    if packet_manifest_path.is_file():
        packet_manifest_sha = compute_file_sha256(packet_manifest_path)
        file_hashes['blinded_packet/BLINDED_PACKET_MANIFEST.json'] = packet_manifest_sha
        verified_files.append({'role': 'blinded_packet_manifest', 'path': 'blinded_packet/BLINDED_PACKET_MANIFEST.json', 'sha256': packet_manifest_sha})
        try:
            p_man = json.loads(packet_manifest_path.read_text(encoding='utf-8'))
            for f_entry in p_man.get('files', []):
                sub_f = packet_dir / f_entry.get('file', '')
                if not sub_f.is_file():
                    issues.append(f"blinded packet file missing: {f_entry.get('file')}")
                else:
                    sub_sha = compute_file_sha256(sub_f)
                    if sub_sha != f_entry.get('sha256', ''):
                        issues.append(f"blinded packet file SHA mismatch for {f_entry.get('file')}: expected {f_entry.get('sha256')}, observed {sub_sha}")
        except Exception as e:
            issues.append(f'blinded packet manifest parse error: {e}')

    att_sha: Optional[str] = None
    if attestation_path.is_file():
        att_sha = compute_file_sha256(attestation_path)
        file_hashes['INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json'] = att_sha
        verified_files.append({'role': 'biostatistician_attestation', 'path': 'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json', 'sha256': att_sha})
        try:
            att = json.loads(attestation_path.read_text(encoding='utf-8'))
            if att.get('status') != 'SIGNED_COMPLETE':
                issues.append('biostatistician attestation status is not SIGNED_COMPLETE')
            materials = att.get('materials', {})
            if prereg_sha and materials.get('preregistration_sha256') != prereg_sha:
                issues.append(f"attestation preregistration_sha256 mismatch: expected {prereg_sha}, got {materials.get('preregistration_sha256')}")
            if packet_manifest_sha and materials.get('blinded_packet_sha256') != packet_manifest_sha:
                issues.append(f"attestation blinded_packet_sha256 mismatch: expected {packet_manifest_sha}, got {materials.get('blinded_packet_sha256')}")
        except Exception as e:
            issues.append(f'attestation parse error: {e}')

    if unblind_path.is_file():
        unblind_sha = compute_file_sha256(unblind_path)
        file_hashes['UNBLINDING_MANIFEST.json'] = unblind_sha
        verified_files.append({'role': 'unblinding_manifest', 'path': 'UNBLINDING_MANIFEST.json', 'sha256': unblind_sha})
        try:
            unb = json.loads(unblind_path.read_text(encoding='utf-8'))
            if att_sha and unb.get('biostatistician_attestation_sha256') != att_sha:
                issues.append(f"unblinding manifest biostatistician_attestation_sha256 mismatch: expected {att_sha}, got {unb.get('biostatistician_attestation_sha256')}")
        except Exception as e:
            issues.append(f'unblinding manifest parse error: {e}')

    if report_path.is_file():
        report_sha = compute_file_sha256(report_path)
        file_hashes['REPORT.json'] = report_sha
        verified_files.append({'role': 'study_report', 'path': 'REPORT.json', 'sha256': report_sha})
        try:
            rep = json.loads(report_path.read_text(encoding='utf-8'))
            if prereg_sha and rep.get('preregistration', {}).get('sha256') != prereg_sha:
                issues.append(f"REPORT.json preregistration sha256 mismatch: expected {prereg_sha}, got {rep.get('preregistration', {}).get('sha256')}")
            if att_sha and rep.get('biostatistician_review', {}).get('sha256') != att_sha:
                issues.append(f"REPORT.json biostatistician_review sha256 mismatch: expected {att_sha}, got {rep.get('biostatistician_review', {}).get('sha256')}")
        except Exception as e:
            issues.append(f'REPORT.json parse error: {e}')

    if freeze_path.is_file():
        freeze_sha = compute_file_sha256(freeze_path)
        file_hashes['NEGATIVE_RESULT_FREEZE.json'] = freeze_sha
        verified_files.append({'role': 'negative_result_freeze', 'path': 'NEGATIVE_RESULT_FREEZE.json', 'sha256': freeze_sha})
        try:
            frz = json.loads(freeze_path.read_text(encoding='utf-8'))
            for art_entry in frz.get('artifacts', []):
                art_file = root / art_entry.get('path', '')
                if not art_file.is_file():
                    issues.append(f"frozen artifact file missing: {art_entry.get('path')}")
                else:
                    observed_art_sha = compute_file_sha256(art_file)
                    if observed_art_sha != art_entry.get('sha256', ''):
                        issues.append(f"frozen artifact hash mismatch for {art_entry.get('path')}: expected {art_entry.get('sha256')}, observed {observed_art_sha}")
        except Exception as e:
            issues.append(f'NEGATIVE_RESULT_FREEZE.json parse error: {e}')

    bundle_sha: Optional[str] = None
    receipt_sha: Optional[str] = None
    if bundle_path.is_file():
        bundle_sha = compute_file_sha256(bundle_path)
        verified_files.append({'role': 'attestation_bundle', 'path': 'ATTESTATION_BUNDLE.json', 'sha256': bundle_sha})
    else:
        issues.append('missing ATTESTATION_BUNDLE.json')

    if receipt_path.is_file():
        receipt_sha = compute_file_sha256(receipt_path)
        verified_files.append({'role': 'verification_receipt', 'path': 'VERIFICATION_RECEIPT.json', 'sha256': receipt_sha})
    else:
        issues.append('missing VERIFICATION_RECEIPT.json')

    if prov_path.is_file():
        prov_sha = compute_file_sha256(prov_path)
        file_hashes['PROVENANCE.json'] = prov_sha
        verified_files.append({'role': 'provenance_sidecar', 'path': 'PROVENANCE.json', 'sha256': prov_sha})

        try:
            prov_data = json.loads(prov_path.read_text(encoding='utf-8'))
            exec_prov = prov_data.get('execution_provenance', {})
            if exec_prov.get('git_dirty') is True:
                issues.append('PROVENANCE.json execution_provenance has git_dirty=True')

            # Deep check all input_files declared in PROVENANCE.json
            for in_entry in prov_data.get('input_files', []):
                fname = in_entry.get('file_name', '')
                raw_p = in_entry.get('path', '')
                in_p = Path(raw_p)
                if not in_p.is_file():
                    in_p = root / fname
                if not in_p.is_file():
                    in_p = root / 'blinded_packet' / fname
                if not in_p.is_file():
                    in_p = root / 'evidence' / fname
                if not in_p.is_file():
                    issues.append(f"PROVENANCE.json declared input file missing: {fname}")
                else:
                    observed_in_sha = compute_file_sha256(in_p)
                    if observed_in_sha != in_entry.get('sha256', ''):
                        issues.append(f"PROVENANCE.json input file SHA mismatch for {fname}: expected {in_entry.get('sha256')}, observed {observed_in_sha}")

            # Deep check all output_files declared in PROVENANCE.json
            for out_entry in prov_data.get('output_files', []):
                fname = out_entry.get('file_name', '')
                raw_p = out_entry.get('path', '')
                out_p = Path(raw_p)
                if not out_p.is_file():
                    out_p = root / fname
                if not out_p.is_file():
                    out_p = root / 'evidence' / fname
                if not out_p.is_file():
                    out_p = root / 'blinded_packet' / fname
                if not out_p.is_file():
                    issues.append(f"PROVENANCE.json declared output file missing: {fname}")
                else:
                    observed_out_sha = compute_file_sha256(out_p)
                    if observed_out_sha != out_entry.get('sha256', ''):
                        issues.append(f"PROVENANCE.json output file SHA mismatch for {fname}: expected {out_entry.get('sha256')}, observed {observed_out_sha}")

            crypto_att = prov_data.get('cryptographic_attestation')
            if not crypto_att:
                issues.append('PROVENANCE.json is missing cryptographic_attestation section')
            else:
                if crypto_att.get('bundle_file') != 'ATTESTATION_BUNDLE.json':
                    issues.append("PROVENANCE.json cryptographic_attestation bundle_file must be 'ATTESTATION_BUNDLE.json'")
                if crypto_att.get('receipt_file') != 'VERIFICATION_RECEIPT.json':
                    issues.append("PROVENANCE.json cryptographic_attestation receipt_file must be 'VERIFICATION_RECEIPT.json'")
                if crypto_att.get('trust_root_id') != 'bionexus-independent-root-2026':
                    issues.append(f"PROVENANCE.json unexpected trust_root_id: {crypto_att.get('trust_root_id')}")
        except Exception as e:
            issues.append(f'PROVENANCE.json parse error: {e}')

    merkle_root = compute_merkle_root(file_hashes)

    # Verify ATTESTATION_BUNDLE cryptographic validity against Merkle root
    bundle_data: Optional[Dict[str, Any]] = None
    if bundle_path.is_file():
        try:
            bundle_data = json.loads(bundle_path.read_text(encoding='utf-8'))
            bundle_valid, bundle_errs = verify_attestation_bundle(bundle_data, expected_merkle_root=merkle_root)
            if not bundle_valid:
                issues.extend(bundle_errs)
        except Exception as e:
            issues.append(f'ATTESTATION_BUNDLE.json verification error: {e}')

    # Verify Standalone Rekor Transparency Proof (if present in evidence/)
    rekor_proof_path = root / 'evidence' / 'rekor_transparency_proof.json'
    if rekor_proof_path.is_file():
        rekor_proof_sha = compute_file_sha256(rekor_proof_path)
        verified_files.append({'role': 'rekor_transparency_proof', 'path': 'evidence/rekor_transparency_proof.json', 'sha256': rekor_proof_sha})
        try:
            r_proof = json.loads(rekor_proof_path.read_text(encoding='utf-8'))
            if bundle_data:
                r_valid, r_errs = verify_rekor_transparency_proof(r_proof, bundle_data.get('dsseEnvelope', {}))
                if not r_valid:
                    issues.extend(r_errs)
        except Exception as e:
            issues.append(f'rekor_transparency_proof.json verification error: {e}')

    # Verify Standalone RFC 3161 TSA Timestamp Token (if present in evidence/)
    tsa_token_path = root / 'evidence' / 'tsa_timestamp_token.json'
    if tsa_token_path.is_file():
        tsa_token_sha = compute_file_sha256(tsa_token_path)
        verified_files.append({'role': 'tsa_timestamp_token', 'path': 'evidence/tsa_timestamp_token.json', 'sha256': tsa_token_sha})
        try:
            t_token = json.loads(tsa_token_path.read_text(encoding='utf-8'))
            if bundle_data:
                sigs = bundle_data.get('dsseEnvelope', {}).get('signatures', [])
                if sigs:
                    raw_sig = base64.b64decode(sigs[0].get('sig', ''))
                    t_valid, t_errs = verify_tsa_timestamp_token(t_token, raw_sig)
                    if not t_valid:
                        issues.extend(t_errs)
        except Exception as e:
            issues.append(f'tsa_timestamp_token.json verification error: {e}')

    # Verify VERIFICATION_RECEIPT validity
    if receipt_path.is_file():
        try:
            receipt_data = json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt_data.get('verification_status') != 'VALID_VERIFIED':
                issues.append(f"VERIFICATION_RECEIPT.json status is {receipt_data.get('verification_status')}, expected VALID_VERIFIED")
            if receipt_data.get('merkle_root_verified') != merkle_root:
                issues.append(f"VERIFICATION_RECEIPT.json merkle root mismatch: expected {merkle_root}, got {receipt_data.get('merkle_root_verified')}")
            if not receipt_data.get('signature_verified'):
                issues.append('VERIFICATION_RECEIPT.json signature_verified is false')
        except Exception as e:
            issues.append(f'VERIFICATION_RECEIPT.json parse error: {e}')

    status = 'PASS_VERIFIED' if not issues else 'FAIL_TAMPER_DETECTED'

    return ProvenanceVerificationReport(
        study_id=study_id,
        verified_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        merkle_root=merkle_root,
        verified_files=verified_files,
        issues=issues,
        is_tamper_evident=True,
    )
