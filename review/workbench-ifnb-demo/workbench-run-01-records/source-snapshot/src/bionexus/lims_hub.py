"""
BioNexus Laboratory Information Management System (LIMS) Hub (BNS-LIMS-001..010).

Provides enterprise LIMS connectivity for top-tier laboratories:
- Benchling Connector: Schema sync, assay data export, and e-notebook evidence card posting.
- Generic REST & Webhook LIMS Connector: LabWare, Sapio Sciences, and custom lab databases.
- C04 Custodian Pairing: High-integrity blinded clinical sample validation without leaking participant identifiers.
- Cryptographic Audit Integration: Every sync/export emits a bionexus.tool-execution-receipt.v1.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from bionexus.tool_receipt import create_tool_receipt
from bionexus.versions import VERSION


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
        """Format raw plate reader measurements into Benchling Assay Results schema."""
        fields_payload: Dict[str, Any] = {}
        rows = []
        for idx, m in enumerate(measurements):
            well = m.get("well", f"A{idx+1}")
            value = m.get("value", 0.0)
            unit = m.get("unit", "RFU")
            rows.append({
                "well": well,
                "value": float(value),
                "unit": unit,
                "sample_id": m.get("sample_id", f"SMP-{plate_id}-{well}"),
            })

        return {
            "schemaId": schema_id,
            "projectId": project_id or self.config.project_id or "prj_default",
            "plateId": plate_id,
            "fields": fields_payload,
            "results": rows,
            "generated_by": f"BioNexus/{self.plugin_version}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_assay_results(
        self,
        schema_id: str,
        plate_id: str,
        measurements: List[Dict[str, Any]],
        mock_response: bool = True,
    ) -> LIMSExportResult:
        """Export assay results to Benchling and return a cryptographically signed receipt."""
        payload = self.format_assay_payload(schema_id, plate_id, measurements)

        if mock_response:
            resp_data = {
                "status": "CREATED",
                "assayResultIds": [f"asyr_{plate_id}_{i}" for i in range(len(measurements))],
                "benchlingUri": f"https://benchling.com/entity/plate/{plate_id}",
                "is_mock": True,
            }
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
        req_payload = {
            "entryId": entry_id,
            "title": title,
            "evidenceCard": evidence_card,
            "attachedAt": datetime.now(timezone.utc).isoformat(),
        }

        if mock_response:
            resp_data = {
                "entryId": entry_id,
                "status": "UPDATED",
                "customFieldKey": "bionexus_evidence_card",
                "is_mock": True,
            }
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
        target_url = urljoin(self.config.base_url, endpoint_path)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "batch_size": len(samples),
            "samples": samples,
        }

        if mock_response:
            resp_data = {
                "status": "ACCEPTED",
                "processed": len(samples),
                "endpoint": target_url,
                "is_mock": True,
            }
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
