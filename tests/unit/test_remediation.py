"""
Unit tests for BioNexus Prescriptive Power & Experimental Remediation Engine.
"""

from __future__ import annotations

from bionexus.contracts import ConclusionMaturity
from bionexus.remediation import (
    RemediationStrategy,
    calculate_pseudobulk_power,
    calculate_required_replicates,
    generate_prescription_for_violation,
)


def test_pseudobulk_power_monotonicity() -> None:
    # Power increases as sample size increases
    p_n2 = calculate_pseudobulk_power(n_per_group=2, log2fc=1.0, dispersion=0.2)
    p_n5 = calculate_pseudobulk_power(n_per_group=5, log2fc=1.0, dispersion=0.2)
    p_n15 = calculate_pseudobulk_power(n_per_group=15, log2fc=1.0, dispersion=0.2)

    assert p_n2.power < p_n5.power < p_n15.power
    assert p_n15.is_adequate

    # Power increases as effect size increases
    p_fc05 = calculate_pseudobulk_power(n_per_group=5, log2fc=0.5, dispersion=0.2)
    p_fc20 = calculate_pseudobulk_power(n_per_group=5, log2fc=2.0, dispersion=0.2)
    assert p_fc05.power < p_fc20.power

    # Power decreases as biological dispersion increases
    p_low_disp = calculate_pseudobulk_power(n_per_group=5, log2fc=1.0, dispersion=0.05)
    p_high_disp = calculate_pseudobulk_power(n_per_group=5, log2fc=1.0, dispersion=0.50)
    assert p_low_disp.power > p_high_disp.power


def test_required_replicates_calculation() -> None:
    # Replicates needed to detect log2fc=1.0 with 80% power at dispersion=0.2
    req_n = calculate_required_replicates(target_power=0.80, target_log2fc=1.0, dispersion=0.2)
    assert req_n >= 3

    # Verification: calculate power with req_n
    p_req = calculate_pseudobulk_power(n_per_group=req_n, log2fc=1.0, dispersion=0.2)
    assert p_req.power >= 0.80


def test_generate_prescription_bn_f006() -> None:
    meta = {"n_donors_min": 2, "target_log2fc": 1.0, "dispersion": 0.25}
    presc = generate_prescription_for_violation("BN-F006", meta)

    assert presc.violation_id == "BN-F006"
    assert presc.primary_strategy == RemediationStrategy.ADD_BIOLOGICAL_REPLICATES.value
    assert presc.minimum_required_samples >= 3
    assert presc.additional_samples_needed >= 1
    assert presc.power_assessment is not None
    assert len(presc.analytical_remedies) > 0
    assert len(presc.academic_citations) > 0
    assert "Nature Comms" in " ".join(presc.academic_citations)


def test_generate_prescription_bn_f001() -> None:
    presc = generate_prescription_for_violation("BN-F001")
    assert presc.violation_id == "BN-F001"
    assert presc.primary_strategy == RemediationStrategy.CORRECT_COUNT_PREPROCESSING.value
    assert presc.target_maturity == ConclusionMaturity.ROBUST.value


def test_generate_prescription_bn_f005() -> None:
    presc = generate_prescription_for_violation("BN-F005")
    assert presc.violation_id == "BN-F005"
    assert presc.primary_strategy == RemediationStrategy.APPLY_FDR_CORRECTION.value


def test_generate_prescription_bn_f010() -> None:
    presc = generate_prescription_for_violation("BN-F010")
    assert presc.violation_id == "BN-F010"
    assert presc.primary_strategy == RemediationStrategy.BACKEND_FIDELITY_ENFORCEMENT.value
