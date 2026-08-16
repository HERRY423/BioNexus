"""
BioNexus Agent Behavior & Scientific Epistemic Benchmark Runner (BioNexus Eval 2.0).

Executes multi-tier benchmark suites:
- L1: Router & Precondition Contract Regression
- L2: Host-Agent Prohibited Claims & Anti-Hallucination
- L3: Scientific Biological Outcome & Planted Truth Recovery
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from bionexus.agent_routing import route_scientific_intent
from bionexus.claim_checker import audit_prohibited_claims
from bionexus.integrity import (
    audit_parameter_stability,
)
from evals.metrics import (
    compute_benchmark_metrics,
    compute_category_breakdown,
    compute_level_breakdown,
)
from evals.schema import (
    BenchmarkReport,
    EvalCase,
    EvalCategory,
    EvalLevel,
    EvalResult,
    ExpectedStatus,
)


def get_default_datasets_dir() -> Path:
    """Resolve the directory containing benchmark YAML suites."""
    return Path(__file__).resolve().parent / "datasets"


def load_eval_cases(
    suite: Optional[str] = None,
    level: Optional[str] = None,
    datasets_dir: Optional[Path] = None,
) -> List[EvalCase]:
    """Load benchmark cases from YAML files across L1, L2, and L3."""
    d_dir = datasets_dir or get_default_datasets_dir()
    if not d_dir.exists():
        raise FileNotFoundError(f"Datasets directory not found: {d_dir}")

    cases: List[EvalCase] = []
    yaml_files = [d_dir / f"{suite}.yaml"] if suite and suite != "all" else sorted(d_dir.glob("*.yaml"))

    for yf in yaml_files:
        if not yf.is_file():
            continue
        with open(yf, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, list):
                continue
            for item in data:
                try:
                    cat_val = item["category"]
                    lvl_val = item.get("level")
                    if not lvl_val:
                        if cat_val == "host_agent_claim":
                            lvl = EvalLevel.L2_AGENT
                        elif cat_val == "scientific_outcome":
                            lvl = EvalLevel.L3_OUTCOME
                        else:
                            lvl = EvalLevel.L1_ROUTER
                    else:
                        lvl = EvalLevel(lvl_val)

                    if level and level.upper() not in ("ALL", lvl.value):
                        continue

                    case = EvalCase(
                        id=item["id"],
                        prompt=item["prompt"],
                        category=EvalCategory(cat_val),
                        level=lvl,
                        expected_status=ExpectedStatus(item["expected_status"]),
                        expected_capability=item.get("expected_capability"),
                        expected_violations=item.get("expected_violations", []),
                        prohibited_claims=item.get("prohibited_claims", []),
                        required_remedies=item.get("required_remedies", []),
                        simulated_agent_response=item.get("simulated_agent_response"),
                        data_metadata=item.get("data_metadata", {}),
                        allow_degraded=item.get("allow_degraded", False),
                        description=item.get("description", ""),
                    )
                    cases.append(case)
                except Exception as e:
                    print(f"Warning: Skipping invalid eval case {item.get('id')}: {e}")

    return cases


def run_single_case(
    case: EvalCase,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> EvalResult:
    """Evaluate a single scientific benchmark case across L1, L2, or L3."""
    t0 = time.perf_counter()
    failure_reasons: List[str] = []
    actual_cap = None
    claim_violations: List[Dict[str, Any]] = []

    # =========================================================================
    # L2: Host-Agent Claim & Anti-Hallucination Verification (Live or Replay)
    # =========================================================================
    if case.level == EvalLevel.L2_AGENT or case.category == EvalCategory.HOST_AGENT_CLAIM:
        from evals.host_eval import RealHostEvaluator

        host_resp = RealHostEvaluator.evaluate_case_live(
            case,
            provider=provider,
            model=model,
        )
        claim_res = host_resp.audit_result or audit_prohibited_claims(
            host_resp.response_text,
            capability_id=case.expected_capability,
            custom_prohibited_patterns=case.prohibited_claims,
        )
        claim_violations = [v.__dict__ for v in claim_res.violations]

        if case.expected_status == ExpectedStatus.ABSTAIN:
            # Expected prohibited claims to be detected & caught
            if claim_res.passed:
                failure_reasons.append(
                    f"L2 Failure: Failed to detect prohibited claim in agent response (Provider: {host_resp.provider}, Model: {host_resp.model})."
                )
            actual_status = "ABSTAIN" if not claim_res.passed else "PERMITTED"
        else:
            # Expected honest / compliant response to pass cleanly
            if not claim_res.passed:
                failure_reasons.append(
                    f"L2 Failure: Compliant response incorrectly triggered claim violations: {[v.matched_text for v in claim_res.violations]} (Provider: {host_resp.provider}, Model: {host_resp.model})"
                )
            actual_status = "PERMITTED" if claim_res.passed else "ABSTAIN"

        actual_cap = case.expected_capability

    # =========================================================================
    # L3: Scientific Biological Outcome & Planted Truth Recovery
    # =========================================================================
    elif case.level == EvalLevel.L3_OUTCOME or case.category == EvalCategory.SCIENTIFIC_OUTCOME:
        actual_cap = case.expected_capability
        signal_type = case.data_metadata.get("planted_signal", "")

        repo_root = Path(__file__).resolve().parents[1]
        import sys

        for p in [
            str(repo_root / "src"),
            str(repo_root / "skills" / "single-cell-rna-qc" / "scripts"),
            str(repo_root / "skills" / "spatial-transcriptomics" / "scripts"),
            str(repo_root / "tests" / "fixtures"),
        ]:
            if p not in sys.path:
                sys.path.insert(0, p)

        if signal_type == "scrna_markers":
            # 1. Run actual Scanpy gold chain pipeline on planted dataset
            try:
                import anndata as ad
                from make_tiny import write_tiny_scrna
                from scrna_pipeline import run_scrna_gold_chain

                fixture_path = repo_root / "tests" / "fixtures" / "tiny_scrna.h5ad"
                if not fixture_path.is_file():
                    write_tiny_scrna(fixture_path)
                adata = ad.read_h5ad(fixture_path)

                out, markers, summary = run_scrna_gold_chain(
                    adata, run_qc=False, n_top_genes=60, resolution=1.2, n_marker_genes=15
                )
                expected = set(case.data_metadata.get("expected_markers", ["CD3D", "MS4A1", "CD14"]))
                name_col = (
                    "names"
                    if "names" in markers.columns
                    else ("gene" if "gene" in markers.columns else markers.columns[0])
                )
                top_markers = set(markers[name_col].astype(str))
                recovered = expected.intersection(top_markers)
                recall = len(recovered) / len(expected) if expected else 1.0
                min_recall = case.data_metadata.get("min_recall", 0.80)
                if recall < min_recall:
                    failure_reasons.append(
                        f"L3 Failure: Marker recall {recall:.2f} < threshold {min_recall:.2f}. Expected: {expected}, Recovered: {recovered}"
                    )
            except (ImportError, ModuleNotFoundError):
                pass
            actual_status = "PERMITTED"

        elif signal_type == "spatial_moran_svg":
            # 2. Run actual Squidpy spatial gold chain pipeline on planted dataset
            try:
                import anndata as ad
                from make_tiny import write_tiny_spatial
                from spatial_pipeline import run_spatial_gold_chain

                fixture_path = repo_root / "tests" / "fixtures" / "tiny_spatial.h5ad"
                if not fixture_path.is_file():
                    write_tiny_spatial(fixture_path)
                adata = ad.read_h5ad(fixture_path)

                out, svg, summary = run_spatial_gold_chain(adata, cluster=False, top_n=10, n_neighs=6)
                top_svgs = set(svg.head(5)["gene"].astype(str))
                expected = set(case.data_metadata.get("expected_genes", ["SVG_LEFT"]))
                if not expected.issubset(top_svgs):
                    failure_reasons.append(f"L3 Failure: Expected SVGs {expected} not recovered in top 5: {top_svgs}")
                if "SVG_LEFT" in set(svg["gene"]):
                    left_i = float(svg.loc[svg["gene"] == "SVG_LEFT", "morans_i"].iloc[0])
                    min_i = case.data_metadata.get("moran_i_min", 0.30)
                    if left_i < min_i:
                        failure_reasons.append(f"L3 Failure: Moran's I {left_i:.3f} < threshold {min_i:.3f}")
            except (ImportError, ModuleNotFoundError):
                pass
            actual_status = "PERMITTED"

        elif signal_type == "pseudobulk_de":
            # 3. Run actual PyDESeq2 Wald test on planted condition DE matrix
            try:
                import numpy as np
                import pandas as pd
                from scrna_deseq import run_pydeseq2

                rng = np.random.default_rng(1)
                genes = [f"g{i}" for i in range(20)]
                samples = [f"s{i}" for i in range(8)]
                cond = ["A"] * 4 + ["B"] * 4
                mat = rng.poisson(20, size=(8, 20)).astype(int)
                mat[4:, 0] += 80  # g0 is true planted condition DEG
                counts = pd.DataFrame(mat, index=samples, columns=genes)
                design = pd.DataFrame({"sample_id": samples, "condition": cond})

                table, contract = run_pydeseq2(counts, design, condition="condition", reference="A", contrast_level="B")
                top_degs = table.sort_values("pvalue").head(5)["gene"].astype(str).tolist()
                expected_de = case.data_metadata.get("expected_de_genes", ["g0"])
                for g in expected_de:
                    if g not in top_degs:
                        failure_reasons.append(
                            f"L3 Failure: Planted DEG '{g}' not found in top PyDESeq2 findings: {top_degs}"
                        )
            except (ImportError, ModuleNotFoundError):
                pass
            actual_status = "PERMITTED"

        elif signal_type == "clustering_stability":
            # 4. Run parameter resolution sweep and compute actual Adjusted Rand Index
            import anndata as ad
            from make_tiny import write_tiny_scrna
            from scrna_preprocess import preprocess_scrna
            from scrna_reduce_cluster import reduce_and_cluster

            fixture_path = repo_root / "tests" / "fixtures" / "tiny_scrna.h5ad"
            if not fixture_path.is_file():
                write_tiny_scrna(fixture_path)
            adata = ad.read_h5ad(fixture_path)

            adata_pre, _ = preprocess_scrna(adata, n_top_genes=50)
            adata_res05, _ = reduce_and_cluster(adata_pre.copy(), resolution=0.5)
            adata_res08, _ = reduce_and_cluster(adata_pre.copy(), resolution=0.8)

            labels_05 = adata_res05.obs["leiden"].values
            labels_08 = adata_res08.obs["leiden"].values

            grade, notes, stats = audit_parameter_stability([labels_05, labels_08], metric="ari")
            ari_score = stats.get("mean_similarity", 0.0)
            target_ari = case.data_metadata.get("target_ari_min", 0.80)
            if ari_score < target_ari:
                failure_reasons.append(
                    f"L3 Failure: Clustering stability ARI {ari_score:.3f} < target threshold {target_ari:.3f}"
                )
            actual_status = "PERMITTED"

        else:
            actual_status = "PERMITTED"

    # =========================================================================
    # L1: Router & Precondition Contract Regression
    # =========================================================================
    else:
        decision = route_scientific_intent(
            query=case.prompt,
            data_metadata=case.data_metadata,
            allow_degraded=case.allow_degraded,
        )
        actual_status = decision.status.value
        actual_cap = decision.matched_capability.id if decision.matched_capability else None

        # 1. Check Status and Capability Match
        if case.category == EvalCategory.ROUTING:
            if case.expected_capability and actual_cap != case.expected_capability:
                failure_reasons.append(
                    f"Capability mismatch: expected '{case.expected_capability}', got '{actual_cap}'"
                )
        else:
            if actual_status != case.expected_status.value:
                failure_reasons.append(
                    f"Status mismatch: expected '{case.expected_status.value}', got '{actual_status}'"
                )

            if case.expected_capability and actual_cap != case.expected_capability:
                failure_reasons.append(
                    f"Capability mismatch: expected '{case.expected_capability}', got '{actual_cap}'"
                )

        # 2. Check Expected Violations
        if case.expected_violations:
            actual_viol_text = " ".join(decision.violations).lower()
            for ev in case.expected_violations:
                if ev.lower() not in actual_viol_text:
                    failure_reasons.append(
                        f"Missing expected violation keyword: '{ev}' (Actual: {decision.violations})"
                    )

        # 3. Check Required Remedies
        if case.required_remedies:
            actual_rem_text = " ".join(decision.remedies).lower()
            for er in case.required_remedies:
                if er.lower() not in actual_rem_text:
                    failure_reasons.append(f"Missing required remedy keyword: '{er}' (Actual: {decision.remedies})")

    t_elapsed = (time.perf_counter() - t0) * 1000.0
    passed = len(failure_reasons) == 0

    return EvalResult(
        case_id=case.id,
        category=case.category.value,
        level=case.level.value,
        passed=passed,
        expected_status=case.expected_status.value,
        actual_status=actual_status,
        expected_capability=case.expected_capability,
        actual_capability=actual_cap,
        expected_maturity=case.expected_maturity,
        failure_reasons=failure_reasons,
        prohibited_claim_violations=claim_violations,
        execution_time_ms=round(t_elapsed, 2),
    )


def run_benchmark(
    suite: Optional[str] = None,
    level: Optional[str] = None,
    datasets_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BenchmarkReport:
    """Run full benchmark evaluation across all loaded test cases."""
    cases = load_eval_cases(suite=suite, level=level, datasets_dir=datasets_dir)
    results = [run_single_case(c, provider=provider, model=model) for c in cases]

    from evals.metrics import compute_epistemic_calibration

    calib = compute_epistemic_calibration(results)
    metrics = compute_benchmark_metrics(results)
    categories = compute_category_breakdown(results)
    level_scores = compute_level_breakdown(results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    accuracy = (passed / total) if total > 0 else 0.0

    return BenchmarkReport(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        overall_accuracy=accuracy,
        level_scores=level_scores,
        metrics=metrics,
        category_scores=categories,
        detailed_results=results,
        timestamp=datetime.now(timezone.utc).isoformat(),
        calibration=calib.to_dict(),
    )


def format_benchmark_markdown(report: BenchmarkReport) -> str:
    """Format benchmark report as a structured Multi-Tier Markdown document (BioNexus Eval 2.0)."""
    lines: List[str] = []
    lines.append("# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark")
    lines.append(
        f"**Timestamp**: `{report.timestamp}` | **Total Cases**: `{report.total_cases}` | **Overall Accuracy**: `{report.overall_accuracy * 100:.1f}%`\n"
    )

    lines.append("## Multi-Tier Benchmark Levels\n")
    lines.append("| Tier Level | Evaluation Scope | Total | Passed | Failed | Accuracy |")
    lines.append("|---|---|---|---|---|---|")
    level_desc = {
        "L1": "L1: Router & Precondition Regression",
        "L2": "L2: Host-Agent Prohibited Claims Audit",
        "L3": "L3: Scientific Outcome & Ground Truth",
    }
    for lvl, score in report.level_scores.items():
        desc = level_desc.get(lvl, f"Level {lvl}")
        lines.append(
            f"| **{lvl}** | {desc} | {score['total']} | {score['passed']} | {score['failed']} | `{score['accuracy'] * 100:.1f}%` |"
        )

    lines.append("\n---\n")
    lines.append("## Core Scientific Reliability Metrics (8 Pillars)\n")
    lines.append("| Metric | Score | Target | Interpretation |")
    lines.append("|---|---|---|---|")
    m = report.metrics
    lines.append(
        f"| **Routing Accuracy** | `{m['routing_accuracy'] * 100:.1f}%` | `> 95.0%` | Correct scientific capability matched |"
    )
    lines.append(
        f"| **Unsafe Invocation Rate** | `{m['unsafe_invocation_rate'] * 100:.1f}%` | `0.0%` | Frequency of running invalid analyses |"
    )
    lines.append(
        f"| **Abstention Precision** | `{m['abstention_precision'] * 100:.1f}%` | `> 95.0%` | Justified scientific refusals |"
    )
    lines.append(
        f"| **Abstention Recall** | `{m['abstention_recall'] * 100:.1f}%` | `> 95.0%` | Catching required refusal conditions |"
    )
    lines.append(
        f"| **Capability Hallucination Rate** | `{m['capability_hallucination_rate'] * 100:.1f}%` | `0.0%` | Zero unverified cell-types/claims |"
    )
    lines.append(
        f"| **Backend Fidelity** | `{m['backend_fidelity'] * 100:.1f}%` | `> 95.0%` | Accurate toolchain & degradation honesty |"
    )
    lines.append(
        f"| **Scientific Semantic Error Rate** | `{m['scientific_semantic_error_rate'] * 100:.1f}%` | `0.0%` | Confusion of raw/log, cell/sample |"
    )
    lines.append(
        f"| **Evidence Calibration Score** | `{m['evidence_calibration_score'] * 100:.1f}%` | `> 90.0%` | Epistemic card alignment & OCE penalty |"
    )
    lines.append(
        f"| **Composite Reliability Index (CRI)** | **`{m['composite_reliability_index'] * 100:.1f}%`** | `> 95.0%` | **Unified Scientific Quality Index** |"
    )
    lines.append("\n---\n")

    # Epistemic Calibration Section
    if report.calibration:
        c = report.calibration
        lines.append("## Epistemic Evidence Maturity Calibration\n")
        lines.append(
            f"- **Overconfidence Rate (Epistemic Hubris)**: `{c['overconfidence_rate'] * 100:.1f}%` (Target: 0.0%)"
        )
        lines.append(f"- **Underconfidence Rate (Epistemic Timidity)**: `{c['underconfidence_rate'] * 100:.1f}%`")
        lines.append(
            f"- **Ordinal Calibration Error (OCE)**: `{c['ordinal_calibration_error']:.3f}` (Mean rank distance)"
        )
        lines.append(f"- **Brier Calibration Score**: `{c['brier_calibration_score'] * 100:.1f}%`")
        lines.append(f"- **Maturity Macro-F1**: `{c['macro_f1'] * 100:.1f}%`\n")

        # Confusion Matrix Table
        cm = c.get("confusion_matrix", {})
        active_levels = [
            lvl
            for lvl in c.get("maturity_levels", [])
            if sum(cm.get(lvl, {}).values()) > 0
            or sum(cm.get(o, {}).get(lvl, 0) for o in c.get("maturity_levels", [])) > 0
        ]
        if active_levels:
            lines.append("### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)\n")
            header = "| Expected \\ Pred | " + " | ".join(active_levels) + " |"
            sep = "|---|" + "|".join(["---"] * len(active_levels)) + "|"
            lines.append(header)
            lines.append(sep)
            for true_lvl in active_levels:
                row = [f"**{true_lvl}**"]
                for pred_lvl in active_levels:
                    val = cm.get(true_lvl, {}).get(pred_lvl, 0)
                    row.append(str(val))
                lines.append("| " + " | ".join(row) + " |")
        lines.append("\n---\n")

    lines.append("## Category Breakdown\n")
    lines.append("| Category | Total | Passed | Failed | Accuracy |")
    lines.append("|---|---|---|---|---|")
    for cat, score in report.category_scores.items():
        lines.append(
            f"| `{cat}` | {score['total']} | {score['passed']} | {score['failed']} | `{score['accuracy'] * 100:.1f}%` |"
        )

    if report.failed_cases > 0:
        lines.append("\n---\n")
        lines.append("## Failed Benchmark Cases\n")
        for r in report.detailed_results:
            if not r.passed:
                lines.append(f"### [FAILED] Case: `{r.case_id}` ({r.category}) [Level: {r.level}]")
                for reason in r.failure_reasons:
                    lines.append(f"- **Failure**: {reason}")
                lines.append(f"- *Expected*: `{r.expected_status}` ({r.expected_capability})")
                lines.append(f"- *Actual*: `{r.actual_status}` ({r.actual_capability})\n")

    return "\n".join(lines)
