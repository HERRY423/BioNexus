"""
Schema definitions for BioNexus Agent Behavior & Scientific Epistemic Benchmark (BioNexus Eval 2.0).

Defines:
- EvalLevel: L1 (Router & Precondition), L2 (Host-Agent & Claim Audit), L3 (Scientific Outcome & Ground Truth).
- EvalCategory: Functional benchmark dimensions.
- EvalCase, EvalResult, BenchmarkReport, EpistemicCalibrationReport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvalLevel(str, Enum):
    """Multi-tier benchmark hierarchy."""

    L1_ROUTER = "L1"  # L1: Router & Precondition Contract Regression
    L2_AGENT = "L2"  # L2: Host-Agent Claim & Anti-Hallucination Behavior
    L3_OUTCOME = "L3"  # L3: Scientific Biological Outcome & Planted Truth Recovery
    ALL = "ALL"


class EvalCategory(str, Enum):
    """Benchmark evaluation categories."""

    ROUTING = "routing"  # Intent recognition and capability matching (L1)
    REFUSAL = "refusal"  # Deterministic refusal of invalid analyses (L1)
    CAPABILITY_CLAIM = "capability_claim"  # Anti-hallucination of capabilities and cell types (L1/L2)
    SCIENTIFIC_SEMANTICS = "scientific_semantics"  # Data semantics: raw vs log, cell vs sample (L1)
    BACKEND_FAILURE = "backend_failure"  # Missing backend degradation and fallback honesty (L1)
    ADVERSARIAL = "adversarial"  # Adversarial prompts attempting invariant bypass (L1/L2)
    HOST_AGENT_CLAIM = "host_agent_claim"  # L2 generated response prohibited claim audit
    SCIENTIFIC_OUTCOME = "scientific_outcome"  # L3 biological ground truth & statistics recovery


class ExpectedStatus(str, Enum):
    """Expected evaluation status."""

    PERMITTED = "PERMITTED"
    NEEDS_DATA = "NEEDS_DATA"
    ABSTAIN = "ABSTAIN"
    DEGRADED_ADVISORY = "DEGRADED_ADVISORY"
    EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN = "EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN"


@dataclass
class EvalCase:
    """A single scientific agent evaluation benchmark case."""

    id: str
    prompt: str
    category: EvalCategory
    expected_status: ExpectedStatus
    level: EvalLevel = EvalLevel.L1_ROUTER
    expected_capability: Optional[str] = None
    expected_maturity: Optional[str] = None
    expected_violations: List[str] = field(default_factory=list)
    prohibited_claims: List[str] = field(default_factory=list)
    required_remedies: List[str] = field(default_factory=list)
    simulated_agent_response: Optional[str] = None
    data_metadata: Dict[str, Any] = field(default_factory=dict)
    allow_degraded: bool = False
    allow_frontier: bool = False
    description: str = ""
    known_limitation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level.value,
            "prompt": self.prompt,
            "category": self.category.value,
            "expected_status": self.expected_status.value,
            "expected_capability": self.expected_capability,
            "expected_maturity": self.expected_maturity,
            "expected_violations": self.expected_violations,
            "prohibited_claims": self.prohibited_claims,
            "required_remedies": self.required_remedies,
            "simulated_agent_response": self.simulated_agent_response,
            "data_metadata": self.data_metadata,
            "allow_degraded": self.allow_degraded,
            "allow_frontier": self.allow_frontier,
            "description": self.description,
            "known_limitation": self.known_limitation,
        }


@dataclass
class EvalResult:
    """Evaluation result for a single benchmark case."""

    case_id: str
    category: str
    passed: bool
    expected_status: str
    actual_status: str
    level: str = "L1"
    expected_capability: Optional[str] = None
    actual_capability: Optional[str] = None
    expected_maturity: Optional[str] = None
    actual_maturity: Optional[str] = None
    failure_reasons: List[str] = field(default_factory=list)
    prohibited_claim_violations: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None
    known_limitation: bool = False
    provider: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EpistemicCalibrationReport:
    """Detailed scientific evidence maturity calibration statistics."""

    total_evaluated: int
    exact_accuracy: float
    overconfidence_count: int
    overconfidence_rate: float
    underconfidence_count: int
    underconfidence_rate: float
    ordinal_calibration_error: float
    brier_calibration_score: float
    macro_f1: float
    confusion_matrix: Dict[str, Dict[str, int]]
    maturity_levels: List[str]
    adjacent_error_rate: float = 0.0
    within_one_accuracy: float = 1.0
    per_class: Dict[str, Dict[str, float]] = field(default_factory=dict)
    verdict: str = "CALIBRATED"
    skipped_no_backend: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark evaluation report across all test cases."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_accuracy: float
    level_scores: Dict[str, Dict[str, Any]]
    metrics: Dict[str, float]
    category_scores: Dict[str, Dict[str, Any]]
    detailed_results: List[EvalResult]
    timestamp: str
    calibration: Optional[Dict[str, Any]] = None
    provider: str = "replay"
    model: str = "simulated_trace_v1"
    is_live: bool = False
    skipped_cases: int = 0
    strict_mode: bool = False
    frontier_results: List[EvalResult] = field(default_factory=list)
    frontier_metrics: Dict[str, Any] = field(default_factory=dict)
    frontier_calibration: Optional[Dict[str, Any]] = None
    union_total: int = 0
    union_passed: int = 0
    union_accuracy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "skipped_cases": self.skipped_cases,
            "strict_mode": self.strict_mode,
            "overall_accuracy": round(self.overall_accuracy, 4),
            "provider": self.provider,
            "model": self.model,
            "is_live": self.is_live,
            "level_scores": self.level_scores,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "category_scores": self.category_scores,
            "timestamp": self.timestamp,
            "calibration": self.calibration,
            "detailed_results": [r.to_dict() for r in self.detailed_results],
            "frontier_results": [r.to_dict() for r in self.frontier_results],
            "frontier_metrics": self.frontier_metrics,
            "frontier_calibration": self.frontier_calibration,
            "union_total": self.union_total,
            "union_passed": self.union_passed,
            "union_accuracy": round(self.union_accuracy, 4),
        }
