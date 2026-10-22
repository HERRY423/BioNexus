"""Shared nf-prov Workflow Run RO-Crate fixture writer for unit tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_nf_prov_crate(
    run_dir: Path,
    *,
    pipeline_name: str = "nf-core/rnaseq",
    pipeline_version: str = "3.14.0",
    nextflow_version: str = "23.10.0",
    failed: bool = False,
) -> Path:
    """Write a minimal nf-prov-shaped Workflow Run RO-Crate under pipeline_info/."""
    pipe_info = run_dir / "pipeline_info"
    pipe_info.mkdir(parents=True, exist_ok=True)
    counts = b"gene\tCTRL_1\tCTRL_2\tTREAT_1\nG1\t10\t12\t50\n"
    report = b"<html>MultiQC Complete</html>"
    (run_dir / "salmon.merged.gene_counts.tsv").write_bytes(counts)
    (run_dir / "multiqc_report.html").write_bytes(report)
    status = (
        "http://schema.org/ActionStatusType/FailedActionStatus"
        if failed
        else "http://schema.org/ActionStatusType/CompletedActionStatus"
    )
    doc: Dict[str, Any] = {
        "@context": [
            "https://w3id.org/ro/crate/1.1/context",
            "https://w3id.org/ro/terms/workflow-run/context",
        ],
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": [
                    {"@id": "https://w3id.org/ro/crate/1.1"},
                    {"@id": "https://w3id.org/ro/wfrun/process/0.5"},
                    {"@id": "https://w3id.org/ro/wfrun/workflow/0.5"},
                ],
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": f"{pipeline_name} run",
                "mainEntity": {"@id": "workflow.nf"},
                "mentions": [{"@id": "#workflow-run"}],
            },
            {
                "@id": "workflow.nf",
                "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
                "name": pipeline_name,
                "version": pipeline_version,
            },
            {
                "@id": "#nextflow",
                "@type": "SoftwareApplication",
                "name": "Nextflow",
                "version": nextflow_version,
            },
            {
                "@id": "#workflow-run",
                "@type": "CreateAction",
                "name": pipeline_name,
                "instrument": {"@id": "workflow.nf"},
                "agent": {"@id": "#nextflow"},
                "result": [
                    {"@id": "salmon.merged.gene_counts.tsv"},
                    {"@id": "multiqc_report.html"},
                ],
                "actionStatus": {"@id": status},
            },
            {
                "@id": "#process/FASTQC",
                "@type": "CreateAction",
                "name": "NFCORE_RNASEQ:FASTQC (sample1)",
                "actionStatus": {"@id": "http://schema.org/ActionStatusType/CompletedActionStatus"},
            },
            {
                "@id": "#process/SALMON",
                "@type": "CreateAction",
                "name": "NFCORE_RNASEQ:SALMON_QUANT (sample1)",
                "actionStatus": {"@id": "http://schema.org/ActionStatusType/CompletedActionStatus"},
            },
            {
                "@id": "salmon.merged.gene_counts.tsv",
                "@type": "File",
                "name": "gene counts",
                "sha256": sha256_bytes(counts),
            },
            {
                "@id": "multiqc_report.html",
                "@type": "File",
                "name": "MultiQC report",
                "sha256": sha256_bytes(report),
            },
        ],
    }
    metadata = pipe_info / "ro-crate-metadata.json"
    metadata.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return metadata
