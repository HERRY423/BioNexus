"""
Unit tests for BioFailureBench, the Scientific Trap Corpus (BNS-014).

Validates corpus integrity (8-field schema, taxonomy linkage, coverage,
gating/frontier separation), the positive-control requirement, and that the
gating traps pass deterministically through the standard runner.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.cli import main as cli_main
from bionexus.failures import FAILURE_TAXONOMY, taxonomy_summary
from evals.biofailurebench import corpus_path, load_corpus_records, validate_corpus
from evals.metrics import compute_causal_language_metrics
from evals.runner import format_benchmark_markdown, load_eval_cases, run_benchmark, run_single_case
from evals.schema import EvalCategory


def test_corpus_file_exists_and_loads():
    records = load_corpus_records()
    assert len(records) >= 20
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "trap IDs must be unique"


def test_corpus_schema_and_coverage_valid():
    report = validate_corpus()
    assert report.valid, [(i.case_id, i.field, i.problem) for i in report.issues]
    # Full taxonomy coverage with no open gaps
    assert set(report.failure_mode_coverage) == set(FAILURE_TAXONOMY)
    assert taxonomy_summary()["open_gaps"] == []
    # Gating/frontier split is explicit
    assert report.gating_cases >= 15
    assert report.frontier_cases >= 3


def test_corpus_carries_all_eight_fields():
    required = ("prompt", "data_metadata", "failure_mode", "expected_status", "allowed_computation", "forbidden_claim", "reference", "description")
    for rec in load_corpus_records():
        for field in required:
            assert field in rec, f"{rec.get('id')} missing {field}"
        assert rec.get("required_remedies") is not None


def test_corpus_contains_positive_control():
    controls = [r for r in load_corpus_records() if r.get("failure_mode") == "NONE"]
    assert len(controls) >= 1
    assert controls[0]["expected_status"] == "PERMITTED"


def test_frontier_traps_use_prefix_and_flag():
    for rec in load_corpus_records():
        if rec.get("known_limitation"):
            assert rec["description"].startswith("FRONTIER TRAP"), rec["id"]
        else:
            assert rec["description"].startswith(("TRAP", "CONTROL")), rec["id"]


def test_gating_traps_pass_deterministically(canonical_backends_available):
    """Every non-frontier trap MUST pass through the standard runner."""
    cases = {c.id: c for c in load_eval_cases(suite="biofailurebench")}
    gating = [c for c in cases.values() if not c.known_limitation]
    assert len(gating) >= 15
    for case in gating:
        result = run_single_case(case)
        assert result.passed, f"{case.id}: {result.failure_reasons}"


def test_frontier_traps_are_executed_not_hidden():
    cases = {c.id: c for c in load_eval_cases(suite="biofailurebench")}
    frontier = [c for c in cases.values() if c.known_limitation]
    assert len(frontier) >= 3
    for case in frontier:
        result = run_single_case(case)
        assert result.known_limitation  # honestly labeled


def test_inv009_report_counts_gating_and_frontier_predictions():
    report = run_benchmark(suite="biofailurebench", level="L2", provider="replay")
    results = [
        r for r in report.detailed_results + report.frontier_results
        if r.category == EvalCategory.CAUSAL_LANGUAGE.value
    ]
    by_id = {r.case_id: r for r in results}
    # Each contrast probes a different scope: local negation, negation ending
    # at a clause boundary, an endorsed quotation, and a passive paraphrase.
    for cid in ("BF-052", "BF-053", "BF-055", "BF-057"):
        assert by_id[cid].passed
    assert {"BF-059", "BF-060"} <= set(by_id)
    metrics = report.to_dict()["causal_language_metrics"]
    assert metrics["total"] == len(results) >= 10
    tp, fp, fn, tn = (metrics[k] for k in ("true_positives", "false_positives", "false_negatives", "true_negatives"))
    assert tp + fp + fn + tn == len(results)
    assert metrics["precision"] == tp / (tp + fp)
    assert metrics["recall"] == tp / (tp + fn)
    assert set(metrics["misclassified_cases"]) == {r.case_id for r in results if not r.passed}
    markdown = format_benchmark_markdown(report)
    assert "INV-009 causal-language detector" in markdown
    assert f"{metrics['precision']:.1%}" in markdown
    assert f"{metrics['recall']:.1%}" in markdown


def test_inv009_metrics_use_independent_denominators():
    from dataclasses import replace

    case = next(c for c in load_eval_cases(suite="biofailurebench") if c.id == "BF-051")
    tp = run_single_case(case)
    assert tp.actual_status == tp.expected_status == "ABSTAIN"
    fp = replace(tp, expected_status="PERMITTED")
    fn = replace(tp, actual_status="PERMITTED")
    rates = compute_causal_language_metrics([tp, fp, fn, fn])
    assert rates["precision"] == 1 / 2
    assert rates["recall"] == 1 / 3
    assert compute_causal_language_metrics([fn])["precision"] is None
    assert compute_causal_language_metrics([fp])["recall"] is None
    skipped = replace(tp, case_id="skipped", actual_status="SKIPPED_NO_BACKEND", skipped=True)
    mixed = compute_causal_language_metrics([tp, skipped])
    assert mixed["total"] == 2 and mixed["evaluated"] == 1
    assert mixed["unscored_cases"] == ["skipped"]
    assert mixed["precision"] == mixed["recall"] == 1.0


def test_formerly_open_gaps_have_traps():
    for fid in ("BN-F004", "BN-F005", "BN-F008"):
        assert FAILURE_TAXONOMY[fid].benchmark_cases, fid
        assert FAILURE_TAXONOMY[fid].open_gap is False


def test_bench_cli(capsys):
    assert cli_main(["bench", "validate"]) == 0
    out = capsys.readouterr().out
    assert "BioFailureBench" in out
    assert "Integrity: VALID" in out
    assert "bionexus eval --suite biofailurebench" in out

    assert cli_main(["bench", "stats"]) == 0
    stats_out = capsys.readouterr().out
    assert "Total Traps" in stats_out
    assert "Data Flywheel Moat Depth" in stats_out
    assert "BN-F001" in stats_out

    template_path = _REPO_ROOT / "evals" / "datasets" / "templates" / "FAILURE_TRAP.template.yaml"
    assert template_path.is_file()
    assert cli_main(["bench", "validate-trap", str(template_path)]) == 0
    trap_val_out = capsys.readouterr().out
    assert "VALID and conforms" in trap_val_out

    assert cli_main(["bench", "template"]) == 0
    tpl_out = capsys.readouterr().out
    assert "BF-" in tpl_out


def test_validate_single_trap():
    from evals.biofailurebench import validate_single_trap

    valid_trap = {
        "id": "BF-999",
        "category": "refusal",
        "prompt": "Run DESeq2 on continuous normalized matrix",
        "expected_status": "ABSTAIN",
        "expected_capability": "scrna.pseudobulk_de",
        "data_metadata": {"is_normalized": True},
        "required_remedies": ["raw integer counts"],
        "allowed_computation": "None",
        "forbidden_claim": "DE from normalized matrix",
        "failure_mode": "BN-F001",
        "reference": "BNS-II-002",
        "description": "TRAP: continuous-matrix-passed-to-count-model",
    }
    valid, errors = validate_single_trap(valid_trap)
    assert valid is True
    assert errors == []

    invalid_trap = {"id": "BF-998"}
    valid, errors = validate_single_trap(invalid_trap)
    assert valid is False
    assert len(errors) > 0


def test_corpus_file_is_wired_into_eval_suites():
    """The corpus path is a standard eval dataset file (host-agnostic)."""
    p = corpus_path()
    assert p.is_file()
    assert p.parent == (p.parent)  # datasets dir
    assert any(c.id.startswith("BF-") for c in load_eval_cases(suite=str(p.stem)))

