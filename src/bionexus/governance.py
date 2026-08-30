"""
Data governance for BioNexus: sensitivity classification + egress policy enforcement.

Closes the data-residency gap: BioNexus ships 10+ *hosted* MCP endpoints (external
processors) alongside a zero-egress local stdio server, but nothing told researchers
which data may safely touch which endpoint. This module makes the boundary explicit,
deterministic, and enforceable:

- ``classify_dataset``: declaration-driven sensitivity classification with a
  deterministic, documented heuristic cap (never upgrades sensitivity silently,
  only restricts), writing a hash-bound governance sidecar.
- ``check_egress_policy``: a tier x zone policy matrix returning the same decision
  vocabulary as the intent router (PERMITTED / DEGRADED_ADVISORY / ABSTAIN).
- ``zone_for_endpoint`` / ``assert_query_permitted``: helpers so agents and the MCP
  layer can gate queries that would carry data fragments to external endpoints.

Honesty invariants:
- Classification is a *user declaration*; heuristics only ever restrict (cap) a
  declared tier and record why. BioNexus never silently downgrades sensitivity.
- ``RESTRICTED`` (PHI / clinical diagnostic data) is refused for any external zone
  unconditionally, and locally only behind an explicit acknowledgement flag,
  because BioNexus is RUO and holds no clinical certifications.
- This module records policy decisions; it cannot control what a human pastes into a
  chat box. It is a guardrail, not a DLP system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from bionexus.contracts import attach_meta, refuse
from bionexus.provenance import sha256_file

PathLike = Union[str, Path]


class SensitivityTier(str, Enum):
    """Dataset sensitivity tiers (most permissive -> most restrictive)."""

    PUBLIC = "PUBLIC"  # Published data, reference data, public DBs
    INTERNAL = "INTERNAL"  # Lab-internal but non-identifying research data (default when undeclared)
    SENSITIVE = "SENSITIVE"  # Proprietary / unpublished / potentially identifying research data
    RESTRICTED = "RESTRICTED"  # PHI / clinical diagnostic data (RUO boundary)


class EgressZone(str, Enum):
    """Where query/content bytes can travel."""

    LOCAL = "LOCAL"  # Local stdio MCP / local scripts: zero network egress
    ORGANIZATION = "ORGANIZATION"  # Institution-hosted services
    EXTERNAL = "EXTERNAL"  # Third-party hosted endpoints (external processors)


DECISION_PERMITTED = "PERMITTED"
DECISION_ADVISORY = "DEGRADED_ADVISORY"
DECISION_ABSTAIN = "ABSTAIN"

# Deterministic filename/metadata signals that CAP a tier at SENSITIVE.
PHI_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "patient",
    "clinical",
    "clinic",
    "phi",
    "mrn",
    "medical_record",
    "medicalrecord",
    "diagnosis",
    "hospital",
    "icd",
    "subject_id",
    "case_id",
)

GOVERNANCE_SIDECAR_SUFFIX = ".bionexus-governance.json"

_STATIC_EXTERNAL_ENDPOINTS = frozenset(
    {
        "pubmed",
        "biorender",
        "biorxiv",
        "consensus",
        "c-trials",
        "chembl",
        "synapse",
        "wiley",
        "owkin",
        "ot",
        "benchling",
    }
)


def _more_restrictive(a: SensitivityTier, b: SensitivityTier) -> SensitivityTier:
    order = [SensitivityTier.PUBLIC, SensitivityTier.INTERNAL, SensitivityTier.SENSITIVE, SensitivityTier.RESTRICTED]
    return a if order.index(a) >= order.index(b) else b


def detect_sensitivity_signals(path: PathLike, metadata: Optional[Dict[str, Any]] = None) -> List[str]:
    """Deterministic keyword scan over the filename and caller-supplied metadata values."""
    p = Path(path)
    haystack_parts = [p.name.lower()]
    for value in (metadata or {}).values():
        haystack_parts.append(str(value).lower())
    haystack = " ".join(haystack_parts)
    return [kw for kw in PHI_SIGNAL_KEYWORDS if kw in haystack]


def classify_dataset(
    path: PathLike,
    *,
    declared_tier: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    write_sidecar: bool = True,
) -> Dict[str, Any]:
    """
    Classify a dataset's sensitivity tier and (optionally) write a hash-bound
    governance sidecar (``<path>.bionexus-governance.json``).

    Rules:
    - Declared tier wins, unless deterministic signals fire, in which case the tier is
      capped at SENSITIVE (signals never *lower* a declared restriction).
    - Undeclared data defaults to INTERNAL (usable, but external egress is advisory).
    - RESTRICTED is only ever reached by explicit declaration.
    """
    p = Path(path)
    if not p.is_file():
        return refuse(
            method="bionexus.governance.classify_dataset",
            reason=f"Dataset not found or is not a regular file: {p}",
            extra={"path": str(p)},
        )

    declared: Optional[SensitivityTier] = None
    if declared_tier:
        try:
            declared = SensitivityTier(declared_tier.upper())
        except ValueError:
            return refuse(
                method="bionexus.governance.classify_dataset",
                reason=(
                    f"Unknown sensitivity tier '{declared_tier}'. Valid tiers: "
                    f"{[t.value for t in SensitivityTier]}"
                ),
            )

    signals = detect_sensitivity_signals(p, metadata)
    effective = declared or SensitivityTier.INTERNAL
    signal_capped = False
    if signals and effective in (SensitivityTier.PUBLIC, SensitivityTier.INTERNAL):
        effective = _more_restrictive(effective, SensitivityTier.SENSITIVE)
        signal_capped = True

    record = {
        "schema": "bionexus.governance.sidecar/1.0",
        "path": str(p),
        "sha256": sha256_file(p),
        "declared_tier": declared.value if declared else None,
        "effective_tier": effective.value,
        "signals_detected": signals,
        "signal_capped": signal_capped,
        "classified_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Classification records policy intent; it is not a DLP scan and not a "
            "certification of data contents."
        ),
    }

    if write_sidecar:
        sidecar_path = p.with_name(p.name + GOVERNANCE_SIDECAR_SUFFIX)
        sidecar_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        record["sidecar"] = str(sidecar_path)

    limitations = [
        "Heuristic signals cap (never raise) a declared tier; they cannot detect de-identified data.",
        "Not a DLP system: policy is only as good as the declaration and the agent honoring it.",
    ]
    if signal_capped:
        limitations.append(
            "Sensitivity was raised by filename/metadata signals despite a permissive declaration."
        )
    return attach_meta(
        {"classification": record},
        method="bionexus.governance.classify_dataset",
        backend="bionexus.governance",
        evidence_grade="A",
        limitations=limitations,
    )


# ------------------------------------------------------------------ policy engine


@dataclass
class PolicyDecision:
    """Deterministic outcome of a tier x zone policy check."""

    decision: str  # PERMITTED | DEGRADED_ADVISORY | ABSTAIN
    rationale: str
    remedies: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "remedies": self.remedies,
            "limitations": self.limitations,
        }


def check_egress_policy(
    tier: str,
    zone: str,
    *,
    allow_restricted_local_ack: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate the tier x zone egress policy matrix.

    Returns a standard contract payload whose ``policy`` key holds a ``PolicyDecision``.
    Exit-code convention downstream: PERMITTED/DEGRADED_ADVISORY -> 0, ABSTAIN -> 1.
    """
    try:
        t = SensitivityTier(str(tier).upper())
    except ValueError:
        return refuse(
            method="bionexus.governance.check_egress_policy",
            reason=f"Unknown sensitivity tier '{tier}'. Valid tiers: {[x.value for x in SensitivityTier]}",
        )
    try:
        z = EgressZone(str(zone).upper())
    except ValueError:
        return refuse(
            method="bionexus.governance.check_egress_policy",
            reason=f"Unknown egress zone '{zone}'. Valid zones: {[x.value for x in EgressZone]}",
        )

    decision: PolicyDecision
    if t is SensitivityTier.PUBLIC:
        decision = PolicyDecision(
            decision=DECISION_PERMITTED,
            rationale="PUBLIC data may reach any egress zone, including third-party hosted endpoints.",
        )
    elif t is SensitivityTier.INTERNAL:
        if z is EgressZone.EXTERNAL:
            decision = PolicyDecision(
                decision=DECISION_ADVISORY,
                rationale=(
                    "INTERNAL data may query external endpoints, but every query leaves the "
                    "organization. Keep fragments minimal and prefer local endpoints."
                ),
                remedies=["Prefer the local stdio MCP server for internal-data lookups."],
                limitations=["External processors receive query content; treat as disclosure."],
            )
        else:
            decision = PolicyDecision(
                decision=DECISION_PERMITTED,
                rationale="INTERNAL data may flow to local or organization-zone services.",
            )
    elif t is SensitivityTier.SENSITIVE:
        if z is EgressZone.LOCAL:
            decision = PolicyDecision(
                decision=DECISION_PERMITTED,
                rationale="SENSITIVE data is restricted to zero-egress local analysis.",
            )
        elif z is EgressZone.ORGANIZATION:
            decision = PolicyDecision(
                decision=DECISION_ADVISORY,
                rationale=(
                    "SENSITIVE data should stay local; organization-zone services are permitted "
                    "only with an explicit institutional data-handling approval."
                ),
                remedies=["Confirm institutional approval before organization-zone processing."],
            )
        else:
            decision = PolicyDecision(
                decision=DECISION_ABSTAIN,
                rationale=(
                    "SENSITIVE data must not be sent to third-party hosted endpoints. BioNexus "
                    "refuses rather than risking undisclosed data egress."
                ),
                remedies=[
                    "De-identify and re-classify the data before any external lookup.",
                    "Use the local stdio MCP server (zero egress) for these queries.",
                ],
            )
    else:  # RESTRICTED
        if z is EgressZone.LOCAL and allow_restricted_local_ack:
            decision = PolicyDecision(
                decision=DECISION_PERMITTED,
                rationale=(
                    "RESTRICTED (PHI/clinical) data acknowledged for local, zero-egress analysis only, "
                    "behind an explicit operator acknowledgement."
                ),
                limitations=[
                    "BioNexus is Research Use Only: outputs must never drive clinical decisions.",
                    "No CLIA/CAP/IVDR or 21 CFR Part 11 certification applies.",
                ],
            )
        elif z is EgressZone.LOCAL:
            decision = PolicyDecision(
                decision=DECISION_ABSTAIN,
                rationale=(
                    "RESTRICTED (PHI/clinical) data requires an explicit acknowledgement "
                    "(allow_restricted_local_ack=True) before any BioNexus processing."
                ),
                remedies=[
                    "Re-run with explicit acknowledgement for local-only analysis.",
                    "Or route the dataset to a certified clinical pipeline; BioNexus is RUO.",
                ],
            )
        else:
            decision = PolicyDecision(
                decision=DECISION_ABSTAIN,
                rationale=(
                    "RESTRICTED (PHI/clinical) data must never leave the local zone. BioNexus "
                    "refuses unconditionally, independent of any flag."
                ),
                remedies=["Use certified clinical infrastructure for PHI; BioNexus is RUO."],
            )

    return attach_meta(
        {"policy": decision.to_dict()},
        method="bionexus.governance.check_egress_policy",
        backend="bionexus.governance",
        evidence_grade="A",
        limitations=decision.limitations
        or ["Policy matrix is deterministic and documented in docs/data-governance.md."],
    )


def assert_query_permitted(tier: str, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
    """Gate one query to one named endpoint (convenience wrapper over the policy matrix)."""
    zone = zone_for_endpoint(endpoint)
    payload = check_egress_policy(tier, zone, **kwargs)
    if not payload.get("refused"):
        payload["policy"]["endpoint"] = endpoint
        payload["policy"]["zone"] = zone
    return payload


def zone_for_endpoint(endpoint: str) -> str:
    """
    Resolve an endpoint id to its egress zone.

    Hosted MCP server ids from ``bionexus.registry.yaml`` map to EXTERNAL; the local
    stdio server and unknown ids resolve conservatively (unknown -> LOCAL for explicit
    local ids, otherwise EXTERNAL is never assumed... unknown ids map to EXTERNAL so
    the restrictive branch of the policy matrix applies).
    """
    name = endpoint.strip().lower()
    if name in ("local", "bionexus-local-mcp", "local_mcp", "local-stdio"):
        return EgressZone.LOCAL.value
    if name in _load_external_endpoint_ids():
        return EgressZone.EXTERNAL.value
    # Unknown endpoints are treated as EXTERNAL (conservative default).
    return EgressZone.EXTERNAL.value


def _load_external_endpoint_ids() -> frozenset:
    """Load hosted endpoint ids from the canonical registry, with a static fallback."""

    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "bionexus.registry.yaml"
    if registry_path.is_file():
        try:
            import yaml

            registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            hosted = (registry or {}).get("mcp_servers", {}).get("hosted", {})
            ids = frozenset(str(k).lower() for k in hosted)
            if ids:
                return ids
        except Exception:  # pragma: no cover - fall back to the static set
            pass
    return _STATIC_EXTERNAL_ENDPOINTS


def iter_governed_endpoints() -> Iterable[Dict[str, str]]:
    """Yield endpoint id/zone pairs known to the governance layer (for docs & doctor)."""
    for endpoint_id in sorted(_load_external_endpoint_ids()):
        yield {"endpoint": endpoint_id, "zone": EgressZone.EXTERNAL.value}
    yield {"endpoint": "bionexus-local-mcp", "zone": EgressZone.LOCAL.value}
