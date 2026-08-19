"""
Scientific Rule Provenance Registry: Consensus Level, Exceptions, Evidence, and Classification.

BioNexus preconditions and refusal triggers should never look like the project
authors invented scientific law out of thin air.  Every scientific rule carries
explicit, VERIFIABLE provenance metadata loaded from an evidence-backed registry
(`bionexus/data/rule_registry.json`):

- **source**: Where the rule comes from (textbook, landmark paper, community
  guideline, statistical theory, or project-internal invariant).
- **evidence**: Machine-verifiable references (DOIs, URLs, ISBNs) backing the rule.
- **consensus_level**: How broadly the rule is accepted (ESTABLISHED, STRONG,
  EMERGING, DEBATED, PROJECT_INTERNAL).
- **exceptions**: Known situations where the rule does not apply or is relaxed.
- **last_verified**: When the rule was last checked against the literature.

The registry is DATA, not code.  Labs can fork `rule_registry.json`, extend it
with domain-specific rules, and point BioNexus at their copy via the
`BIONEXUS_RULE_REGISTRY` environment variable.  The Python constants below
(PROVENANCE_*) are built from the registry at import time so code that
references them keeps working.

Every rule is also CLASSIFIED (see rule_classification.py) into one of two
ontologically distinct categories:

- **Execution Invariants** (safety or integrity): non-negotiable rules that
  MUST prevent execution when violated. Breaking these produces garbage or harms.
- **Warrant Constraints** (epistemic): limits on what claims the current evidence
  can justify. They do NOT block execution; they cap post-hoc claim maturity.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.rule_classification import (
    EnforcementLevel,
    EpistemicKind,
    RuleCategory,
    RuleClassification,
)


class ConsensusLevel(str, Enum):
    """How broadly a scientific rule is accepted in the relevant community.

    - ESTABLISHED: Textbook-level consensus; no serious dissent.
    - STRONG: Strong majority support; dissent exists but is minority.
    - EMERGING: Active research area; the rule reflects current best practice
      but may evolve.
    - DEBATED: Meaningful disagreement in the community; the rule represents
      one defensible position, not a universal law.
    - PROJECT_INTERNAL: A BioNexus project invariant (e.g. honesty policy);
      not a scientific claim about the natural world.
    """

    ESTABLISHED = "ESTABLISHED"
    STRONG = "STRONG"
    EMERGING = "EMERGING"
    DEBATED = "DEBATED"
    PROJECT_INTERNAL = "PROJECT_INTERNAL"


class RuleSourceKind(str, Enum):
    """The kind of source a scientific rule derives from."""

    TEXTBOOK = "textbook"
    LANDMARK_PAPER = "landmark_paper"
    COMMUNITY_GUIDELINE = "community_guideline"
    STATISTICAL_THEORY = "statistical_theory"
    REGULATORY = "regulatory"
    PROJECT_INVARIANT = "project_invariant"
    BEST_PRACTICE = "best_practice"


@dataclass
class EvidenceReference:
    """A machine-verifiable reference backing a scientific rule.

    Attributes:
        kind: paper | regulation | documentation | book | spec | database
        ref: The resolvable reference (doi:..., https://..., isbn:..., repo path)
        note: One-line explanation of what this reference supports.
    """

    kind: str
    ref: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "note": self.note}


@dataclass
class RuleProvenance:
    """Provenance metadata for a scientific rule (precondition or refusal trigger).

    Attributes:
        source_kind: What kind of source the rule derives from.
        source_citation: Human-readable citation or description of the source.
        evidence: Machine-verifiable references (DOIs / URLs / ISBNs).
        consensus: How broadly the rule is accepted.
        exceptions: Known situations where the rule does not apply.
        last_verified: ISO date string of when the rule was last verified against
            the literature (e.g. "2025-06").
        hard_rule: Whether this rule is a hard safety invariant (never overridable)
            or a soft methodological guideline (overridable with documentation).
            DEPRECATED: use `classification.category` instead. Kept for backward
            compatibility only.
        classification: Distinguishes INVARIANT (safety/integrity, blocks
            execution) from WARRANT (epistemic limits on claims).
    """

    source_kind: RuleSourceKind = RuleSourceKind.BEST_PRACTICE
    source_citation: str = ""
    evidence: List[EvidenceReference] = field(default_factory=list)
    consensus: ConsensusLevel = ConsensusLevel.STRONG
    exceptions: List[str] = field(default_factory=list)
    last_verified: str = ""
    hard_rule: bool = False
    classification: Optional[RuleClassification] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "source_kind": self.source_kind.value,
            "source_citation": self.source_citation,
            "evidence": [e.to_dict() for e in self.evidence],
            "consensus": self.consensus.value,
            "exceptions": self.exceptions,
            "last_verified": self.last_verified,
            "hard_rule": self.hard_rule,
        }
        if self.classification is not None:
            d["classification"] = self.classification.to_dict()
        return d


# ---------------------------------------------------------------------------
# Evidence-backed Registry Loading
# ---------------------------------------------------------------------------

_REGISTRY_FILENAME = Path(__file__).parent / "data" / "rule_registry.json"
_REGISTRY_ENV_VAR = "BIONEXUS_RULE_REGISTRY"


class RuleRegistryError(RuntimeError):
    """Raised when the rule provenance registry is missing or malformed.

    BioNexus fails closed on provenance: a rule without verifiable provenance
    must never be silently enforced.
    """


def registry_path() -> Path:
    """Return the active registry path (env override or bundled default)."""
    override = os.environ.get(_REGISTRY_ENV_VAR)
    return Path(override) if override else _REGISTRY_FILENAME


def _build_classification(record: Dict[str, Any]) -> RuleClassification:
    cat = RuleCategory(record["classification"]["category"])
    kind_raw = record["classification"].get("epistemic_kind")
    kind = EpistemicKind(kind_raw) if kind_raw else None
    return RuleClassification(
        category=cat,
        enforcement_level=EnforcementLevel(record["classification"]["enforcement_level"]),
        rationale=record["classification"].get("rationale", ""),
        epistemic_kind=kind,
    )


def _build_provenance(record: Dict[str, Any]) -> RuleProvenance:
    """Build a RuleProvenance from one registry record (dict)."""
    classification = _build_classification(record)
    return RuleProvenance(
        source_kind=RuleSourceKind(record["source_kind"]),
        source_citation=record["source_citation"],
        evidence=[EvidenceReference(**e) for e in record.get("evidence", [])],
        consensus=ConsensusLevel(record["consensus"]),
        exceptions=list(record.get("exceptions", [])),
        last_verified=record.get("last_verified", ""),
        hard_rule=classification.category in (RuleCategory.INVARIANT_SAFETY, RuleCategory.INVARIANT_INTEGRITY),
        classification=classification,
    )


def _validate_registry(data: Dict[str, Any]) -> None:
    """Fail-closed validation of registry structure and enum values."""
    if not isinstance(data.get("rules"), dict) or not data["rules"]:
        raise RuleRegistryError("Rule registry has no 'rules' mapping.")
    for rule_id, record in data["rules"].items():
        for required in ("source_kind", "source_citation", "consensus", "classification"):
            if required not in record:
                raise RuleRegistryError(f"Registry rule '{rule_id}' is missing required field '{required}'.")
        try:
            RuleSourceKind(record["source_kind"])
            ConsensusLevel(record["consensus"])
            RuleCategory(record["classification"]["category"])
            EnforcementLevel(record["classification"]["enforcement_level"])
            if record["classification"].get("epistemic_kind"):
                EpistemicKind(record["classification"]["epistemic_kind"])
        except ValueError as exc:
            raise RuleRegistryError(f"Registry rule '{rule_id}' contains an invalid enum value: {exc}") from exc


def load_rule_registry(path: Optional[Path] = None) -> Dict[str, RuleProvenance]:
    """Load the evidence-backed rule provenance registry.

    Resolution order:
    1. Explicit `path` argument.
    2. `BIONEXUS_RULE_REGISTRY` environment variable (lab override).
    3. Bundled `bionexus/data/rule_registry.json`.

    Raises RuleRegistryError (fail-closed) when the file is missing or invalid.
    """
    p = Path(path) if path else registry_path()
    if not p.exists():
        raise RuleRegistryError(
            f"Rule provenance registry not found at '{p}'. "
            f"Set {_REGISTRY_ENV_VAR} to point at a valid registry, or restore "
            "the bundled bionexus/data/rule_registry.json."
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuleRegistryError(f"Rule provenance registry '{p}' is not valid JSON: {exc}") from exc
    _validate_registry(data)
    return {rule_id: _build_provenance(record) for rule_id, record in data["rules"].items()}


# ---------------------------------------------------------------------------
# Module-level registry (loaded once at import; the PROVENANCE_* constants
# below are built FROM the registry, not hand-written).
# ---------------------------------------------------------------------------

try:
    _REGISTRY: Dict[str, RuleProvenance] = load_rule_registry()
except RuleRegistryError:
    # Fail loud at import time is too harsh for in-tree dev with a broken env
    # override; fall back to the bundled file if the override is broken.
    if os.environ.get(_REGISTRY_ENV_VAR):
        _REGISTRY = load_rule_registry(_REGISTRY_FILENAME)
    else:
        raise

# Alias index: condition_id (and every alias) -> canonical rule_id.
_RULE_INDEX: Dict[str, str] = {}
_registry_data = json.loads(_REGISTRY_FILENAME.read_text(encoding="utf-8"))
for _rule_id, _record in _registry_data.get("rules", {}).items():
    _RULE_INDEX[_rule_id] = _rule_id
    for _alias in _record.get("aliases", []):
        _RULE_INDEX[_alias] = _rule_id


def _prov(rule_id: str, fallback: Optional[RuleProvenance] = None) -> RuleProvenance:
    """Fetch a provenance record from the registry, with a code-level fallback.

    The fallback keeps module constants resolvable if a lab's custom registry
    drops a rule BioNexus itself still enforces; it is marked PROJECT_INTERNAL.
    """
    record = _REGISTRY.get(rule_id)
    if record is not None:
        return record
    if fallback is not None:
        return fallback
    return RuleProvenance(
        source_kind=RuleSourceKind.PROJECT_INVARIANT,
        source_citation=f"Rule '{rule_id}' resolved from registry fallback (not in active registry).",
        consensus=ConsensusLevel.PROJECT_INTERNAL,
        last_verified="",
        classification=RuleClassification(
            category=RuleCategory.WARRANT_EPISTEMIC,
            enforcement_level=EnforcementLevel.ADVISORY,
            rationale="Unregistered rule: enforceability defaults to advisory warrant.",
        ),
    )


# --- Execution invariants (never overridable) ---

PROVENANCE_CLINICAL_DIAGNOSIS = _prov("clinical_diagnosis_without_certification")
PROVENANCE_IDENTIFIER_NAMESPACE = _prov("identifier_namespace_mismatch")
PROVENANCE_MODEL_SUBSTITUTION = _prov("model_substitution_attempt")
PROVENANCE_BACKEND_IDENTITY = _prov("missing_backend")

# --- Warrant constraints (overridable with documentation) ---

PROVENANCE_RAW_COUNTS_DE = _prov("normalized_matrix_only")
PROVENANCE_BIOLOGICAL_REPLICATES = _prov("missing_replicates")
PROVENANCE_SPATIAL_COORDINATES = _prov("spatial_coords_present")
PROVENANCE_ANNOTATION_EVIDENCE = _prov("annotation_source_recorded")
PROVENANCE_MULTIPLE_TESTING = _prov("multiple_testing_uncorrected")


def default_provenance_for_condition_id(condition_id: str) -> Optional[RuleProvenance]:
    """Look up the evidence-backed provenance for a refusal/precondition ID.

    Resolves both canonical rule IDs and their aliases (e.g. 'min_replicates'
    resolves to the 'missing_replicates' registry record).  Returns None for
    unknown condition IDs (callers should supply their own provenance).
    """
    canonical = _RULE_INDEX.get(condition_id)
    if canonical is None:
        return None
    return _REGISTRY.get(canonical)


# ---------------------------------------------------------------------------
# Registry inspection API
# ---------------------------------------------------------------------------


def registry_stats() -> Dict[str, Any]:
    """Summary statistics for the active rule provenance registry."""
    by_cat: Dict[str, int] = {}
    by_consensus: Dict[str, int] = {}
    for record in _REGISTRY.values():
        cat = record.classification.category.value if record.classification else "UNCLASSIFIED"
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_consensus[record.consensus.value] = by_consensus.get(record.consensus.value, 0) + 1
    return {
        "registry_path": str(registry_path()),
        "registry_version": _registry_data.get("registry_version"),
        "last_reviewed": _registry_data.get("last_reviewed"),
        "n_rules": len(_REGISTRY),
        "n_indexed_condition_ids": len(_RULE_INDEX),
        "by_classification": by_cat,
        "by_consensus": by_consensus,
    }


def list_registry_rules() -> List[str]:
    """All canonical rule IDs in the active registry."""
    return sorted(_REGISTRY.keys())
