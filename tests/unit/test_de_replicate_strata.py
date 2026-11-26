"""Observed biological replication and batch assignment in the requested comparison."""
import pandas as pd
import pytest

from bionexus.de.engine import DEAuditEngine
from bionexus.de.models import CheckStatus, FindingSeverity


def cells(*groups):
    rows = [(kind, condition, donor, batch)
            for kind, condition, donor, batch, size in groups
            for _ in range(size)]
    return pd.DataFrame(rows, columns=["cell_type", "condition", "donor", "batch"])


def test_observed_cell_type_condition_counts_use_eligible_donors():
    frame = cells(*[(kind, condition, condition + str(i), "b1", 5 if (kind, condition, i) == ("B", "A", 2) else 20)
                    for kind in ("T", "B") for condition in ("A", "Z") for i in range(3)])
    frame["condition"] = pd.Categorical(frame.condition, categories=["A", "Z", "unused"])
    frame["cell_type"] = pd.Categorical(frame.cell_type, categories=["B", "T", "unused"])
    report = DEAuditEngine().audit(sample_metadata=frame)
    hits = [f for f in report.findings if f.rule_id in {"BFA-001", "BFA-001b"}]
    assert len(hits) == 1
    assert hits[0].rule_id == "BFA-001b"
    assert hits[0].evidence_data["cell_type"] == "B"
    assert hits[0].evidence_data["donors_by_condition"] == {"A": 2, "Z": 3}
    assert hits[0].evidence_data["excluded_donors"] == [{"condition": "A", "donor": "A2", "cells": 5}]
    assert hits[0].evidence_data["min_cells_per_eligible_sample"] == 20
    assert len(report.cohort_summary["replicate_strata"]) == 2
    assert not any(f.rule_id == "BFA-001b" for f in DEAuditEngine(
        {"min_cells_per_donor": 5}).audit(sample_metadata=frame).findings)


def test_missing_condition_in_observed_cell_type_has_zero_eligible_donors():
    frame = cells(*[(kind, condition, condition + str(i), "b1", 20)
                    for kind in ("T", "B") for condition in ("A", "Z") for i in range(3)
                    if (kind, condition) != ("B", "Z")])
    report = DEAuditEngine().audit(sample_metadata=frame)
    hit = next(f for f in report.findings if f.rule_id == "BFA-001")
    assert hit.evidence_data["donors_by_condition"] == {"A": 3, "Z": 0}


def test_sample_sheet_rows_are_not_treated_as_individual_cells():
    meta = pd.DataFrame({"condition": ["A"] * 3 + ["Z"] * 3, "donor": list("abcdef")})
    report = DEAuditEngine().audit(sample_metadata=meta)
    check = next(c for c in report.checks if c.check_id == "donor_replicates")
    assert "n_cells" not in report.cohort_summary and report.cohort_summary["n_metadata_rows"] == 6
    assert check.status == CheckStatus.ASSESSED and "未按细胞类型分层" in check.summary
    stratum, = report.cohort_summary["replicate_strata"]
    assert stratum["row_unit"] == "sample"
    assert stratum["min_cells_per_eligible_sample"] is None and stratum["min_donors"] == 3
    high = DEAuditEngine({"min_donors_required": 4}).audit(sample_metadata=meta)
    assert any(f.rule_id == "BFA-001b" for f in high.findings)


@pytest.mark.parametrize("batches, severity", [
    (["a"] * 4 + ["b"] * 4, FindingSeverity.BLOCKER),
    (["a"] * 3 + ["b"] * 5, FindingSeverity.ADVISORY),
    (["a", "b"] * 4, None),
])
def test_batch_severity_uses_sample_level_design(batches, severity):
    frame = cells(*[("T", "A" if i < 4 else "B", f"d{i}", batch, 200 if i == 0 else 20)
                    for i, batch in enumerate(batches)])
    result = DEAuditEngine().audit(sample_metadata=frame)
    hits = [f for f in result.findings if f.rule_id == "BFA-004"]
    assert [f.severity for f in hits] == ([] if severity is None else [severity])
    design = result.cohort_summary["replicate_strata"][0]["design"]
    assert design["design_rows"] == 8
    if severity == FindingSeverity.ADVISORY:
        assert design["cramer_v"] == pytest.approx((3 / 5) ** 0.5)
    if severity is None:
        assert design["residual_df"] == 5


def test_dominance_is_reported_within_condition():
    report = DEAuditEngine().audit(sample_metadata=cells(
        ("T", "A", "a1", "b1", 80), ("T", "A", "a2", "b1", 20),
        ("T", "B", "b1", "b1", 50), ("T", "B", "b2", "b1", 50)))
    hit = next(f for f in report.findings if f.rule_id == "BFA-007")
    dominance, = hit.evidence_data["imbalanced_clusters"]
    assert (dominance["condition"], dominance["dominant_donor"], dominance["fraction"]) == ("A", "a1", .8)
    assert "DIRECTION_SENSITIVE" in hit.minimal_fix


def test_reconstructed_paired_design_uses_donor_effects_and_does_not_inflate_df_with_lanes():
    meta = cells(*[("T", condition, donor, batch, 20)
                   for condition in ("A", "B") for donor in ("d1", "d2", "d3") for batch in ("b1", "b2")])
    report = DEAuditEngine().audit(sample_metadata=meta)
    design = report.cohort_summary["replicate_strata"][0]["design"]
    assert sorted(design["paired_donors"]) == ["d1", "d2", "d3"]
    assert design["n_donor_condition_units"] == 6
    assert design["residual_df"] <= 2 < design["design_rows"] - design["rank"]

@pytest.mark.parametrize("metadata", [
    pd.DataFrame({"condition": ["A"] * 3 + ["Z"] * 3, "donor": list("abcdef"),
                  "cell_type": pd.Series([None] * 6, dtype="category")}),
    pd.DataFrame({"condition": pd.Categorical(["A"] * 3, categories=["A", "Z"]),
                  "donor": list("abc"), "cell_type": ["T"] * 3}),
])
def test_absent_strata_and_one_observed_condition_cannot_pass(metadata):
    report = DEAuditEngine().audit(sample_metadata=metadata)
    replicate = next(c for c in report.checks if c.check_id == "donor_replicates")
    assert replicate.required_for_pass and replicate.status == CheckStatus.MISSING_EVIDENCE
    assert not report.passed
    assert "n_cells" not in report.cohort_summary


def test_named_contrast_binds_to_the_eligible_donors_in_the_selected_type():
    meta = cells(*[(kind, group, group + str(i), "run", 1 if (kind, group, i) == ("T", "A", 0) else 20)
                   for kind in ("T", "B") for group in ("A", "M", "Z") for i in range(3)])
    report = DEAuditEngine().audit(sample_metadata=meta, cell_type="T", case="Z", reference="A")
    assert report.cohort_summary["replicate_scope"] == {"cell_type": "T", "case": "Z", "reference": "A"}
    stratum, = report.cohort_summary["replicate_strata"]
    assert stratum["eligible_donors"] == ["A1", "A2", "Z0", "Z1", "Z2"]
