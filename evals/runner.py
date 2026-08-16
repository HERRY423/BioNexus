"""
BioNexus Agent Behavior & Scientific Epistemic Benchmark Runner (BioNexus Eval 2.0).

Executes multi-tier benchmark suites:
- L1: Router & Precondition Contract Regression
- L2: Host-Agent Prohibited Claims & Anti-Hallucination
- L3: Scientific Biological Outcome & Planted Truth Recovery
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from bionexus.agent_routing import route_scientific_intent
from bionexus.backends import BackendUnavailable
from bionexus.claim_checker import audit_prohibited_claims
from bionexus.integrity import (
    audit_parameter_stability,
)
from bionexus.intent_router import RoutingStatus
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


def _strict_mode_enabled(strict: Optional[bool] = None) -> bool:
    """Resolve strict-mode: explicit argument wins, else BIONEXUS_EVAL_STRICT env var.

    In strict mode a missing backend is a benchmark FAILURE, not a skip. This is
    the mode CI must use when it claims an L3 outcome score.
    """
    if strict is not None:
        return strict
    return os.getenv("BIONEXUS_EVAL_STRICT", "").strip().lower() in ("1", "true", "yes", "on")


def _l3_backend_unavailable(exc: Exception) -> Dict[str, Any]:
    """Mark an L3 case as SKIPPED_NO_BACKEND.

    A missing backend must NEVER be recorded as PERMITTED: an unexecuted
    pipeline has no verified outcome. Non-strict runs report the case in a
    dedicated `skipped` bucket (excluded from accuracy); strict runs promote
    the skip to a failure so the exit code blocks unverified score claims.
    """
    reason = (
        f"L3 backend unavailable ({type(exc).__name__}: {exc}). "
        "Planted-truth outcome NOT verified in this environment."
    )
    return {"actual_status": "SKIPPED_NO_BACKEND", "skipped": True, "skip_reason": reason}


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
    actual_status = "PERMITTED"
    actual_maturity = case.expected_maturity or "UNASSESSED"
    claim_violations: List[Dict[str, Any]] = []
    skipped = False
    skip_reason: Optional[str] = None

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
                if markers is None or len(markers) == 0:
                    failure_reasons.append("L3 Failure: Scanpy marker calling produced empty markers dataframe.")
                else:
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
                actual_status = "PERMITTED" if len(failure_reasons) == 0 else "OUTCOME_MISMATCH"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                failure_reasons.append(f"L3 Pipeline Execution Crash: {type(e).__name__}: {str(e)}")

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
                if svg is None or len(svg) == 0:
                    failure_reasons.append("L3 Failure: Squidpy spatial pipeline produced empty SVG table.")
                else:
                    top_svgs = set(svg.head(5)["gene"].astype(str))
                    expected = set(case.data_metadata.get("expected_genes", ["SVG_LEFT"]))
                    if not expected.issubset(top_svgs):
                        failure_reasons.append(f"L3 Failure: Expected SVGs {expected} not recovered in top 5: {top_svgs}")
                    if "SVG_LEFT" in set(svg["gene"]):
                        left_i = float(svg.loc[svg["gene"] == "SVG_LEFT", "morans_i"].iloc[0])
                        min_i = case.data_metadata.get("moran_i_min", 0.30)
                        if left_i < min_i:
                            failure_reasons.append(f"L3 Failure: Moran's I {left_i:.3f} < threshold {min_i:.3f}")
                actual_status = "PERMITTED" if len(failure_reasons) == 0 else "OUTCOME_MISMATCH"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                failure_reasons.append(f"L3 Pipeline Execution Crash: {type(e).__name__}: {str(e)}")

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
                if table is None or len(table) == 0:
                    failure_reasons.append("L3 Failure: PyDESeq2 Wald test produced empty results table.")
                else:
                    top_degs = table.sort_values("pvalue").head(5)["gene"].astype(str).tolist()
                    expected_de = case.data_metadata.get("expected_de_genes", ["g0"])
                    for g in expected_de:
                        if g not in top_degs:
                            failure_reasons.append(
                                f"L3 Failure: Planted DEG '{g}' not found in top PyDESeq2 findings: {top_degs}"
                            )
                actual_status = "PERMITTED" if len(failure_reasons) == 0 else "OUTCOME_MISMATCH"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                failure_reasons.append(f"L3 Pipeline Execution Crash: {type(e).__name__}: {str(e)}")

        elif signal_type == "clustering_stability":
            # 4. Run parameter resolution sweep and compute actual Adjusted Rand Index
            try:
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

                key_05 = "leiden" if "leiden" in adata_res05.obs else "cluster"
                key_08 = "leiden" if "leiden" in adata_res08.obs else "cluster"
                labels_05 = adata_res05.obs[key_05].values
                labels_08 = adata_res08.obs[key_08].values

                grade, notes, stats = audit_parameter_stability([labels_05, labels_08], metric="ari")
                ari_score = stats.get("mean_similarity", 0.0)
                target_ari = case.data_metadata.get("target_ari_min", 0.80)
                if ari_score < target_ari:
                    failure_reasons.append(
                        f"L3 Failure: Clustering stability ARI {ari_score:.3f} < target threshold {target_ari:.3f}"
                    )
                actual_status = "PERMITTED" if len(failure_reasons) == 0 else "OUTCOME_MISMATCH"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                failure_reasons.append(f"L3 Pipeline Execution Crash: {type(e).__name__}: {str(e)}")

        else:
            # Unknown planted_signal must fail loudly: an unverified outcome can
            # never auto-pass, otherwise dataset typos would inflate the score.
            actual_status = "OUTCOME_MISMATCH"
            failure_reasons.append(
                f"L3 Failure: Unknown planted_signal '{signal_type}' has no verifier. Case cannot auto-pass."
            )

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

        # Determine inferred conclusion maturity from routing decision
        if decision.status == RoutingStatus.ABSTAIN:
            actual_maturity = "ABSTAIN"
        elif decision.status == RoutingStatus.PERMITTED:
            actual_maturity = (
                decision.evidence_card_template.synthesize_status()
                if decision.evidence_card_template
                else "UNASSESSED"
            )
        elif decision.status == RoutingStatus.DEGRADED_ADVISORY:
            actual_maturity = "FRAGILE"
        else:
            actual_maturity = "UNASSESSED"

        # 1. Check Status & Capability Matches
        if actual_status != case.expected_status.value:
            failure_reasons.append(
                f"Status mismatch: Expected {case.expected_status.value}, got {actual_status} (Rationale: {decision.rationale})"
            )

        if case.expected_capability and actual_cap != case.expected_capability:
            failure_reasons.append(
                f"Capability mismatch: Expected '{case.expected_capability}', got '{actual_cap}'"
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
    # A skipped case is never "passed": unexecuted pipelines have no verified
    # outcome. Strict-mode promotion to failure happens in run_benchmark so the
    # aggregate accounting (failed_cases / exit code) stays in one place.
    passed = (not skipped) and (len(failure_reasons) == 0)

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
        actual_maturity=actual_maturity,
        failure_reasons=failure_reasons,
        prohibited_claim_violations=claim_violations,
        execution_time_ms=round(t_elapsed, 2),
        skipped=skipped,
        skip_reason=skip_reason,
    )


def run_benchmark(
    suite: Optional[str] = None,
    level: Optional[str] = None,
    datasets_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    strict: Optional[bool] = None,
) -> BenchmarkReport:
    """Run full benchmark evaluation across all loaded test cases.

    Accounting rules (fail-closed):
    - A skipped case (SKIPPED_NO_BACKEND) never counts as passed.
    - Non-strict mode: skips are excluded from the accuracy denominator and
      reported separately, so the headline makes verification gaps visible.
    - Strict mode (``strict=True`` or BIONEXUS_EVAL_STRICT=1): skips are
      promoted to failures, the accuracy denominator includes them, and the
      CLI exit code becomes non-zero. CI legs that claim an L3 score must run
      in this mode.
    """
    strict_mode = _strict_mode_enabled(strict)
    cases = load_eval_cases(suite=suite, level=level, datasets_dir=datasets_dir)
    results = [run_single_case(c, provider=provider, model=model) for c in cases]

    if strict_mode:
        for r in results:
            if r.skipped:
                r.failure_reasons.append(
                    "[STRICT MODE] Backend-unavailable skip treated as FAILURE: "
                    "this environment claims an L3 outcome score without the required backend."
                )

    from evals.metrics import compute_epistemic_calibration

    calib = compute_epistemic_calibration(results)
    metrics = compute_benchmark_metrics(results)
    categories = compute_category_breakdown(results)
    level_scores = compute_level_breakdown(results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    skipped_count = sum(1 for r in results if r.skipped)
    if strict_mode:
        failed = total - passed
        attempted = total
    else:
        failed = sum(1 for r in results if (not r.passed) and (not r.skipped))
        attempted = total - skipped_count
    accuracy = (passed / attempted) if attempted > 0 else 0.0

    prov = (provider or os.getenv("BIONEXUS_EVAL_PROVIDER", "replay")).lower()
    mod = model or ("gpt-4o-mini" if prov == "openai" else ("claude-3-5-sonnet" if prov == "anthropic" else "simulated_trace_v1"))
    is_live = prov in ("openai", "anthropic", "gemini")

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
        provider=prov,
        model=mod,
        is_live=is_live,
        skipped_cases=skipped_count,
        strict_mode=strict_mode,
    )


def format_benchmark_markdown(report: BenchmarkReport) -> str:
    """Format benchmark report as a structured Multi-Tier Markdown document (BioNexus Eval 2.0)."""
    lines: List[str] = []
    lines.append("# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark")
    lines.append(
        f"**Timestamp**: `{report.timestamp}` | **Total Cases**: `{report.total_cases}` | "
        f"**Passed**: `{report.passed_cases}` | **Failed**: `{report.failed_cases}` | "
        f"**Skipped (backend unavailable)**: `{getattr(report, 'skipped_cases', 0)}` | "
        f"**Overall Accuracy (attempted)**: `{report.overall_accuracy * 100:.1f}%`"
    )
    exec_mode = "LIVE HOST LLM GENERATION" if getattr(report, "is_live", False) else "OFFLINE TRACE REPLAY"
    lines.append(
        f"**Execution Mode**: `{exec_mode}` | **Host Provider**: `{getattr(report, 'provider', 'replay')}` | "
        f"**Model**: `{getattr(report, 'model', 'simulated_trace_v1')}` | "
        f"**Strict Mode**: `{'ON' if getattr(report, 'strict_mode', False) else 'OFF'}`\n"
    )

    if not getattr(report, "is_live", False):
        lines.append(
            "> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* "
            "(`simulated_agent_response`) texts authored in the same YAML as the expectations — they are "
            "regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. "
            "Use `--provider openai|anthropic|gemini` for live host evaluation.\n"
        )

    skipped_total = getattr(report, "skipped_cases", 0)
    if skipped_total > 0:
        lines.append(
            f"> ⚠️ **VERIFICATION GAP**: {skipped_total} case(s) SKIPPED_NO_BACKEND — the required "
            "scientific backend was not installed, so those planted-truth outcomes were **NOT verified** "
            "in this environment. They are excluded from the accuracy denominator and must not be "
            "reported as passing. Re-run with full backends "
            "(`pip install -e \".[goldchain,spatial]\"`) or with `BIONEXUS_EVAL_STRICT=1` to enforce.\n"
        )

    lines.append("## Multi-Tier Benchmark Levels\n")
    lines.append("| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |")
    lines.append("|---|---|---|---|---|---|---|")
    level_desc = {
        "L1": "L1: Router & Precondition Regression",
        "L2": "L2: Host-Agent Prohibited Claims Audit",
        "L3": "L3: Scientific Outcome & Ground Truth",
    }
    for lvl, score in report.level_scores.items():
        desc = level_desc.get(lvl, f"Level {lvl}")
        lines.append(
            f"| **{lvl}** | {desc} | {score['total']} | {score['passed']} | {score['failed']} | "
            f"{score.get('skipped', 0)} | `{score['accuracy'] * 100:.1f}%` |"
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
    lines.append("| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |")
    lines.append("|---|---|---|---|---|---|")
    for cat, score in report.category_scores.items():
        lines.append(
            f"| `{cat}` | {score['total']} | {score['passed']} | {score['failed']} | "
            f"{score.get('skipped', 0)} | `{score['accuracy'] * 100:.1f}%` |"
        )

    if report.failed_cases > 0:
        lines.append("\n---\n")
        lines.append("## Failed Benchmark Cases\n")
        for r in report.detailed_results:
            if not r.passed and not r.skipped:
                lines.append(f"### [FAILED] Case: `{r.case_id}` ({r.category}) [Level: {r.level}]")
                for reason in r.failure_reasons:
                    lines.append(f"- **Failure**: {reason}")
                lines.append(f"- *Expected*: `{r.expected_status}` ({r.expected_capability})")
                lines.append(f"- *Actual*: `{r.actual_status}` ({r.actual_capability})\n")

    skipped_results = [r for r in report.detailed_results if r.skipped]
    if skipped_results:
        lines.append("\n---\n")
        lines.append("## Skipped Benchmark Cases (Backend Unavailable — NOT Verified)\n")
        for r in skipped_results:
            lines.append(f"### [SKIPPED_NO_BACKEND] Case: `{r.case_id}` ({r.category}) [Level: {r.level}]")
            lines.append(f"- **Skip reason**: {r.skip_reason or 'backend unavailable'}")
            if getattr(report, "strict_mode", False):
                lines.append("- **Strict mode**: promoted to FAILURE (see exit code).")
            lines.append(f"- *Expected*: `{r.expected_status}` ({r.expected_capability})\n")

    return "\n".join(lines)
