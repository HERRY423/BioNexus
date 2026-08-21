from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, Path]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def compute_file_sha256(path: PathLike) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


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

    study_id = 'UNKNOWN'
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
    if packet_manifest_path.is_file():
        packet_manifest_sha = compute_file_sha256(packet_manifest_path)
        file_hashes['blinded_packet/BLINDED_PACKET_MANIFEST.json'] = packet_manifest_sha
        verified_files.append({'role': 'blinded_packet_manifest', 'path': 'blinded_packet/BLINDED_PACKET_MANIFEST.json', 'sha256': packet_manifest_sha})

    if attestation_path.is_file():
        att_sha = compute_file_sha256(attestation_path)
        file_hashes['INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json'] = att_sha
        verified_files.append({'role': 'biostatistician_attestation', 'path': 'INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json', 'sha256': att_sha})
        att = json.loads(attestation_path.read_text(encoding='utf-8'))
        if att.get('status') != 'SIGNED_COMPLETE':
            issues.append('biostatistician attestation status is not SIGNED_COMPLETE')

    if unblind_path.is_file():
        unblind_sha = compute_file_sha256(unblind_path)
        file_hashes['UNBLINDING_MANIFEST.json'] = unblind_sha
        verified_files.append({'role': 'unblinding_manifest', 'path': 'UNBLINDING_MANIFEST.json', 'sha256': unblind_sha})

    if report_path.is_file():
        report_sha = compute_file_sha256(report_path)
        file_hashes['REPORT.json'] = report_sha
        verified_files.append({'role': 'study_report', 'path': 'REPORT.json', 'sha256': report_sha})

    if freeze_path.is_file():
        freeze_sha = compute_file_sha256(freeze_path)
        file_hashes['NEGATIVE_RESULT_FREEZE.json'] = freeze_sha
        verified_files.append({'role': 'negative_result_freeze', 'path': 'NEGATIVE_RESULT_FREEZE.json', 'sha256': freeze_sha})

    if prov_path.is_file():
        prov_sha = compute_file_sha256(prov_path)
        file_hashes['PROVENANCE.json'] = prov_sha
        verified_files.append({'role': 'provenance_sidecar', 'path': 'PROVENANCE.json', 'sha256': prov_sha})

    merkle_root = compute_merkle_root(file_hashes)
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