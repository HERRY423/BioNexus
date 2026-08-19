"""
BioNexus Backend Identity Conformance (BNS-EF-012..016, BN-F010).

The fourth conformance pillar, next to Capability Certification,
BioFailureBench, and Host Conformance.

Every capability must be able to answer, machine-checkably:

    Claimed backend:            PyDESeq2
    Observed executed backend:  PyDESeq2
    Entry point:                DeseqDataSet / DeseqStats
    Version:                    0.4.x
    Execution fingerprint:      sha256(...)
    Fallback:                   False

and the invariant is ``declared_backend == observed_backend``. A violation is
BN-F010 (backend degradation masquerading) and the action is BLOCK.

This upgrades BioNexus from "we say we never silently substitute" to
"the absence of silent substitution is machine-provable":

- the observed backend is resolved from the distribution that actually
  provides the imported top-level package (``importlib.metadata.
  packages_distributions``), never from a self-declared name;
- declared entry points are resolved symbol-by-symbol at audit time;
- a deterministic execution fingerprint binds backend + version + entry
  points into one hash that a ledger can carry.

States (normative):

- CONFORMANT            declared == observed, all entry points resolve,
                        version-compatible. Action: RUN PERMITTED (identity).
- NOT_INSTALLED         backend absent; nothing executed, no identity claim
                        made. The routing gate refuses execution (BNS-010
                        capability-bound backend gate); NOT a BN-F010.
- INCOMPATIBLE_VERSION  backend present but below the declared minimum:
                        the version contract is broken -> BLOCK (BN-F010).
- MASQUERADE            the import name resolves to a different distribution,
                        or a declared entry point is missing: something would
                        execute under a name it does not own -> BLOCK (BN-F010).

``fallback`` is always False in an identity report: a report that needed a
fallback would, by definition, be a masquerade.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.backends import BackendState, is_version_compatible, probe
from bionexus.capabilities import (
    ALL_CAPABILITIES,
    CANONICAL_CAPABILITIES,
    FRONTIER_CAPABILITIES,
    CapabilityContract,
)


class BackendIdentityState(str, Enum):
    """Normative outcome of one backend identity audit."""

    CONFORMANT = "CONFORMANT"
    NOT_INSTALLED = "NOT_INSTALLED"
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
    MASQUERADE = "MASQUERADE"


@dataclass
class BackendIdentityReport:
    """The machine-checkable identity statement for one capability's backend."""

    capability_id: str
    track: str  # "canonical" | "frontier"
    claimed_backend: str
    observed_backend: Optional[str]
    entry_points_declared: List[str] = field(default_factory=list)
    entry_points_resolved: List[str] = field(default_factory=list)
    entry_points_missing: List[str] = field(default_factory=list)
    version: Optional[str] = None
    execution_fingerprint: Optional[str] = None
    fallback: bool = False  # structural invariant: an identity report never hides a fallback
    state: BackendIdentityState = BackendIdentityState.NOT_INSTALLED
    action: str = "ABSTAIN"  # RUN PERMITTED (identity) | BLOCK | ABSTAIN
    failure_mode_ids: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def conformant(self) -> bool:
        return self.state == BackendIdentityState.CONFORMANT

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["state"] = self.state.value
        return out


def _norm_dist(name: str) -> str:
    """PEP 503-style normalization for distribution name comparison."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _top_level_package(import_name: str) -> str:
    return import_name.split(".")[0]


def _observed_distribution(import_name: str) -> Optional[str]:
    """The distribution that actually provides the top-level import name.

    This is the anti-masquerade witness: it comes from installed metadata,
    not from anything the caller claims.
    """
    top = _top_level_package(import_name)
    try:
        mapping = importlib.metadata.packages_distributions()
    except Exception:
        return None
    dists = mapping.get(top)
    if not dists:
        return None
    return dists[0]


def _resolve_entry_point(dotted: str) -> bool:
    """Resolve a dotted import path (module or module.attribute) without executing it."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        module_path = ".".join(parts[:cut])
        try:
            mod = importlib.import_module(module_path)
        except Exception:
            continue
        obj: Any = mod
        try:
            for attr in parts[cut:]:
                obj = getattr(obj, attr)
            return True
        except AttributeError:
            return False
    return False


def _fingerprint(claimed: str, observed: Optional[str], version: Optional[str], entry_points: List[str]) -> str:
    payload = "|".join(
        [
            claimed,
            observed or "<absent>",
            version or "<unknown>",
            ",".join(sorted(entry_points)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def verify_backend_identity(cap: CapabilityContract) -> BackendIdentityReport:
    """Audit one capability's backend identity: declared == observed, or BLOCK."""
    track = "frontier" if cap.id in FRONTIER_CAPABILITIES else "canonical"
    declared_entry_points = list(cap.backend.entry_points)

    report = BackendIdentityReport(
        capability_id=cap.id,
        track=track,
        claimed_backend=cap.backend.canonical_name,
        observed_backend=None,
        entry_points_declared=declared_entry_points,
    )

    import_name = cap.backend.import_name
    if not import_name or import_name == "none":
        # No backend declared at all: nothing to masquerade as.
        report.state = BackendIdentityState.CONFORMANT
        report.action = "RUN PERMITTED (identity)"
        report.observed_backend = "none"
        report.execution_fingerprint = _fingerprint("none", "none", None, [])
        report.reason = "Capability declares no external backend; identity is vacuously satisfied."
        return report

    status = probe(import_name)

    # Absent backend: honest refusal territory, handled by the routing gate.
    # No execution can occur, so no identity claim is made and no BN-F010 fires.
    if status.state in (BackendState.MISSING, BackendState.PARTIAL, BackendState.MISSING_BINARY, BackendState.MISSING_WEIGHTS):
        report.state = BackendIdentityState.NOT_INSTALLED
        report.action = "ABSTAIN"
        report.reason = (
            f"Backend '{cap.backend.canonical_name}' is not available ({status.state.value}). "
            "No execution can occur, so no identity claim is made; the capability-bound "
            "routing gate refuses execution (BNS-010)."
        )
        return report

    version = status.version
    observed = _observed_distribution(import_name)
    report.observed_backend = observed

    # In-tree backends (bionexus.*): no per-submodule distribution exists; the
    # identity version is the version of the bionexus package actually imported
    # — the honest runtime witness, not a per-module claim.
    top = _top_level_package(import_name)
    if top == "bionexus":
        try:
            version = version or getattr(importlib.import_module("bionexus"), "__version__", None)
        except Exception:
            pass
    report.version = version

    # Version contract: the contract-declared minimum is part of the identity
    # and is enforced here directly (probe() only knows the registry minimum).
    if status.state == BackendState.INCOMPATIBLE_VERSION or not status.available or not is_version_compatible(version, cap.backend.minimum_version):
        report.state = BackendIdentityState.INCOMPATIBLE_VERSION
        report.action = "BLOCK"
        report.failure_mode_ids = ["BN-F010"]
        report.execution_fingerprint = _fingerprint(cap.backend.canonical_name, observed, version, [])
        report.reason = (
            f"Backend '{cap.backend.canonical_name}' is present at version "
            f"'{version or 'unknown'}' but the capability declares >= "
            f"{cap.backend.minimum_version}: the version contract is broken."
        )
        return report

    # Distribution identity: the installed distribution providing the import
    # name must be the declared one (in-tree 'bionexus.*' backends are
    # witnessed by the 'bionexus' distribution). A missing witness fails
    # closed: identity that cannot be verified is identity that cannot be
    # claimed.
    # The witness must match the CLAIM, not merely the top-level import name:
    # otherwise any claim would pass as long as the right package is importable.
    # In-tree 'bionexus.*' backends are additionally witnessed by the 'bionexus'
    # distribution itself.
    declared_candidates = {_norm_dist(cap.backend.canonical_name)}
    if top == "bionexus":
        declared_candidates.add("bionexus")
        if observed is None:
            # In-tree backends run from a source checkout without distribution
            # metadata; the importable module itself is the identity witness
            # (an in-tree module cannot be distribution-squatted).
            try:
                mod = importlib.import_module(import_name)
                observed = getattr(mod, "__name__", import_name)
                report.observed_backend = observed
                version = version or getattr(mod, "__version__", None)
                report.version = version
            except Exception:
                pass
    if observed is None or _norm_dist(observed) not in declared_candidates:
        report.state = BackendIdentityState.MASQUERADE
        report.action = "BLOCK"
        report.failure_mode_ids = ["BN-F010"]
        report.execution_fingerprint = _fingerprint(cap.backend.canonical_name, observed, version, [])
        report.reason = (
            f"declared_backend != observed_backend: import '{import_name}' is provided by "
            f"distribution '{observed or '<unwitnessed>'}', not by the declared canonical backend "
            f"'{cap.backend.canonical_name}'. Silent substitution is blocked (BN-F010)."
        )
        return report

    # Entry points: every declared symbol must resolve on the observed backend.
    resolved: List[str] = []
    missing: List[str] = []
    for ep in declared_entry_points:
        if _resolve_entry_point(ep):
            resolved.append(ep)
        else:
            missing.append(ep)
    report.entry_points_resolved = resolved
    report.entry_points_missing = missing

    if missing:
        report.state = BackendIdentityState.MASQUERADE
        report.action = "BLOCK"
        report.failure_mode_ids = ["BN-F010"]
        report.execution_fingerprint = _fingerprint(cap.backend.canonical_name, observed, version, resolved)
        report.reason = (
            f"Backend '{cap.backend.canonical_name}' ({observed or import_name}, v{version}) does not "
            f"expose declared entry points: {missing}. Executing under this name would be a "
            "silent substitution (BN-F010)."
        )
        return report

    report.state = BackendIdentityState.CONFORMANT
    report.action = "RUN PERMITTED (identity)"
    report.execution_fingerprint = _fingerprint(cap.backend.canonical_name, observed, version, resolved)
    report.reason = (
        f"declared_backend == observed_backend: '{cap.backend.canonical_name}' "
        f"(distribution '{observed}', version {version}, entry points {len(resolved)}/{len(declared_entry_points)} resolved, "
        "fallback False)."
    )
    return report


def verify_all_backend_identity(include_frontier: bool = True) -> List[BackendIdentityReport]:
    """Audit every registered capability (canonical core first, then frontier)."""
    reports: List[BackendIdentityReport] = []
    for cap_id in sorted(CANONICAL_CAPABILITIES):
        reports.append(verify_backend_identity(ALL_CAPABILITIES[cap_id]))
    if include_frontier:
        for cap_id in sorted(FRONTIER_CAPABILITIES):
            if cap_id in ALL_CAPABILITIES:
                reports.append(verify_backend_identity(ALL_CAPABILITIES[cap_id]))
    return reports


def backend_identity_summary(reports: List[BackendIdentityReport]) -> Dict[str, Any]:
    """Aggregate identity audit into a gating-grade summary."""
    blocked = [r.capability_id for r in reports if r.action == "BLOCK"]
    return {
        "total": len(reports),
        "conformant": sum(1 for r in reports if r.state == BackendIdentityState.CONFORMANT),
        "not_installed": sum(1 for r in reports if r.state == BackendIdentityState.NOT_INSTALLED),
        "blocked": blocked,
        "verdict": "BLOCK" if blocked else "PASS",
        "fallback_reports": sum(1 for r in reports if r.fallback),
    }
