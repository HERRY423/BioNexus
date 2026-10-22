"""Opt-in, local-first anonymous failure reports.

Default is off. Air-gapped, PHI, and controlled-access modes never transmit.
BioNexus does not ship a vendor telemetry backend in this release.
"""

from __future__ import annotations

import json
import os
import platform
import re
import traceback
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request

from bionexus.egress_guard import (
    DataClassification,
    DataGovernanceGuard,
    EgressBlockedError,
    EgressMode,
    guarded_urlopen,
)
from bionexus.schema_registry import SchemaError, validate_document
from bionexus.versions import PLUGIN_VERSION

SCHEMA_VERSION = "bionexus.failure-report.v1"
ENV_MODE = "BIONEXUS_FAILURE_REPORTS"
ENV_ENDPOINT = "BIONEXUS_FAILURE_REPORTS_ENDPOINT"
ENV_DIR = "BIONEXUS_FAILURE_REPORTS_DIR"
MODE_OFF = "off"
MODE_LOCAL = "local"
MODE_TRANSMIT = "transmit"

_PATH_RE = re.compile(r"(?i)(?:[a-z]:\\|\\\\|/)[^\s'\"<>]+")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_USER_RE = re.compile(r"(?i)\b(?:users|home)[/\\][^/\\]+")
_PHI_RE = re.compile(
    r"(?i)\b(mrn|patient_id|ssn|date_of_birth|dob|patient_name|medical_record_number)\b"
)
_SECRET_RE = re.compile(r"(?i)\b(ghp_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16})\b")
_SEQUENCE_RE = re.compile(r"\b[ACGTNacgtn]{80,}\b")


@dataclass
class FailureReport:
    """Sanitized, schema-versioned failure record."""

    schema_version: str
    report_id: str
    created_at: str
    bionexus_version: str
    python_version: str
    platform: str
    exception_type: str
    sanitized_traceback: str
    command: Optional[str]
    capability_id: Optional[str]
    egress_mode: str
    data_classification: str
    contains_phi: bool
    transmit_eligible: bool
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def report_mode(raw: Optional[str] = None) -> str:
    value = (raw if raw is not None else os.environ.get(ENV_MODE, MODE_OFF)).strip().lower()
    if value in {"1", "true", "yes", "on", MODE_TRANSMIT}:
        return MODE_TRANSMIT
    if value in {"local", "disk"}:
        return MODE_LOCAL
    return MODE_OFF


def sanitize_text(text: str, *, max_chars: int = 4000) -> str:
    """Strip paths, identifiers, secrets, and long sequences from diagnostic text."""
    cleaned = _PATH_RE.sub("<PATH>", text)
    cleaned = _EMAIL_RE.sub("<EMAIL>", cleaned)
    cleaned = _IP_RE.sub("<IP>", cleaned)
    cleaned = _USER_RE.sub("<USERDIR>", cleaned)
    cleaned = _SECRET_RE.sub("<SECRET>", cleaned)
    cleaned = _SEQUENCE_RE.sub("<SEQUENCE>", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 18] + "\n<TRUNCATED>"
    return cleaned


def _contains_phi(text: str) -> bool:
    return bool(_PHI_RE.search(text))


def local_report_dir() -> Path:
    override = os.environ.get(ENV_DIR)
    if override:
        return Path(override)
    return Path.home() / ".bionexus" / "failure-reports"


def telemetry_status() -> Dict[str, Any]:
    mode = report_mode()
    endpoint = os.environ.get(ENV_ENDPOINT, "")
    guard = DataGovernanceGuard()
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "default": MODE_OFF,
        "endpoint_configured": bool(endpoint),
        "endpoint": "<CONFIGURED>" if endpoint else None,
        "local_dir": str(local_report_dir()),
        "egress_mode": guard.mode.value,
        "vendor_backend": "NONE",
        "note": (
            "Failure reports are opt-in and local-first. BioNexus does not operate a "
            "telemetry service. Transmit requires CONNECTED egress, PUBLIC_BENCHMARK "
            "classification, an operator endpoint, and explicit opt-in."
        ),
    }


def build_failure_report(
    exc: BaseException | None = None,
    *,
    exception_type: Optional[str] = None,
    traceback_text: Optional[str] = None,
    command: Optional[str] = None,
    capability_id: Optional[str] = None,
    data_classification: str = "UNKNOWN",
    notes: str = "",
) -> FailureReport:
    """Build a sanitized report. Never includes argv paths or payload bytes."""
    if exc is not None:
        exception_type = exception_type or type(exc).__name__
        traceback_text = traceback_text or "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    if not exception_type:
        raise SchemaError("failure report requires an exception type")
    raw_trace = traceback_text or exception_type
    sanitized = sanitize_text(raw_trace)
    contains_phi = _contains_phi(raw_trace) or _contains_phi(notes)
    guard = DataGovernanceGuard()
    classification = DataClassification(data_classification) if data_classification != "UNKNOWN" else None
    blocked_class = classification in {
        DataClassification.RESTRICTED_CLINICAL_PHI,
        DataClassification.CONTROLLED_ACCESS_GENOMIC,
    }
    transmit_eligible = (
        report_mode() == MODE_TRANSMIT
        and guard.mode == EgressMode.CONNECTED
        and classification == DataClassification.PUBLIC_BENCHMARK
        and not contains_phi
        and bool(os.environ.get(ENV_ENDPOINT))
    )
    report = FailureReport(
        schema_version=SCHEMA_VERSION,
        report_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        bionexus_version=PLUGIN_VERSION,
        python_version=platform.python_version(),
        platform=sys_platform(),
        exception_type=sanitize_text(exception_type, max_chars=120),
        sanitized_traceback=sanitized,
        command=sanitize_text(command, max_chars=80) if command else None,
        capability_id=capability_id,
        egress_mode=guard.mode.value,
        data_classification=classification.value if classification else "UNKNOWN",
        contains_phi=contains_phi or blocked_class,
        transmit_eligible=transmit_eligible and not blocked_class,
        notes=sanitize_text(notes, max_chars=400) if notes else "",
    )
    result = validate_document(report.to_dict(), family="failure-report")
    if not result.valid:
        raise SchemaError("failure report failed schema: " + "; ".join(result.errors))
    return report


def sys_platform() -> str:
    return platform.system().lower() or "unknown"


def persist_failure_report(report: FailureReport, dest_dir: Optional[Path] = None) -> Path:
    directory = dest_dir or local_report_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.report_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def transmit_failure_report(report: FailureReport, *, opt_in: bool) -> Dict[str, Any]:
    """POST a sanitized report to a lab-configured endpoint. Never the default path."""
    if not opt_in:
        return {"status": "REFUSED", "reason": "transmit requires explicit operator opt-in"}
    guard = DataGovernanceGuard()
    if (
        not report.transmit_eligible
        or report.data_classification != DataClassification.PUBLIC_BENCHMARK.value
        or report.contains_phi
        or report_mode() != MODE_TRANSMIT
        or guard.mode != EgressMode.CONNECTED
        or not os.environ.get(ENV_ENDPOINT)
    ):
        return {
            "status": "REFUSED",
            "reason": "transmit blocked by mode, egress policy, classification, or missing endpoint",
        }
    endpoint = os.environ.get(ENV_ENDPOINT, "")
    payload = json.dumps(report.to_dict(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", f"BioNexus-FailureReport/{PLUGIN_VERSION}")
    try:
        with guarded_urlopen(
            request,
            timeout=10,
            purpose="opt-in anonymous BioNexus failure report",
            payload={"keys": sorted(report.to_dict().keys())},
            data_classification=DataClassification.PUBLIC_BENCHMARK,
        ) as response:
            status = getattr(response, "status", 0)
        return {"status": "SENT", "http_status": status}
    except EgressBlockedError as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    except OSError as exc:
        return {"status": "FAILED", "reason": sanitize_text(str(exc), max_chars=200)}


def capture_failure_report(
    exc: BaseException,
    *,
    command: Optional[str] = None,
    persist: bool = True,
    transmit: bool = False,
    dest_dir: Optional[Path] = None,
    data_classification: str = "UNKNOWN",
) -> Dict[str, Any]:
    """Library helper used by CLI. No-op when the mode is off and persist was not requested."""
    mode = report_mode()
    if mode == MODE_OFF and not persist:
        return {"status": "DISABLED", "mode": mode}
    report = build_failure_report(exc, command=command, data_classification=data_classification)
    outcome: Dict[str, Any] = {"status": "CAPTURED", "mode": mode, "report": report.to_dict()}
    if persist or mode in {MODE_LOCAL, MODE_TRANSMIT}:
        outcome["path"] = str(persist_failure_report(report, dest_dir=dest_dir))
    if transmit:
        outcome["transmit"] = transmit_failure_report(report, opt_in=True)
    return outcome
