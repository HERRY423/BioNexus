"""Cross-check claims and ceilings at the public audit entry point."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from bionexus.de.engine import audit_de


def _cohort(tmp_path, *, thin=False, confounded=False):
    rows = []
    for condition in ("A", "B"):
        for donor in range(5):
            batch = condition if confounded else str(donor % 2)
            for ct in ("B cell", "T cell"):
                n = 5 if thin and condition == "B" and ct == "B cell" and donor >= 2 else 20
                rows.extend([(f"{condition}{donor}", condition, batch, ct)] * n)
    obs = pd.DataFrame(rows, columns=["donor", "condition", "batch", "cell_type"])
    obs["condition"] = pd.Categorical(obs["condition"], categories=["A", "B", "unused"])
    adata = SimpleNamespace(obs=obs, X=np.ones((len(obs), 2), dtype=int), var_names=["x", "y"], uns={})
    path = tmp_path / "de.csv"
    pd.DataFrame({"gene": ["x", "y"], "log2FoldChange": [1.1, -0.7],
                  "pvalue": [.001, .02], "padj": [.002, .04]}).to_csv(path, index=False)
    receipt = dict(method="DESeq2", statistical_unit="donor", fit_status="CONVERGED",
                   design="~ batch + condition", design_matrix_columns=["Intercept", "batch[T.1]", "condition[T.B]"],
                   n_donors=10, donor_ids=sorted(obs.donor.unique()), result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   evidence_factors=["replication", "external_validation"])
    return dict(adata=adata, de_table=path, execution_record=receipt, case="B", reference="A", cell_type="B cell")


def test_power_and_factors_use_the_requested_eligible_stratum(tmp_path):
    inputs = _cohort(tmp_path, thin=True)
    result = audit_de(**inputs)
    assessment = result.evidence_assessment
    assert assessment["measurement_results"]["replication"] is False
    assert set(assessment["unverified_factors"]) == {"replication", "external_validation"}
    issue = next(f for f in result.findings if f.rule_id == "BFA-017")
    assert issue.evidence_data["conflicting_factors"] == ["replication"]
    assert result.design_warrants[0]["donors_by_condition"] == {"B": 2, "A": 5}
    assert result.design_warrants[0]["verdict"]["population_claims_allowed"] is False
    assert result.design_warrants[0]["verdict"]["maturity_ceiling"] == "PRELIMINARY"
    inputs["cell_type"] = "T cell"
    result = audit_de(**inputs, config={"power_parameters": {"n_tests": 15000, "n_true_effects": 300}})
    assert set(result.evidence_assessment["satisfied_factors"]) == {"replication", "sample_design", "confound_controls", "provenance"}
    assert result.design_warrants[0]["status"] == "CONDITIONAL_DESIGN_CEILING"
    assert result.design_warrants[0]["power"]["alpha_basis"] == "jung2005"
    # The two constant expressed genes have no measured within-condition
    # overdispersion. This fixture no longer inherits the planning default.
    assert result.design_warrants[0]["power"]["dispersion_basis"] == "pseudobulk_moment_mean"
    assert result.design_warrants[0]["power"]["dispersion"] == 0
    assert result.evidence_assessment["evidence_maturity"] == "SUPPORTED"
    assert "jung2005" in result.summary_text(False) and "jung2005" in result.to_markdown()
    json.dumps(result.to_dict(), allow_nan=False)


def test_unestimable_design_cannot_supply_confound_controls(tmp_path):
    result = audit_de(**_cohort(tmp_path, confounded=True))
    assert result.design_warrants[0]["verdict"]["regime"] == "ABSTAIN_CONFOUNDED"
    assert "confound_controls" not in result.evidence_assessment["satisfied_factors"]


def test_empty_audit_and_ambiguous_contrast():
    assert audit_de().evidence_assessment["evidence_maturity"] == "UNASSESSED"
    with pytest.raises(ValueError, match="both case and reference"):
        audit_de(case="T")


def test_sample_ids_do_not_replace_biological_donors_or_establish_cell_depth():
    samples = pd.DataFrame({
        "patient_id": ["p1", "p2", "p3"] * 2, "sample": list("abcdef"),
        "condition": ["A"] * 3 + ["B"] * 3, "cell_type": "T",
    })
    result = audit_de(sample_metadata=samples, declared_factors=["replication"])
    assert result.metadata_columns_used["donor"] == "patient_id"
    assert result.cohort_summary["n_donors"] == 3
    assert set(result.cohort_summary["replicate_strata"][0]["design"]["paired_donors"]) == {"p1", "p2", "p3"}
    assert "replication" in result.evidence_assessment["unverified_factors"]
