"""
BioNexus Agent Behavior & Scientific Epistemic Benchmark Runner (BioNexus Eval 2.0).

Executes multi-tier benchmark suites:
- L1: Router & Precondition Contract Regression
- L2: Host-Agent Prohibited Claims & Anti-Hallucination
- L3: Scientific Biological Outcome & Planted Truth Recovery
"""

from __future__ import annotations

import os
import sys
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
    compute_epistemic_calibration,
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
    exclude: Optional[List[str]] = None,
) -> List[EvalCase]:
    """Load benchmark cases from YAML files across L1, L2, and L3.

    ``exclude`` lists dataset file stems to omit (e.g. ``flagship_validation``
    when the real external datasets are not present in the environment); the
    omission is always disclosed in the report, never silently.
    """
    d_dir = datasets_dir or get_default_datasets_dir()
    if not d_dir.exists():
        raise FileNotFoundError(f"Datasets directory not found: {d_dir}")

    excluded_stems = {Path(x).stem for x in (exclude or [])}
    cases: List[EvalCase] = []
    yaml_files = [d_dir / f"{suite}.yaml"] if suite and suite != "all" else sorted(d_dir.glob("*.yaml"))

    for yf in yaml_files:
        if not yf.is_file():
            continue
        if yf.stem in excluded_stems:
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
                        expected_maturity=item.get("expected_maturity"),
                        expected_violations=item.get("expected_violations", []),
                        prohibited_claims=item.get("prohibited_claims", []),
                        required_remedies=item.get("required_remedies", []),
                        simulated_agent_response=item.get("simulated_agent_response"),
                        data_metadata=item.get("data_metadata", {}),
                        allow_degraded=item.get("allow_degraded", False),
                        allow_frontier=item.get("allow_frontier", False),
                        description=item.get("description", ""),
                        known_limitation=bool(item.get("known_limitation", False)),
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
    result_provider: Optional[str] = None

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
        result_provider = host_resp.provider
        claim_res = host_resp.audit_result or audit_prohibited_claims(
            host_resp.response_text,
            capability_id=case.expected_capability,
            custom_prohibited_patterns=case.prohibited_claims,
        )
        claim_violations = [v.__dict__ for v in claim_res.violations]

        # Honest maturity attribution for claim audits: a clean claim audit
        # warrants at most PRELIMINARY (it verifies absence of overclaim,
        # not presence of statistical support); detected violations ABSTAIN.
        actual_maturity = "ABSTAIN" if not claim_res.passed else "PRELIMINARY"

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

        if case.data_metadata.get("flagship_suite"):
            # 0. Flagship external-validation track (BNS-015 real-data): runs on
            # real public datasets under data/flagship/, never on synthetic
            # planted-signal fixtures. Absent dataset => honest skip (BNS-EM-009).
            try:
                from evals.flagship_validation import run_flagship_case

                fres = run_flagship_case(case)
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                # A missing scientific backend is never a verified outcome
                # (BNS-EM-009): honest skip, same policy as other L3 tracks.
                fres = _l3_backend_unavailable(exc)
            except Exception as e:
                fres = {
                    "actual_status": "EXECUTION_FAILURE",
                    "actual_maturity": "ABSTAIN",
                    "failure_reasons": [f"Flagship suite crash: {type(e).__name__}: {e}"],
                    "skipped": False,
                    "skip_reason": None,
                }
            actual_status = fres["actual_status"]
            actual_maturity = fres.get("actual_maturity") or "UNASSESSED"
            failure_reasons.extend(fres.get("failure_reasons", []))
            if fres.get("skipped"):
                skipped = True
                skip_reason = fres.get("skip_reason")
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"

        elif signal_type == "scrna_markers":
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
                if len(failure_reasons) == 0:
                    actual_status = "PERMITTED"
                    actual_maturity = "SUPPORTED"
                else:
                    actual_status = "OUTCOME_MISMATCH"
                    actual_maturity = "FRAGILE"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                actual_maturity = "ABSTAIN"
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
                if len(failure_reasons) == 0:
                    actual_status = "PERMITTED"
                    actual_maturity = "SUPPORTED"
                else:
                    actual_status = "OUTCOME_MISMATCH"
                    actual_maturity = "FRAGILE"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                actual_maturity = "ABSTAIN"
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
                if len(failure_reasons) == 0:
                    actual_status = "PERMITTED"
                    actual_maturity = "SUPPORTED"
                else:
                    actual_status = "OUTCOME_MISMATCH"
                    actual_maturity = "FRAGILE"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                actual_maturity = "ABSTAIN"
                failure_reasons.append(f"L3 Pipeline Execution Crash: {type(e).__name__}: {str(e)}")

        elif signal_type == "pseudobulk_de_stability":
            # 3b. Declared parameter perturbation audit for the DE model:
            # re-run PyDESeq2 across a leave-one-out sample-composition grid
            # and require the significant-DEG call set to stay stable
            # (pairwise Jaccard, audited by audit_parameter_stability).
            try:
                import numpy as np
                import pandas as pd
                from scrna_deseq import run_pydeseq2

                rng = np.random.default_rng(1)
                genes = [f"g{i}" for i in range(20)]
                samples = [f"s{i}" for i in range(8)]
                cond = ["A"] * 4 + ["B"] * 4
                mat = rng.poisson(20, size=(8, 20)).astype(int)
                mat[4:, 0] += 80  # g0 is the true planted condition DEG
                counts_full = pd.DataFrame(mat, index=samples, columns=genes)

                drop_samples = case.data_metadata.get("drop_samples", ["s0", "s4"])
                grids = [list(samples)]
                for drop in drop_samples:
                    grids.append([s for s in samples if s != drop])

                sig_sets = []
                for grid in grids:
                    sub_counts = counts_full.loc[grid]
                    sub_design = pd.DataFrame(
                        {"sample_id": grid, "condition": [cond[samples.index(s)] for s in grid]}
                    )
                    table, _contract = run_pydeseq2(
                        sub_counts, sub_design, condition="condition", reference="A", contrast_level="B"
                    )
                    sig = table[table["padj"] < 0.05]["gene"].astype(str).tolist()
                    sig_sets.append(sig)

                target = case.data_metadata.get("target_stability_min", 0.80)
                grade, _notes, stats = audit_parameter_stability(
                    sig_sets, metric="jaccard", tolerance_threshold=target
                )
                mean_jaccard = stats.get("mean_similarity", 0.0)
                if mean_jaccard < target:
                    failure_reasons.append(
                        f"L3 Failure: Pseudobulk DE stability Jaccard {mean_jaccard:.3f} < target {target:.3f} "
                        f"across {len(grids)} composition grids (grade {grade})"
                    )
                if len(failure_reasons) == 0:
                    actual_status = "PERMITTED"
                    actual_maturity = "SUPPORTED"
                else:
                    actual_status = "OUTCOME_MISMATCH"
                    actual_maturity = "FRAGILE"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                actual_maturity = "ABSTAIN"
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
                if len(failure_reasons) == 0:
                    actual_status = "PERMITTED"
                    actual_maturity = "SUPPORTED"
                else:
                    actual_status = "OUTCOME_MISMATCH"
                    actual_maturity = "FRAGILE"
            except (ImportError, ModuleNotFoundError, BackendUnavailable) as exc:
                skip = _l3_backend_unavailable(exc)
                actual_status = skip["actual_status"]
                skipped = skip["skipped"]
                skip_reason = skip["skip_reason"]
                actual_maturity = "NOT_EVALUATED_NO_BACKEND"
            except Exception as e:
                actual_status = "EXECUTION_FAILURE"
                actual_maturity = "ABSTAIN"
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
        # Optional deterministic backend-absence simulation (eval category
        # backend_failure): the case forces a named backend to probe as
        # missing so degradation behavior is auditable even on hosts where
        # the package is installed (BNS-EF-007).
        simulated_missing = case.data_metadata.get("simulate_missing_backend")
        _caps_module = None
        _real_probe = None
        if simulated_missing:
            from bionexus import backends as _backends
            from bionexus import capabilities as _caps_module

            _real_probe = _caps_module.probe

            def _simulated_probe(name, *args, **kwargs):
                if name == simulated_missing:
                    return _backends.BackendStatus(
                        name=name,
                        available=False,
                        import_name=name,
                        extra=None,
                        note=f"simulated absence for eval case {case.id}",
                    )
                return _real_probe(name, *args, **kwargs)

            _caps_module.probe = _simulated_probe
        try:
            decision = route_scientific_intent(
                query=case.prompt,
                data_metadata=case.data_metadata,
                allow_degraded=case.allow_degraded,
                allow_frontier=case.allow_frontier,
            )
        finally:
            if simulated_missing and _caps_module is not None and _real_probe is not None:
                _caps_module.probe = _real_probe
        actual_status = decision.status.value
        actual_cap = decision.matched_capability.id if decision.matched_capability else None

        # Determine inferred conclusion maturity from routing decision
        if decision.status == RoutingStatus.ABSTAIN:
            actual_maturity = "ABSTAIN"
        elif decision.status == RoutingStatus.EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN:
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

        # 4. ABI Statistical-Warrant Audit (BNS-CC-013 / BNS-CC-009 / BN-F005)
        # The case plants a host-asserted maturity claim; the ABI clamp must
        # reduce it to the capability's warranted ceiling, and a missing FDR
        # correction on a multiple-testing-required capability caps the
        # warrant at PRELIMINARY (enforce_statistical_warrant).
        claimed_maturity = case.data_metadata.get("claimed_maturity")
        if claimed_maturity and actual_cap:
            from bionexus.abi import enforce_statistical_warrant

            clamped = enforce_statistical_warrant(
                actual_cap,
                str(claimed_maturity).upper(),
                has_external_validation=bool(case.data_metadata.get("external_validation", False)),
                has_fdr_correction=case.data_metadata.get("multiple_testing_correction"),
                min_replicates_per_condition=case.data_metadata.get("min_replicates_per_condition"),
            )
            actual_maturity = clamped
            if case.expected_maturity and clamped.upper() != str(case.expected_maturity).upper():
                failure_reasons.append(
                    f"Evidence ceiling mismatch: claimed {claimed_maturity}, "
                    f"ABI-clamped to {clamped}, expected {case.expected_maturity}"
                )

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
        known_limitation=case.known_limitation,
        provider=result_provider,
    )


def run_benchmark(
    suite: Optional[str] = None,
    level: Optional[str] = None,
    datasets_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    strict: Optional[bool] = None,
    exclude: Optional[List[str]] = None,
) -> BenchmarkReport:
    strict_mode = _strict_mode_enabled(strict)
    cases = load_eval_cases(suite=suite, level=level, datasets_dir=datasets_dir, exclude=exclude)
    results = [run_single_case(c, provider=provider, model=model) for c in cases]

    if strict_mode:
        for r in results:
            if r.skipped:
                r.failure_reasons.append(
                    "[STRICT MODE] Backend-unavailable skip treated as FAILURE: "
                    "this environment claims an L3 outcome score without the required backend."
                )

    from evals.metrics import compute_cross_host_consistency, compute_frontier_metrics

    gating_results = [r for r in results if not r.known_limitation]
    frontier = [r for r in results if r.known_limitation]

    calib = compute_epistemic_calibration(gating_results)
    metrics = compute_benchmark_metrics(gating_results)
    cross_host = compute_cross_host_consistency(results)
    metrics["cross_host_consistency"] = (
        cross_host["agreement_rate"] if cross_host.get("evaluated") and cross_host.get("agreement_rate") is not None else -1.0
    )
    categories = compute_category_breakdown(gating_results)
    level_scores = compute_level_breakdown(gating_results)
    total = len(gating_results)
    passed = sum(1 for r in gating_results if r.passed)
    skipped_count = sum(1 for r in gating_results if r.skipped)
    if strict_mode:
        failed = total - passed
        attempted = total
    else:
        failed = sum(1 for r in gating_results if (not r.passed) and (not r.skipped))
        attempted = total - skipped_count
    accuracy = (passed / attempted) if attempted > 0 else 0.0

    frontier_metrics = compute_frontier_metrics(frontier)
    frontier_metrics["cross_host_consistency"] = cross_host

    union_calib = compute_epistemic_calibration(results)
    frontier_metrics["union_calibration"] = union_calib.to_dict()
    union_total = len(results)
    union_passed = sum(1 for r in results if r.passed)
    union_skipped = sum(1 for r in results if r.skipped)
    union_attempted = union_total if strict_mode else (union_total - union_skipped)
    union_accuracy = (union_passed / union_attempted) if union_attempted > 0 else 0.0

    prov = (provider or os.getenv("BIONEXUS_EVAL_PROVIDER", "replay")).lower()
    mod = model or ("gpt-4o-mini" if prov == "openai" else ("claude-3-5-sonnet" if prov == "anthropic" else "simulated_trace_v1"))
    is_live = prov in ("openai", "anthropic", "gemini")

    report = BenchmarkReport(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        overall_accuracy=accuracy,
        level_scores=level_scores,
        metrics=metrics,
        category_scores=categories,
        detailed_results=gating_results,
        timestamp=datetime.now(timezone.utc).isoformat(),
        calibration=calib.to_dict(),
        provider=prov,
        model=mod,
        is_live=is_live,
        skipped_cases=skipped_count,
        strict_mode=strict_mode,
        frontier_results=frontier,
        frontier_metrics=frontier_metrics,
        frontier_calibration=frontier_metrics.get("calibration"),
        union_total=union_total,
        union_passed=union_passed,
        union_accuracy=union_accuracy,
    )

    # Tamper-evident audit receipt (BNS-006 / eval-receipt chain v1): append the
    # run's aggregates, per-case digests, and ABI-manifest digest to the
    # hash-chained log so published accuracy claims stay re-derivable.
    try:
        from bionexus.eval_receipt import append_eval_receipt, audit_enabled
        from bionexus.versions import PLUGIN_VERSION

        if audit_enabled():
            payload = _receipt_payload_from_report(report)
            receipt = append_eval_receipt(
                suite=suite or "all",
                provider=prov,
                model=mod,
                strict_mode=strict_mode,
                gating_summary=payload["gating_summary"],
                frontier_summary=payload["frontier_summary"],
                union_summary=payload["union_summary"],
                case_digests=payload["case_digests"],
                plugin_version=PLUGIN_VERSION,
            )
            report.audit_receipt_hash = receipt.get("event_hash")
    except Exception as exc:  # noqa: BLE001 - audit must never corrupt results
        print(f"[eval-receipt] WARNING: audit receipt not written: {exc}", file=sys.stderr)

    return report


def _receipt_payload_from_report(report: BenchmarkReport) -> Dict[str, Any]:
    from bionexus.eval_receipt import summarize_report_for_receipt

    return summarize_report_for_receipt(report)


def format_benchmark_markdown(report: BenchmarkReport) -> str:
    """Format benchmark report as a structured Multi-Tier Markdown document (BioNexus Eval 2.0)."""
    lines: List[str] = []
    lines.append("# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark")
    lines.append(
        f"**Timestamp**: `{report.timestamp}` | **Gating Cases**: `{report.total_cases}` | "
        f"**Passed**: `{report.passed_cases}` | **Failed**: `{report.failed_cases}` | "
        f"**Skipped (backend unavailable)**: `{getattr(report, 'skipped_cases', 0)}` | "
        f"**Gating Accuracy (attempted)**: `{report.overall_accuracy * 100:.1f}%`"
    )
    if getattr(report, "union_total", 0):
        lines.append(
            f"**Union (gating + frontier)**: `{report.union_total}` cases | **Union Accuracy**: `{report.union_accuracy * 100:.1f}%` (the honest number, BNS-LC-006)"
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
        lines.append("## Epistemic Evidence Maturity Calibration (Gating Track)\n")
        lines.append(
            f"- **Verdict**: `{c.get('verdict', 'CALIBRATED')}` (overconfidence is the dominant failure mode)"
        )
        lines.append(
            f"- **Overconfidence Rate (Epistemic Hubris)**: `{c['overconfidence_rate'] * 100:.1f}%` (Target: 0.0%)"
        )
        lines.append(f"- **Underconfidence Rate (Epistemic Timidity)**: `{c['underconfidence_rate'] * 100:.1f}%`")
        lines.append(
            f"- **Ordinal Calibration Error (OCE)**: `{c['ordinal_calibration_error']:.3f}` (Mean rank distance)"
        )
        lines.append(
            f"- **Adjacent-Rank Error Rate**: `{c.get('adjacent_error_rate', 0.0) * 100:.1f}%` (hardest discrimination: PRELIMINARY vs FRAGILE vs SUPPORTED)"
        )
        lines.append(f"- **Within-One Accuracy**: `{c.get('within_one_accuracy', 1.0) * 100:.1f}%`")
        lines.append(f"- **Brier Calibration Score**: `{c['brier_calibration_score'] * 100:.1f}%`")
        lines.append(f"- **Maturity Macro-F1**: `{c['macro_f1'] * 100:.1f}%`")
        lines.append(
            f"- **Cases Evaluated**: `{c['total_evaluated']}` (calibration claims are only valid over stated case counts, BNS-EM-009)"
        )
        skipped = c.get("skipped_no_backend", 0)
        if skipped:
            lines.append(
                f"- **Skipped (no backend, not executed)**: `{skipped}` — excluded from calibration; unexecuted analyses carry no maturity claim"
            )
        lines.append("")

        # Per-class precision / recall / F1
        per_class = c.get("per_class") or {}
        if per_class:
            lines.append("### Per-Class Maturity Discrimination\n")
            lines.append("| Maturity Class | Support | Precision | Recall | F1 |")
            lines.append("|---|---|---|---|---|")
            for label, stats in per_class.items():
                lines.append(
                    f"| `{label}` | {stats['support']} | `{stats['precision'] * 100:.1f}%` | `{stats['recall'] * 100:.1f}%` | `{stats['f1'] * 100:.1f}%` |"
                )
            lines.append("")

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

    # Frontier (Known Limitation) Track — the honest numbers (BNS-LC-004..006)
    fm = report.frontier_metrics or {}
    if fm.get("total", 0) > 0:
        lines.append("## Frontier Calibration Track (Known Limitations — Honest Reporting)\n")
        lines.append(
            f"- **Frontier Cases**: `{fm['total']}` | **Passed**: `{fm['passed']}` | **Failed**: `{fm['failed']}` | **Pass Rate**: `{fm['pass_rate'] * 100:.1f}%`"
        )
        lines.append(
            f"- **Union Accuracy (gating + frontier)**: `{report.union_passed}/{report.union_total}` = `{report.union_accuracy * 100:.1f}%`"
        )
        lines.append(
            "- Frontier cases probe beyond currently-guaranteed behavior (BNS-LC-004). They are excluded from gating CRI, "
            "reported with honest pass/fail, and graduate into the gating suite once passed deterministically (BNS-LC-005)."
        )
        lines.append(
            "- A gating-only 100% is NOT a calibration claim; calibration claims span the union (BNS-LC-006).\n"
        )
        if fm.get("failed_cases"):
            lines.append("### Open Known Limitations\n")
            for fc in fm["failed_cases"]:
                lines.append(f"- **`{fc['case_id']}`** [{fc['level']}/{fc['category']}]")
                for reason in fc["failure_reasons"]:
                    lines.append(f"  - {reason}")
            lines.append("")
        if fm.get("graduation_eligible"):
            lines.append(
                f"- **Graduation-eligible (passing) frontier cases**: {', '.join(f'`{cid}`' for cid in fm['graduation_eligible'])}\n"
            )

        union_cal = fm.get("union_calibration") or {}
        if union_cal:
            lines.append("### Union Calibration (Gating + Frontier)\n")
            lines.append(f"- **Verdict**: `{union_cal.get('verdict', 'N/A')}`")
            lines.append(
                f"- **Exact Accuracy**: `{union_cal.get('exact_accuracy', 0.0) * 100:.1f}%` | **OCE**: `{union_cal.get('ordinal_calibration_error', 0.0):.3f}` | **Macro-F1**: `{union_cal.get('macro_f1', 0.0) * 100:.1f}%`"
            )
            lines.append(
                f"- **Overconfidence**: `{union_cal.get('overconfidence_rate', 0.0) * 100:.1f}%` | **Underconfidence**: `{union_cal.get('underconfidence_rate', 0.0) * 100:.1f}%`\n"
            )

        cross_host = fm.get("cross_host_consistency") or {}
        lines.append("### Cross-Host Consistency (BNS-HC-007)\n")
        if cross_host.get("evaluated"):
            lines.append(
                f"- **Providers**: {', '.join(cross_host.get('providers', []))} | **Agreement Rate**: `{cross_host.get('agreement_rate', 0.0) * 100:.1f}%` over {cross_host.get('cases_compared', 0)} L2 cases"
            )
        else:
            lines.append(f"- **Not evaluated**: {cross_host.get('note', 'single-host run')}")
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
