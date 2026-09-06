"""Evidence Independence Graph and Epistemic Lineage for BioNexus.

Models epistemic relationships between multi-connector evidence objects to eliminate
epistemic double counting (e.g., resolving preprints vs. publications, AI summaries
derived from the same paper, and secondary database mirrors into canonical primary
study equivalence clusters).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


class OriginType(str, Enum):
    """The epistemic origin class of an evidence object."""

    PRIMARY_STUDY = "primary_study"
    PREPRINT = "preprint"
    DATABASE_MIRROR = "database_mirror"
    DERIVED_SYNTHESIS = "derived_synthesis"
    META_ANALYSIS = "meta_analysis"
    COMPUTATIONAL_MODEL = "computational_model"
    ASSAY_RESULT = "assay_result"
    UNKNOWN = "unknown"


def _clean_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    s = str(value).strip()
    if s.lower() in {"", "unknown", "none", "null", "unspecified", "not_provided", "n/a"}:
        return None
    return s


def _clean_tuple(value: Any) -> Tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        cleaned = _clean_str(value)
        return (cleaned,) if cleaned else ()
    if not isinstance(value, (list, tuple)):
        return ()
    items: List[str] = []
    for item in value:
        cleaned = _clean_str(item)
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return tuple(items)


@dataclass(frozen=True)
class EpistemicLineage:
    """Epistemic lineage metadata for an evidence node."""

    origin_id: Optional[str] = None
    origin_type: str = OriginType.UNKNOWN.value
    derived_from: Tuple[str, ...] = ()
    same_study_as: Tuple[str, ...] = ()
    aggregates: Tuple[str, ...] = ()
    cites: Tuple[str, ...] = ()
    dataset_identity: Optional[str] = None
    assay_identity: Optional[str] = None
    model_identity: Optional[str] = None
    primary_source_ids: Tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Optional[Mapping[str, Any]]) -> "EpistemicLineage":
        if not value or not isinstance(value, Mapping):
            return cls()
        origin_type = _clean_str(value.get("origin_type")) or OriginType.UNKNOWN.value
        try:
            origin_type = OriginType(origin_type).value
        except ValueError:
            origin_type = OriginType.UNKNOWN.value

        return cls(
            origin_id=_clean_str(value.get("origin_id")),
            origin_type=origin_type,
            derived_from=_clean_tuple(value.get("derived_from")),
            same_study_as=_clean_tuple(value.get("same_study_as")),
            aggregates=_clean_tuple(value.get("aggregates")),
            cites=_clean_tuple(value.get("cites")),
            dataset_identity=_clean_str(value.get("dataset_identity")),
            assay_identity=_clean_str(value.get("assay_identity")),
            model_identity=_clean_str(value.get("model_identity")),
            primary_source_ids=_clean_tuple(value.get("primary_source_ids")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["derived_from"] = list(self.derived_from)
        data["same_study_as"] = list(self.same_study_as)
        data["aggregates"] = list(self.aggregates)
        data["cites"] = list(self.cites)
        data["primary_source_ids"] = list(self.primary_source_ids)
        return {k: v for k, v in data.items() if v not in (None, [], "")}


@dataclass(frozen=True)
class IndependenceMetrics:
    """Declared lineage diagnostics; distinct origins do not prove independence."""

    raw_evidence_count: int
    independent_origins: int
    primary_studies: int
    derived_syntheses: int
    database_mirrors: int
    connector_count: int
    study_clusters: Dict[str, List[str]]
    lineage_roots: Dict[str, List[str]]
    effective_independence_ratio: float
    summary_statement: str
    unresolved_evidence_ids: List[str] = field(default_factory=list)
    independence_status: str = "NOT_ESTABLISHED"
    dependency_tokens: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceIndependenceGraph:
    """Graph structure resolving lineage, shared studies, and independence boundaries."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}

    def add_evidence(
        self,
        *,
        evidence_id: str,
        lineage: Optional[EpistemicLineage] = None,
        payload_sha256: str = "",
        connector_id: str = "",
        family: str = "",
    ) -> None:
        """Register an evidence envelope node in the graph."""
        self._nodes[evidence_id] = {
            "evidence_id": evidence_id,
            "lineage": lineage or EpistemicLineage(),
            "payload_sha256": payload_sha256,
            "connector_id": connector_id,
            "family": family,
        }

    def compute_metrics(self) -> IndependenceMetrics:
        """Resolve identity separately from directed derivation and shared resources.

        Only origin identity, same-study aliases and identical payloads establish
        equivalence. A synthesis can have several roots without merging them.
        Counts describe supplied declarations, never verified independence.
        """
        parent: Dict[str, str] = {}

        def find(item: str) -> str:
            parent.setdefault(item, item)
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(left: str, right: str) -> None:
            a, b = sorted((find(left), find(right)))
            parent[b] = a

        for eid, node in sorted(self._nodes.items()):
            key = f"evidence:{eid}"
            find(key)
            lineage = node["lineage"]
            if lineage.origin_id:
                union(key, f"origin:{lineage.origin_id}")
            for alias in lineage.same_study_as:
                union(key, f"origin:{alias}")
            if node["payload_sha256"]:
                union(key, f"payload:{node['payload_sha256']}")

        groups: Dict[str, List[str]] = {}
        for eid in sorted(self._nodes):
            groups.setdefault(find(f"evidence:{eid}"), []).append(eid)
        roots: Dict[str, Set[str]] = {group: set() for group in groups}
        resources: Dict[str, Set[str]] = {group: set() for group in groups}
        edges: Dict[str, Set[str]] = {group: set() for group in groups}
        dangling: Set[str] = set()
        primary_roots: Set[str] = set()
        derived_count = mirror_count = 0
        terminal_types = {
            OriginType.PRIMARY_STUDY.value, OriginType.PREPRINT.value,
            OriginType.ASSAY_RESULT.value, OriginType.COMPUTATIONAL_MODEL.value,
            OriginType.UNKNOWN.value,
        }

        for group, eids in groups.items():
            # Prefer a stable declared origin to an insertion-dependent node ID.
            origins = sorted(key[7:] for key in parent
                             if key.startswith("origin:") and find(key) == group)
            origin = f"origin:{origins[0]}" if origins else None
            for eid in eids:
                lineage = self._nodes[eid]["lineage"]
                refs = (*lineage.derived_from, *lineage.aggregates,
                        *lineage.primary_source_ids)
                is_mirror = lineage.origin_type == OriginType.DATABASE_MIRROR.value
                is_derived = bool(refs) or lineage.origin_type in {
                    OriginType.DERIVED_SYNTHESIS.value, OriginType.META_ANALYSIS.value,
                }
                mirror_count += int(is_mirror)
                derived_count += int(is_derived and not is_mirror)
                if origin and not refs and lineage.origin_type in terminal_types:
                    roots[group].add(origin)
                    if lineage.origin_type in {
                        OriginType.PRIMARY_STUDY.value, OriginType.PREPRINT.value,
                    }:
                        primary_roots.add(origin)
                for namespace, identity in (
                    ("dataset", lineage.dataset_identity),
                    ("assay", lineage.assay_identity),
                    ("model", lineage.model_identity),
                ):
                    if identity:
                        resources[group].add(f"{namespace}:{identity}")
                for ref in refs:
                    # Origin references are preferred; local evidence IDs are
                    # also supported, without conflating their namespaces.
                    target = f"origin:{ref}"
                    if target not in parent and ref in self._nodes:
                        target = f"evidence:{ref}"
                    if target not in parent:
                        dangling.add(group)
                        continue
                    target_group = find(target)
                    if target_group != group:
                        edges[group].add(target_group)
                    elif not roots[group]:
                        # Self-derivation without a declared terminal is not
                        # evidence of an independently originating study.
                        edges[group].add(group)

        for group in groups:
            if roots[group]:
                edges[group].discard(group)

        # Iterative propagation terminates even for cycles and long chains.
        # Completeness is separate: a cycle with one reachable root remains
        # unresolved rather than silently discarding the cyclic dependency.
        complete = {
            group for group in groups
            if roots[group] and not edges[group] and group not in dangling
        }
        changed = True
        while changed:
            changed = False
            for group in groups:
                before = (len(roots[group]), len(resources[group]), group in complete)
                for target in edges[group]:
                    roots[group].update(roots[target])
                    resources[group].update(resources[target])
                if (group not in dangling and roots[group]
                        and all(target in complete for target in edges[group])):
                    complete.add(group)
                after = (len(roots[group]), len(resources[group]), group in complete)
                changed |= before != after

        lineage_roots = {
            eid: sorted(roots[group]) for group, eids in groups.items() for eid in eids
        }
        dependency_tokens = {
            eid: sorted(roots[group] | resources[group] | {f"equivalence:{group}"})
            for group, eids in groups.items() for eid in eids
        }
        unresolved = sorted(eid for group, eids in groups.items()
                            if group not in complete for eid in eids)
        all_roots = set().union(*roots.values()) if roots else set()
        study_clusters = {
            root: sorted(eid for eid, sources in lineage_roots.items() if root in sources)
            for root in sorted(all_roots)
        }
        connector_count = len({node["connector_id"] for node in self._nodes.values()
                               if node["connector_id"]})
        raw_count = len(self._nodes)
        summary = (
            f"{raw_count} evidence objects from {connector_count} declared connectors resolve to "
            f"{len(all_roots)} declared source origins, including {len(primary_roots)} "
            f"declared primary studies; {len(unresolved)} objects have unresolved lineage. "
            "Scientific independence is NOT_ESTABLISHED."
        )
        return IndependenceMetrics(
            raw_evidence_count=raw_count,
            independent_origins=len(all_roots),
            primary_studies=len(primary_roots),
            derived_syntheses=derived_count,
            database_mirrors=mirror_count,
            connector_count=connector_count,
            study_clusters=study_clusters,
            lineage_roots=lineage_roots,
            effective_independence_ratio=round(len(all_roots) / raw_count, 3) if raw_count else 0.0,
            summary_statement=summary,
            unresolved_evidence_ids=unresolved,
            dependency_tokens=dependency_tokens,
        )

    def get_independent_support_set(
        self, supported_by: Sequence[str], *, require_resolved: bool = True,
    ) -> Tuple[List[str], List[str]]:
        """Choose non-overlapping declared support, preferring original sources.

        This is a deterministic conservative selection, not an independence
        attestation. Unknown IDs never qualify. Claim assessment may preserve
        explicitly adjudicated unresolved support with require_resolved=False;
        that does not make it independent replication.
        """
        metrics = self.compute_metrics()
        unresolved = set(metrics.unresolved_evidence_ids)
        priority = {
            OriginType.PRIMARY_STUDY.value: 0,
            OriginType.PREPRINT.value: 1,
            OriginType.ASSAY_RESULT.value: 2,
            OriginType.UNKNOWN.value: 3,
            OriginType.COMPUTATIONAL_MODEL.value: 4,
            OriginType.DATABASE_MIRROR.value: 5,
            OriginType.DERIVED_SYNTHESIS.value: 6,
            OriginType.META_ANALYSIS.value: 6,
        }

        def order(eid: str) -> tuple:
            node = self._nodes.get(eid)
            lineage = node["lineage"] if node else EpistemicLineage()
            derived = bool(lineage.derived_from or lineage.aggregates or lineage.primary_source_ids)
            return (derived, priority.get(lineage.origin_type, 7), eid)

        seen: Set[str] = set()
        selected: List[str] = []
        dependent: List[str] = []
        for eid in sorted(set(supported_by), key=order):
            tokens = set(metrics.dependency_tokens.get(eid, ()))
            if (eid not in self._nodes or (require_resolved and eid in unresolved)
                    or tokens & seen):
                dependent.append(eid)
            else:
                selected.append(eid)
                seen.update(tokens)
        return selected, dependent
