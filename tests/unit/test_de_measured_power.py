"""Power inputs follow the audited libraries and the bound model receipt."""
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import sparse
from test_de_claim_conditions import package, seal

from bionexus.de.engine import audit_de


@pytest.fixture
def nb_counts():
    rng = np.random.default_rng(302)
    n_genes = 3000
    means = np.full((11, n_genes), 80.)
    means[5:, :150] *= 4
    libraries = rng.negative_binomial(1 / .16, 1 / (1 + .16 * means))
    genes = [f"G{i}" for i in range(n_genes)]
    conditions = ["A"] * 5 + ["B"] * 6
    donors = [f"{s}{i}" for i, s in enumerate(conditions)]
    # Each donor contributes two cells. Technical splitting must leave the NB
    # dispersion and expected pseudobulk depth unchanged.
    rows = [(d, s, "T") for d, s in zip(donors, conditions) for _ in range(2)]
    cells = np.empty((len(rows), n_genes), dtype=int)
    cells[::2] = libraries // 2
    cells[1::2] = libraries - cells[::2]
    return SimpleNamespace(X=sparse.csr_matrix(cells), obs=pd.DataFrame(rows, columns=["donor", "condition", "cell_type"]),
                           var_names=genes, uns={})


def audit(adata, **kwargs):
    return audit_de(adata=adata, case="B", reference="A", cell_type="T",
                    config={"min_cells_per_donor": 2}, **kwargs)


def test_library_moments_and_depth_are_independent_of_sign_check(nb_counts):
    result = audit(nb_counts)
    expected = result.design_warrants[0]["power"]
    assert expected["dispersion_basis"] == "pseudobulk_moment_mean"
    assert "pseudobulk_moment_mean" in result.to_markdown()
    assert .13 < expected["dispersion"] < .18
    assert expected["n_by_group"] == {"A": 5, "B": 6}
    assert 33 < expected["mean_count_per_cell"] < 48
    assert expected["cells_per_sample"] == 2
    # Even a DE table with entirely disjoint genes must not lose the depth
    # and dispersion measured independently from the count layer.
    unrelated = pd.DataFrame({"gene": ["other"], "log2FoldChange": [1.0], "padj": [.05]})
    second = audit(nb_counts, de_table=unrelated)
    assert second.cohort_summary["lfc_concordance"]["status"] == "NOT_ESTIMABLE"
    assert second.design_warrants[0]["power"] == expected


def test_estimator_excludes_other_cell_types_and_conditions(nb_counts):
    baseline = audit(nb_counts).design_warrants[0]["power"]
    extra = nb_counts.obs.assign(cell_type="other")
    third = nb_counts.obs.assign(condition="other")
    nb_counts.obs = pd.concat([nb_counts.obs, extra, third], ignore_index=True)
    noise = sparse.csr_matrix(np.ones(nb_counts.X.shape, dtype=int))
    nb_counts.X = sparse.vstack([nb_counts.X, noise, noise]).tocsr()
    assert audit(nb_counts).design_warrants[0]["power"] == baseline


def test_low_counts_use_planning_fallback_and_empty_library_is_not_a_donor(nb_counts):
    small = np.ones((len(nb_counts.obs), 10), dtype=int)
    small[:2] = 0
    nb_counts.X = small
    nb_counts.var_names = nb_counts.var_names[:10]
    warrant = audit(nb_counts).design_warrants[0]
    assert warrant["count_inputs"]["design"]["n_donor_condition_units"] == 10
    assert warrant["power"]["dispersion_basis"] == "planning_default"
    assert warrant["power"]["dispersion"] == .16
    assert warrant["power"]["n_by_group"] == {"A": 4, "B": 6}
    assert warrant["power"]["mean_count_per_cell"] == pytest.approx(1)
    assert warrant["count_inputs"]["zero_libraries"] == [{"condition": "A", "donor": "A0"}]


def test_zero_library_batch_bridge_cannot_make_design_estimable(nb_counts):
    # Only donor A0 crossed the otherwise perfectly confounded batches.
    nb_counts.obs["batch"] = nb_counts.obs.condition.copy()
    nb_counts.obs.loc[nb_counts.obs.donor == "A0", "batch"] = "B"
    counts = nb_counts.X.toarray()
    counts[:2] = 0
    nb_counts.X = sparse.csr_matrix(counts)
    warrant = audit(nb_counts).design_warrants[0]
    assert warrant["count_inputs"]["design"]["estimable"] is False
    assert warrant["verdict"]["regime"] == "ABSTAIN_CONFOUNDED"


def test_bound_dispersion_has_precedence_over_within_group_estimate(tmp_path, nb_counts):
    path = tmp_path / "de.csv"
    path.write_text("gene,log2FoldChange,padj\nG1,1.1,.05\n", encoding="utf-8")
    receipt = dict(method="edgeR", statistical_unit="donor", design="~ condition",
                   design_matrix_columns=["Intercept", "condition[T.B]"], fit_status="CONVERGED",
                   n_donors=11, donor_ids=list(nb_counts.obs.donor.unique()),
                   result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), common_dispersion=.23)
    result = audit(nb_counts, de_table=path, execution_record=receipt)
    assert result.design_warrants[0]["power"]["dispersion"] == .23
    assert result.design_warrants[0]["power"]["dispersion_basis"] == "common_dispersion"
    receipt["result_sha256"] = "0" * 64
    unbound = audit(nb_counts, de_table=path, execution_record=receipt)
    assert unbound.design_warrants[0]["power"]["dispersion_basis"] == "pseudobulk_moment_mean"


@pytest.mark.parametrize("column", ["log2FoldChange", "log2_fold_change"])
def test_standard_deseq2_lfc_requires_bound_shrinkage(tmp_path, column):
    root = package.__wrapped__(tmp_path)
    result_path = root / "results.csv"
    table = pd.read_csv(result_path).rename(columns={"log2_fold_change": column})
    table["baseMean"] = 100
    table.to_csv(result_path, index=False)
    contract = seal(root)
    obs = pd.read_csv(root / "metadata.csv")
    obs["cell_type"] = "T"
    adata = SimpleNamespace(obs=obs, X=np.full((len(obs), 1), 100), var_names=["X"], uns={})
    receipt = dict(method="DESeq2", statistical_unit="donor", fit_status="CONVERGED", design="~ condition + batch",
                   design_matrix_columns=["Intercept", "condition[T.disease]", "batch[T.b]"], n_donors=len(obs),
                   donor_ids=obs.donor.tolist(), result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
    def power(record):
        res = audit_de(adata=adata, de_table=result_path, claim_contract=contract, execution_record=record,
                       config={"min_cells_per_donor": 1})
        return res.design_warrants[0]["power"]
    assert power(receipt)["shrunk_log2fc"] is None
    receipt["lfc_shrinkage"] = "apeglm"
    assert power(receipt)["shrunk_log2fc"] == pytest.approx(1.2)
    assert power({**receipt, "lfc_shrinkage": "MLE"})["shrunk_log2fc"] is None
    assert power({**receipt, "result_sha256": "0"*64})["shrunk_log2fc"] is None
    json.dumps(power(receipt), allow_nan=False)
