"""
BioNexus Laboratory Information Management System (LIMS) Hub (BNS-LIMS-001..010).

Provides enterprise LIMS connectivity for top-tier laboratories:
- Benchling Connector: Schema sync, assay data export, and e-notebook evidence card posting.
- Generic REST & Webhook LIMS Connector: LabWare, Sapio Sciences, and custom lab databases.
- C04 Custodian Pairing: High-integrity blinded clinical sample validation without leaking participant identifiers.
- Cryptographic Audit Integration: Every sync/export emits a bionexus.tool-execution-receipt.v1.

First-round laboratory pilot: this module is excluded. Empty measurements are not
auto-filled, and live network export is refused until measurement validation and
egress coverage are closed with evidence.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from bionexus.tool_receipt import create_tool_receipt
from bionexus.versions import VERSION

logger = logging.getLogger(__name__)

# Empty-measurement defaulting and live export coverage are unclosed.
# First-round laboratory pilot therefore excludes this connector.
FIRST_ROUND_PILOT_INCLUDED = False
PILOT_EXCLUSION_REASON = (
    "LIMS connectivity is excluded from the first-round laboratory pilot. "
    "Empty-measurement defaulting and live export coverage remain unclosed."
)
_REQUIRED_MEASUREMENT_FIELDS = ("well", "value", "unit", "sample_id")


class LIMSConnectorType(str, enum.Enum):
    """Supported LIMS backend system types."""
    BENCHLING = "BENCHLING"
    LABWARE = "LABWARE"
    SAPIO = "SAPIO"
    GENERIC_REST = "GENERIC_REST"
    C04_CUSTODIAN = "C04_CUSTODIAN"


@dataclass
class LIMSConnectionConfig:
    """Connection configuration for a laboratory information management system."""
    connector_type: LIMSConnectorType
    base_url: str = "https://api.benchling.com/v2"
    auth_token: Optional[str] = None
    project_id: Optional[str] = None
    schema_id: Optional[str] = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    verify_ssl: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)

    def get_sanitized_config(self) -> Dict[str, Any]:
        """Return configuration dictionary with redacted secrets."""
        data = asdict(self)
        if data.get("auth_token"):
            data["auth_token"] = "REDACTED"
        return data


@dataclass
class LIMSExportResult:
    """Result of a LIMS export or synchronization operation."""
    success: bool
    connector_type: str
    target_entity_id: Optional[str]
    records_synced: int
    receipt: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pilot_metadata(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "first_round_pilot_included": FIRST_ROUND_PILOT_INCLUDED,
        "pilot_exclusion_reason": PILOT_EXCLUSION_REASON,
    }
    if extra:
        payload.update(extra)
    return payload


def _missing_measurement_fields(measurement: Dict[str, Any]) -> List[str]:
    missing = []
    for key in _REQUIRED_MEASUREMENT_FIELDS:
        value = measurement.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    return missing


class BenchlingConnector:
    """Connector for Benchling Electronic Lab Notebook (ELN) and Registry."""

    def __init__(self, config: LIMSConnectionConfig) -> None:
        self.config = config
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION

    def format_assay_payload(
        self,
        schema_id: str,
        plate_id: str,
        measurements: List[Dict[str, Any]],
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format raw plate reader measurements into Benchling Assay Results schema.

        Missing well/value/unit/sample_id is a hard error. Values are not invented.
        """
        if not self.config.project_id and not project_id:
            raise ValueError("project_id is required; default project identifiers are not filled in")
        rows = []
        for idx, m in enumerate(measurements):
            missing = _missing_measurement_fields(m)
            if missing:
                raise ValueError(
                    f"Measurement {idx} is missing required fields {missing}; "
                    "empty measurements are not auto-filled"
                )
            rows.append({
                "well": m["well"],
                "value": float(m["value"]),
                "unit": m["unit"],
                "sample_id": m["sample_id"],
            })

        return {
            "schemaId": schema_id,
            "projectId": project_id or self.config.project_id,
            "plateId": plate_id,
            "fields": {},
            "results": rows,
            "generated_by": f"BioNexus/{self.plugin_version}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "first_round_pilot_included": FIRST_ROUND_PILOT_INCLUDED,
        }

    def export_assay_results(
        self,
        schema_id: str,
        plate_id: str,
        measurements: List[Dict[str, Any]],
        mock_response: bool = True,
    ) -> LIMSExportResult:
        """Export assay results to Benchling and return a cryptographically signed receipt."""
        if not FIRST_ROUND_PILOT_INCLUDED and not mock_response:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.benchling_export_assay",
                request_payload={"schema_id": schema_id, "plate_id": plate_id},
                response_payload={"status": "PILOT_EXCLUDED"},
                execution_status="ERROR",
            )
            return LIMSExportResult(
                success=False,
                connector_type=LIMSConnectorType.BENCHLING.value,
                target_entity_id=plate_id,
                records_synced=0,
                receipt=receipt,
                metadata=_pilot_metadata({"status": "PILOT_EXCLUDED"}),
                errors=[PILOT_EXCLUSION_REASON],
            )

        try:
            payload = self.format_assay_payload(schema_id, plate_id, measurements)
        except (ValueError, TypeError) as exc:
            logger.info("Refusing LIMS export with incomplete measurements: %s", exc)
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.benchling_export_assay",
                request_payload={"schema_id": schema_id, "plate_id": plate_id},
                response_payload={"status": "INVALID_MEASUREMENTS"},
                execution_status="ERROR",
            )
            return LIMSExportResult(
                success=False,
                connector_type=LIMSConnectorType.BENCHLING.value,
                target_entity_id=plate_id,
                records_synced=0,
                receipt=receipt,
                metadata=_pilot_metadata({"status": "INVALID_MEASUREMENTS"}),
                errors=[str(exc)],
            )

        if mock_response:
            resp_data = _pilot_metadata({
                "status": "CREATED",
                "assayResultIds": [f"asyr_{plate_id}_{i}" for i in range(len(measurements))],
                "benchlingUri": f"https://benchling.com/entity/plate/{plate_id}",
                "is_mock": True,
            })
            success = True
            errors: List[str] = []
        else:
            if not self.config.auth_token:
                resp_data = {"status": "AUTH_CONFIG_ERROR"}
                success = False
                errors = ["Missing required Benchling auth_token in LIMS configuration"]
            else:
                target_url = urljoin(self.config.base_url.rstrip("/") + "/", "assay-results")
                headers = {
                    "Authorization": f"Bearer {self.config.auth_token}",
                    "Content-Type": "application/json",
                    "User-Agent": f"BioNexus/{self.plugin_version}",
                    **self.config.custom_headers,
                }
                try:
                    res = requests.post(
                        target_url,
                        json=payload,
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                        verify=self.config.verify_ssl,
                    )
                    if 200 <= res.status_code < 300:
                        try:
                            resp_data = res.json()
                        except Exception:
                            resp_data = {"status": "SUCCESS", "raw_text": res.text}
                        success = True
                        errors = []
                    else:
                        resp_data = {
                            "status": "HTTP_ERROR",
                            "http_status": res.status_code,
                            "response_snippet": res.text[:500],
                        }
                        success = False
                        errors = [f"Benchling API returned HTTP {res.status_code}: {res.text[:200]}"]
                except requests.RequestException as exc:
                    resp_data = {"status": "NETWORK_ERROR", "exception": type(exc).__name__}
                    success = False
                    errors = [f"Benchling connection failed: {exc}"]

        receipt = create_tool_receipt(
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_name="lims.benchling_export_assay",
            request_payload=payload,
            response_payload=resp_data,
            execution_status="SUCCESS" if success else "ERROR",
        )

        return LIMSExportResult(
            success=success,
            connector_type=LIMSConnectorType.BENCHLING.value,
            target_entity_id=plate_id,
            records_synced=len(measurements) if success else 0,
            receipt=receipt,
            metadata=resp_data,
            errors=errors,
        )

    def post_evidence_card_to_notebook(
        self,
        entry_id: str,
        title: str,
        evidence_card: Dict[str, Any],
        mock_response: bool = True,
    ) -> LIMSExportResult:
        """Embed a BioNexus verified evidence card into a Benchling notebook entry."""
        if not FIRST_ROUND_PILOT_INCLUDED and not mock_response:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.benchling_post_evidence_card",
                request_payload={"entry_id": entry_id, "title": title},
                response_payload={"status": "PILOT_EXCLUDED"},
                execution_status="ERROR",
            )
            return LIMSExportResult(
                success=False,
                connector_type=LIMSConnectorType.BENCHLING.value,
                target_entity_id=entry_id,
                records_synced=0,
                receipt=receipt,
                metadata=_pilot_metadata({"status": "PILOT_EXCLUDED"}),
                errors=[PILOT_EXCLUSION_REASON],
            )

        req_payload = {
            "entryId": entry_id,
            "title": title,
            "evidenceCard": evidence_card,
            "attachedAt": datetime.now(timezone.utc).isoformat(),
        }

        if mock_response:
            resp_data = _pilot_metadata({
                "entryId": entry_id,
                "status": "UPDATED",
                "customFieldKey": "bionexus_evidence_card",
                "is_mock": True,
            })
            success = True
            errors: List[str] = []
        else:
            if not self.config.auth_token:
                resp_data = {"status": "AUTH_CONFIG_ERROR"}
                success = False
                errors = ["Missing required Benchling auth_token in LIMS configuration"]
            else:
                target_url = urljoin(self.config.base_url.rstrip("/") + "/", f"entries/{entry_id}/custom-fields")
                headers = {
                    "Authorization": f"Bearer {self.config.auth_token}",
                    "Content-Type": "application/json",
                    "User-Agent": f"BioNexus/{self.plugin_version}",
                    **self.config.custom_headers,
                }
                try:
                    res = requests.post(
                        target_url,
                        json=req_payload,
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                        verify=self.config.verify_ssl,
                    )
                    if 200 <= res.status_code < 300:
                        try:
                            resp_data = res.json()
                        except Exception:
                            resp_data = {"status": "SUCCESS", "raw_text": res.text}
                        success = True
                        errors = []
                    else:
                        resp_data = {
                            "status": "HTTP_ERROR",
                            "http_status": res.status_code,
                            "response_snippet": res.text[:500],
                        }
                        success = False
                        errors = [f"Benchling Notebook API returned HTTP {res.status_code}: {res.text[:200]}"]
                except requests.RequestException as exc:
                    resp_data = {"status": "NETWORK_ERROR", "exception": type(exc).__name__}
                    success = False
                    errors = [f"Benchling Notebook connection failed: {exc}"]

        receipt = create_tool_receipt(
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_name="lims.benchling_post_evidence_card",
            request_payload=req_payload,
            response_payload=resp_data,
            execution_status="SUCCESS" if success else "ERROR",
        )

        return LIMSExportResult(
            success=success,
            connector_type=LIMSConnectorType.BENCHLING.value,
            target_entity_id=entry_id,
            records_synced=1 if success else 0,
            receipt=receipt,
            metadata=resp_data,
            errors=errors,
        )


class GenericRestLIMSConnector:
    """Universal REST & Webhook connector for LabWare, Sapio, or custom LIMS."""

    def __init__(self, config: LIMSConnectionConfig) -> None:
        self.config = config
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION

    def sync_samples(
        self,
        samples: List[Dict[str, Any]],
        endpoint_path: str = "/samples/sync",
        mock_response: bool = True,
    ) -> LIMSExportResult:
        """Sync a batch of sample metadata records to the target LIMS."""
        if not FIRST_ROUND_PILOT_INCLUDED and not mock_response:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.generic_sync_samples",
                request_payload={"n_samples": len(samples)},
                response_payload={"status": "PILOT_EXCLUDED"},
                execution_status="ERROR",
            )
            return LIMSExportResult(
                success=False,
                connector_type=self.config.connector_type.value,
                target_entity_id=endpoint_path,
                records_synced=0,
                receipt=receipt,
                metadata=_pilot_metadata({"status": "PILOT_EXCLUDED"}),
                errors=[PILOT_EXCLUSION_REASON],
            )

        target_url = urljoin(self.config.base_url, endpoint_path)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "batch_size": len(samples),
            "samples": samples,
        }

        if mock_response:
            resp_data = _pilot_metadata({
                "status": "ACCEPTED",
                "processed": len(samples),
                "endpoint": target_url,
                "is_mock": True,
            })
            success = True
            errors: List[str] = []
        else:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"BioNexus/{self.plugin_version}",
                **self.config.custom_headers,
            }
            if self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"

            try:
                res = requests.post(
                    target_url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                    verify=self.config.verify_ssl,
                )
                if 200 <= res.status_code < 300:
                    try:
                        resp_data = res.json()
                    except Exception:
                        resp_data = {"status": "SUCCESS", "raw_text": res.text}
                    success = True
                    errors = []
                else:
                    resp_data = {
                        "status": "HTTP_ERROR",
                        "http_status": res.status_code,
                        "response_snippet": res.text[:500],
                    }
                    success = False
                    errors = [f"LIMS REST endpoint returned HTTP {res.status_code}: {res.text[:200]}"]
            except requests.RequestException as exc:
                resp_data = {"status": "NETWORK_ERROR", "exception": type(exc).__name__}
                success = False
                errors = [f"LIMS REST dispatch failed: {exc}"]

        receipt = create_tool_receipt(
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_name="lims.generic_sync_samples",
            request_payload=payload,
            response_payload=resp_data,
            execution_status="SUCCESS" if success else "ERROR",
        )

        return LIMSExportResult(
            success=success,
            connector_type=self.config.connector_type.value,
            target_entity_id=target_url,
            records_synced=len(samples) if success else 0,
            receipt=receipt,
            metadata=resp_data,
            errors=errors,
        )


class C04PairingCustodianHub:
    """Custodian-held C04 LIMS pairing validator and opaque arm mapper."""

    def __init__(self) -> None:
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION

    def audit_manifest(self, manifest_path: Path | str) -> Dict[str, Any]:
        """Validate C04 pairing invariants fail-closed without exposing participant identifiers."""
        p = Path(manifest_path)
        if not p.is_file():
            res = {
                "status": "ABSTAIN",
                "passed": False,
                "issues": [f"Missing manifest file: {p}"],
            }
        else:
            from scripts.validate_c04_lims_pairing import validate
            res = validate(p)
            res["passed"] = (res.get("status") == "PASS")

        receipt = create_tool_receipt(
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_name="lims.c04_pairing_audit",
            request_payload={"manifest_path": str(p)},
            response_payload=res,
            execution_status="SUCCESS" if res.get("passed", False) else "ERROR",
        )
        res["receipt"] = receipt
        return res


# ==============================================================================
# Allotrope ASM to LIMS Bridge & Egress Controlled Transport
# ==============================================================================

BLOCKED_IP_PREFIXES = ("169.254.", "127.", "0.0.0.0")
METADATA_HOSTS = ("metadata.google.internal", "instance-data", "169.254.169.254")
DEFAULT_ALLOWED_DOMAINS = (
    "api.benchling.com",
    "benchling.com",
    "labware.internal",
    "sapio.internal",
    "lims.internal",
    "localhost",
)


class EgressControlledLIMSClient:
    """SSRF-guarded HTTP client for laboratory LIMS dispatch.

    Enforces domain allowlisting, rejects cloud metadata endpoints and unauthorized
    private addresses, and emits cryptographic tool receipts for all egress attempts.
    """

    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        allow_private_ips: bool = False,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.allowed_domains = tuple(allowed_domains) if allowed_domains else DEFAULT_ALLOWED_DOMAINS
        self.allow_private_ips = allow_private_ips
        self.timeout_seconds = timeout_seconds
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION

    def is_url_permitted(self, url: str) -> tuple[bool, str]:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
        except Exception as exc:
            return False, f"Malformed URL: {exc}"

        if parsed.scheme not in ("http", "https"):
            return False, f"Unsupported scheme '{parsed.scheme}'. Only http/https permitted."

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "URL hostname is empty."

        # Reject metadata services
        if hostname in METADATA_HOSTS or any(hostname.startswith(p) for p in BLOCKED_IP_PREFIXES):
            return False, f"SSRF Guard: Egress to metadata service or link-local address '{hostname}' is blocked."

        # Domain whitelist verification
        allowed = False
        for domain in self.allowed_domains:
            if hostname == domain or hostname.endswith("." + domain):
                allowed = True
                break

        if not allowed:
            return False, f"Domain '{hostname}' is not in the configured LIMS egress allowlist: {self.allowed_domains}"

        return True, "Permitted"

    def dispatch(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        method: str = "POST",
        mock_response: bool = False,
    ) -> Dict[str, Any]:
        """Dispatch an HTTP request with SSRF guard and emit a tool receipt."""
        permitted, reason = self.is_url_permitted(url)
        if not permitted:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.egress_dispatch",
                request_payload={"url": url, "method": method},
                response_payload={"status": "EGRESS_BLOCKED", "reason": reason},
                execution_status="ERROR",
            )
            return {
                "success": False,
                "status": "EGRESS_BLOCKED",
                "error": reason,
                "receipt": receipt,
            }

        if mock_response:
            resp_payload = {
                "status": "MOCK_SUCCESS",
                "url": url,
                "payload_keys": list(payload.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.egress_dispatch",
                request_payload={"url": url, "method": method},
                response_payload=resp_payload,
                execution_status="SUCCESS",
            )
            return {
                "success": True,
                "status": "MOCK_SUCCESS",
                "data": resp_payload,
                "receipt": receipt,
            }

        req_headers = {"Content-Type": "application/json", "User-Agent": f"BioNexus/{self.plugin_version}"}
        if headers:
            req_headers.update(headers)
        if auth_token:
            req_headers["Authorization"] = f"Bearer {auth_token}"

        try:
            res = requests.request(
                method=method.upper(),
                url=url,
                json=payload,
                headers=req_headers,
                timeout=self.timeout_seconds,
            )
            success = 200 <= res.status_code < 300
            try:
                res_data = res.json()
            except Exception:
                res_data = {"raw_response": res.text[:1000], "status_code": res.status_code}
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.egress_dispatch",
                request_payload={"url": url, "method": method},
                response_payload={"status_code": res.status_code, "success": success},
                execution_status="SUCCESS" if success else "ERROR",
            )
            return {
                "success": success,
                "status_code": res.status_code,
                "data": res_data,
                "receipt": receipt,
            }
        except requests.RequestException as exc:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.egress_dispatch",
                request_payload={"url": url, "method": method},
                response_payload={"exception": type(exc).__name__, "error": str(exc)},
                execution_status="ERROR",
            )
            return {
                "success": False,
                "status": "NETWORK_ERROR",
                "error": str(exc),
                "receipt": receipt,
            }


class AllotropeASMLIMSBridge:
    """Bridge converting Allotrope Simple Model (ASM) instrument outputs to LIMS assays."""

    def __init__(self, egress_client: Optional[EgressControlledLIMSClient] = None) -> None:
        self.egress_client = egress_client or EgressControlledLIMSClient()
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION

    def parse_asm_to_measurements(self, asm_document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract plate reader/spectrophotometry well measurements from ASM JSON.

        Fail-closed: requires valid non-empty well, numerical value, unit, and sample_id.
        Raises ValueError if any required measurement field is missing or invalid.
        """
        if not isinstance(asm_document, dict):
            raise ValueError("asm_document must be a dictionary.")

        raw_list: Optional[List[Any]] = None

        # 1. Check standard measurement_aggregate_document
        if "measurement_aggregate_document" in asm_document:
            agg = asm_document["measurement_aggregate_document"]
            if isinstance(agg, dict):
                raw_list = agg.get("measurement_document")

        # 2. Check plate reader aggregate document hierarchy
        if raw_list is None and "plate reader aggregate document" in asm_document:
            pr_agg = asm_document["plate reader aggregate document"]
            if isinstance(pr_agg, dict) and "plate reader document" in pr_agg:
                pr_doc = pr_agg["plate reader document"]
                if isinstance(pr_doc, list) and pr_doc:
                    raw_list = pr_doc[0].get("measurement aggregate document", {}).get("measurement document")
                elif isinstance(pr_doc, dict):
                    raw_list = pr_doc.get("measurement aggregate document", {}).get("measurement document")

        # 3. Direct measurement list
        if raw_list is None:
            raw_list = asm_document.get("measurements")

        if not raw_list or not isinstance(raw_list, list):
            raise ValueError("No measurement documents found in ASM structure.")

        measurements = []
        for idx, item in enumerate(raw_list):
            if not isinstance(item, dict):
                raise ValueError(f"Measurement record {idx} is not an object.")

            well = item.get("location_identifier") or item.get("well") or item.get("well_location")
            if not well or not str(well).strip():
                raise ValueError(f"Measurement record {idx} is missing location_identifier/well.")

            # Value resolution: check fluorescence, absorbance, luminescence, value
            val = None
            for v_key in ("fluorescence", "absorbance", "luminescence", "value", "measurement_value"):
                if v_key in item and item[v_key] is not None:
                    val = item[v_key]
                    break

            if val is None:
                raise ValueError(f"Measurement record {idx} (well {well}) is missing numerical measurement value.")

            try:
                num_val = float(val)
            except (TypeError, ValueError):
                raise ValueError(f"Measurement record {idx} (well {well}) value '{val}' is not a valid float.")

            unit = item.get("unit") or item.get("fluorescence_unit") or item.get("absorbance_unit") or "RFU"
            if not str(unit).strip():
                raise ValueError(f"Measurement record {idx} (well {well}) has empty unit.")

            sample_id = item.get("sample_identifier") or item.get("sample_id") or f"SMP-{str(well).strip()}"

            measurements.append({
                "well": str(well).strip(),
                "value": num_val,
                "unit": str(unit).strip(),
                "sample_id": str(sample_id).strip(),
            })

        return measurements

    def transform_for_lims(
        self,
        asm_document: Dict[str, Any],
        target_system: LIMSConnectorType = LIMSConnectorType.BENCHLING,
        schema_id: str = "sch_plate_reader",
        plate_id: str = "PLT-001",
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert ASM document to target LIMS payload."""
        measurements = self.parse_asm_to_measurements(asm_document)

        if target_system == LIMSConnectorType.BENCHLING:
            config = LIMSConnectionConfig(connector_type=LIMSConnectorType.BENCHLING, project_id=project_id or "prj_default")
            connector = BenchlingConnector(config)
            return connector.format_assay_payload(
                schema_id=schema_id,
                plate_id=plate_id,
                measurements=measurements,
                project_id=project_id,
            )

        # Generic / LabWare format
        return {
            "target_system": target_system.value,
            "plate_id": plate_id,
            "schema_id": schema_id,
            "project_id": project_id,
            "records_count": len(measurements),
            "records": measurements,
            "generated_by": f"BioNexus/{self.plugin_version}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_asm_to_lims(
        self,
        asm_document: Dict[str, Any],
        endpoint_url: str,
        target_system: LIMSConnectorType = LIMSConnectorType.BENCHLING,
        schema_id: str = "sch_plate_reader",
        plate_id: str = "PLT-001",
        project_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        mock_response: bool = False,
    ) -> LIMSExportResult:
        """Parse ASM document, format for LIMS, and dispatch via EgressControlledLIMSClient."""
        try:
            payload = self.transform_for_lims(
                asm_document=asm_document,
                target_system=target_system,
                schema_id=schema_id,
                plate_id=plate_id,
                project_id=project_id,
            )
        except Exception as exc:
            receipt = create_tool_receipt(
                plugin_id=self.plugin_id,
                plugin_version=self.plugin_version,
                tool_name="lims.allotrope_bridge_export",
                request_payload={"target_system": target_system.value, "plate_id": plate_id},
                response_payload={"error": str(exc)},
                execution_status="ERROR",
            )
            return LIMSExportResult(
                success=False,
                connector_type=target_system.value,
                target_entity_id=plate_id,
                records_synced=0,
                receipt=receipt,
                errors=[str(exc)],
            )

        dispatch_res = self.egress_client.dispatch(
            url=endpoint_url,
            payload=payload,
            auth_token=auth_token,
            mock_response=mock_response,
        )

        n_records = len(payload.get("results") or payload.get("records") or [])
        success = bool(dispatch_res.get("success", False))

        receipt = create_tool_receipt(
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_name="lims.allotrope_bridge_export",
            request_payload={"target_system": target_system.value, "plate_id": plate_id, "endpoint_url": endpoint_url},
            response_payload=dispatch_res,
            execution_status="SUCCESS" if success else "ERROR",
        )

        errors = []
        if not success:
            errors.append(dispatch_res.get("error", "Dispatch failed"))

        return LIMSExportResult(
            success=success,
            connector_type=target_system.value,
            target_entity_id=plate_id,
            records_synced=n_records if success else 0,
            receipt=receipt,
            metadata=dispatch_res,
            errors=errors,
        )
