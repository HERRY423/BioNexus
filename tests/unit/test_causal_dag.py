"""
Unit tests for BioNexus Causal Epistemic DAG & Structural Identifiability Engine.
"""

from __future__ import annotations

from bionexus.causal_dag import (
    CausalDAG,
    CausalViolationType,
    CausalWarrantResult,
    NodeType,
)
from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef


def test_causal_dag_basics() -> None:
    dag = CausalDAG("TestDAG")
    dag.add_node("Treatment", NodeType.TREATMENT)
    dag.add_node("Outcome", NodeType.OUTCOME)
    dag.add_node("Confounder", NodeType.OBSERVED_CONFOUNDER)

    dag.add_edge("Confounder", "Treatment")
    dag.add_edge("Confounder", "Outcome")
    dag.add_edge("Treatment", "Outcome")

    assert dag.parents("Treatment") == {"Confounder"}
    assert dag.children("Confounder") == {"Treatment", "Outcome"}
    assert dag.ancestors("Outcome") == {"Confounder", "Treatment"}
    assert dag.descendants("Confounder") == {"Treatment", "Outcome"}


def test_d_separation_chain() -> None:
    # X -> M -> Y
    dag = CausalDAG("ChainDAG")
    dag.add_node("X")
    dag.add_node("M")
    dag.add_node("Y")
    dag.add_edge("X", "M")
    dag.add_edge("M", "Y")

    assert not dag.is_d_separated({"X"}, {"Y"}, set())
    assert dag.is_d_separated({"X"}, {"Y"}, {"M"})


def test_d_separation_fork() -> None:
    # X <- C -> Y
    dag = CausalDAG("ForkDAG")
    dag.add_node("X")
    dag.add_node("C")
    dag.add_node("Y")
    dag.add_edge("C", "X")
    dag.add_edge("C", "Y")

    assert not dag.is_d_separated({"X"}, {"Y"}, set())
    assert dag.is_d_separated({"X"}, {"Y"}, {"C"})


def test_d_separation_collider() -> None:
    # X -> C <- Y and C -> D
    dag = CausalDAG("ColliderDAG")
    dag.add_node("X")
    dag.add_node("C")
    dag.add_node("Y")
    dag.add_node("D")
    dag.add_edge("X", "C")
    dag.add_edge("Y", "C")
    dag.add_edge("C", "D")

    # Marginal independence (d-separated given empty set)
    assert dag.is_d_separated({"X"}, {"Y"}, set())
    # Conditioning on collider opens path (not d-separated)
    assert not dag.is_d_separated({"X"}, {"Y"}, {"C"})
    # Conditioning on descendant of collider also opens path
    assert not dag.is_d_separated({"X"}, {"Y"}, {"D"})


def test_backdoor_criterion_confounding() -> None:
    # Batch -> Treatment, Batch -> Expression, Treatment -> Expression
    dag = CausalDAG("SingleCellDE")
    dag.add_node("Condition", NodeType.TREATMENT)
    dag.add_node("Expression", NodeType.OUTCOME)
    dag.add_node("Batch", NodeType.OBSERVED_CONFOUNDER)

    dag.add_edge("Batch", "Condition")
    dag.add_edge("Batch", "Expression")
    dag.add_edge("Condition", "Expression")

    # Without adjustment: Backdoor path Condition <- Batch -> Expression is open
    satisfied, violations, open_paths = dag.backdoor_criterion("Condition", "Expression", set())
    assert not satisfied
    assert len(open_paths) == 1
    assert any(CausalViolationType.UNBLOCKED_BACKDOOR.value in v for v in violations)

    # With adjustment for Batch: Backdoor is blocked
    satisfied_adj, violations_adj, open_paths_adj = dag.backdoor_criterion(
        "Condition", "Expression", {"Batch"}
    )
    assert satisfied_adj
    assert len(violations_adj) == 0
    assert len(open_paths_adj) == 0


def test_backdoor_criterion_descendant_violation() -> None:
    # Treatment -> Mediator -> Outcome
    dag = CausalDAG("MediatorDAG")
    dag.add_node("Treatment", NodeType.TREATMENT)
    dag.add_node("Mediator", NodeType.MEDIATOR)
    dag.add_node("Outcome", NodeType.OUTCOME)

    dag.add_edge("Treatment", "Mediator")
    dag.add_edge("Mediator", "Outcome")

    # Adjusting for Mediator violates condition 1 (descendant of treatment)
    satisfied, violations, _ = dag.backdoor_criterion("Treatment", "Outcome", {"Mediator"})
    assert not satisfied
    assert any(CausalViolationType.DESCENDANT_OF_TREATMENT_ADJUSTED.value in v for v in violations)


def test_evaluate_causal_claim_unblocked_confounding() -> None:
    dag = CausalDAG("ConfoundedStudy")
    dag.add_node("Drug", NodeType.TREATMENT)
    dag.add_node("Survival", NodeType.OUTCOME)
    dag.add_node("Age", NodeType.OBSERVED_CONFOUNDER)

    dag.add_edge("Age", "Drug")
    dag.add_edge("Age", "Survival")
    dag.add_edge("Drug", "Survival")

    # Requesting CAUSAL claim without adjusting for Age
    res = dag.evaluate_causal_claim(
        treatment="Drug",
        outcome="Survival",
        conditioned_set=set(),
        requested_claim_class=ClaimClass.CAUSAL,
    )

    assert not res.is_warranted
    assert res.warranted_claim_class == ClaimClass.ASSOCIATION.value
    assert res.maturity_ceiling == ConclusionMaturity.FRAGILE.value
    assert res.recommended_adjustment_set == ["Age"]

    # Requesting CAUSAL claim WITH adjusting for Age
    res_adj = dag.evaluate_causal_claim(
        treatment="Drug",
        outcome="Survival",
        conditioned_set={"Age"},
        requested_claim_class=ClaimClass.CAUSAL,
    )

    assert res_adj.is_warranted
    assert res_adj.warranted_claim_class == ClaimClass.CAUSAL.value
    assert res_adj.maturity_ceiling == ConclusionMaturity.ROBUST.value


def test_collider_stratification_detection() -> None:
    # Treatment -> ResponsiveCluster <- Outcome
    dag = CausalDAG("SelectionBias")
    dag.add_node("Treatment", NodeType.TREATMENT)
    dag.add_node("Outcome", NodeType.OUTCOME)
    dag.add_node("SelectedCluster", NodeType.COLLIDER_SELECTION)

    dag.add_edge("Treatment", "SelectedCluster")
    dag.add_edge("Outcome", "SelectedCluster")

    res = dag.evaluate_causal_claim(
        treatment="Treatment",
        outcome="Outcome",
        conditioned_set={"SelectedCluster"},
        requested_claim_class=ClaimClass.CAUSAL,
    )

    assert not res.is_warranted
    assert any(CausalViolationType.COLLIDER_STRATIFICATION.value in v for v in res.violations)


def test_ledger_integration_with_causal_evaluation() -> None:
    ledger = ClaimLedger()

    # Evidence node
    ref = EvidenceRef(
        ref_id="EVID-EXP-01",
        kind="statistical_result",
        summary="p-value < 0.01",
        maturity=ConclusionMaturity.ROBUST.value,
    )
    ledger.add_evidence(ref)

    # Claim with failing causal evaluation
    failing_causal = CausalWarrantResult(
        is_warranted=False,
        requested_claim_class="causal",
        warranted_claim_class="association",
        maturity_ceiling=ConclusionMaturity.FRAGILE.value,
        violations=["UNBLOCKED_BACKDOOR"],
    ).to_dict()

    claim = ClaimRecord(
        claim_id="CLAIM-001",
        statement="Drug X causes upregulation of Gene Y",
        supported_by=["EVID-EXP-01"],
        causal_evaluation=failing_causal,
    )
    ledger.add_claim(claim)

    # The claim's maturity should be clamped by causal_evaluation to FRAGILE (not ROBUST)
    assert claim.evidence_status == ConclusionMaturity.FRAGILE.value


def test_frontdoor_criterion_identification() -> None:
    # Classic Frontdoor: X -> M -> Y with unobserved confounder U (U -> X and U -> Y)
    dag = CausalDAG("FrontdoorDAG")
    dag.add_node("X", NodeType.TREATMENT)
    dag.add_node("M", NodeType.MEDIATOR)
    dag.add_node("Y", NodeType.OUTCOME)
    dag.add_node("U", NodeType.UNOBSERVED_CONFOUNDER)

    dag.add_edge("U", "X")
    dag.add_edge("U", "Y")
    dag.add_edge("X", "M")
    dag.add_edge("M", "Y")

    # 1. Direct backdoor fails due to unobserved U
    is_bd, bd_viols, _ = dag.backdoor_criterion("X", "Y", set())
    assert not is_bd

    # 2. Frontdoor criterion on M succeeds
    is_fd, fd_viols, details = dag.frontdoor_criterion("X", "Y", "M")
    assert is_fd
    assert len(fd_viols) == 0
    assert details["intercepts_all_directed_paths"]

    # 3. Overall causal evaluation detects frontdoor and warrants causal claim!
    res = dag.evaluate_causal_claim("X", "Y", requested_claim_class=ClaimClass.CAUSAL)
    assert res.is_warranted
    assert res.identification_method == "frontdoor"
    assert res.frontdoor_mediator == "M"
    assert res.warranted_claim_class == ClaimClass.CAUSAL.value
    assert res.maturity_ceiling == ConclusionMaturity.SUPPORTED.value
    assert "Pearl 1995 Frontdoor Criterion" in res.rationale


def test_instrumental_variable_mendelian_randomization() -> None:
    # Classic IV: Z (eQTL) -> X (Gene Expression) -> Y (Disease Outcome), with unobserved confounder U -> X, U -> Y
    dag = CausalDAG("MendelianRandomizationDAG")
    dag.add_node("Z", NodeType.INSTRUMENT)
    dag.add_node("X", NodeType.TREATMENT)
    dag.add_node("Y", NodeType.OUTCOME)
    dag.add_node("U", NodeType.UNOBSERVED_CONFOUNDER)

    dag.add_edge("Z", "X")
    dag.add_edge("X", "Y")
    dag.add_edge("U", "X")
    dag.add_edge("U", "Y")

    # 1. Test IV criterion directly
    is_iv, iv_viols, details = dag.instrumental_variable_criterion("Z", "X", "Y")
    assert is_iv
    assert len(iv_viols) == 0

    # 2. Overall causal evaluation warrants causal claim via IV
    res = dag.evaluate_causal_claim("X", "Y", requested_claim_class=ClaimClass.CAUSAL)
    assert res.is_warranted
    assert res.identification_method == "instrumental_variable"
    assert res.valid_instrument == "Z"
    assert res.warranted_claim_class == ClaimClass.CAUSAL.value
    assert "Instrumental Variable / Mendelian Randomization" in res.rationale


def test_invalid_instrument_pleiotropic_violation() -> None:
    # Pleiotropy violation: Z -> X -> Y and direct pleiotropic edge Z -> Y
    dag = CausalDAG("PleiotropicIVDAG")
    dag.add_node("Z", NodeType.INSTRUMENT)
    dag.add_node("X", NodeType.TREATMENT)
    dag.add_node("Y", NodeType.OUTCOME)
    dag.add_node("U", NodeType.UNOBSERVED_CONFOUNDER)

    dag.add_edge("Z", "X")
    dag.add_edge("X", "Y")
    dag.add_edge("Z", "Y")  # Direct pleiotropy!
    dag.add_edge("U", "X")
    dag.add_edge("U", "Y")

    is_iv, iv_viols, _ = dag.instrumental_variable_criterion("Z", "X", "Y")
    assert not is_iv
    assert any(CausalViolationType.INVALID_INSTRUMENT_EXCLUSION_VIOLATED.value in v for v in iv_viols)

