"""Unit tests for orthogonal-evidence validation (bionexus.validation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))

import scrna_cross_method_audit as cma

from bionexus.contracts import EvidenceCard
from bionexus.validation import (
    apply_cross_method_concordance,
    apply_external_validation,
    external_validation,
    rank_concordance,
)


def _scored(genes: list, scores: list) -> dict:
    return dict(zip(genes, scores))


def _marker_genes(k: int) -> list:
    return [f"g{i:03d}" for i in range(k)]


def test_rank_concordance_perfect_agreement_grades_a():
    genes = _marker_genes(30)
    scores = [float(i) for i in range(30)]
    payload = rank_concordance(_scored(genes, scores), _scored(genes, [s * 2.0 + 1 for s in scores]), top_k=10)
    assert payload["refused"] is False
    audit = payload["audit"]
    assert audit["grade"] == "A"
    assert audit["spearman_rho"] >= 0.99
    assert audit["top_k_jaccard"] == 1.0


def test_rank_concordance_conflict_detected():
    genes = _marker_genes(30)
    scores = [float(i) for i in range(30)]
    payload = rank_concordance(_scored(genes, scores), _scored(genes, list(reversed(scores))), top_k=10)
    audit = payload["audit"]
    assert audit["grade"] == "CONFLICTED"
    assert audit["spearman_rho"] <= -0.99


def test_rank_concordance_degenerate_overlap_refused():
    primary = _scored(_marker_genes(10), [float(i) for i in range(10)])
    orthogonal = _scored([f"other{i}" for i in range(10)], [float(i) for i in range(10)])
    payload = rank_concordance(primary, orthogonal)
    assert payload["refused"] is True
    assert "degenerate overlap" in payload["abstain_reason"]


def test_rank_concordance_ties_do_not_crash():
    genes = _marker_genes(12)
    payload = rank_concordance(_scored(genes, [1.0] * 12), _scored(genes, [2.0] * 12))
    assert payload["refused"] is False  # constant vectors yield rho 0.0 but valid audit


def test_read_scored_table_csv_and_tsv(tmp_path: Path):
    csv_p = tmp_path / "markers.csv"
    csv_p.write_text("names,scores\ng1,0.5\ng2,1.5\n", encoding="utf-8")
    tsv_p = tmp_path / "de.tsv"
    tsv_p.write_text("gene\tlog2FC\ng1\t0.5\ng2\t1.5\n", encoding="utf-8")
    from bionexus.validation import _read_scored_table

    assert _read_scored_table(csv_p) == {"g1": 0.5, "g2": 1.5}
    assert _read_scored_table(tsv_p) == {"g1": 0.5, "g2": 1.5}
    with pytest.raises(FileNotFoundError):
        _read_scored_table(tmp_path / "missing.csv")


def test_external_validation_perfect_recovery_grades_a():
    truth = {f"t{i}" for i in range(10)}
    predicted = set(truth) | {"fp1"}
    payload = external_validation(predicted, truth)
    audit = payload["audit"]
    assert audit["grade"] == "A"
    assert audit["recall"] == 1.0
    assert audit["precision"] == pytest.approx(10 / 11, abs=1e-3)


def test_external_validation_poor_overlap_conflicted():
    payload = external_validation({"a", "b", "c", "d"}, {"x", "y", "z", "w"})
    assert payload["audit"]["grade"] == "CONFLICTED"


def test_external_validation_empty_sets_refused():
    assert external_validation({"a"}, set())["refused"] is True
    assert external_validation(set(), {"a"})["refused"] is True


def test_external_validation_json_truth_with_key(tmp_path: Path):
    truth_file = tmp_path / "truth.json"
    truth_file.write_text(json.dumps({"clinvar_significant": ["BRCA1", "TP53", "PTEN"]}), encoding="utf-8")
    payload = external_validation(["BRCA1", "TP53", "EGFR"], truth_file, truth_key="clinvar_significant")
    audit = payload["audit"]
    assert audit["true_positives"] == 2
    assert audit["recall"] == pytest.approx(2 / 3, abs=1e-3)


def test_apply_dimensions_updates_evidence_card():
    card = EvidenceCard(execution_state="EXECUTED")
    conc = rank_concordance(_scored(_marker_genes(20), [float(i) for i in range(20)]),
                           _scored(_marker_genes(20), [float(i) * 0.5 for i in range(20)]))
    apply_cross_method_concordance(card, conc)
    assert card.cross_method_concordance == "A"
    ext = external_validation({f"t{i}" for i in range(5)}, {f"t{i}" for i in range(5)})
    apply_external_validation(card, ext)
    assert card.external_validation == "A"
    assert "Spearman" in card.details["concordance_notes"]
    assert "Precision" in card.details["validation_notes"]


def test_apply_dimensions_tolerates_refusals():
    card = EvidenceCard(execution_state="EXECUTED")
    apply_cross_method_concordance(card, {"refused": True, "abstain_reason": "degenerate"})
    apply_external_validation(card, {"refused": True, "abstain_reason": "empty"})
    assert card.cross_method_concordance == "UNTESTED"
    assert "degenerate" in card.details["concordance_notes"]


def test_scrna_cross_method_audit_script(tmp_path: Path):
    primary = tmp_path / "markers.csv"
    primary.write_text("names,scores\n" + "\n".join(f"g{i},{i}" for i in range(25)) + "\n", encoding="utf-8")
    # PyDESeq2-style table: smaller pvalue = more significant (lower-is-better).
    orthogonal = tmp_path / "deseq.csv"
    orthogonal.write_text("gene,pvalue\n" + "\n".join(f"g{i},{1e-3 * (25 - i)}" for i in range(25)) + "\n", encoding="utf-8")
    payload = cma.audit_marker_methods(
        primary, orthogonal, top_k=10, orthogonal_lower_is_better=True
    )
    assert payload["refused"] is False
    assert payload["audit"]["grade"] == "A"
    assert payload["inputs"]["orthogonal_lower_is_better"] is True

    # Calling without the direction flag must surface the conflict, not hide it.
    wrong = cma.audit_marker_methods(primary, orthogonal, top_k=10)
    assert wrong["audit"]["grade"] == "CONFLICTED"


def test_l3_dataset_contains_expanded_signals():
    import yaml

    dataset = PROJECT_ROOT / "evals" / "datasets" / "l3_scientific_outcomes.yaml"
    cases = yaml.safe_load(dataset.read_text(encoding="utf-8"))
    signals = {c["data_metadata"]["planted_signal"] for c in cases if c["level"] == "L3"}
    assert {"rank_concordance", "external_validation", "egress_policy", "survival_separation"} <= signals
    assert len(cases) == 8
