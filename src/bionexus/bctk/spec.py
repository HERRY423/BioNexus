"""
BioNexus Conformance Test Kit (BCTK) Specification & Normative Rule Catalog.

Defines:
1. The 8 Conformance Dimensions
2. Normative Rule Catalog (BCTK-SEM-*, BCTK-INP-*, BCTK-BAK-*, BCTK-PRV-*, BCTK-WAR-*, BCTK-ABS-*, BCTK-FAI-*, BCTK-HST-*)
3. Diagnostic tier calculations (not certification)
4. Target-bound diagnostic data structures
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ConformanceDimension(str, Enum):
    """The 8 Core Scientific Conformance Dimensions evaluated by BCTK."""

    BIOLOGICAL_SEMANTICS = "BIOLOGICAL SEMANTICS"
    INPUT_STATE_HONESTY = "INPUT STATE HONESTY"
    BACKEND_IDENTITY = "BACKEND IDENTITY"
    PROVENANCE = "PROVENANCE"
    CLAIM_WARRANT = "CLAIM WARRANT"
    ABSTENTION = "ABSTENTION"
    FAILURE_HANDLING = "FAILURE HANDLING"
    CROSS_HOST_CONSISTENCY = "CROSS-HOST CONSISTENCY"


class DimensionStatus(str, Enum):
    """Evaluation status for a conformance dimension or rule."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    NOT_APPLICABLE = "N/A"
    NOT_ASSESSED = "NOT_ASSESSED"


class RuleSeverity(str, Enum):
    """Severity of a rule violation in BCTK."""

    CRITICAL = "CRITICAL"  # Blocker: immediate disqualification from GOLD/SILVER (e.g. Masquerading, Hallucination)
    HIGH = "HIGH"          # Major: degrades score significantly (e.g. missing provenance, bad matrix scale)
    MEDIUM = "MEDIUM"      # Moderate: warning or point penalty (e.g. missing optional metadata)
    INFO = "INFO"          # Informational


class ConformanceTier(str, Enum):
    """
    BioNexus Conformance Certification Tiers.

    - GOLD: >=95% overall score, 100% on Backend Identity & Abstention, 0 Critical violations.
    - SILVER: >=85% overall score, 100% on Backend Identity & Abstention, 0 Critical violations.
    - BRONZE: >=70% overall score, >=80% on Abstention, 0 Critical masquerading violations.
    - NON_CONFORMANT: <70% score or any unmitigated silent substitution / critical corruption.
    """

    NOT_ASSESSED = "NOT_ASSESSED"
    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    NON_CONFORMANT = "NON_CONFORMANT"


@dataclass
class RuleDefinition:
    """Normative definition of a BCTK conformance rule."""

    rule_id: str
    dimension: ConformanceDimension
    title: str
    description: str
    severity: RuleSeverity
    bns_reference: str
    weight: float = 1.0


@dataclass
class RuleEvaluation:
    """Result of evaluating a specific BCTK rule against a target."""

    rule_id: str
    dimension: ConformanceDimension
    status: DimensionStatus
    severity: RuleSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension.value,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


@dataclass
class DimensionResult:
    """Aggregated result for one conformance dimension."""

    dimension: ConformanceDimension
    status: DimensionStatus
    score_percentage: float
    passed_rules: int
    total_rules: int
    critical_failures: int
    rule_evaluations: List[RuleEvaluation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "status": self.status.value,
            "score_percentage": round(self.score_percentage, 1),
            "passed_rules": self.passed_rules,
            "total_rules": self.total_rules,
            "critical_failures": self.critical_failures,
            "evaluations": [e.to_dict() for e in self.rule_evaluations],
        }


@dataclass
class ConformanceReport:
    """Target-bound development diagnostic; not a certificate or endorsement."""

    target_name: str
    target_type: str
    target_path: str
    abi_version: str
    bctk_version: str
    timestamp: str
    overall_score: float
    conformance_tier: ConformanceTier
    biofailurebench_score: Optional[float]
    dimension_results: Dict[str, DimensionResult]
    critical_violations: List[Dict[str, Any]] = field(default_factory=list)
    assessment_status: str = "DEVELOPMENT_NOT_CERTIFIABLE"
    diagnostic_tier: ConformanceTier = ConformanceTier.NOT_ASSESSED
    target_content_sha256: str = ""
    target_file_count: int = 0
    badge_eligible: bool = False
    evidence_attestation_ids: List[str] = field(default_factory=list)
    trust_decision: str = "NOT_ASSESSED"
    cryptographic_fingerprint: str = ""
    badge_markdown: str = ""
    summary_text: str = ""

    def compute_fingerprint(self) -> str:
        """Hash the complete diagnostic payload; this hash is not a signature."""
        canonical_repr = {
            "target_name": self.target_name,
            "target_type": self.target_type,
            "abi_version": self.abi_version,
            "bctk_version": self.bctk_version,
            "timestamp": self.timestamp,
            "assessment_status": self.assessment_status,
            "diagnostic_tier": self.diagnostic_tier.value,
            "target_content_sha256": self.target_content_sha256,
            "target_file_count": self.target_file_count,
            "badge_eligible": self.badge_eligible,
            "evidence_attestation_ids": self.evidence_attestation_ids,
            "trust_decision": self.trust_decision,
            "overall_score": round(self.overall_score, 2),
            "conformance_tier": self.conformance_tier.value,
            "dimensions": {dim: res.to_dict() for dim, res in self.dimension_results.items()},
            "critical_violations": self.critical_violations,
        }
        raw_json = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_name": self.target_name,
            "target_type": self.target_type,
            "target_path": self.target_path,
            "abi_version": self.abi_version,
            "bctk_version": self.bctk_version,
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 1),
            "conformance_tier": self.conformance_tier.value,
            "assessment_status": self.assessment_status,
            "diagnostic_tier": self.diagnostic_tier.value,
            "target_content_sha256": self.target_content_sha256,
            "target_file_count": self.target_file_count,
            "badge_eligible": self.badge_eligible,
            "evidence_attestation_ids": self.evidence_attestation_ids,
            "trust_decision": self.trust_decision,
            "biofailurebench_score": round(self.biofailurebench_score, 1) if self.biofailurebench_score is not None else None,
            "cryptographic_fingerprint": self.cryptographic_fingerprint or self.compute_fingerprint(),
            "badge_markdown": self.badge_markdown,
            "dimensions": {k: v.to_dict() for k, v in self.dimension_results.items()},
            "critical_violations": self.critical_violations,
            "summary": self.summary_text,
        }


# ==============================================================================
# Normative Rule Catalog (BCTK-*)
# ==============================================================================

BCTK_RULE_CATALOG: Dict[str, RuleDefinition] = {
    # 1. Biological Semantics (BCTK-SEM-*)
    "BCTK-SEM-001": RuleDefinition(
        rule_id="BCTK-SEM-001",
        dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
        title="Gene Identifier Hygiene",
        description="Declared or processed gene identifiers must adhere to standard namespaces (HGNC, Ensembl, UniProt) with valid symbol syntax.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-002 §2",
    ),
    "BCTK-SEM-002": RuleDefinition(
        rule_id="BCTK-SEM-002",
        dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
        title="Expression Matrix Scale Semantics",
        description="Input and output expression matrices must explicitly distinguish raw integer counts from log-normalized and scaled data.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-002 §3 (BNS-II-001)",
    ),
    "BCTK-SEM-003": RuleDefinition(
        rule_id="BCTK-SEM-003",
        dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
        title="Spatial Coordinate Space Justification",
        description="Spatial coordinates must be physical micrometer/pixel coordinates; dimensional reduction embeddings (e.g. UMAP/PCA) must not be falsely treated as physical coordinates.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-002 §4 (BNS-II-005/006)",
    ),
    "BCTK-SEM-004": RuleDefinition(
        rule_id="BCTK-SEM-004",
        dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
        title="Species Reference Genome Consistency",
        description="Genomic coordinates, annotations, and transcripts must explicitly state reference genome assembly (e.g. GRCh38, mm10).",
        severity=RuleSeverity.MEDIUM,
        bns_reference="BNS-001 §4",
    ),

    # 2. Input State Honesty (BCTK-INP-*)
    "BCTK-INP-001": RuleDefinition(
        rule_id="BCTK-INP-001",
        dimension=ConformanceDimension.INPUT_STATE_HONESTY,
        title="Non-Negative Count Invariant for Count Models",
        description="Negative binomial and Poisson count-based models (e.g. DESeq2, scVI) must strictly reject negative expression values.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-002 §3.1 (BN-F001)",
    ),
    "BCTK-INP-002": RuleDefinition(
        rule_id="BCTK-INP-002",
        dimension=ConformanceDimension.INPUT_STATE_HONESTY,
        title="Non-Integer Count Model Invariant",
        description="Continuous float matrices (e.g. log1p CPM) must not be silently passed into discrete dispersion estimation models.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-002 §3.2 (BN-F001)",
    ),
    "BCTK-INP-003": RuleDefinition(
        rule_id="BCTK-INP-003",
        dimension=ConformanceDimension.INPUT_STATE_HONESTY,
        title="Biological Replicate Sample Size Honesty",
        description="Differential expression and population inferences must audit biological sample size (n >= 3 per condition for parametric inference).",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-002 §5 (BN-F006)",
    ),
    "BCTK-INP-004": RuleDefinition(
        rule_id="BCTK-INP-004",
        dimension=ConformanceDimension.INPUT_STATE_HONESTY,
        title="Input Data Preflight Audit",
        description="Analyses must audit input matrix dimensions, missing values (NaN/Inf), and sparsity before running analytical pipelines.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-013 §2",
    ),

    # 3. Backend Identity (BCTK-BAK-*)
    "BCTK-BAK-001": RuleDefinition(
        rule_id="BCTK-BAK-001",
        dimension=ConformanceDimension.BACKEND_IDENTITY,
        title="Zero Silent Substitution (Anti-Masquerading)",
        description="Declared backend must match observed runtime backend. A local heuristic or toy formula MUST NOT execute under a gold-standard community tool name.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-003 §3 (BN-F010, BNS-EF-012)",
    ),
    "BCTK-BAK-002": RuleDefinition(
        rule_id="BCTK-BAK-002",
        dimension=ConformanceDimension.BACKEND_IDENTITY,
        title="Backend Version Contract Verification",
        description="Observed backend package version must satisfy declared minimum version constraints.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-003 §4 (BNS-EF-014)",
    ),
    "BCTK-BAK-003": RuleDefinition(
        rule_id="BCTK-BAK-003",
        dimension=ConformanceDimension.BACKEND_IDENTITY,
        title="Entry Point Symbol Resolution",
        description="All declared entry point classes, functions, and symbols must successfully import and resolve from the genuine distribution package.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-003 §4.1 (BNS-EF-015)",
    ),
    "BCTK-BAK-004": RuleDefinition(
        rule_id="BCTK-BAK-004",
        dimension=ConformanceDimension.BACKEND_IDENTITY,
        title="Cryptographic Execution Fingerprinting",
        description="Backend identity, versions, and entry points must bind into a deterministic execution fingerprint attached to output ledgers.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-003 §5 (BNS-EF-016)",
    ),

    # 4. Provenance (BCTK-PRV-*)
    "BCTK-PRV-001": RuleDefinition(
        rule_id="BCTK-PRV-001",
        dimension=ConformanceDimension.PROVENANCE,
        title="W3C PROV-O Activity Sidecar Generation",
        description="Pipelines must generate machine-readable provenance sidecars recording entities, activities, agents, and parameters.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-006 §2",
    ),
    "BCTK-PRV-002": RuleDefinition(
        rule_id="BCTK-PRV-002",
        dimension=ConformanceDimension.PROVENANCE,
        title="SHA-256 Input/Output Integrity Binding",
        description="Provenance sidecars and ledgers must record cryptographic SHA-256 hashes of all input and output artifacts.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-006 §3",
    ),
    "BCTK-PRV-003": RuleDefinition(
        rule_id="BCTK-PRV-003",
        dimension=ConformanceDimension.PROVENANCE,
        title="Environment & Software Capture",
        description="Execution metadata must record Python version, OS platform, package dependencies, and timestamp.",
        severity=RuleSeverity.MEDIUM,
        bns_reference="BNS-006 §4",
    ),
    "BCTK-PRV-004": RuleDefinition(
        rule_id="BCTK-PRV-004",
        dimension=ConformanceDimension.PROVENANCE,
        title="Standards Interoperability (RO-Crate / BCO)",
        description="Target should support exporting run capsules into RO-Crate or IEEE 2791-2020 BioCompute Object formats.",
        severity=RuleSeverity.MEDIUM,
        bns_reference="BNS-016 §2",
    ),

    # 5. Claim Warrant (BCTK-WAR-*)
    "BCTK-WAR-001": RuleDefinition(
        rule_id="BCTK-WAR-001",
        dimension=ConformanceDimension.CLAIM_WARRANT,
        title="Evidence-Capped Claim Ceilings",
        description="Scientific statements emitted must not exceed the evidence ceiling (e.g. observational correlations must not claim causal treatment effects without DAG/perturbation).",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-004 §3 (BNS-CC-013, BNS-017)",
    ),
    "BCTK-WAR-002": RuleDefinition(
        rule_id="BCTK-WAR-002",
        dimension=ConformanceDimension.CLAIM_WARRANT,
        title="Prohibited Cell-Type Hallucination Defense",
        description="Unsupervised cluster numbers (e.g. 'Cluster 3') must not be asserted as specific cell types without canonical marker reference evidence.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-001 §6 (BN-F005)",
    ),
    "BCTK-WAR-003": RuleDefinition(
        rule_id="BCTK-WAR-003",
        dimension=ConformanceDimension.CLAIM_WARRANT,
        title="Multiple Testing Correction Honesty",
        description="Genome-wide p-values must not be reported as statistically significant without Benjamini-Hochberg FDR or Bonferroni multiple testing adjustment.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-004 §2.4 (BN-F002)",
    ),
    "BCTK-WAR-004": RuleDefinition(
        rule_id="BCTK-WAR-004",
        dimension=ConformanceDimension.CLAIM_WARRANT,
        title="Regulatory / GxP Compliance Non-Overclaim",
        description="Analyses must not claim 21 CFR Part 11, GxP, or CLIA certification unless verified by authorized attestation authority.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-001 §6.3",
    ),

    # 6. Abstention (BCTK-ABS-*)
    "BCTK-ABS-001": RuleDefinition(
        rule_id="BCTK-ABS-001",
        dimension=ConformanceDimension.ABSTENTION,
        title="Deterministic Precondition Refusal",
        description="When critical preconditions fail (missing backend, invalid matrix, negative replicates), execution must refuse with structured ABSTAIN status.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-005 §2",
    ),
    "BCTK-ABS-002": RuleDefinition(
        rule_id="BCTK-ABS-002",
        dimension=ConformanceDimension.ABSTENTION,
        title="Structured EvidenceCard Refusal Payload",
        description="Refusals must return machine-readable EvidenceCard with conclusion_status='ABSTAIN', evidence_grade='abstain', and explicit refusal reason.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-005 §3",
    ),
    "BCTK-ABS-003": RuleDefinition(
        rule_id="BCTK-ABS-003",
        dimension=ConformanceDimension.ABSTENTION,
        title="Zero Silent Fallback to Toy Heuristics",
        description="Missing primary backend must trigger clean abstention rather than falling back to an unverified approximation without researcher consent.",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-005 §4",
    ),

    # 7. Failure Handling (BCTK-FAI-*)
    "BCTK-FAI-001": RuleDefinition(
        rule_id="BCTK-FAI-001",
        dimension=ConformanceDimension.FAILURE_HANDLING,
        title="BioFailureBench Trap Defense",
        description="Target must detect and intercept hidden methodological traps in the BioFailureBench corpus (e.g. batch confounding, sample swaps, label leakage).",
        severity=RuleSeverity.CRITICAL,
        bns_reference="BNS-014 §2",
    ),
    "BCTK-FAI-002": RuleDefinition(
        rule_id="BCTK-FAI-002",
        dimension=ConformanceDimension.FAILURE_HANDLING,
        title="Failure Taxonomy Linkage",
        description="Detected errors and refusals must link to canonical failure taxonomy codes (BN-F001..BN-F020).",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-011 §2",
    ),
    "BCTK-FAI-003": RuleDefinition(
        rule_id="BCTK-FAI-003",
        dimension=ConformanceDimension.FAILURE_HANDLING,
        title="Actionable Remediation Prescription",
        description="Refusals should include actionable remediation guidance (e.g. required sample size, alternative valid backend).",
        severity=RuleSeverity.MEDIUM,
        bns_reference="BNS-011 §3",
    ),

    # 8. Cross-Host Consistency (BCTK-HST-*)
    "BCTK-HST-001": RuleDefinition(
        rule_id="BCTK-HST-001",
        dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
        title="Host-Agnostic Interface Compliance",
        description="Target must adhere to identical ABI contracts regardless of host agent (Claude, Codex, Cursor, CLI, MCP).",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-008 §2",
    ),
    "BCTK-HST-002": RuleDefinition(
        rule_id="BCTK-HST-002",
        dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
        title="Deterministic Execution Under Fixed Seed",
        description="Stochastic algorithms must yield identical deterministic outputs given fixed random seed.",
        severity=RuleSeverity.HIGH,
        bns_reference="BNS-008 §3",
    ),
    "BCTK-HST-003": RuleDefinition(
        rule_id="BCTK-HST-003",
        dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
        title="Headless & Non-Interactive CI Compatibility",
        description="Target must run deterministically in headless CI environments without requiring interactive GUI or unmanaged network calls.",
        severity=RuleSeverity.MEDIUM,
        bns_reference="BNS-008 §4",
    ),
}


def calculate_conformance_tier(
    overall_score: float,
    dimension_results: Dict[str, DimensionResult],
    critical_failures: int,
) -> ConformanceTier:
    """Compute normative Conformance Tier according to BCTK grading specification."""
    bak_res = dimension_results.get(ConformanceDimension.BACKEND_IDENTITY.value)
    abs_res = dimension_results.get(ConformanceDimension.ABSTENTION.value)

    bak_pass = bak_res and bak_res.status == DimensionStatus.PASS and bak_res.critical_failures == 0
    abs_pass = abs_res and abs_res.status == DimensionStatus.PASS and abs_res.critical_failures == 0

    if critical_failures > 0:
        return ConformanceTier.NON_CONFORMANT

    if overall_score >= 95.0 and bak_pass and abs_pass:
        return ConformanceTier.GOLD
    elif overall_score >= 85.0 and bak_pass and abs_pass:
        return ConformanceTier.SILVER
    elif overall_score >= 70.0 and (abs_res and abs_res.score_percentage >= 80.0):
        return ConformanceTier.BRONZE
    else:
        return ConformanceTier.NON_CONFORMANT
