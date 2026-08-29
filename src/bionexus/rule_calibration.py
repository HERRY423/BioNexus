"""
BioNexus Rule Calibration & Scientific Challenge Network (BNS-018).

Holds development rule propositions and a fail-closed challenge workflow.

Phase-1 Scientific Trust Reset removed all packaged empirical calibrations and
reviewer endorsements. They may return only as artifact-bound attestations that
verify against an explicit trust registry.

Every scientific rule represents a calibrated epistemic asset with:
1. Scientific Proposition (formal hypothesis & modeling assumptions)
2. Epistemic Class (Invariants vs Warrant Constraints vs Calibrated Thresholds)
3. Supporting Evidence (literature DOIs, benchmark datasets, proofs)
4. Contradictory Evidence (dissenting studies, contested assumptions)
5. Applicable Regimes (platforms, sample sizes, design pairedness)
6. Known Counterexamples (explicit boundary conditions where rule breaks)
7. Dataset Calibration (empirical metric distributions across real atlases)
8. Platform Calibration (assay-specific parameters, e.g. 10x v2/v3, Visium HD)
9. Sensitivity Analysis (elasticity of warrant verdicts to parameter drift)
10. Reviewer Identities & Attestations (ORCIDs, affiliations, crypto signatures)
11. Version History (semantic changelog of epistemic evolution)
12. Confidence & Consensus State (ESTABLISHED, STRONG, EMERGING, CONTESTED)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from bionexus.rule_classification import (
    EnforcementLevel,
    EpistemicKind,
    RuleCategory,
)
from bionexus.rule_provenance import ConsensusLevel, EvidenceReference, RuleSourceKind

# ==============================================================================
# 1. Calibration Data Structures
# ==============================================================================


class ChallengeType(str, Enum):
    """Category of challenge submitted to the scientific rule knowledge base."""

    EMPIRICAL_COUNTEREXAMPLE = "EMPIRICAL_COUNTEREXAMPLE"
    BENCHMARK_DISSENT = "BENCHMARK_DISSENT"
    REGIME_BOUNDARY_VIOLATION = "REGIME_BOUNDARY_VIOLATION"
    PARAMETER_DRIFT = "PARAMETER_DRIFT"
    MATHEMATICAL_FLAW = "MATHEMATICAL_FLAW"
    PLATFORM_INCOMPATIBILITY = "PLATFORM_INCOMPATIBILITY"


class ChallengeStatus(str, Enum):
    """Lifecycle status of a scientific rule challenge."""

    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED_AMENDMENT = "ACCEPTED_AMENDMENT"
    REGIME_SPLIT = "REGIME_SPLIT"
    REJECTED_REFUTED = "REJECTED_REFUTED"
    DEPRECATED = "DEPRECATED"


@dataclass
class ScientificProposition:
    """The formal theoretical proposition and mathematical assumptions of a rule."""

    statement: str
    formal_predicate: str = ""
    underlying_assumptions: List[str] = field(default_factory=list)
    theoretical_framework: str = ""  # e.g. "Frequentist Hypothesis Testing", "Pearl SCM", "Negative Binomial GLM"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicableRegime:
    """Empirical regime where this scientific rule is valid and applicable."""

    regime_id: str
    description: str
    target_platforms: List[str] = field(default_factory=list)  # ["10x_chromium_v3", "visium_hd", "smart_seq2"]
    min_samples: int = 1
    min_features: int = 1
    sample_design: str = "any"  # "paired" | "unpaired" | "time_series" | "spatial"
    tissue_contexts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnownCounterexample:
    """Explicit boundary condition or edge-case where the standard rule does NOT hold."""

    counterexample_id: str
    description: str
    empirical_citation: str
    boundary_mechanism: str
    mitigation_strategy: str
    citation_status: str = ""  # e.g. "UNVERIFIED_REMOVED_2026-08-25" when a prior citation failed audit

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetCalibration:
    """Empirical calibration benchmark on real biological atlases or reference cohorts."""

    dataset_id: str
    dataset_name: str
    sample_size: int
    cell_or_feature_count: int
    empirical_metric_name: str
    empirical_metric_value: float
    confidence_interval: Tuple[float, float] = (0.0, 0.0)
    dataset_doi_or_url: str = ""
    source_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlatformCalibration:
    """Instrument and chemistry-specific parameter calibration."""

    platform_id: str
    platform_name: str
    recommended_threshold: float
    safe_operating_range: Tuple[float, float] = (0.0, 0.0)
    calibration_notes: str = ""
    last_calibrated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SensitivityAnalysis:
    """Sensitivity analysis documenting how rule outcomes vary with parameter shifts."""

    parameter_name: str
    nominal_value: float
    tested_perturbations: List[float] = field(default_factory=list)
    elasticity_score: float = 0.0  # Percentage shift in warrant verdicts per % parameter change
    cliff_edge_risk: bool = False  # True if small parameter changes cause catastrophic phase transitions
    risk_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewerAttestation:
    """Legacy reviewer metadata. Production acceptance requires a verified evidence attestation."""

    reviewer_id: str  # ORCID or GitHub handle (e.g. "orcid:0000-0002-1825-0097")
    reviewer_name: str
    institution: str
    attestation_date: str
    verdict: str  # "ENDORSED" | "ENDORSED_WITH_LIMITS" | "CHALLENGED"
    signature_sha256: str = ""
    review_comments: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleVersionEntry:
    """Changelog entry documenting the epistemic evolution of a rule."""

    version: str
    date: str
    author: str
    summary: str
    epistemic_rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleChallenge:
    """A formal challenge submitted by a researcher against an existing rule."""

    challenge_id: str
    target_rule_id: str
    challenger_identity: str
    challenge_type: ChallengeType
    title: str
    description: str
    empirical_evidence_refs: List[str] = field(default_factory=list)
    reproduction_script_sha256: str = ""
    status: ChallengeStatus = ChallengeStatus.PROPOSED
    reviewer_votes: Dict[str, str] = field(default_factory=dict)
    reviewer_attestation_ids: Dict[str, str] = field(default_factory=dict)
    resolution_notes: str = ""
    created_at: str = ""
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "target_rule_id": self.target_rule_id,
            "challenger_identity": self.challenger_identity,
            "challenge_type": self.challenge_type.value,
            "title": self.title,
            "description": self.description,
            "empirical_evidence_refs": self.empirical_evidence_refs,
            "reproduction_script_sha256": self.reproduction_script_sha256,
            "status": self.status.value,
            "reviewer_votes": self.reviewer_votes,
            "reviewer_attestation_ids": self.reviewer_attestation_ids,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


# ==============================================================================
# 2. Calibrated Rule Model
# ==============================================================================


@dataclass
class CalibratedRule:
    """A rule proposition whose evidence state is explicit in ``metadata``."""

    rule_id: str
    aliases: List[str] = field(default_factory=list)
    proposition: ScientificProposition = field(default_factory=lambda: ScientificProposition(statement=""))
    epistemic_kind: EpistemicKind = EpistemicKind.WARRANT_CONSTRAINT
    category: RuleCategory = RuleCategory.WARRANT_EPISTEMIC
    enforcement_level: EnforcementLevel = EnforcementLevel.ADVISORY
    consensus: ConsensusLevel = ConsensusLevel.STRONG
    source_kind: RuleSourceKind = RuleSourceKind.BEST_PRACTICE
    source_citation: str = ""
    supporting_evidence: List[EvidenceReference] = field(default_factory=list)
    contradictory_evidence: List[EvidenceReference] = field(default_factory=list)
    applicable_regimes: List[ApplicableRegime] = field(default_factory=list)
    known_counterexamples: List[KnownCounterexample] = field(default_factory=list)
    dataset_calibrations: List[DatasetCalibration] = field(default_factory=list)
    platform_calibrations: List[PlatformCalibration] = field(default_factory=list)
    sensitivity_analysis: List[SensitivityAnalysis] = field(default_factory=list)
    reviewers: List[ReviewerAttestation] = field(default_factory=list)
    version_history: List[RuleVersionEntry] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    context_factors: List[str] = field(default_factory=list)
    last_verified: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "aliases": self.aliases,
            "proposition": self.proposition.to_dict(),
            "epistemic_kind": self.epistemic_kind.value,
            "classification": {
                "category": self.category.value,
                "enforcement_level": self.enforcement_level.value,
                "epistemic_kind": self.epistemic_kind.value,
                "rationale": self.metadata.get("rationale", ""),
            },
            "consensus": self.consensus.value,
            "source_kind": self.source_kind.value,
            "source_citation": self.source_citation,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradictory_evidence": [e.to_dict() for e in self.contradictory_evidence],
            "applicable_regimes": [r.to_dict() for r in self.applicable_regimes],
            "known_counterexamples": [k.to_dict() for k in self.known_counterexamples],
            "dataset_calibrations": [d.to_dict() for d in self.dataset_calibrations],
            "platform_calibrations": [p.to_dict() for p in self.platform_calibrations],
            "sensitivity_analysis": [s.to_dict() for s in self.sensitivity_analysis],
            "reviewers": [r.to_dict() for r in self.reviewers],
            "version_history": [v.to_dict() for v in self.version_history],
            "exceptions": self.exceptions,
            "context_factors": self.context_factors,
            "last_verified": self.last_verified,
            "metadata": self.metadata,
        }


# ==============================================================================
# 3. Scientific Challenge Network Engine
# ==============================================================================


class ChallengeNetwork:
    """
    Development Scientific Rule Challenge & Calibration Network.

    Consensus-changing votes count only when their artifact-bound attestation IDs
    have already been verified by :mod:`bionexus.trust_evidence`.
    """

    def __init__(
        self,
        registry_file: Optional[Union[str, Path]] = None,
        *,
        verified_attestation_ids: Optional[Set[str]] = None,
    ) -> None:
        self.registry_file = Path(registry_file) if registry_file else Path(__file__).parent / "data" / "rule_registry.json"
        self.rules: Dict[str, CalibratedRule] = {}
        self.challenges: Dict[str, RuleChallenge] = {}
        self.registry_metadata: Dict[str, Any] = {}
        self.verified_attestation_ids = set(verified_attestation_ids or set())
        self.load()

    def load(self) -> None:
        """Load and parse the full calibrated rule registry."""
        if not self.registry_file.exists():
            return

        raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
        self.registry_metadata = {
            key: value for key, value in raw.items() if key not in {"rules", "challenges"}
        }
        rules_data = raw.get("rules", {})

        if raw.get("registry_status") == "DEVELOPMENT_UNVERIFIED":
            forbidden = []
            for rid, rdata in rules_data.items():
                for field_name in ("dataset_calibrations", "platform_calibrations", "sensitivity_analysis", "reviewers"):
                    if rdata.get(field_name):
                        forbidden.append(f"{rid}.{field_name}")
            if forbidden:
                raise ValueError(
                    "DEVELOPMENT_UNVERIFIED registry contains evidence-like endorsements: "
                    + ", ".join(forbidden)
                )

        for rid, rdata in rules_data.items():
            # Build Proposition
            prop_data = rdata.get("proposition", {})
            if isinstance(prop_data, dict):
                prop = ScientificProposition(
                    statement=prop_data.get("statement", rdata.get("source_citation", "")),
                    formal_predicate=prop_data.get("formal_predicate", ""),
                    underlying_assumptions=list(prop_data.get("underlying_assumptions", [])),
                    theoretical_framework=prop_data.get("theoretical_framework", ""),
                )
            else:
                prop = ScientificProposition(statement=str(prop_data))

            # Build Epistemic Kind & Classification
            clf = rdata.get("classification", {})
            cat = RuleCategory(clf.get("category", RuleCategory.WARRANT_EPISTEMIC.value))
            enf = EnforcementLevel(clf.get("enforcement_level", EnforcementLevel.ADVISORY.value))
            kind_raw = clf.get("epistemic_kind") or rdata.get("epistemic_kind")
            kind = EpistemicKind(kind_raw) if kind_raw else EpistemicKind.WARRANT_CONSTRAINT

            # Build Supporting & Contradictory Evidence
            supp_ev = [EvidenceReference(**e) for e in rdata.get("supporting_evidence", rdata.get("evidence", []))]
            contra_ev = [EvidenceReference(**e) for e in rdata.get("contradictory_evidence", [])]

            # Build Regimes & Counterexamples
            regimes = [ApplicableRegime(**reg) for reg in rdata.get("applicable_regimes", [])]
            counterexamples = [KnownCounterexample(**c) for c in rdata.get("known_counterexamples", [])]

            # Build Dataset & Platform Calibrations
            dataset_cals = []
            for d in rdata.get("dataset_calibrations", []):
                ci = tuple(d.get("confidence_interval", (0.0, 0.0)))
                dataset_cals.append(
                    DatasetCalibration(
                        dataset_id=d.get("dataset_id", ""),
                        dataset_name=d.get("dataset_name", ""),
                        sample_size=d.get("sample_size", 0),
                        cell_or_feature_count=d.get("cell_or_feature_count", 0),
                        empirical_metric_name=d.get("empirical_metric_name", ""),
                        empirical_metric_value=d.get("empirical_metric_value", 0.0),
                        confidence_interval=(float(ci[0]), float(ci[1])),
                        dataset_doi_or_url=d.get("dataset_doi_or_url", ""),
                        source_sha256=d.get("source_sha256", ""),
                    )
                )

            platform_cals = []
            for p in rdata.get("platform_calibrations", []):
                rng = tuple(p.get("safe_operating_range", (0.0, 0.0)))
                platform_cals.append(
                    PlatformCalibration(
                        platform_id=p.get("platform_id", ""),
                        platform_name=p.get("platform_name", ""),
                        recommended_threshold=p.get("recommended_threshold", 0.0),
                        safe_operating_range=(float(rng[0]), float(rng[1])),
                        calibration_notes=p.get("calibration_notes", ""),
                        last_calibrated=p.get("last_calibrated", ""),
                    )
                )

            # Build Sensitivity Analysis
            sensitivities = []
            for s in rdata.get("sensitivity_analysis", []):
                sensitivities.append(
                    SensitivityAnalysis(
                        parameter_name=s.get("parameter_name", ""),
                        nominal_value=s.get("nominal_value", 0.0),
                        tested_perturbations=list(s.get("tested_perturbations", [])),
                        elasticity_score=s.get("elasticity_score", 0.0),
                        cliff_edge_risk=s.get("cliff_edge_risk", False),
                        risk_summary=s.get("risk_summary", ""),
                    )
                )

            # Build Reviewers & Version History
            reviewers = [ReviewerAttestation(**rev) for rev in rdata.get("reviewers", [])]
            versions = [RuleVersionEntry(**ver) for ver in rdata.get("version_history", [])]

            rule = CalibratedRule(
                rule_id=rid,
                aliases=list(rdata.get("aliases", [])),
                proposition=prop,
                epistemic_kind=kind,
                category=cat,
                enforcement_level=enf,
                consensus=ConsensusLevel(rdata.get("consensus", ConsensusLevel.STRONG.value)),
                source_kind=RuleSourceKind(rdata.get("source_kind", RuleSourceKind.BEST_PRACTICE.value)),
                source_citation=rdata.get("source_citation", ""),
                supporting_evidence=supp_ev,
                contradictory_evidence=contra_ev,
                applicable_regimes=regimes,
                known_counterexamples=counterexamples,
                dataset_calibrations=dataset_cals,
                platform_calibrations=platform_cals,
                sensitivity_analysis=sensitivities,
                reviewers=reviewers,
                version_history=versions,
                exceptions=list(rdata.get("exceptions", [])),
                context_factors=list(rdata.get("context_factors", [])),
                last_verified=rdata.get("last_verified", ""),
                metadata=rdata.get("metadata", {}),
            )
            self.rules[rid] = rule

        # Load Challenges if present in data
        for cid, cdata in raw.get("challenges", {}).items():
            self.challenges[cid] = RuleChallenge(
                challenge_id=cid,
                target_rule_id=cdata.get("target_rule_id", ""),
                challenger_identity=cdata.get("challenger_identity", ""),
                challenge_type=ChallengeType(cdata.get("challenge_type", ChallengeType.EMPIRICAL_COUNTEREXAMPLE.value)),
                title=cdata.get("title", ""),
                description=cdata.get("description", ""),
                empirical_evidence_refs=list(cdata.get("empirical_evidence_refs", [])),
                reproduction_script_sha256=cdata.get("reproduction_script_sha256", ""),
                status=ChallengeStatus(cdata.get("status", ChallengeStatus.PROPOSED.value)),
                reviewer_votes=dict(cdata.get("reviewer_votes", {})),
                reviewer_attestation_ids=dict(cdata.get("reviewer_attestation_ids", {})),
                resolution_notes=cdata.get("resolution_notes", ""),
                created_at=cdata.get("created_at", ""),
                resolved_at=cdata.get("resolved_at"),
            )

    def get_rule(self, rule_id: str) -> Optional[CalibratedRule]:
        """Look up a rule by canonical ID or alias."""
        if rule_id in self.rules:
            return self.rules[rule_id]
        for r in self.rules.values():
            if rule_id in r.aliases:
                return r
        return None

    def get_platform_calibration(self, rule_id: str, platform: str) -> Optional[PlatformCalibration]:
        """Retrieve instrument-specific calibration parameters for a given rule and platform."""
        rule = self.get_rule(rule_id)
        if not rule:
            return None
        platform_norm = platform.lower().replace("-", "_").replace(" ", "_")
        for cal in rule.platform_calibrations:
            if cal.platform_id.lower() == platform_norm or platform_norm in cal.platform_id.lower():
                return cal
        return None

    def is_applicable_to_regime(
        self,
        rule_id: str,
        platform: Optional[str] = None,
        sample_count: int = 1,
        design: str = "unpaired",
    ) -> Tuple[bool, str]:
        """Evaluate if this rule applies to the specified analytical regime."""
        rule = self.get_rule(rule_id)
        if not rule:
            return (False, f"Rule '{rule_id}' not found in registry.")

        if not rule.applicable_regimes:
            return (True, "Rule applies universally (no regime restrictions declared).")

        for regime in rule.applicable_regimes:
            platform_match = True
            if platform and regime.target_platforms:
                p_norm = platform.lower().replace("-", "_")
                platform_match = any(p_norm in tp.lower() for tp in regime.target_platforms)

            sample_match = sample_count >= regime.min_samples
            design_match = regime.sample_design == "any" or regime.sample_design == design

            if platform_match and sample_match and design_match:
                return (True, f"Rule matches applicable regime: '{regime.regime_id}' ({regime.description}).")

        return (False, f"Experimental setup does not match declared applicable regimes for rule '{rule_id}'.")

    def submit_challenge(
        self,
        target_rule_id: str,
        challenger_identity: str,
        challenge_type: Union[ChallengeType, str],
        title: str,
        description: str,
        empirical_evidence_refs: Optional[List[str]] = None,
        reproduction_script: Optional[str] = None,
    ) -> RuleChallenge:
        """Propose a formal challenge to a rule in the knowledge base."""
        rule = self.get_rule(target_rule_id)
        if not rule:
            raise KeyError(f"Cannot challenge unknown rule '{target_rule_id}'")

        if isinstance(challenge_type, str):
            challenge_type = ChallengeType(challenge_type)

        script_hash = ""
        if reproduction_script:
            script_hash = hashlib.sha256(reproduction_script.encode("utf-8")).hexdigest()

        cid = f"CHALLENGE-{target_rule_id}-{len(self.challenges) + 1:03d}"
        challenge = RuleChallenge(
            challenge_id=cid,
            target_rule_id=rule.rule_id,
            challenger_identity=challenger_identity,
            challenge_type=challenge_type,
            title=title,
            description=description,
            empirical_evidence_refs=empirical_evidence_refs or [],
            reproduction_script_sha256=script_hash,
            status=ChallengeStatus.PROPOSED,
            created_at="2026-08",
        )
        self.challenges[cid] = challenge
        return challenge

    def adjudicate_challenge(
        self,
        challenge_id: str,
        reviewer_id: str,
        vote: str,  # "ACCEPT_AMENDMENT" | "SPLIT_REGIME" | "REJECT_CHALLENGE"
        review_note: str,
        review_attestation_id: Optional[str] = None,
    ) -> ChallengeStatus:
        """Record a vote; change consensus only for previously verified attestations."""
        challenge = self.challenges.get(challenge_id)
        if not challenge:
            raise KeyError(f"Challenge '{challenge_id}' not found.")

        challenge.reviewer_votes[reviewer_id] = vote
        challenge.status = ChallengeStatus.UNDER_REVIEW
        if review_attestation_id:
            challenge.reviewer_attestation_ids[reviewer_id] = review_attestation_id

        verified_reviewers = {
            reviewer
            for reviewer, attestation_id in challenge.reviewer_attestation_ids.items()
            if attestation_id in self.verified_attestation_ids
        }
        if reviewer_id not in verified_reviewers:
            challenge.resolution_notes = (
                "Vote recorded but excluded from consensus: no verified, unrevoked, "
                "artifact-bound review attestation was supplied."
            )

        # Consensus determination
        verified_votes = [challenge.reviewer_votes[r] for r in verified_reviewers]
        accept_votes = sum(1 for v in verified_votes if v == "ACCEPT_AMENDMENT")
        reject_votes = sum(1 for v in verified_votes if v == "REJECT_CHALLENGE")
        split_votes = sum(1 for v in verified_votes if v == "SPLIT_REGIME")

        total = len(verified_votes)
        if total >= 3:
            if accept_votes >= 2:
                challenge.status = ChallengeStatus.ACCEPTED_AMENDMENT
                challenge.resolution_notes = f"Challenge accepted by peer consensus ({accept_votes}/{total} votes). {review_note}"
            elif split_votes >= 2:
                challenge.status = ChallengeStatus.REGIME_SPLIT
                challenge.resolution_notes = f"Rule split into distinct regimes ({split_votes}/{total} votes). {review_note}"
            elif reject_votes >= 2:
                challenge.status = ChallengeStatus.REJECTED_REFUTED
                challenge.resolution_notes = f"Challenge refuted by peer reviewers ({reject_votes}/{total} votes). {review_note}"

        return challenge.status

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.registry_metadata,
            "registry_version": self.registry_metadata.get("registry_version", "3.1.0-trust-reset"),
            "registry_status": self.registry_metadata.get("registry_status", "DEVELOPMENT_UNVERIFIED"),
            "description": self.registry_metadata.get(
                "description",
                "BioNexus development rule propositions and challenge ledger (BNS-018)",
            ),
            "rules": {rid: r.to_dict() for rid, r in self.rules.items()},
            "challenges": {cid: c.to_dict() for cid, c in self.challenges.items()},
        }

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        p = Path(path) if path else self.registry_file
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p
