"""Ingest Workflow Run RO-Crate documents as Nextflow execution provenance.

nf-prov owns the crate. This module consumes it. It does not emit a competing
crate, parse samplesheets into evidence factors, or treat workflow success as
scientific warrant.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from bionexus.nextflow_bridge import NextflowExecutionSummary
from bionexus.roc_validator import STATUS_NOT_RUN, run_rocrate_validator

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

PROVENANCE_WRROC = "WRROC"
PROVENANCE_TRACE = "TRACE_FALLBACK"
PROVENANCE_MISSING = "MISSING"

_COMPLETED_MARKERS = (
    "CompletedActionStatus",
    "http://schema.org/ActionStatusType/CompletedActionStatus",
    "http://schema.org/CompletedActionStatus",
)
_FAILED_MARKERS = (
    "FailedActionStatus",
    "http://schema.org/ActionStatusType/FailedActionStatus",
    "http://schema.org/FailedActionStatus",
)
_ACTIVE_MARKERS = (
    "ActiveActionStatus",
    "http://schema.org/ActionStatusType/ActiveActionStatus",
    "http://schema.org/ActiveActionStatus",
)

_SKIP_DIR_NAMES = {".nextflow", "work", ".git"}


def _sha256_file(path: Path) -> str:
    try:
        if not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _as_type_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _entity_id(value: Any) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        ref = value.get("@id")
        if isinstance(ref, str) and ref:
            return ref
    return None


def _ref_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        refs = [_entity_id(item) for item in value]
        return [ref for ref in refs if ref]
    ref = _entity_id(value)
    return [ref] if ref else []


def _action_status_token(entity: Dict[str, Any]) -> str:
    raw = entity.get("actionStatus")
    token = _entity_id(raw) or (raw if isinstance(raw, str) else "")
    return str(token)


def _status_from_action(entity: Dict[str, Any]) -> Optional[str]:
    token = _action_status_token(entity)
    if not token:
        return None
    if any(marker in token for marker in _FAILED_MARKERS):
        return "FAILED"
    if any(marker in token for marker in _COMPLETED_MARKERS):
        return "SUCCESS"
    if any(marker in token for marker in _ACTIVE_MARKERS):
        return "INCOMPLETE"
    return None


def locate_wrroc_crate(run_dir: PathLike) -> Optional[Path]:
    """Find ``ro-crate-metadata.json`` under a Nextflow run directory.

    Prefers ``pipeline_info/`` (nf-core + generated BioNexus config) then the
    run root. Skips ``work/`` and ``.nextflow/``.
    """
    root = Path(run_dir)
    if not root.exists():
        return None
    preferred = [
        root / "pipeline_info" / "ro-crate-metadata.json",
        root / "ro-crate-metadata.json",
        root / "ro-crate" / "ro-crate-metadata.json",
    ]
    for candidate in preferred:
        if candidate.is_file():
            return candidate
    matches: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES]
        if "ro-crate-metadata.json" in filenames:
            matches.append(Path(dirpath) / "ro-crate-metadata.json")
    if not matches:
        return None
    matches.sort(key=lambda item: (len(item.parts), str(item)))
    return matches[0]


def load_wrroc_document(crate_path: PathLike) -> Dict[str, Any]:
    """Load and minimally sanity-check a Workflow Run RO-Crate metadata file."""
    path = Path(crate_path)
    if path.is_dir():
        path = path / "ro-crate-metadata.json"
    if not path.is_file():
        raise FileNotFoundError(f"RO-Crate metadata not found: {crate_path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"RO-Crate metadata is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("RO-Crate metadata MUST be a JSON object")
    graph = doc.get("@graph")
    if not isinstance(graph, list) or not graph:
        raise ValueError("RO-Crate metadata MUST contain a non-empty @graph")
    return doc


def _graph_by_id(graph: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for entity in graph:
        if not isinstance(entity, dict):
            continue
        eid = entity.get("@id")
        if isinstance(eid, str) and eid:
            if eid in by_id:
                raise ValueError(f"Duplicate RO-Crate entity identifier: {eid}")
            by_id[eid] = entity
    return by_id


def _is_workflow_entity(entity: Dict[str, Any]) -> bool:
    types = _as_type_list(entity.get("@type"))
    return "ComputationalWorkflow" in types or (
        "SoftwareSourceCode" in types and "File" in types
    )


def _select_workflow_run(
    graph: List[Any], by_id: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Select the workflow CreateAction. Never guess a process run by graph order."""
    root = by_id.get("./") or {}
    for ref in _ref_list(root.get("mentions")):
        entity = by_id.get(ref)
        if entity and "CreateAction" in _as_type_list(entity.get("@type")):
            instrument = by_id.get(_entity_id(entity.get("instrument")) or "")
            if instrument is None or _is_workflow_entity(instrument):
                return entity
    actions = [
        entity
        for entity in graph
        if isinstance(entity, dict) and "CreateAction" in _as_type_list(entity.get("@type"))
    ]
    for action in actions:
        instrument = by_id.get(_entity_id(action.get("instrument")) or "")
        if instrument and _is_workflow_entity(instrument):
            return action
    return None


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _resolve_data_file(crate_root: Path, entity_id: str, run_dir: Optional[Path]) -> Optional[Path]:
    if not entity_id or entity_id.startswith("#") or "://" in entity_id:
        return None
    rel = entity_id[2:] if entity_id.startswith("./") else entity_id
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return None
    anchors = [crate_root]
    if crate_root.parent != crate_root:
        anchors.append(crate_root.parent)
    if run_dir is not None:
        anchors.append(run_dir)
    for anchor in anchors:
        candidate = (anchor / rel)
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        if _is_within(resolved, anchor.resolve()):
            return resolved
    return None


def ingest_wrroc_crate(
    crate_path: PathLike,
    *,
    pipeline_name: Optional[str] = None,
    samplesheet_path: Optional[PathLike] = None,
    run_dir: Optional[PathLike] = None,
    official_validation: str = "auto",
) -> NextflowExecutionSummary:
    """Map an nf-prov Workflow Run RO-Crate onto ``NextflowExecutionSummary``.

    ``official_validation``: ``skip`` never calls the CLI; ``auto`` records the
    result without blocking ingest; ``require`` raises if the CLI is missing or
    fails. Scientific evidence factors are never derived.
    """
    metadata_path = Path(crate_path)
    if official_validation not in {"skip", "auto", "require"}:
        raise ValueError("official_validation must be skip, auto, or require")
    if metadata_path.is_dir():
        metadata_path = metadata_path / "ro-crate-metadata.json"
    crate_root = metadata_path.parent
    resolved_run = Path(run_dir) if run_dir is not None else crate_root
    if samplesheet_path is not None:
        sheet = Path(samplesheet_path)
        if not sheet.is_file():
            raise FileNotFoundError(f"Explicit samplesheet does not exist: {sheet}")

    doc = load_wrroc_document(metadata_path)
    graph = [entity for entity in doc.get("@graph", []) if isinstance(entity, dict)]
    by_id = _graph_by_id(graph)
    workflow_run = _select_workflow_run(graph, by_id)
    if workflow_run is None:
        raise ValueError("Workflow Run RO-Crate contains no CreateAction")

    instrument = by_id.get(_entity_id(workflow_run.get("instrument")) or "")
    computed_name = None
    pipeline_version: Optional[str] = None
    if instrument:
        computed_name = instrument.get("name") or instrument.get("@id")
        version = instrument.get("version")
        if isinstance(version, str) and version:
            pipeline_version = version
    if not computed_name:
        computed_name = workflow_run.get("name") or pipeline_name or "nf-core/pipeline"
    if pipeline_name is not None and pipeline_name != computed_name:
        raise ValueError("Requested pipeline name conflicts with RO-Crate producer identity")

    nextflow_version: Optional[str] = None
    software_versions: Dict[str, str] = {}
    for entity in graph:
        types = _as_type_list(entity.get("@type"))
        if "SoftwareApplication" not in types:
            continue
        name = str(entity.get("name") or entity.get("@id") or "software")
        version = entity.get("version")
        if isinstance(version, str) and version:
            software_versions[name] = version
            if name.lower() == "nextflow":
                nextflow_version = version

    actions = [
        entity
        for entity in graph
        if "CreateAction" in _as_type_list(entity.get("@type"))
    ]
    workflow_run_id = workflow_run.get("@id")
    process_entities = [entity for entity in actions if entity.get("@id") != workflow_run_id]
    total = len(process_entities)
    succeeded = 0
    failed = 0
    for entity in process_entities:
        status = _status_from_action(entity)
        if status == "FAILED":
            failed += 1
        elif status == "SUCCESS":
            succeeded += 1
    if total == 0:
        total = 1 if _status_from_action(workflow_run) else 0
        run_status = _status_from_action(workflow_run)
        if run_status == "FAILED":
            failed = 1
        elif run_status == "SUCCESS":
            succeeded = 1

    execution_status = _status_from_action(workflow_run)
    if execution_status is None:
        execution_status = "UNKNOWN"

    # Producer hashes and current observations are separate facts. Never rewrite
    # an execution record's digest to match possibly corrupted current bytes.
    artifact_integrity: List[Dict[str, str]] = []

    def collect_artifacts(refs: List[str], role: str) -> Dict[str, str]:
        artifacts: Dict[str, str] = {}
        for ref in refs:
            rel = ref[2:] if ref.startswith("./") else ref
            record = {"role": role, "entity_id": ref, "path": rel,
                      "producer_sha256": "", "observed_sha256": "", "status": "NOT_VERIFIED"}
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                record["status"] = "UNSAFE_PATH"
                artifact_integrity.append(record)
                continue
            entity = by_id.get(ref, {})
            # Parameters remain bound by the crate digest; file inputs need bytes.
            if role == "input" and "File" not in _as_type_list(entity.get("@type")):
                record["status"] = "UNVERIFIED_INPUT_ENTITY"
                artifact_integrity.append(record)
                continue
            producer = entity.get("sha256") if isinstance(entity.get("sha256"), str) else ""
            record["producer_sha256"] = producer
            on_disk = _resolve_data_file(crate_root, ref, resolved_run)
            if on_disk is not None:
                try:
                    key = on_disk.resolve().relative_to(resolved_run.resolve()).as_posix()
                except ValueError:
                    record["status"] = "OUTSIDE_RUN_DIRECTORY"
                    artifact_integrity.append(record)
                    continue
                record["path"] = key
                record["observed_sha256"] = _sha256_file(on_disk)
            else:
                key = ref
            observed = record["observed_sha256"]
            if not producer:
                record["status"] = "PRODUCER_HASH_MISSING"
            elif not re.fullmatch(r"[0-9a-fA-F]{64}", producer):
                record["status"] = "INVALID_PRODUCER_HASH"
            elif not observed:
                record["status"] = "ARTIFACT_MISSING"
            elif producer.lower() != observed:
                record["status"] = "HASH_MISMATCH"
            else:
                record["status"] = "VERIFIED"
            if key in artifacts:
                record["status"] = "DUPLICATE_ARTIFACT_PATH"
            artifacts[key] = producer
            artifact_integrity.append(record)
        return artifacts

    primary_inputs = collect_artifacts(_ref_list(workflow_run.get("object")), "input")
    primary_outputs = collect_artifacts(_ref_list(workflow_run.get("result")), "output")
    artifact_status = "VERIFIED" if artifact_integrity and all(
        item["status"] == "VERIFIED" for item in artifact_integrity
    ) else "NOT_VERIFIED"
    if any(item["status"] in {"HASH_MISMATCH", "INVALID_PRODUCER_HASH", "UNSAFE_PATH",
                               "DUPLICATE_ARTIFACT_PATH", "OUTSIDE_RUN_DIRECTORY"}
           for item in artifact_integrity):
        artifact_status = "FAILED"

    official_status = STATUS_NOT_RUN
    if official_validation != "skip":
        official = run_rocrate_validator(crate_root)
        official_status = official.status
        if official_validation == "require" and not official.passed:
            raise ValueError(
                "Official rocrate-validator did not validate this crate "
                f"({official.status}): {official.log[:500]}"
            )

    return NextflowExecutionSummary(
        pipeline_name=str(computed_name),
        pipeline_version=pipeline_version,
        nextflow_version=nextflow_version,
        execution_status=execution_status,
        run_dir=str(resolved_run),
        samplesheet_path=str(Path(samplesheet_path)) if samplesheet_path else None,
        sample_count=0,
        samples=[],
        biological_replicates_count=0,
        min_replicates_per_condition=0,
        conditions_count=0,
        total_processes=total,
        succeeded_processes=succeeded,
        failed_processes=failed,
        cached_processes=0,
        total_cpu_hours=0.0,
        peak_rss_gb=0.0,
        software_versions=software_versions,
        primary_outputs=primary_outputs,
        derived_evidence_factors=[],
        provenance_source=PROVENANCE_WRROC,
        crate_path=str(metadata_path),
        official_validation_status=official_status,
        workflow_run_id=workflow_run_id,
        workflow_id=_entity_id(workflow_run.get("instrument")),
        crate_sha256=_sha256_file(metadata_path),
        primary_inputs=primary_inputs,
        artifact_integrity_status=artifact_status,
        artifact_integrity=artifact_integrity,
    )
