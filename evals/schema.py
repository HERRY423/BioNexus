"""
Schema definitions for BioNexus Agent Behavior & Scientific Epistemic Benchmark.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvalCategory(str, Enum):
    """Benchmark evaluation categories."""

    ROUTING = "routing"  # Intent recognition and capability matching
    REFUSAL = "refusal"  # Deterministic refusal of invalid analyses (pseudoreplication, wrong distribution)
    CAPABILITY_CLAIM = "capability_claim"  # Anti-hallucination of capabilities and cell types
    SCIENTIFIC_SEMANTICS = "scientific_semantics"  # Data semantic distinction (raw vs log, cell vs sample, marker vs DE)
    BACKEND_FAILURE = "backend_failure"  # Missing backend, degradation, and fallback honesty
    ADVERSARIAL = "adversarial"  # Tricky/adversarial prompts attempting to bypass scientific invariants


class ExpectedStatus(str, Enum):
    """Expected evaluation status."""

    PERMITTED = "PERMITTED"
    NEEDS_DATA = "NEEDS_DATA"
    ABSTAIN = "ABSTAIN"
    DEGRADED_ADVISORY = "DEGRADED_ADVISORY"


@dataclass
class EvalCase:
    """A single scientific agent evaluation benchmark case."""

    id: str
    prompt: str
    category: EvalCategory
    expected_status: ExpectedStatus
    expected_capability: Optional[str] = None
    expected_violations: List[str] = field(default_factory=list)
    prohibited_claims: List[str] = field(default_factory=list)
    required_remedies: List[str] = field(default_factory=list)
    data_metadata: Dict[str, Any] = field(default_factory=dict)
    allow_degraded: bool = False
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "category": self.category.value,
            "expected_status": self.expected_status.value,
            "expected_capability": self.expected_capability,
            "expected_violations": self.expected_violations,
            "prohibited_claims": self.prohibited_claims,
            "required_remedies": self.required_remedies,
            "data_metadata": self.data_metadata,
            "allow_degraded": self.allow_degraded,
            "description": self.description,
        }


@dataclass
class EvalResult:
    """Evaluation result for a single benchmark case."""

    case_id: str
    category: str
    passed: bool
    expected_status: str
    actual_status: str
    expected_capability: Optional[str]
    actual_capability: Optional[str]
    failure_reasons: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark evaluation report across all test cases."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_accuracy: float
    metrics: Dict[str, float]
    category_scores: Dict[str, Dict[str, Any]]
    detailed_results: List[EvalResult]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "overall_accuracy": round(self.overall_accuracy, 4),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "category_scores": self.category_scores,
            "detailed_results": [r.to_dict() for r in self.detailed_results],
            "timestamp": self.timestamp,
        }
