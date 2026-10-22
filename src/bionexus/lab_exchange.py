"""Laboratory import/export paths with end-to-end acceptance.

Import is a file contract, not scientific warrant. Native Seurat RDS objects
and live Cell Ranger / nf-core binaries are out of the Python runtime.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bionexus.artifacts import RunBundle, verify_run_bundle
from bionexus.compatibility_matrix import VERIFIED_ADAPTER_STATUSES, get_product
from bionexus.egress_guard import DataClassification
from bionexus.interop import export_bco, export_ro_crate
from bionexus.schema_registry import (
    SchemaError,
    canonical_json_sha256,
    migrate_document,
    validate_document,
)
from bionexus.versions import PLUGIN_VERSION

PRODUCTS = ("cellranger", "scanpy", "seurat", "deseq2", "edger", "nf-core")
ENVELOPE_NAME = "lab-exchange-envelope.json"
DATA_CLASSIFICATIONS = ("UNKNOWN", *(value.value for value in DataClassification))
ACCEPTANCE_RECEIPT_NAME = "lab-acceptance-receipt.json"

_DESEQ_LFC = {"log2foldchange", "log2fc", "log2_fold_change"}
_DESEQ_PADJ = {"padj", "fdr", "p.adj", "p_adj"}
_EDGER_LFC = {"logfc", "log_fc"}
_EDGER_FDR = {"fdr", "pvalue", "p.value", "p_value"}


@dataclass
class ProductDetection:
    """Declared product identity for a lab path. Detection is not execution."""

    product: str
    kind: str
    root: str
    confidence: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceGate:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceReport:
    passed: bool
    product: str
    source: str
    output_dir: str
    gates: List[AcceptanceGate]
    envelope_path: Optional[str] = None
    capsule_path: Optional[str] = None
    ro_crate_path: Optional[str] = None
    bco_path: Optional[str] = None
    scientific_authorization: str = "NONE"
    data_classification: str = "UNKNOWN"
    receipt_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["gates"] = [gate.to_dict() for gate in self.gates]
        return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read_header(path: Path, max_bytes: int = 4096) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError:
        return ""


def _csv_columns(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    first = next((line for line in text.splitlines() if line.strip()), "")
    if not first:
        return []
    delimiter = "\t" if first.count("\t") >= first.count(",") else ","
    return [col.strip().lstrip("\ufeff#") for col in first.split(delimiter)]


def _lower_set(values: Iterable[str]) -> set[str]:
    return {value.strip().lower() for value in values}


def _contained_path(root: Path, relpath: str) -> Path:
    base = root.resolve()
    candidate = (root / relpath).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise SchemaError(f"refusing path outside lab root: {relpath}") from exc
    return candidate


def _file_record(path: Path, root: Path, role: str) -> Dict[str, Any]:
    resolved = path.resolve()
    return {
        "role": role,
        "relpath": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
        "integrity_status": "BYTE_VERIFIED",
    }


def _collect_files(root: Path, mapping: Dict[str, Path]) -> List[Dict[str, Any]]:
    records = []
    for role, path in mapping.items():
        if path.is_file():
            records.append(_file_record(path, root, role))
    if not records:
        raise SchemaError(f"no readable lab files under {root}")
    return records


def _envelope(
    *,
    product: str,
    kind: str,
    root: Path,
    files: List[Dict[str, Any]],
    semantic_type: str,
    summary: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    product_version: Optional[str] = None,
) -> Dict[str, Any]:
    source = {"kind": kind, "root_name": root.name, "files": files}
    doc = {
        "schema_version": "bionexus.lab-exchange-envelope.v2",
        "producer": {
            "product": product,
            "product_version": product_version,
            "bionexus_version": PLUGIN_VERSION,
        },
        "source": source,
        "semantic_type": semantic_type,
        "data_classification": "UNKNOWN",
        "scientific_authorization": "NONE",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "payload_sha256": canonical_json_sha256(files),
        "summary": summary or {},
        "warnings": warnings or [],
    }
    result = validate_document(doc, family="lab-exchange-envelope")
    if not result.valid:
        raise SchemaError("lab envelope failed validation: " + "; ".join(result.errors))
    return doc


def _find_mtx_bundle(root: Path) -> Optional[Dict[str, Path]]:
    candidates = [root, root / "filtered_feature_bc_matrix", root / "outs" / "filtered_feature_bc_matrix"]
    for folder in candidates:
        matrix = folder / "matrix.mtx"
        features = folder / "features.tsv" if (folder / "features.tsv").is_file() else folder / "genes.tsv"
        barcodes = folder / "barcodes.tsv"
        if matrix.is_file() and features.is_file() and barcodes.is_file():
            return {"matrix": matrix, "features": features, "barcodes": barcodes}
    return None


def detect_lab_product(path: str | Path) -> ProductDetection:
    """Identify a lab product from directory layout or table headers."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"lab source not found: {target}")
    if target.is_file() and target.suffix.lower() in {".rds", ".qs"}:
        raise SchemaError("unable to detect: native Seurat .rds/.qs is unsupported; export MTX/TSV or h5ad")

    if target.is_file() and target.suffix.lower() == ".h5ad":
        return ProductDetection("scanpy", "scanpy_h5ad", str(target), "HIGH", [target.name])
    if target.is_file() and target.suffix.lower() in {".csv", ".tsv"}:
        columns = _lower_set(_csv_columns(target))
        if columns & _DESEQ_LFC and columns & _DESEQ_PADJ:
            return ProductDetection("deseq2", "deseq2_results", str(target), "HIGH", sorted(columns))
        if columns & _EDGER_LFC and columns & _EDGER_FDR:
            return ProductDetection("edger", "edger_results", str(target), "HIGH", sorted(columns))
        if target.name != "samplesheet.csv":
            raise SchemaError(f"unsupported explicit results table: {target.name}")
    elif target.is_file():
        raise SchemaError(f"unsupported explicit lab file: {target.name}")

    root = target if target.is_dir() else target.parent
    evidence: List[str] = []
    outs = root / "outs" if (root / "outs").is_dir() else root
    metrics = outs / "metrics_summary.csv"
    mtx = _find_mtx_bundle(root)
    if metrics.is_file() or (mtx and "outs" in str(outs)):
        if metrics.is_file():
            evidence.append("metrics_summary.csv")
        if mtx:
            evidence.extend(sorted(mtx))
        if metrics.is_file() or mtx:
            return ProductDetection("cellranger", "cellranger_outs", str(outs), "HIGH", evidence)

    metadata = root / "metadata.csv"
    if mtx and metadata.is_file():
        return ProductDetection("seurat", "seurat_mtx_export", str(root), "HIGH", ["metadata.csv", *sorted(mtx)])

    pipeline_info = root / "pipeline_info"
    samplesheet = root / "samplesheet.csv"
    versions = root / "pipeline_info" / "software_versions.yml"
    if not versions.is_file():
        versions = root / "software_versions.yml"
    if samplesheet.is_file() or pipeline_info.is_dir() or versions.is_file():
        if samplesheet.is_file():
            evidence.append("samplesheet.csv")
        if pipeline_info.is_dir():
            evidence.append("pipeline_info")
        if versions.is_file():
            evidence.append(versions.name)
        return ProductDetection("nf-core", "nfcore_results", str(root), "HIGH", evidence)

    counts = root / "counts.tsv"
    obs = root / "obs.tsv"
    if counts.is_file() and obs.is_file():
        return ProductDetection("scanpy", "scanpy_table", str(root), "HIGH", ["counts.tsv", "obs.tsv"])
    if mtx:
        return ProductDetection("seurat", "seurat_mtx_export", str(root), "MEDIUM", sorted(mtx))
    raise SchemaError(f"unable to detect a supported lab product under {root}")


def _import_cellranger(root: Path) -> Dict[str, Any]:
    mapping: Dict[str, Path] = {}
    metrics = root / "metrics_summary.csv"
    if metrics.is_file():
        mapping["metrics"] = metrics
    mtx = _find_mtx_bundle(root)
    if mtx:
        mapping.update(mtx)
    web = root / "web_summary.html"
    if web.is_file():
        mapping["web_summary"] = web
    h5 = root / "filtered_feature_bc_matrix.h5"
    if h5.is_file():
        mapping["feature_bc_matrix_h5"] = h5
    summary: Dict[str, Any] = {"n_files": len(mapping)}
    if metrics.is_file():
        columns = _csv_columns(metrics)
        summary["metrics_columns"] = columns[:12]
    return _envelope(
        product="cellranger",
        kind="cellranger_outs",
        root=root,
        files=_collect_files(root, mapping),
        semantic_type="scrna.counts.cellranger",
        summary=summary,
        warnings=["Cell Ranger binary was not executed; outs/ files were hashed only."],
    )


def _import_seurat(root: Path) -> Dict[str, Any]:
    mtx = _find_mtx_bundle(root)
    if mtx is None:
        raise SchemaError("Seurat import requires MTX + features/genes + barcodes")
    mapping = dict(mtx)
    metadata = root / "metadata.csv"
    if metadata.is_file():
        mapping["metadata"] = metadata
    return _envelope(
        product="seurat",
        kind="seurat_mtx_export",
        root=root,
        files=_collect_files(root, mapping),
        semantic_type="scrna.counts.seurat_export",
        summary={"native_rds": False, "export_format": "mtx_tsv"},
        warnings=["Native Seurat .rds/.qs objects are unsupported; this path accepts exported MTX/TSV."],
    )


def _import_scanpy(path: Path) -> Dict[str, Any]:
    if path.is_file() and path.suffix.lower() == ".h5ad":
        summary: Dict[str, Any] = {"format": "h5ad"}
        warnings = []
        try:
            import anndata as ad

            adata = ad.read_h5ad(str(path), backed="r")
            try:
                summary["n_obs"] = int(adata.n_obs)
                summary["n_vars"] = int(adata.n_vars)
            finally:
                adata.file.close()
        except ImportError:
            warnings.append("anndata is not installed; .h5ad was hashed without opening the matrix.")
        files = [_file_record(path, path.parent, "h5ad")]
        return _envelope(
            product="scanpy",
            kind="scanpy_h5ad",
            root=path.parent,
            files=files,
            semantic_type="scrna.anndata.h5ad",
            summary=summary,
            warnings=warnings,
        )
    mapping = {"counts": path / "counts.tsv", "obs": path / "obs.tsv"}
    if (path / "var.tsv").is_file():
        mapping["var"] = path / "var.tsv"
    return _envelope(
        product="scanpy",
        kind="scanpy_table",
        root=path,
        files=_collect_files(path, mapping),
        semantic_type="scrna.anndata.table_export",
        summary={"format": "tsv_tables"},
    )


def _import_de_table(path: Path, product: str, kind: str) -> Dict[str, Any]:
    columns = _csv_columns(path)
    lower = _lower_set(columns)
    if product == "deseq2" and not (lower & _DESEQ_LFC and lower & _DESEQ_PADJ):
        raise SchemaError("DESeq2 table missing log2FoldChange/padj aliases")
    if product == "edger" and not (lower & _EDGER_LFC and lower & _EDGER_FDR):
        raise SchemaError("edgeR table missing logFC/FDR aliases")
    n_rows = max(len(path.read_text(encoding="utf-8", errors="replace").splitlines()) - 1, 0)
    return _envelope(
        product=product,
        kind=kind,
        root=path.parent,
        files=[_file_record(path, path.parent, "results_table")],
        semantic_type=f"de.results.{product}",
        summary={"columns": columns, "n_rows": n_rows},
        warnings=[f"{product} was not re-executed; the result table was imported as-is."],
    )


def _import_nfcore(root: Path) -> Dict[str, Any]:
    mapping: Dict[str, Path] = {}
    samplesheet = root / "samplesheet.csv"
    if samplesheet.is_file():
        mapping["samplesheet"] = samplesheet
    for rel in (
        "pipeline_info/software_versions.yml",
        "software_versions.yml",
        "pipeline_info/execution_trace.txt",
        "pipeline_info/pipeline_report.txt",
    ):
        candidate = root / rel
        if candidate.is_file():
            # Two producers may emit the same basename at different locations.
            # Both declarations must remain independently bound to their bytes.
            mapping[rel] = candidate
    if not mapping:
        raise SchemaError("nf-core import requires samplesheet.csv or pipeline_info artifacts")
    return _envelope(
        product="nf-core",
        kind="nfcore_results",
        root=root,
        files=_collect_files(root, mapping),
        semantic_type="workflow.nfcore.results",
        summary={"n_files": len(mapping)},
        warnings=["Nextflow was not launched; workflow success is not scientific warrant."],
    )


def import_lab_source(
    path: str | Path,
    *,
    product: Optional[str] = None,
    data_classification: str = "UNKNOWN",
) -> Tuple[ProductDetection, Dict[str, Any]]:
    """Import a lab directory or table into a current lab-exchange envelope."""
    if data_classification not in DATA_CLASSIFICATIONS:
        raise SchemaError(f"unsupported data classification: {data_classification!r}")
    detection = detect_lab_product(path)
    if product and product != detection.product:
        raise SchemaError(f"declared product {product!r} does not match detected {detection.product!r}")
    target = Path(path)
    root = Path(detection.root)
    if detection.product == "cellranger":
        envelope = _import_cellranger(root)
    elif detection.product == "seurat":
        envelope = _import_seurat(root)
    elif detection.product == "scanpy":
        envelope = _import_scanpy(target if target.suffix.lower() == ".h5ad" else root)
    elif detection.product == "deseq2":
        envelope = _import_de_table(target if target.is_file() else root / target.name, "deseq2", "deseq2_results")
    elif detection.product == "edger":
        envelope = _import_de_table(target if target.is_file() else root / target.name, "edger", "edger_results")
    elif detection.product == "nf-core":
        envelope = _import_nfcore(root)
    else:
        raise SchemaError(f"unsupported lab product: {detection.product}")
    envelope["data_classification"] = data_classification
    return detection, envelope


def write_envelope(envelope: Dict[str, Any], dest: str | Path) -> Path:
    validation = validate_document(envelope, family="lab-exchange-envelope")
    if not validation.valid:
        raise SchemaError("invalid lab envelope: " + "; ".join(validation.errors))
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n")
    return path


def _verify_envelope_files(envelope: Dict[str, Any], root: Path) -> None:
    """Verify manifest identity and every file's current bytes, with no digest substitution."""
    validation = validate_document(envelope, family="lab-exchange-envelope")
    if not validation.valid:
        raise SchemaError("invalid lab envelope: " + "; ".join(validation.errors))
    records = envelope["source"]["files"]
    if envelope["payload_sha256"] != canonical_json_sha256(records):
        raise SchemaError("envelope payload_sha256 does not match its file records")
    seen_paths: set[str] = set()
    seen_roles: set[str] = set()
    for record in records:
        relpath = str(record["relpath"])
        relative = Path(relpath)
        if relative.is_absolute() or relative.drive or ".." in relative.parts or "\\" in relpath:
            raise SchemaError(f"refusing path outside lab root or nonportable path: {relpath}")
        # Casefold is deliberate: capsules may move between case-sensitive and Windows filesystems.
        normalized = relative.as_posix().casefold()
        if normalized in seen_paths or record["role"] in seen_roles:
            raise SchemaError(f"duplicate lab file path or role: {relpath}")
        seen_paths.add(normalized)
        seen_roles.add(record["role"])
        file_path = _contained_path(root, relpath)
        if not file_path.is_file():
            raise FileNotFoundError(f"envelope file missing: {relpath}")
        if file_path.stat().st_size != record["size_bytes"] or _sha256_file(file_path) != record["sha256"]:
            raise SchemaError(f"lab file bytes do not match envelope: {relpath}")


def _require_empty_destination(dest: Path) -> None:
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise FileExistsError(f"refusing to overwrite an existing lab output: {dest}")


def export_lab_capsule(
    envelope: Dict[str, Any],
    source: str | Path,
    dest: str | Path,
    *,
    ro_crate: bool = True,
    bco: bool = True,
) -> Dict[str, Path]:
    """Materialize a run capsule and optional RO-Crate / BCO projections."""
    dest_dir = Path(dest).resolve()
    _require_empty_destination(dest_dir)
    source_path = Path(source)
    detection = detect_lab_product(source_path)
    if detection.product != envelope["producer"]["product"]:
        raise SchemaError("export product does not match source detection")
    root = source_path.parent if source_path.is_file() and detection.product != "nf-core" else Path(detection.root)
    _verify_envelope_files(envelope, root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    bundle = RunBundle.create(
        dest_dir,
        capability_id="lab.exchange.import",
        skill_name="lab-exchange",
    )
    imported = bundle.results_dir / "imported"
    imported.mkdir(parents=True, exist_ok=True)
    copied: List[Tuple[str, Path]] = []
    for item in envelope["source"]["files"]:
        relpath = str(item["relpath"])
        src_file = _contained_path(root, relpath)
        copied_path = _contained_path(imported, relpath)
        copied_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, copied_path)
        copied.append((item["role"], copied_path))
        bundle.record_input(
            item["role"], copied_path, semantic_type=envelope["semantic_type"],
            metadata={"data_classification": envelope["data_classification"], "source_relpath": relpath},
        )
        # Bind inputs to the archived copies so the capsule remains verifiable after handoff.
        bundle.inputs[item["role"]].path = copied_path.relative_to(dest_dir.resolve()).as_posix()
    _verify_envelope_files(envelope, root)
    _verify_envelope_files(envelope, imported)
    envelope_path = bundle.results_dir / ENVELOPE_NAME
    write_envelope(envelope, envelope_path)
    bundle.add_result("lab_exchange_envelope", envelope_path, semantic_type="lab.exchange.envelope", is_primary=True)
    for role, copied_file in copied:
        bundle.add_result(role, copied_file, semantic_type=envelope["semantic_type"], metadata={
            "data_classification": envelope["data_classification"],
        })
    bundle.record_parameters(
        product=envelope["producer"]["product"],
        scientific_authorization="NONE",
        payload_sha256=envelope["payload_sha256"],
        data_classification=envelope["data_classification"],
        classification_effect="LOCAL_ONLY_UNTIL_CLASSIFIED" if envelope["data_classification"] == "UNKNOWN" else "EXPLICIT_OPERATOR_CLASSIFICATION",
    )
    bundle.execution_state = "EXECUTED"
    bundle.conclusion_maturity = "UNASSESSED"
    capsule = bundle.finalize(status="COMPLETED")
    verification = verify_run_bundle(dest_dir)
    if not verification.valid:
        raise SchemaError(f"exported capsule failed byte integrity: {verification.to_dict()}")
    artifacts = {"envelope": envelope_path, "capsule": capsule}
    if ro_crate:
        crate, errors = export_ro_crate(dest_dir, dest_dir / "ro-crate-metadata.json")
        if errors:
            raise SchemaError("RO-Crate structural precheck failed: " + "; ".join(errors))
        document = json.loads(crate.read_text(encoding="utf-8"))
        for entity in document["@graph"]:
            if entity.get("@id") == "./":
                entity["conditionsOfAccess"] = envelope["data_classification"]
        crate.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        artifacts["ro_crate"] = crate
    if bco:
        bco_path, errors = export_bco(dest_dir, dest_dir / "bco.json")
        if errors:
            raise SchemaError("BCO structural precheck failed: " + "; ".join(errors))
        artifacts["bco"] = bco_path
    return artifacts


def _accept_lab_roundtrip(
    path: str | Path, dest: str | Path, *, product: Optional[str], data_classification: str,
) -> AcceptanceReport:
    """End-to-end lab import → envelope → capsule → RO-Crate/BCO → reimport checksums."""
    gates: List[AcceptanceGate] = []
    source = Path(path)
    dest_dir = Path(dest).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        detection, envelope = import_lab_source(source, product=product, data_classification=data_classification)
        gates.append(AcceptanceGate("DETECT", True, detection.product))
    except Exception as exc:
        return AcceptanceReport(False, product or "unknown", str(source), str(dest_dir), [
            AcceptanceGate("DETECT", False, str(exc))
        ])
    try:
        result = validate_document(envelope, family="lab-exchange-envelope")
        gates.append(AcceptanceGate("IMPORT", result.valid, result.document_id if result.valid else "; ".join(result.errors)))
        if not result.valid:
            raise SchemaError("; ".join(result.errors))
        envelope_path = write_envelope(envelope, dest_dir / ENVELOPE_NAME)
    except Exception as exc:
        gates.append(AcceptanceGate("IMPORT", False, str(exc)))
        return AcceptanceReport(False, detection.product, str(source), str(dest_dir), gates)

    try:
        artifacts = export_lab_capsule(envelope, source, dest_dir / "capsule", ro_crate=True, bco=True)
        gates.append(AcceptanceGate("CAPSULE", True, str(artifacts["capsule"])))
        gates.append(AcceptanceGate("RO_CRATE", True, f"STRUCTURAL_PRECHECK_ONLY: {artifacts['ro_crate']}"))
        gates.append(AcceptanceGate("BCO", True, f"STRUCTURAL_PRECHECK_ONLY: {artifacts['bco']}"))
    except Exception as exc:
        gates.append(AcceptanceGate("EXPORT", False, str(exc)))
        return AcceptanceReport(
            False, detection.product, str(source), str(dest_dir), gates, envelope_path=str(envelope_path)
        )

    try:
        imported = dest_dir / "capsule" / "results" / "imported"
        reloaded = migrate_document(json.loads(artifacts["envelope"].read_text(encoding="utf-8")))
        _verify_envelope_files(reloaded, imported)
        if reloaded != envelope:
            raise SchemaError("exported envelope differs from imported source envelope")
        reimport_path = imported
        if detection.kind in {"scanpy_h5ad", "deseq2_results", "edger_results"}:
            reimport_path = imported / envelope["source"]["files"][0]["relpath"]
        _, reimported = import_lab_source(
            reimport_path, product=detection.product, data_classification=data_classification,
        )
        same = (
            reimported["payload_sha256"] == envelope["payload_sha256"]
            and reimported["semantic_type"] == envelope["semantic_type"]
            and reimported["data_classification"] == envelope["data_classification"]
        )
        if not verify_run_bundle(dest_dir / "capsule").valid:
            raise SchemaError("capsule integrity failed after reimport")
        gates.append(AcceptanceGate("REIMPORT", same, reimported["payload_sha256"]))
        if not same:
            raise SchemaError("payload_sha256 changed across export/reimport")
    except Exception as exc:
        gates.append(AcceptanceGate("REIMPORT", False, str(exc)))
        return AcceptanceReport(
            False,
            detection.product,
            str(source),
            str(dest_dir),
            gates,
            envelope_path=str(envelope_path),
            capsule_path=str(artifacts.get("capsule")),
        )

    try:
        matrix_row = get_product(detection.product)
        compatible = matrix_row["status"] in VERIFIED_ADAPTER_STATUSES
        gates.append(AcceptanceGate("COMPAT", compatible, f"{matrix_row['id']}:{matrix_row['status']}; adapter fixture scope only; producer version NOT_ASSESSED"))
    except Exception as exc:
        gates.append(AcceptanceGate("COMPAT", False, str(exc)))
        compatible = False

    passed = all(gate.passed for gate in gates) and compatible
    return AcceptanceReport(
        passed=passed,
        product=detection.product,
        source=str(source),
        output_dir=str(dest_dir),
        gates=gates,
        envelope_path=str(envelope_path),
        capsule_path=str(artifacts["capsule"]),
        ro_crate_path=str(artifacts["ro_crate"]),
        bco_path=str(artifacts["bco"]),
    )


def accept_lab_roundtrip(
    path: str | Path, dest: str | Path, *, product: Optional[str] = None,
    data_classification: str = "UNKNOWN",
) -> AcceptanceReport:
    """Archive a byte-verified file round trip and its bounded acceptance receipt."""
    if data_classification not in DATA_CLASSIFICATIONS:
        raise SchemaError(f"unsupported data classification: {data_classification!r}")
    dest_dir = Path(dest).resolve()
    _require_empty_destination(dest_dir)
    report = _accept_lab_roundtrip(path, dest_dir, product=product, data_classification=data_classification)
    report.data_classification = data_classification
    receipt = dest_dir / ACCEPTANCE_RECEIPT_NAME
    report.receipt_path = str(receipt)
    payload = report.to_dict()
    payload.update({
        "schema_version": "bionexus.lab-acceptance-receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bionexus_version": PLUGIN_VERSION,
        "scope": "LOCAL_FILE_ROUNDTRIP_ONLY",
        "producer_version_verification": "NOT_ASSESSED",
        "official_profile_conformance": "NOT_ASSESSED",
        "implementation_sha256": {
            Path(__file__).name: _sha256_file(Path(__file__)),
            "schema_registry.py": _sha256_file(Path(__file__).with_name("schema_registry.py")),
            "compatibility_matrix.py": _sha256_file(Path(__file__).with_name("compatibility_matrix.py")),
        },
        "artifact_sha256": {
            Path(value).relative_to(dest_dir).as_posix(): _sha256_file(Path(value))
            for value in (report.envelope_path, report.capsule_path, report.ro_crate_path, report.bco_path)
            if value and Path(value).is_file()
        },
    })
    validated = validate_document(payload, family="lab-acceptance-receipt")
    if not validated.valid:
        raise SchemaError("acceptance receipt failed validation: " + "; ".join(validated.errors))
    with receipt.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return report
