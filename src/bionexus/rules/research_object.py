"""
BioNexus Scientific Rule Research Objects (BNS-019).

Transforms audit and governance rules from arbitrary source heuristics into
fully auditable, calibrated scientific research objects suitable for scholarly
peer review and formal empirical verification.

Every ScientificRuleObject contains:
1. Identifiers & Semantic Versioning
2. Epistemic Identity & Consensus Classification
3. Applicability Regimes & Conditions
4. Explicit Exceptions & Relaxation Boundaries
5. Expected Scientific Benefit (Value Proposition)
6. Expected False Rejection Risk (Over-Enforcement Hazard)
7. Formal Literature Citations (DOI, Author, Journal, Findings)
8. Version Change Rationale (Evolutionary Trajectory)
9. Dual-Track Semantics (Rule Flag vs Expert Ground Truth)
10. Frozen Empirical Calibration Metrics (FPR, FNR, ECE, Cohen's Kappa)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from bionexus.rule_classification import (
    EnforcementLevel,
    EpistemicKind,
    RuleCategory,
)
from bionexus.rule_provenance import ConsensusLevel


@dataclass
class CitationRef:
    """Scholarly publication reference establishing normative backing for a rule."""

    author: str
    year: int
    title: str
    journal: str
    doi: str
    evidence_quote: str = ""
    relevance: str = ""
    verification_status: str = "UNVERIFIED_BIBLIOGRAPHIC_REFERENCE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleEmpiricalMetrics:
    """Descriptive metrics; independence must be established outside this object."""

    sample_size: int = 0
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    false_positive_rate: Optional[float] = None
    false_negative_rate: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    expert_concordance: Optional[float] = None
    cohens_kappa: Optional[float] = None
    holdout_cohort_hash: str = ""
    evaluation_date: str = ""
    n_labeled_cases: int = 0
    evidence_kind: str = "CALLER_SUPPLIED_REFERENCE_LABELS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "n_labeled_cases": self.n_labeled_cases,
            "evidence_kind": self.evidence_kind,
            "scientific_authorization": "NONE",
            "independent_validation_status": "NOT_ESTABLISHED",
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "false_positive_rate": round(self.false_positive_rate, 4) if self.false_positive_rate is not None else None,
            "false_negative_rate": round(self.false_negative_rate, 4) if self.false_negative_rate is not None else None,
            "expected_calibration_error": round(self.expected_calibration_error, 4) if self.expected_calibration_error is not None else None,
            "expert_concordance": round(self.expert_concordance, 4) if self.expert_concordance is not None else None,
            "cohens_kappa": round(self.cohens_kappa, 4) if self.cohens_kappa is not None else None,
            "holdout_cohort_hash": self.holdout_cohort_hash,
            "evaluation_date": self.evaluation_date,
            "metric_status": {name: "NOT_ESTIMABLE" if getattr(self, name) is None else "DESCRIPTIVE_ONLY" for name in ("false_positive_rate", "false_negative_rate", "expected_calibration_error", "expert_concordance", "cohens_kappa")},
        }


@dataclass
class RuleDualTrackSemantics:
    """Decouples algorithmic rule detection from biological/scientific defect truth."""

    rule_flag_meaning: str
    expert_flaw_meaning: str
    harmless_exception_context: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScientificRuleObject:
    """Rule specification, distinct from empirical calibration or endorsement."""

    rule_id: str
    name: str
    version: str
    category: RuleCategory
    epistemic_kind: EpistemicKind
    enforcement_level: EnforcementLevel
    consensus: ConsensusLevel
    applicability_conditions: List[str]
    exceptions: List[str]
    expected_benefit: str
    false_rejection_risk: str
    literature_citations: List[CitationRef]
    change_rationale: str
    dual_track_semantics: RuleDualTrackSemantics
    empirical_metrics: Optional[RuleEmpiricalMetrics] = None
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "version": self.version,
            "aliases": list(self.aliases),
            "category": self.category.value,
            "epistemic_kind": self.epistemic_kind.value,
            "enforcement_level": self.enforcement_level.value,
            "consensus": self.consensus.value,
            "applicability_conditions": list(self.applicability_conditions),
            "exceptions": list(self.exceptions),
            "expected_benefit": self.expected_benefit,
            "false_rejection_risk": self.false_rejection_risk,
            "literature_citations": [c.to_dict() for c in self.literature_citations],
            "change_rationale": self.change_rationale,
            "dual_track_semantics": self.dual_track_semantics.to_dict(),
            "empirical_metrics": self.empirical_metrics.to_dict() if self.empirical_metrics else None,
            "metadata": dict(self.metadata),
        }

    def to_markdown_card(self) -> str:
        """Render a publication-ready Markdown Specification Card for this rule."""
        lines = [
            f"# Scientific Rule Object Card: `{self.rule_id}`",
            f"**Title**: {self.name}  ",
            f"**Version**: `{self.version}` | **Epistemic Kind**: `{self.epistemic_kind.value}` | **Consensus**: `{self.consensus.value}`  ",
            f"**Category**: `{self.category.value}` | **Default Enforcement**: `{self.enforcement_level.value}`",
            "",
            "## 1. Scientific Proposition & Normative Purpose",
            "Design intent only; these specifications are not independently validated guarantees.",
            f"- **Expected Benefit**: {self.expected_benefit}",
            f"- **False Rejection Risk**: {self.false_rejection_risk}",
            f"- **Evolutionary Rationale**: {self.change_rationale}",
            "",
            "## 2. Applicability & Boundary Conditions",
            "### Applicability Conditions",
        ]
        for cond in self.applicability_conditions:
            lines.append(f"- {cond}")

        lines.append("\n### Documented Exceptions & Relaxations")
        for exc in self.exceptions:
            lines.append(f"- {exc}")

        lines.extend([
            "",
            "## 3. Dual-Track Epistemic Semantics",
            f"- **Rule Flag Meaning (`rule_flagged`)**: {self.dual_track_semantics.rule_flag_meaning}",
            f"- **Expert Flaw Meaning (`expert_confirmed_flaw`)**: {self.dual_track_semantics.expert_flaw_meaning}",
            f"- **Harmless Exception Boundary**: {self.dual_track_semantics.harmless_exception_context}",
            "",
            "## 4. Literature Basis & Normative Citations",
        ])
        for cit in self.literature_citations:
            lines.append(
                f"- **{cit.author} ({cit.year})**. *{cit.title}*. **{cit.journal}**. "
                + (f"[DOI:{cit.doi}](https://doi.org/{cit.doi})" if cit.doi else "No DOI recorded.")
                + f" Status: {cit.verification_status}."
            )
            if cit.evidence_quote:
                lines.append(f"  Unverified reference summary (not a verified quotation): {cit.evidence_quote}")

        lines.extend([
            "",
            "## 5. Frozen Empirical Calibration Metrics",
        ])
        if self.empirical_metrics:
            m = self.empirical_metrics
            lines.extend([
                f"- **Sample Size (N)**: {m.sample_size} cases",
                f"- **False Positive Rate (FPR / False Alarm)**: {format(m.false_positive_rate, '.2%') if m.false_positive_rate is not None else 'NOT_ESTIMABLE'}",
                f"- **False Negative Rate (FNR / Miss Rate)**: {format(m.false_negative_rate, '.2%') if m.false_negative_rate is not None else 'NOT_ESTIMABLE'}",
                f"- **Expected Calibration Error (ECE)**: {format(m.expected_calibration_error, '.4f') if m.expected_calibration_error is not None else 'NOT_ESTIMABLE'}",
                f"- **Supplied Reference-Label Agreement**: {format(m.expert_concordance, '.2%') if m.expert_concordance is not None else 'NOT_ESTIMABLE'}",
                f"- **Cohen's Kappa (κ)**: {format(m.cohens_kappa, '.4f') if m.cohens_kappa is not None else 'NOT_ESTIMABLE'}",
                f"- **Holdout Fingerprint**: `{m.holdout_cohort_hash}`",
                f"- **Evaluation Date**: {m.evaluation_date}",
            ])
        else:
            lines.append("*Awaiting frozen holdout benchmark evaluation.*")

        lines.append("")
        return "\n".join(lines)
