"""BN-PB-IV-006: descriptive DE agreement with author-selected proxy labels.

No independent null truth, executed naive comparator, or biological null
calibration is supplied. Simulation utilities are explicitly fixture-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.de_scientific_reliability import (
    DecisionCurveAnalysis,
    evaluate_de_hard_truth_calibration,
)
from bionexus.provenance import capture_execution_provenance
from bionexus.validation_verifier import bind_validation_source_provenance

STUDY_DIR = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-006"
DE_FULL_CSV = REPO_ROOT / "validation" / "pseudobulk" / "evidence" / "bionexus_pseudobulk_full_de.csv"

# Author-selected canonical IFN reference targets; not experimental ground truth.
HARD_TRUTH_IFN_TARGETS: Set[str] = {
    "IFIT1", "IFIT2", "IFIT3", "IFITM1", "IFITM2", "IFITM3",
    "ISG15", "ISG20", "RSAD2", "OAS1", "OAS2", "OAS3", "OASL",
    "MX1", "MX2", "STAT1", "STAT2", "IRF1", "IRF7", "IRF9",
    "IFI6", "IFI16", "IFI27", "IFI35", "IFI44", "IFI44L", "IFIH1",
    "CXCL10", "CXCL9", "CXCL11", "BST2", "XAF1", "USP18",
    "HERC5", "TRIM22", "EPSTI1", "SP110", "SAMD9", "SAMD9L",
}

# Legacy constant name: author-selected putative non-responsive references.
# Housekeeping/lineage names do not establish biological null effects.
CONFIRMED_NULL_GENES: Set[str] = {
    "CD3D", "MS4A1", "CD19", "CD8A", "FCGR3A", "NKG7", "IL7R", "TRAC",
    "WRAP73", "DNAJC11", "VAMP3", "DFFA", "AGTRAP", "CDC42", "HNRNPR",
    "STPG1", "PAFAH2", "GMEB1", "YTHDF2", "TXLNA", "SF3A3", "PPIE",
    "ARF1", "RPS18", "RPS27A", "TUBB4B", "RAB1A", "NDUFA1", "PSMB2", "EIF4A2",
}


def load_real_de_results(csv_path: Path) -> Tuple[List[str], List[float], List[float]]:
    """Read estimable results without turning missing adjusted p-values into nulls."""
    genes, effects, pvalues = [], [], []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not {"gene", "log2FoldChange", "padj"}.issubset(reader.fieldnames or []):
            raise ValueError("DE evidence requires gene, log2FoldChange and padj columns")
        for row in reader:
            gene = (row["gene"] or "").strip()
            raw_p = (row["padj"] or "").strip()
            if not gene or raw_p.casefold() in {"", "nan", "na"}:
                continue  # Missing tests are excluded and counted in the report.
            effect, pvalue = float(row["log2FoldChange"]), float(raw_p)
            if not np.isfinite(effect) or not np.isfinite(pvalue) or not 0 <= pvalue <= 1:
                raise ValueError(f"Invalid finite DE result for {gene}")
            genes.append(gene)
            effects.append(effect)
            pvalues.append(pvalue)
    return genes, effects, pvalues


def simulate_naive_pseudoreplication(
    genes: List[str],
    log2fc_list: List[float],
    audited_padj: List[float],
    seed: int = 42,
) -> List[float]:
    """
    Synthetic fixture only: inject label-dependent significance; this does not run a comparator.
    Cell-level tests (e.g. Wilcoxon on 13,487 cells without donor design) treat single cells
    as independent statistical replicates, causing massive artificial power and 60-80% false
    discovery inflation on non-differential lineage markers.
    """
    rng = np.random.default_rng(seed)
    naive_padj = []
    for g, p_audited in zip(genes, audited_padj):
        if g in HARD_TRUTH_IFN_TARGETS:
            # True positives remain detected
            naive_padj.append(min(p_audited, 1e-15))
        elif g in CONFIRMED_NULL_GENES:
            # Under N=13,487 cell-level pseudoreplication, mild donor variation causes ~75% false discovery
            if rng.random() < 0.75:
                naive_padj.append(float(rng.uniform(1e-12, 0.01)))
            else:
                naive_padj.append(p_audited)
        else:
            # Background genes
            if p_audited < 0.05:
                naive_padj.append(p_audited)
            else:
                if rng.random() < 0.45:
                    naive_padj.append(float(rng.uniform(1e-6, 0.045)))
                else:
                    naive_padj.append(p_audited)
    return naive_padj


def generate_mock_null_pvalues(n_genes: int = 1000, seed: int = 2026) -> List[float]:
    """
    Synthetic Uniform random-number fixture; not a biological null or donor comparison.
    """
    rng = np.random.default_rng(seed)
    # Under the null, p-values follow Uniform(0, 1)
    return list(rng.uniform(0.0, 1.0, size=n_genes))


def run_benchmark(*, write: bool = False, output_path: Optional[Path] = None) -> Dict[str, Any]:
    genes, effects, padj = load_real_de_results(DE_FULL_CSV)
    with DE_FULL_CSV.open(encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    missing_padj = sum((row.get("padj") or "").strip().casefold() in {"", "nan", "na"} for row in source_rows)
    missing_gene = sum(not (row.get("gene") or "").strip() for row in source_rows)
    metrics = evaluate_de_hard_truth_calibration(
        gene_names=genes, padj_values=padj, log2fc_values=effects,
        ground_truth_positives=HARD_TRUTH_IFN_TARGETS,
        ground_truth_negatives=CONFIRMED_NULL_GENES, nominal_fdr=.05, min_abs_log2fc=0,
    )
    provenance = bind_validation_source_provenance(capture_execution_provenance(
        data_source="Existing GSE96583 donor-aware DE result table; no new comparator execution",
        download_date="2026-08-19", repo_root=REPO_ROOT,
        extra_metadata={"study_id": "BN-PB-IV-006", "evidence_kind": "AUTHOR_SELECTED_PROXY_REFERENCE"},
    ), REPO_ROOT)
    report = {
        "schema_version": "bionexus.de-hard-truth-validation-report.v1",
        "study_id": "BN-PB-IV-006", "generated_at": datetime.now(timezone.utc).isoformat(),
        "capability_id": "scrna.pseudobulk_de",
        "evidence_kind": "AUTHOR_SELECTED_PROXY_REFERENCE", "scientific_authorization": "NONE",
        "status": {"run_status": "completed_proxy_reference_analysis", "verdict": "RESEARCH_ONLY",
                   "real_host_certified": False, "independent_ground_truth_satisfied": False},
        "dataset": {"accession": "GEO GSE96583", "evidence_csv": DE_FULL_CSV.relative_to(REPO_ROOT).as_posix(),
                    "n_total_input_rows": len(source_rows), "n_rows_missing_adjusted_pvalue": missing_padj,
                    "n_rows_missing_gene_identifier": missing_gene,
                    "n_total_genes_evaluated": len(genes), "n_reference_genes_matched": metrics.n_tested,
                    "n_reference_genes_unavailable": len((HARD_TRUTH_IFN_TARGETS | CONFIRMED_NULL_GENES) - set(genes)),
                    "missingness_note": "Exclusion reasons may overlap; missing padj never becomes a confirmed negative.",
                    "n_positive_reference_genes": metrics.n_positive_truth,
                    "n_putative_null_reference_genes": metrics.n_negative_truth,
                    "n_confirmed_null_genes": 0, "n_hard_truth_positives": 0},
        "audited_pipeline_performance": metrics.to_dict(),
        "naive_pipeline_performance": {"estimation_status": "NOT_RUN", "empirical_fdr": None,
                                       "reason": "No actual same-input comparator run is available."},
        "decision_curve_analysis": DecisionCurveAnalysis().to_dict(),
        "empirical_null_calibration": {"estimation_status": "NOT_RUN", "empirical_fwer": None,
                                      "null_uniform": None, "reason": "No donor-level biological null experiment was executed."},
        "scientific_conclusions": {
            "empirical_fdr_controlled": None, "scientific_net_benefit_positive": None,
            "max_avoided_false_claims_per_100": None, "null_distribution_uniform": None,
            "scientific_claim_boundary": {
                "supported": ["Descriptive significance agreement with selected IFN and putative-null reference genes."],
                "not_supported": ["Biological null truth", "Procedure-level FDR control", "Measured superiority or laboratory net benefit",
                                  "Independent validation", "Biological null p-value calibration"],
            },
        },
        "provenance": provenance,
    }
    if write:
        destination = output_path or STUDY_DIR / "REPORT.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="deprecated alias for the default read-only mode")
    parser.add_argument("--output", type=Path, help="write a new report; existing files are never replaced")
    args = parser.parse_args()
    report = run_benchmark(write=args.output is not None and not args.no_write, output_path=args.output)
    print(json.dumps({"study_id": report["study_id"], "status": report["status"], "scientific_authorization": "NONE"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
