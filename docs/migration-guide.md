# BioNexus Migration & Upgrade Guide

This guide assists developers and host agents in upgrading across BioNexus minor versions, specifically detailing the transition from **EvidenceCard 1.0 (Single-layer status)** to **EvidenceCard 2.0 (3-Layer Epistemic Model)** and the **Scientific Intent Router**.

---

## 🚀 Migrating to BioNexus 0.8.0

### 1. EvidenceCard 2.0 Architecture Transition

In BioNexus <= 0.7.x, evidence status and execution state were compressed into a single status string (`SUPPORTED`, `INSUFFICIENT`, `REFUSED`). 

In **BioNexus 0.8.0**, evidence is decoupled into three explicit epistemic layers:
1. **Layer 1: Execution State** (`EXECUTED`, `DEGRADED`, `REFUSED`, `FAILED`)
2. **Layer 2: Qualitative Dimension Grades** (`A`, `B`, `C`, `UNTESTED`, `NOT_APPLICABLE`, `INSUFFICIENT`, `CONFLICTED`)
3. **Layer 3: Scientific Conclusion Maturity** (`ABSTAIN`, `FRAGILE`, `CONFLICTED`, `PRELIMINARY`, `SUPPORTED`, `ROBUST`, `REPLICATED`)

#### Backward Compatibility Support
BioNexus 0.8.0 provides non-breaking compatibility aliases:
```python
# Old import (still supported via aliases)
from bionexus.contracts import ConclusionStatus, EvidenceGrade

# Recommended BioNexus 0.8.0+ imports:
from bionexus.contracts import (
    ExecutionState,
    DimensionGrade,
    ConclusionMaturity,
    EvidenceCard,
)
```

#### Code Migration Example

**Before (0.7.x):**
```python
from bionexus.contracts import EvidenceCard, attach_meta

card = EvidenceCard(
    status="SUPPORTED",
    input_integrity="A",
    statistical_support="A",
)
```

**After (0.8.0+):**
```python
from bionexus.contracts import (
    GRADE_A,
    ConclusionMaturity,
    EvidenceCard,
    ExecutionState,
    attach_meta,
)

card = EvidenceCard(
    execution_state=ExecutionState.EXECUTED.value,
    conclusion_maturity=ConclusionMaturity.ROBUST.value,
    input_integrity=GRADE_A,
    statistical_support=GRADE_A,
    parameter_robustness=GRADE_A,
)
```

---

### 2. Migrating from Static Skill Routing to Scientific Intent Router

**Before (0.7.x - Static Discovery):**
```python
from bionexus.agent_routing import DEFAULT_SKILLS, is_default_skill

if is_default_skill("single-cell-rna-qc"):
    # Run single cell pipeline without precondition checks
    pass
```

**After (0.8.0+ - Validated Scientific Intent Routing):**
```python
from bionexus.agent_routing import route_scientific_intent, RoutingStatus

decision = route_scientific_intent(
    query="compare tumor vs normal in my scRNA data",
    data_metadata={"min_replicates_per_condition": 3, "is_integer_like": True}
)

if decision.status == RoutingStatus.PERMITTED:
    # Execute verified gold-chain script
    print(f"Running canonical pipeline: {decision.recommended_script}")
elif decision.status == RoutingStatus.NEEDS_DATA:
    # Ask user for biological replicate groupings
    print(f"Requesting data: {decision.missing_data_requests}")
elif decision.status == RoutingStatus.ABSTAIN:
    # Deterministic refusal of invalid analyses (e.g. n=1 pseudoreplication)
    print(f"Refusal rationale: {decision.rationale}")
    print(f"Actionable remedies: {decision.remedies}")
```

---

### 3. Migrating CLI Usage

| 0.7.x Command | 0.8.0+ Command | Description |
|---|---|---|
| `bionexus doctor` | `bionexus doctor` | Preflight runtime environment diagnostics |
| *(New in 0.8.0)* | `bionexus capability list` | List machine-readable capability contracts |
| *(New in 0.8.0)* | `bionexus capability show <id>` | Inspect capability input semantics and preconditions |
| *(New in 0.8.0)* | `bionexus capability check <id>` | Pre-evaluate analytical viability before execution |
| *(New in 0.8.0)* | `bionexus route "<query>"` | 6-stage scientific intent & invariant routing |
| *(New in 0.8.0)* | `bionexus eval` | Run agent behavior benchmark across 8 reliability pillars |
