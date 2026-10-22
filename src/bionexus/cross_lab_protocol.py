"""Local report inventory with explicitly pending external replication.

No host identities or replication executions are manufactured. Checksum equality
alone cannot establish independent hosts, execution, or laboratory agreement.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class HostEnvironmentFingerprint:
    """Tamper-evident record of one computational execution host."""

    host_id: str
    platform_system: str
    platform_release: str
    python_version: str
    repo_commit_sha: str
    execution_mode: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossHostExecutionComparison:
    """Comparison of capability outputs between primary and independent replication hosts."""

    capability_id: str
    study_id: str
    primary_host_id: str
    replication_host_id: str
    primary_checksum: str
    replication_checksum: str
    warrants_identical: Optional[bool]
    agreement_rate: Optional[float]
    verified: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiLabCertificationDossier:
    """Inventory and pending status; metadata alone proves no external execution."""

    dossier_id: str
    generated_at: str
    participating_hosts: List[HostEnvironmentFingerprint]
    comparisons: List[CrossHostExecutionComparison]
    overall_agreement_rate: Optional[float]
    standard_13_satisfied: bool
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "generated_at": self.generated_at,
            "participating_hosts": [h.to_dict() for h in self.participating_hosts],
            "comparisons": [c.to_dict() for c in self.comparisons],
            "overall_agreement_rate": self.overall_agreement_rate,
            "standard_13_satisfied": self.standard_13_satisfied,
            "status": self.status,
            "evidence_kind": "LOCAL_REPORT_INVENTORY",
            "scientific_authorization": "NONE",
            "agreement_status": "NOT_ESTIMABLE",
        }


def capture_host_fingerprint(host_id: str, repo_root: Path, execution_mode: str = "native_runtime") -> HostEnvironmentFingerprint:
    """Capture host telemetry, binding a commit only at the requested Git root."""
    commit_sha = ""
    try:
        requested_root = repo_root.resolve()
        root_result = subprocess.run(
            ["git", "-C", str(requested_root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        observed_root = root_result.stdout.strip()
        # Git searches parent directories. A nested data folder must not inherit
        # that ancestor's provenance. Git's own root also supports .git files.
        if root_result.returncode == 0 and observed_root and Path(observed_root).resolve() == requested_root:
            result = subprocess.run(
                ["git", "-C", str(requested_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            observed = result.stdout.strip()
            if result.returncode == 0 and len(observed) in (40, 64) and all(c in "0123456789abcdef" for c in observed):
                commit_sha = observed
    except (OSError, subprocess.TimeoutExpired):
        pass  # Unknown provenance stays unknown; never invent a fallback revision.

    return HostEnvironmentFingerprint(
        host_id=host_id,
        platform_system=platform.system(),
        platform_release=platform.release(),
        python_version=sys.version.split()[0],
        repo_commit_sha=commit_sha,
        execution_mode=execution_mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def build_cross_host_dossier(
    *,
    repo_root: Path,
    studies_to_compare: List[Tuple[str, str, Path]],
) -> MultiLabCertificationDossier:
    """Inventory local reports while independent replication is still missing.

    A local file or matching checksum is not evidence of execution on another
    host. This legacy API accepts no external run receipts, so it cannot satisfy
    Standard 13. A missing primary report is recorded rather than skipped.
    """
    host = capture_host_fingerprint("host-local-primary", repo_root, execution_mode="local_report_inventory")
    comparisons = [
        CrossHostExecutionComparison(
            capability_id=cap_id,
            study_id=study_id,
            primary_host_id=host.host_id,
            replication_host_id="",
            primary_checksum=hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path.is_file() else "",
            replication_checksum="",
            warrants_identical=None,
            agreement_rate=None,
            verified=False,
        )
        for cap_id, study_id, report_path in studies_to_compare
    ]
    return MultiLabCertificationDossier(
        dossier_id="BND-CROSS-HOST-PENDING",
        generated_at=datetime.now(timezone.utc).isoformat(),
        participating_hosts=[host],
        comparisons=comparisons,
        overall_agreement_rate=None,
        standard_13_satisfied=False,
        status="PENDING_EXTERNAL_REPLICATION",
    )
