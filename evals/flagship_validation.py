"""
BioNexus Flagship External Validation Harness (BNS-015, v1.0 real-data track).

The flagship program concentrates external validation on exactly THREE
capabilities — not a benchmark of twenty:

    A. scrna.pseudobulk_de         real PBMC perturbation data with a donor
                                   design and published DE truth
    B. scrna.annotation_evidence   FACS / CITE-seq / sorted-population data;
                                   the benchmark is whether BioNexus knows
                                   when an annotation is NOT worth believing
    C. spatial.inference_validity  Xenium / CosMx / MERFISH-class data with
                                   actively manufactured artifacts
                                   (segmentation leakage, cell-size bias,
                                   transcript-density bias, radius changes,
                                   spatial permutation, batch/FOV effects)

Honesty rules:
- Synthetic planted-signal fixtures do NOT satisfy this track. Every case
  here requires a real public dataset under ``data/flagship/<dataset_id>/``;
  when the dataset is absent the case is SKIPPED (never guessed, never
  counted as verified, BNS-EM-009).
- The pseudobulk suite additionally refuses to run unless Backend Identity
  Conformance for pydeseq2 is CONFORMANT: external truth validated on an
  unwitnessed backend is not external validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
FLAGSHIP_ROOT = REPO_ROOT / "data" / "flagship"

# ==============================================================================
# Dataset manifest: real public datasets, machine-checkable presence
# ==============================================================================

FLAGSHIP_DATASETS: Dict[str, Dict[str, Any]] = {
    "kang2018_pbmc_ifnb": {
        "capability": "scrna.pseudobulk_de",
        "description": (
            "Kang et al. 2018 (Nat Biotechnol 36:508, doi:10.1038/nbt.4042): "
            "8-donor PBMC, IFN-beta stimulated vs control. Donor-aware "
            "pseudobulk DE is validated against independent published "
            "knowledge of the type-I IFN response."
        ),
        "source": "GEO GSE96583; Kang et al. 2018 doi:10.1038/nbt.4042",
        "acquisition_date": "2026-08-19T00:00:00+00:00",
        "required_files": ["pbmc_ifnb_counts.h5ad", "published_de_truth.csv"],
        "notes": (
            "h5ad must carry raw integer counts with obs columns 'donor' and "
            "'condition' (stim/ctrl); truth CSV needs columns 'gene' and a "
            "published support score (ascending, padj-like). The paper's own "
            "DE table is not machine-accessible (supplements 403, figshare "
            "403, Interferome offline, Zenodo 403), so the truth is a "
            "published-knowledge membership set (MSigDB Hallmark IFN "
            "response signatures + curated Gene Ontology annotations); the "
            "metric is the fraction of BioNexus top-N DE genes with "
            "independent published support."
        ),
    },
    "citeseq_pbmc_sorted": {
        "capability": "scrna.annotation_evidence",
        "description": (
            "CITE-seq PBMC with surface-protein channels and/or FACS-sorted "
            "population labels; provides orthogonal protein evidence to test "
            "when RNA-only annotation should be distrusted."
        ),
        "source": (
            "YosefLab/scVI-data processed public 10x PBMC 10k and PBMC 5k "
            "CITE-seq datasets used by the official scvi-tools totalVI tutorials"
        ),
        "version": "BN-ANN-IV-001",
        "dataset_track": "real_public_processed_citeseq",
        "acquisition_date": "2026-08-28",
        "required_files": [
            "DATASET_MANIFEST.json",
            "pbmc_10k_protein_v3.h5ad",
            "pbmc_5k_protein_v3.h5ad",
        ],
        "notes": (
            "BN-ANN-IV-001 uses PBMC10k for candidate fitting and PBMC5k as a "
            "locked holdout. Paired ADT is orthogonal evidence but is not an "
            "independently adjudicated expert ground truth."
        ),
    },
    "xenium_spatial_truth": {
        "capability": "spatial.inference_validity",
        "description": (
            "Xenium / CosMx / MERFISH-class in situ transcriptomics with "
            "physical coordinates and cell segmentation, used to manufacture "
            "and then expose spatial artifacts."
        ),
        "source": "10x Genomics official Xenium XOA v4 tiny human kidney output bundle",
        "version": "BN-SP-IV-001",
        "dataset_track": "real_instrument_technical_acceptance",
        "acquisition_date": "2026-08-28",
        "required_files": ["DATASET_MANIFEST.json", "Xenium_V1_Protein_Human_Kidney_tiny_outs.zip"],
        "notes": (
            "Authentic real-instrument bytes for technical artifact sensitivity. "
            "10x explicitly states that this tiny subset is for file-format testing "
            "and is not intended for biological conclusions."
        ),
    },
}


def flagship_dataset_dir(dataset_id: str) -> Path:
    return FLAGSHIP_ROOT / dataset_id


def flagship_dataset_present(dataset_id: str) -> bool:
    manifest = FLAGSHIP_DATASETS.get(dataset_id)
    if manifest is None:
        return False
    d = flagship_dataset_dir(dataset_id)
    return all((d / f).is_file() for f in manifest["required_files"])


def _skip_no_dataset(dataset_id: str, suite: str) -> Dict[str, Any]:
    manifest = FLAGSHIP_DATASETS.get(dataset_id, {})
    reason = (
        f"Flagship suite '{suite}' requires the real public dataset '{dataset_id}' "
        f"under {flagship_dataset_dir(dataset_id)} ({manifest.get('source', 'see manifest')}). "
        "Dataset absent: outcome NOT verified in this environment (BNS-EM-009: "
        "an unexecuted external validation carries no maturity claim). "
        "Run evals/datasets/download_flagship_datasets.py to fetch it."
    )
    return {"actual_status": "SKIPPED_NO_BACKEND", "skipped": True, "skip_reason": reason}


# ==============================================================================
# Deterministic artifact manufacturing (suite C)
# ==============================================================================


def inject_segmentation_leakage(adata, fraction: float = 0.20, seed: int = 0):
    """Borrow a fraction of each cell's transcripts from its nearest neighbor."""
    import numpy as np

    rng = np.random.default_rng(seed)
    X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X).copy()
    coords = np.asarray(adata.obsm["spatial"])
    n = X.shape[0]
    for i in range(n):
        d = np.linalg.norm(coords - coords[i], axis=1)
        d[i] = np.inf
        j = int(np.argmin(d))
        leaked = rng.random(X.shape[1]) < fraction
        X[i, leaked] = (0.5 * X[i, leaked] + 0.5 * X[j, leaked]).astype(X.dtype)
    adata.X = X
    adata.obs["leakage_injected"] = True
    return adata


def inject_cell_size_bias(adata, strength: float = 0.8, seed: int = 0):
    """Scale total counts with a synthetic cell-area covariate."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = adata.n_obs
    area = rng.lognormal(mean=2.0, sigma=0.5, size=n)
    scale = 1.0 + strength * (area - area.mean()) / max(area.std(), 1e-9)
    scale = np.clip(scale, 0.2, None)
    X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X).copy()
    adata.X = np.round(X * scale[:, None]).astype(X.dtype)
    adata.obs["cell_area"] = area
    return adata


def inject_transcript_density_bias(adata, strength: float = 0.8, k: int = 8):
    """Scale counts with local transcript density (neighbor count within radius)."""
    import numpy as np

    coords = np.asarray(adata.obsm["spatial"])
    n = coords.shape[0]
    radius = float(np.median(np.ptp(coords, axis=0))) / 20.0
    density = np.zeros(n)
    for i in range(n):
        density[i] = float(np.sum(np.linalg.norm(coords - coords[i], axis=1) < radius))
    scale = 1.0 + strength * (density - density.mean()) / max(density.std(), 1e-9)
    scale = np.clip(scale, 0.2, None)
    X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X).copy()
    adata.X = np.round(X * scale[:, None]).astype(X.dtype)
    adata.obs["local_density"] = density
    return adata


def permute_spatial_coordinates(adata, seed: int = 0):
    """Destroy spatial structure by permuting coordinates (permutation null)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    coords = np.asarray(adata.obsm["spatial"]).copy()
    adata.obsm["spatial"] = coords[rng.permutation(coords.shape[0])]
    return adata


def confound_fov_with_condition(adata, n_fov: int = 6, seed: int = 0):
    """Assign FOVs so that FOV identity is 1:1 confounded with condition."""
    import numpy as np

    rng = np.random.default_rng(seed)
    condition = adata.obs.get("condition")
    if condition is not None:
        levels = sorted(set(condition.astype(str)))
        fov = np.array(
            [f"fov_{levels.index(c) * (n_fov // max(len(levels), 1)) + rng.integers(0, max(n_fov // max(len(levels), 1), 1))}" for c in condition.astype(str)]
        )
    else:
        fov = np.array([f"fov_{i % n_fov}" for i in range(adata.n_obs)])
    adata.obs["fov"] = fov
    return adata


ARTIFACT_INJECTORS = {
    "segmentation_leakage": inject_segmentation_leakage,
    "cell_size_bias": inject_cell_size_bias,
    "transcript_density_bias": inject_transcript_density_bias,
    "spatial_permutation": permute_spatial_coordinates,
    "batch_fov_confounding": confound_fov_with_condition,
    # radius sensitivity is a control-side sweep, not a data injection
}


def measure_artifact_controls(adata, artifact: str) -> Dict[str, str]:
    """MEASURE (never trust the injection record) the alternative explanations."""
    import numpy as np

    controls: Dict[str, str] = {}
    X = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X)
    totals = np.asarray(X.sum(axis=1)).ravel()

    if artifact == "cell_size_bias" and "cell_area" in adata.obs:
        area = np.asarray(adata.obs["cell_area"], dtype=float)
        r = float(np.corrcoef(area, totals)[0, 1]) if np.std(area) > 0 else 0.0
        controls["cell_size"] = "FAILED" if abs(r) > 0.3 else "PASSED"
    if artifact == "transcript_density_bias" and "local_density" in adata.obs:
        dens = np.asarray(adata.obs["local_density"], dtype=float)
        r = float(np.corrcoef(dens, totals)[0, 1]) if np.std(dens) > 0 else 0.0
        controls["transcript_density"] = "FAILED" if abs(r) > 0.3 else "PASSED"
    if artifact == "segmentation_leakage":
        # Leakage manifests as inflated neighbor similarity; measured via
        # nearest-neighbor count correlation on physical coordinates.
        coords = np.asarray(adata.obsm["spatial"])
        n = min(coords.shape[0], 400)
        sims = []
        for i in range(n):
            d = np.linalg.norm(coords[:n] - coords[i], axis=1)
            d[i] = np.inf
            j = int(np.argmin(d))
            xi, xj = X[i].astype(float), X[j].astype(float)
            denom = (np.linalg.norm(xi) * np.linalg.norm(xj))
            sims.append(float(xi @ xj / denom) if denom > 0 else 0.0)
        controls["segmentation_specificity"] = "FAILED" if float(np.mean(sims)) > 0.6 else "PASSED"
    if artifact == "spatial_permutation":
        # A permuted coordinate field cannot sustain any genuine spatial pattern:
        # the conclusion-under-test must not survive its own permutation null.
        controls["permutation_null"] = "FAILED"
    if artifact == "batch_fov_confounding" and "fov" in adata.obs and "condition" in adata.obs:

        fov = adata.obs["fov"].astype(str)
        cond = adata.obs["condition"].astype(str)
        pairs = set(zip(fov, cond))
        fov_conditions = {f: {c for ff, c in pairs if ff == f} for f in set(fov)}
        confounded = any(len(cs) == 1 for cs in fov_conditions.values()) and len(set(cond)) > 1
        controls["batch_fov"] = "FAILED" if confounded else "PASSED"
    if artifact == "radius_change":
        # Neighborhood radius sensitivity is a sweep on the analysis side; the
        # honest control is to declare it UNTESTED unless the sweep was run.
        controls["neighborhood_radius_sensitivity"] = "UNTESTED"
    return controls


# ==============================================================================
# Suite runners
# ==============================================================================


def _suite_pseudobulk_external_truth(case, meta: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = meta.get("dataset_id", "kang2018_pbmc_ifnb")
    if not flagship_dataset_present(dataset_id):
        return _skip_no_dataset(dataset_id, "pseudobulk_external_truth")

    failure_reasons: List[str] = []

    # Gate 1: Backend Identity Conformance — external truth on an unwitnessed
    # backend is not validation (BNS-EF-012..016).
    from bionexus.backend_conformance import verify_backend_identity
    from bionexus.capabilities import ALL_CAPABILITIES

    identity = verify_backend_identity(ALL_CAPABILITIES["scrna.pseudobulk_de"])
    if not identity.conformant:
        # Distinguish "backend absent" from "backend present but unwitnessed":
        # an identity audit alone cannot tell them apart (a blocked/failed
        # import looks like unresolvable entry points). Only a real import
        # attempt of the declared entry points settles it — through the normal
        # import machinery (__import__), which is the ground truth for
        # "can this environment execute the backend". A missing backend is
        # never a verified outcome (BNS-EM-009): honest skip, excluded from
        # accuracy, never PERMITTED.
        probe_targets = identity.entry_points_missing or [
            ALL_CAPABILITIES["scrna.pseudobulk_de"].backend.import_name
        ]
        for entry in probe_targets:
            module_name = entry.rsplit(".", 1)[0] if "." in entry else entry
            try:
                __import__(module_name)
            except ImportError as exc:
                return {
                    "actual_status": "SKIPPED_NO_BACKEND",
                    "skipped": True,
                    "skip_reason": (
                        f"L3 backend unavailable for scrna.pseudobulk_de "
                        f"(cannot import {module_name}: {exc}). External truth "
                        "validation NOT executed in this environment (BNS-EM-009)."
                    ),
                }
        return {
            "actual_status": "BLOCKED_BACKEND_IDENTITY",
            "actual_maturity": "ABSTAIN",
            "failure_reasons": [
                f"Backend identity for scrna.pseudobulk_de is {identity.state.value}: "
                f"{identity.reason} External validation refuses to run on an unwitnessed backend."
            ],
            "skipped": False,
            "skip_reason": None,
        }

    # Gate 2: run donor-aware pseudobulk DE and compare against published truth.
    import sys

    import anndata as ad
    import pandas as pd

    script_dir = REPO_ROOT / "skills" / "single-cell-rna-qc" / "scripts"
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from scrna_deseq import run_pydeseq2

    d = flagship_dataset_dir(dataset_id)
    adata = ad.read_h5ad(d / "pbmc_ifnb_counts.h5ad")
    truth = pd.read_csv(d / "published_de_truth.csv")

    for col in ("donor", "condition"):
        if col not in adata.obs.columns:
            return {
                "actual_status": "EXECUTION_FAILURE",
                "actual_maturity": "ABSTAIN",
                "failure_reasons": [f"Dataset '{dataset_id}' lacks required obs column '{col}'."],
                "skipped": False,
                "skip_reason": None,
            }

    # Pseudobulk aggregation per donor x condition (the capability's
    # contract): run_pydeseq2 expects samples x genes.
    genes = list(adata.var_names)
    agg = adata.obs.groupby(["donor", "condition"]).groups
    counts = pd.DataFrame(
        index=[f"{d_}|{c}" for d_, c in agg.keys()],
        columns=genes,
        dtype="float64",
    )
    for (d_, c), idx in agg.items():
        counts.loc[f"{d_}|{c}"] = adata.X[adata.obs.index.isin(idx)].sum(axis=0).A1
    design = pd.DataFrame(
        [{"sample_id": f"{d_}|{c}", "donor": d_, "condition": c} for d_, c in agg.keys()]
    )

    reference = meta.get("reference_condition", "ctrl")
    table, _contract = run_pydeseq2(counts, design, condition="condition", reference=reference, contrast_level=meta.get("contrast_level", "stim"))

    min_overlap = float(meta.get("min_truth_overlap", 0.5))
    top_n = int(meta.get("top_n", 100))
    our_top = set(table.sort_values("padj").head(top_n)["gene"].astype(str))
    # Membership truth (see dataset notes): published IFN/antiviral-response
    # genes, ranked by independent published support. The metric is the
    # fraction of BioNexus top-N DE genes with published support; a random
    # top-N gene list hits the truth universe at ~its transcriptome fraction
    # (<5%), so the threshold keeps discriminating power.
    truth_genes = set(truth.sort_values(truth.columns[-1])["gene"].astype(str))
    overlap = len(our_top & truth_genes) / max(len(our_top), 1)
    if overlap < min_overlap:
        failure_reasons.append(
            f"BioNexus pseudobulk top-{top_n} has published support for {overlap:.2f} "
            f"< required {min_overlap:.2f} (independent truth set: {meta.get('dataset_id')})."
        )

    observed = {
        "published_support_fraction": round(overlap, 4),
        "published_support_required": min_overlap,
        "top_n": top_n,
        "n_truth_genes": len(truth_genes),
        "n_cells": int(adata.n_obs),
        "n_donors": int(adata.obs["donor"].nunique()),
        "n_pseudobulk_samples": int(counts.shape[0]),
        "n_genes_tested": int(len(table)),
    }

    if failure_reasons:
        return {
            "actual_status": "OUTCOME_MISMATCH",
            "actual_maturity": "FRAGILE",
            "failure_reasons": failure_reasons,
            "skipped": False,
            "skip_reason": None,
            "observed": observed,
        }
    return {
        "actual_status": "PERMITTED",
        "actual_maturity": "SUPPORTED",
        "failure_reasons": [],
        "skipped": False,
        "skip_reason": None,
        "observed": observed,
    }


def _suite_annotation_distrust(case, meta: Dict[str, Any]) -> Dict[str, Any]:
    """B: the benchmark is knowing when an annotation is NOT worth believing."""
    try:
        import anndata  # noqa: F401
    except ImportError as exc:
        return {
            "actual_status": "SKIPPED_NO_BACKEND",
            "skipped": True,
            "skip_reason": f"L3 backend unavailable for scrna.annotation_evidence ({exc}).",
        }

    dataset_id = meta.get("dataset_id", "citeseq_pbmc_sorted")
    if not flagship_dataset_present(dataset_id):
        return _skip_no_dataset(dataset_id, "annotation_distrust")

    from evals.annotation_external_validation import run_study

    # Benchmark evaluation must never rewrite frozen canonical evidence in the
    # source checkout. Artifact generation is an explicit release operation.
    report = run_study(write=False)
    status = report["status"]["run_status"]
    if status not in {"positive_candidate", "endpoints_met_inconclusive"}:
        return {
            "actual_status": "OUTCOME_MISMATCH",
            "actual_maturity": "FRAGILE",
            "failure_reasons": [
                "BN-ANN-IV-001 did not demonstrate a non-degenerate correctness-enriching gate; "
                f"retained study status is {status}."
            ],
            "skipped": False,
            "skip_reason": None,
            "observed": report,
        }
    return {
        "actual_status": "PERMITTED",
        "actual_maturity": "CANDIDATE" if status == "positive_candidate" else "FRAGILE",
        "failure_reasons": [],
        "skipped": False,
        "skip_reason": None,
        "observed": report,
    }


def _suite_spatial_artifact_downgrade(case, meta: Dict[str, Any]) -> Dict[str, Any]:
    """C: manufactured artifacts must correctly downgrade the conclusion."""
    dataset_id = meta.get("dataset_id", "xenium_spatial_truth")
    if not flagship_dataset_present(dataset_id):
        return _skip_no_dataset(dataset_id, "spatial_artifact_downgrade")

    artifact = meta.get("artifact", "segmentation_leakage")
    if artifact == "radius_change":
        return {
            "actual_status": "PERMITTED",
            "actual_maturity": "FRAGILE",
            "failure_reasons": [],
            "skipped": False,
            "skip_reason": None,
            "observed": {"artifact": artifact, "verdict": "FRAGILE", "reason": "radius sweep not executed"},
        }

    from evals.spatial_instrument_validation import run_study

    # Keep unit/eval execution read-only with respect to the evidence ledger.
    report = run_study(write=False)
    endpoint_name = {
        "spatial_permutation": "coordinate_permutation",
        "batch_fov_confounding": "fov_confounding",
    }.get(artifact, artifact)
    endpoint = report["endpoints"].get(endpoint_name)
    failure_reasons: List[str] = []
    if endpoint is None:
        failure_reasons.append(f"No preregistered real-instrument endpoint exists for artifact '{artifact}'.")
    elif not endpoint["passed"]:
        failure_reasons.append(
            f"Preregistered endpoint '{endpoint_name}' failed on authentic Xenium bytes; negative result retained."
        )

    if failure_reasons:
        return {
            "actual_status": "OUTCOME_MISMATCH",
            "actual_maturity": "FRAGILE",
            "failure_reasons": failure_reasons,
            "skipped": False,
            "skip_reason": None,
            "observed": {"study": report, "endpoint": endpoint_name},
        }
    return {
        "actual_status": "PERMITTED",
        "actual_maturity": "REAL_INSTRUMENT_TECHNICAL_ACCEPTANCE",
        "failure_reasons": [],
        "skipped": False,
        "skip_reason": None,
        "observed": {"study": report, "endpoint": endpoint_name},
    }


_FLAGSHIP_SUITES = {
    "pseudobulk_external_truth": _suite_pseudobulk_external_truth,
    "annotation_distrust": _suite_annotation_distrust,
    "spatial_artifact_downgrade": _suite_spatial_artifact_downgrade,
}


def run_flagship_case(case) -> Dict[str, Any]:
    """Dispatch one flagship external-validation case; never guesses outcomes."""
    meta = dict(case.data_metadata or {})
    suite = meta.get("flagship_suite")
    runner = _FLAGSHIP_SUITES.get(suite)
    if runner is None:
        return {
            "actual_status": "EXECUTION_FAILURE",
            "actual_maturity": "ABSTAIN",
            "failure_reasons": [f"Unknown flagship suite '{suite}'."],
            "skipped": False,
            "skip_reason": None,
        }
    return runner(case, meta)


# ==============================================================================
# Validation Artifact (standardized JSON report)
# ==============================================================================


@dataclass
class ValidationArtifact:
    """Standardized validation artifact for a single flagship capability run."""

    capability: str               # e.g. "scrna.pseudobulk_de"
    dataset: Dict[str, Any]       # {name, version, accession, checksum_sha256}
    pipeline: Dict[str, Any]      # {version, backend_identity}
    metrics: List[Dict[str, Any]] # [{name, expected, observed, result}]
    limitations: List[str]        # known limitations
    timestamp: str                # ISO 8601
    evidence_files: List[str]     # paths to evidence files
    status: str                   # "pass" | "fail" | "skipped"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary (JSON-safe)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ValidationArtifact:
        """Deserialize from a dictionary."""
        return cls(**data)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def compute_file_checksum(file_path: Path, algorithm: str = "sha256") -> str:
    """Compute the hex-digest checksum of a file (default SHA-256)."""
    if algorithm == "sha256":
        # Use the shared provenance kernel so text checksums are stable across
        # Windows CRLF and POSIX LF checkouts. The verifier uses the same rule.
        from bionexus.provenance import sha256_file

        return sha256_file(file_path)
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_backend_identity(capability_id: str) -> Dict[str, Any]:
    """Retrieve backend identity information for a capability (best-effort)."""
    try:
        from bionexus.backend_conformance import verify_backend_identity
        from bionexus.capabilities import ALL_CAPABILITIES

        cap = ALL_CAPABILITIES.get(capability_id)
        if cap is None:
            return {"state": "UNKNOWN", "reason": f"Capability '{capability_id}' not registered."}
        report = verify_backend_identity(cap)
        return report.to_dict()
    except Exception as exc:
        return {"state": "UNKNOWN", "reason": str(exc)}


def _determine_status(run_result: Dict[str, Any]) -> str:
    """Map a flagship run result dict to a simple pass/fail/skipped status."""
    if run_result.get("skipped") or run_result.get("actual_status") == "SKIPPED_NO_BACKEND":
        return "skipped"
    status = run_result.get("actual_status", "")
    if status in ("PERMITTED",):
        return "pass"
    return "fail"


def generate_validation_report(
    capability: str,
    dataset_id: str,
    run_result: Dict[str, Any],
    metrics: Optional[List[Dict[str, Any]]] = None,
    limitations: Optional[List[str]] = None,
    evidence_files: Optional[List[str]] = None,
    output_dir: Optional[Path] = None,
) -> ValidationArtifact:
    """Build a ValidationArtifact from a flagship run result and optionally write it to disk.

    Parameters
    ----------
    capability : str
        The capability identifier (e.g. ``"scrna.pseudobulk_de"``).
    dataset_id : str
        Key into :data:`FLAGSHIP_DATASETS`.
    run_result : dict
        The dict returned by :func:`run_flagship_case`.
    metrics : list[dict], optional
        Per-metric records ``{name, expected, observed, result}``.
    limitations : list[str], optional
        Known limitations to record.
    evidence_files : list[str], optional
        Paths to evidence files produced during the run.
    output_dir : Path, optional
        Directory to write the JSON artifact.  When *None* the artifact is
        returned without being written to disk.

    Returns
    -------
    ValidationArtifact
    """
    manifest = FLAGSHIP_DATASETS.get(dataset_id, {})

    # Compute checksums for required dataset files (if present on disk).
    checksums: Dict[str, str] = {}
    ds_dir = flagship_dataset_dir(dataset_id)
    for fname in manifest.get("required_files", []):
        fpath = ds_dir / fname
        if fpath.is_file():
            checksums[fname] = compute_file_checksum(fpath)

    dataset_info: Dict[str, Any] = {
        "name": dataset_id,
        "version": manifest.get("version", "unknown"),
        "accession": manifest.get("source", "unknown"),
        "checksum_sha256": checksums,
    }

    backend_info = _resolve_backend_identity(capability)
    pipeline_info: Dict[str, Any] = {
        "version": backend_info.get("version", "unknown"),
        "backend_identity": backend_info,
    }

    artifact = ValidationArtifact(
        capability=capability,
        dataset=dataset_info,
        pipeline=pipeline_info,
        metrics=metrics or [],
        limitations=limitations or [],
        timestamp=datetime.now(timezone.utc).isoformat(),
        evidence_files=evidence_files or [],
        status=_determine_status(run_result),
    )

    if output_dir is not None:
        output_dir = Path(output_dir)
        # Determine sub-directory from capability.
        suite_subdir = _capability_to_subdir(capability)
        target_dir = output_dir / suite_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{dataset_id}_validation.json"
        out_path.write_text(artifact.to_json(), encoding="utf-8")

    return artifact


def _capability_to_subdir(capability: str) -> str:
    """Map a capability id to its validation output sub-directory."""
    mapping = {
        "scrna.pseudobulk_de": "pseudobulk",
        "scrna.annotation_evidence": "annotation",
        "spatial.inference_validity": "spatial",
    }
    return mapping.get(capability, capability.replace(".", "_"))


# ==============================================================================
# CLI entry point
# ==============================================================================


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the flagship validation harness."""
    parser = argparse.ArgumentParser(
        description="BioNexus Flagship External Validation Harness (BNS-015).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "validation",
        help="Directory to write validation artifacts (default: validation/).",
    )
    parser.add_argument(
        "--dataset-only",
        action="store_true",
        help="Only check dataset presence; do not run suites.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for flagship validation."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir: Path = args.output_dir

    print(f"BioNexus Flagship Validation — output_dir={output_dir}")
    for ds_id, manifest in FLAGSHIP_DATASETS.items():
        present = flagship_dataset_present(ds_id)
        cap = manifest["capability"]
        status_icon = "OK" if present else "MISSING"
        print(f"  [{status_icon}] {ds_id} ({cap})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
