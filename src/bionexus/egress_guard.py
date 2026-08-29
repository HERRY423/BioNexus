"""
BioNexus Data Egress & Governance Guard (BNS-SEC-001..010).

Enforces institutional data governance, air-gapped lab compliance, and egress contracts:
- OFFLINE_STRICT: Zero network egress. Local compute only.
- ALLOWLIST: Approved scientific knowledge services only (e.g. PubMed, UniProt, ChEMBL).
             Strict invariant: ZERO raw biological matrices, count tables,
             unindexed genomic sequences, or clinical PHI transmitted.
- CONNECTED: External calls permitted with mandatory cryptographic audit logging.

Every external call records:
- endpoint
- fields_transmitted (metadata summary, verifying no raw matrices or PHI)
- timestamp
- purpose
- payload_sha256
- response_hash
- egress_mode
- outcome (PERMITTED / BLOCKED)
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlsplit, urlunsplit


class EgressMode(str, enum.Enum):
    """Data egress policy modes."""
    OFFLINE_STRICT = "OFFLINE_STRICT"  # Zero external network access
    ALLOWLIST = "ALLOWLIST"            # Only approved public knowledge services (metadata/queries only)
    CONNECTED = "CONNECTED"            # External calls permitted with audit logging


class DataClassification(str, enum.Enum):
    """Institutional data classification levels."""
    PUBLIC_BENCHMARK = "PUBLIC_BENCHMARK"                    # Public reference / synthetic data
    PROPRIETARY_UNPUBLISHED = "PROPRIETARY_UNPUBLISHED"      # Pre-publication experimental data
    CONTROLLED_ACCESS_GENOMIC = "CONTROLLED_ACCESS_GENOMIC"  # dbGaP, EGA, controlled human omics
    RESTRICTED_CLINICAL_PHI = "RESTRICTED_CLINICAL_PHI"      # HIPAA / GDPR protected health data


# Canonical allowed scientific public knowledge domains under ALLOWLIST mode
APPROVED_ALLOWLIST_DOMAINS: Set[str] = {
    "pubmed.ncbi.nlm.nih.gov",
    "eutils.ncbi.nlm.nih.gov",
    "rest.ensembl.org",
    "rest.uniprot.org",
    "www.uniprot.org",
    "alphafold.ebi.ac.uk",
    "www.ebi.ac.uk",
    "ftp.ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
    "files.rcsb.org",
    "data.rcsb.org",
    "search.rcsb.org",
    "www.rcsb.org",
    "api.platform.opentargets.org",
    "gnomad.broadinstitute.org",
    "reactome.org",
    "string-db.org",
    "gtexportal.org",
    "cancer.sanger.ac.uk",
    "hub.docker.com",
    "nf-co.re",
    "api.github.com",
    "raw.githubusercontent.com",
    "cf.10xgenomics.com",
    "zenodo.org",
    "huggingface.co",
    "api.opentargets.io",
    "platform.opentargets.org",
    "clinicaltrials.gov",
    "api.biorxiv.org",
    "api.crossref.org",
    "api.semanticscholar.org",
    "api.openalex.org",
    "pubmed.mcp.claude.com",
    "hcls.mcp.claude.com",
    "mcp.platform.opentargets.org",
    "mcp.consensus.app",
    "connector.scholargateway.ai",
}

# Patterns indicating raw biological matrices, credentials, or clinical PHI
PHI_OR_RAW_DATA_PATTERNS = [
    (re.compile(r"(?i)\b(mrn|patient_id|ssn|date_of_birth|dob|patient_name|medical_record)\b"), "Clinical PHI field"),
    (re.compile(r"(?i)\b(ghp_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16})\b"), "Hardcoded credential/API key"),
    (re.compile(r"(?i)\b(raw_counts|expression_matrix|count_matrix|cell_by_gene|raw_umi_matrix)\b"), "Raw expression matrix identifier"),
]


class EgressBlockedError(PermissionError):
    """Raised before a network call when the active egress policy denies it."""


def _endpoint_without_query(endpoint: str) -> str:
    """Avoid persisting query values that may contain identifiers or secrets."""
    try:
        parsed = urlsplit(endpoint)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return endpoint.split("?", 1)[0]


def _request_payload(endpoint: str, body: Any = None) -> Dict[str, Any]:
    try:
        query = dict(parse_qsl(urlsplit(endpoint).query, keep_blank_values=True))
    except Exception:
        query = {}
    payload: Dict[str, Any] = {"query_parameters": query}
    if body is not None:
        if isinstance(body, bytes):
            try:
                payload["body"] = json.loads(body.decode("utf-8"))
            except Exception:
                payload["body"] = body.decode("utf-8", errors="replace")
        else:
            payload["body"] = body
    return payload


@dataclass
class EgressAuditRecord:
    """Cryptographically verifiable audit log entry for external network/MCP calls."""
    record_id: str
    timestamp: str
    egress_mode: str
    endpoint: str
    domain: str
    purpose: str
    fields_transmitted: List[str]
    payload_sha256: str
    response_hash: Optional[str] = None
    outcome: str = "PERMITTED"  # PERMITTED / BLOCKED
    block_reason: Optional[str] = None
    data_classification: str = DataClassification.PUBLIC_BENCHMARK.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DataGovernanceGuard:
    """
    BioNexus Runtime Data Governance and Egress Guard.

    Enforces air-gapped lab compliance, validates outgoing payloads,
    and maintains an immutable cryptographic audit ledger.
    """

    def __init__(
        self,
        mode: Optional[EgressMode | str] = None,
        audit_log_path: Optional[Path | str] = None,
        allowed_domains: Optional[Set[str]] = None,
    ) -> None:
        env_mode = os.environ.get("BIONEXUS_EGRESS_MODE", "ALLOWLIST").upper()
        if mode is None:
            self.mode = EgressMode(env_mode) if env_mode in EgressMode.__members__ else EgressMode.ALLOWLIST
        elif isinstance(mode, str):
            self.mode = EgressMode(mode.upper())
        else:
            self.mode = mode

        self.allowed_domains = set(allowed_domains or APPROVED_ALLOWLIST_DOMAINS)
        self.audit_log_path = Path(audit_log_path or os.environ.get("BIONEXUS_AUDIT_LOG", "logs/egress_audit.jsonl"))
        self._records: List[EgressAuditRecord] = []

    def set_mode(self, mode: EgressMode | str) -> None:
        """Dynamically update egress mode (e.g. from CLI or policy configuration)."""
        self.mode = EgressMode(mode) if isinstance(mode, str) else mode

    def extract_domain(self, endpoint: str) -> str:
        """Extract hostname domain from URL or MCP endpoint."""
        clean = endpoint.lower()
        if "://" in clean:
            clean = clean.split("://", 1)[1]
        clean = clean.split("/", 1)[0].split(":", 1)[0]
        return clean

    def inspect_payload(self, payload: Any) -> Tuple[bool, List[str], List[str]]:
        """
        Inspect outgoing payload for prohibited raw matrices, PHI, or credentials.
        Returns: (is_safe, fields_detected, violation_reasons)
        """
        payload_str = json.dumps(payload, default=str) if not isinstance(payload, str) else payload
        fields_detected: List[str] = []
        violations: List[str] = []

        # Check payload size (raw matrices are typically large)
        if len(payload_str.encode("utf-8")) > 1_000_000 and self.mode == EgressMode.ALLOWLIST:
            violations.append("Payload size exceeds 1MB in ALLOWLIST mode (potential raw matrix transmission)")

        # Inspect dictionary keys and values
        if isinstance(payload, dict):
            for k in payload.keys():
                fields_detected.append(str(k))
                for pattern, desc in PHI_OR_RAW_DATA_PATTERNS:
                    if pattern.search(str(k)):
                        violations.append(f"Prohibited field in payload key '{k}': {desc}")

        # Regex scan for PHI, credentials, or embedded matrices
        for pattern, desc in PHI_OR_RAW_DATA_PATTERNS:
            if pattern.search(payload_str):
                violations.append(f"Prohibited pattern detected: {desc}")

        return (len(violations) == 0, fields_detected, violations)

    def evaluate_request(
        self,
        endpoint: str,
        purpose: str,
        payload: Any = None,
        data_classification: DataClassification = DataClassification.PUBLIC_BENCHMARK,
    ) -> Tuple[bool, EgressAuditRecord]:
        """
        Evaluate an outgoing network / MCP request against the active Data Egress Contract.
        Returns (is_permitted, audit_record).
        """
        domain = self.extract_domain(endpoint)
        audit_endpoint = _endpoint_without_query(endpoint)
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_bytes = json.dumps(payload, default=str).encode("utf-8") if payload is not None else b""
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        record_id = hashlib.sha256(f"{timestamp}:{audit_endpoint}:{payload_sha256}".encode("utf-8")).hexdigest()[:16]

        is_safe, fields_transmitted, violations = self.inspect_payload(payload)

        # 1. OFFLINE_STRICT: strictly no external egress
        if self.mode == EgressMode.OFFLINE_STRICT:
            rec = EgressAuditRecord(
                record_id=record_id,
                timestamp=timestamp,
                egress_mode=self.mode.value,
                endpoint=audit_endpoint,
                domain=domain,
                purpose=purpose,
                fields_transmitted=fields_transmitted,
                payload_sha256=payload_sha256,
                outcome="BLOCKED",
                block_reason="OFFLINE_STRICT policy prohibits all external network and cloud MCP egress",
                data_classification=data_classification.value,
            )
            self._log_record(rec)
            return False, rec

        # 2. RESTRICTED_CLINICAL_PHI or CONTROLLED_ACCESS data with ALLOWLIST
        if data_classification in (DataClassification.RESTRICTED_CLINICAL_PHI, DataClassification.CONTROLLED_ACCESS_GENOMIC):
            if self.mode != EgressMode.OFFLINE_STRICT:
                rec = EgressAuditRecord(
                    record_id=record_id,
                    timestamp=timestamp,
                    egress_mode=self.mode.value,
                    endpoint=audit_endpoint,
                    domain=domain,
                    purpose=purpose,
                    fields_transmitted=fields_transmitted,
                    payload_sha256=payload_sha256,
                    outcome="BLOCKED",
                    block_reason=f"Data classification '{data_classification.value}' strictly requires OFFLINE_STRICT local compute",
                    data_classification=data_classification.value,
                )
                self._log_record(rec)
                return False, rec

        # 3. ALLOWLIST mode
        if self.mode == EgressMode.ALLOWLIST:
            if domain not in self.allowed_domains:
                rec = EgressAuditRecord(
                    record_id=record_id,
                    timestamp=timestamp,
                    egress_mode=self.mode.value,
                    endpoint=audit_endpoint,
                    domain=domain,
                    purpose=purpose,
                    fields_transmitted=fields_transmitted,
                    payload_sha256=payload_sha256,
                    outcome="BLOCKED",
                    block_reason=f"Domain '{domain}' is not in approved scientific ALLOWLIST",
                    data_classification=data_classification.value,
                )
                self._log_record(rec)
                return False, rec

            if not is_safe:
                rec = EgressAuditRecord(
                    record_id=record_id,
                    timestamp=timestamp,
                    egress_mode=self.mode.value,
                    endpoint=audit_endpoint,
                    domain=domain,
                    purpose=purpose,
                    fields_transmitted=fields_transmitted,
                    payload_sha256=payload_sha256,
                    outcome="BLOCKED",
                    block_reason="; ".join(violations),
                    data_classification=data_classification.value,
                )
                self._log_record(rec)
                return False, rec

        # 4. CONNECTED mode or validated ALLOWLIST
        if not is_safe:
            rec = EgressAuditRecord(
                record_id=record_id,
                timestamp=timestamp,
                egress_mode=self.mode.value,
                endpoint=audit_endpoint,
                domain=domain,
                purpose=purpose,
                fields_transmitted=fields_transmitted,
                payload_sha256=payload_sha256,
                outcome="BLOCKED",
                block_reason="; ".join(violations),
                data_classification=data_classification.value,
            )
            self._log_record(rec)
            return False, rec

        rec = EgressAuditRecord(
            record_id=record_id,
            timestamp=timestamp,
            egress_mode=self.mode.value,
            endpoint=audit_endpoint,
            domain=domain,
            purpose=purpose,
            fields_transmitted=fields_transmitted,
            payload_sha256=payload_sha256,
            outcome="PERMITTED",
            data_classification=data_classification.value,
        )
        self._log_record(rec)
        return True, rec

    def record_response(self, record_id: str, response_payload: Any) -> None:
        """Record response hash for complete cryptographic audit trace."""
        if isinstance(response_payload, bytes):
            resp_bytes = response_payload
        else:
            resp_bytes = json.dumps(response_payload, default=str).encode("utf-8") if response_payload is not None else b""
        resp_hash = hashlib.sha256(resp_bytes).hexdigest()
        for r in self._records:
            if r.record_id == record_id:
                r.response_hash = resp_hash
                break

    def _log_record(self, record: EgressAuditRecord) -> None:
        """Append audit record to in-memory list and disk ledger."""
        self._records.append(record)
        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass  # Fallback to in-memory

    def get_audit_trail(self) -> List[EgressAuditRecord]:
        """Return all recorded audit entries."""
        return list(self._records)


# Global singleton instance for runtime interception
_GLOBAL_GUARD = DataGovernanceGuard()


def get_egress_guard() -> DataGovernanceGuard:
    """Get the active runtime DataGovernanceGuard instance."""
    return _GLOBAL_GUARD


class _AuditedHTTPResponse:
    """Transparent urllib response proxy that hashes streamed response bytes."""

    def __init__(self, response: Any, guard: DataGovernanceGuard, record_id: str) -> None:
        self._response = response
        self._guard = guard
        self._record_id = record_id
        self._hash = hashlib.sha256()
        self._finalized = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)

    def __enter__(self) -> _AuditedHTTPResponse:
        self._response.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        self._finalize()
        return self._response.__exit__(exc_type, exc, traceback)

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        chunk = self._response.read(*args, **kwargs)
        if chunk:
            self._hash.update(chunk)
        elif not args or args[0] in (-1, None):
            self._finalize()
        return chunk

    def close(self) -> None:
        self._finalize()
        self._response.close()

    def _finalize(self) -> None:
        if self._finalized:
            return
        response_hash = self._hash.hexdigest()
        for record in self._guard._records:
            if record.record_id == self._record_id:
                record.response_hash = response_hash
                break
        self._finalized = True


def guarded_urlopen(
    request: Any,
    *,
    timeout: float = 30,
    purpose: str = "BioNexus public scientific resource request",
    payload: Any = None,
    data_classification: DataClassification = DataClassification.PUBLIC_BENCHMARK,
    guard: Optional[DataGovernanceGuard] = None,
) -> _AuditedHTTPResponse:
    """Policy-check and audit an urllib request before any bytes leave the host."""
    active_guard = guard or get_egress_guard()
    endpoint = request.full_url if hasattr(request, "full_url") else str(request)
    body = getattr(request, "data", None)
    inspected_payload = payload if payload is not None else _request_payload(endpoint, body)
    permitted, record = active_guard.evaluate_request(
        endpoint=endpoint,
        purpose=purpose,
        payload=inspected_payload,
        data_classification=data_classification,
    )
    if not permitted:
        raise EgressBlockedError(record.block_reason or "Network egress blocked by BioNexus policy")
    response = urllib.request.urlopen(request, timeout=timeout)
    return _AuditedHTTPResponse(response, active_guard, record.record_id)


def guarded_requests_get(
    url: str,
    *,
    request_get: Any,
    purpose: str = "BioNexus public scientific resource request",
    payload: Any = None,
    data_classification: DataClassification = DataClassification.PUBLIC_BENCHMARK,
    guard: Optional[DataGovernanceGuard] = None,
    **kwargs: Any,
) -> Any:
    """Policy-check and audit a requests.get call."""
    active_guard = guard or get_egress_guard()
    inspected_payload = payload if payload is not None else _request_payload(url)
    permitted, record = active_guard.evaluate_request(
        endpoint=url,
        purpose=purpose,
        payload=inspected_payload,
        data_classification=data_classification,
    )
    if not permitted:
        raise EgressBlockedError(record.block_reason or "Network egress blocked by BioNexus policy")
    response = request_get(url, **kwargs)
    active_guard.record_response(record.record_id, response.content)
    return response
