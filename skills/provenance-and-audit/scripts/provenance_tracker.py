#!/usr/bin/env python3
"""
Research-grade SHA-256 + environment snapshot. Not GxP or 21 CFR Part 11.
Generates cryptographically verifiable execution records, environment snapshots,
and W3C PROV-O JSON-LD lineage graphs for computational biology analyses.

Usage:
    from provenance_tracker import ProvenanceTracker

    tracker = ProvenanceTracker(activity_name="Single-Cell QC & scVI Training", operator="Computational Biologist")
    tracker.record_input_file("raw_pbmc.h5ad")
    tracker.record_parameters({"mad_counts": 5, "n_latent": 30, "batch_key": "batch"})
    tracker.record_output_file("adata_trained.h5ad")
    prov_record = tracker.finalize(output_dir="./provenance_output")
"""

import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_file_sha256(file_path: str) -> str:
    """Compute SHA-256 checksum of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def capture_environment_snapshot() -> Dict[str, Any]:
    """Capture complete execution environment details for reproducibility."""
    snapshot = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "packages": {},
    }

    # Record key package versions using standard importlib.metadata
    import importlib.metadata

    key_packages = [
        "numpy",
        "scipy",
        "pandas",
        "scanpy",
        "anndata",
        "torch",
        "scvi",
        "optuna",
        "allotropy",
        "polars",
        "jsonschema",
        "yaml",
    ]
    for pkg in key_packages:
        try:
            snapshot["packages"][pkg] = importlib.metadata.version(pkg)
        except Exception:
            try:
                mod = __import__(pkg)
                snapshot["packages"][pkg] = getattr(mod, "__version__", "installed")
            except Exception:
                pass

    # Record GPU hardware if available
    try:
        import torch

        snapshot["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            snapshot["cuda_device_count"] = torch.cuda.device_count()
            snapshot["cuda_device_name"] = torch.cuda.get_device_name(0)
            snapshot["cuda_version"] = torch.version.cuda
    except Exception:
        snapshot["cuda_available"] = False

    return snapshot


class ProvenanceTracker:
    def __init__(self, activity_name: str, operator: str = "Anonymous Researcher", notes: str = ""):
        self.activity_id = f"urn:uuid:{uuid.uuid4()}"
        self.activity_name = activity_name
        self.operator = operator
        self.notes = notes
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.input_files: List[Dict[str, Any]] = []
        self.output_files: List[Dict[str, Any]] = []
        self.parameters: Dict[str, Any] = {}
        self.environment = capture_environment_snapshot()

    def record_input_file(self, file_path: str, role: str = "raw_data") -> Dict[str, Any]:
        """Record an input file with its SHA-256 cryptographic hash."""
        p = Path(file_path)
        sha256 = compute_file_sha256(str(p)) if p.exists() else "FILE_NOT_FOUND"
        size = p.stat().st_size if p.exists() else 0

        record = {
            "entity_id": f"urn:hash:sha256:{sha256}",
            "file_name": p.name,
            "file_path": str(p.absolute()),
            "sha256": sha256,
            "size_bytes": size,
            "role": role,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.input_files.append(record)
        return record

    def record_parameters(self, params: Dict[str, Any]):
        """Record execution parameters."""
        self.parameters.update(params)

    def record_output_file(self, file_path: str, role: str = "processed_result") -> Dict[str, Any]:
        """Record an output artifact with its SHA-256 cryptographic hash."""
        p = Path(file_path)
        sha256 = compute_file_sha256(str(p)) if p.exists() else "FILE_PENDING"
        size = p.stat().st_size if p.exists() else 0

        record = {
            "entity_id": f"urn:hash:sha256:{sha256}",
            "file_name": p.name,
            "file_path": str(p.absolute()),
            "sha256": sha256,
            "size_bytes": size,
            "role": role,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.output_files.append(record)
        return record

    def generate_w3c_provo(self) -> Dict[str, Any]:
        """Generate standard W3C PROV-O JSON-LD ontology representation."""
        agent_id = f"urn:operator:{hashlib.sha256(self.operator.encode()).hexdigest()[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        prov_doc = {
            "@context": {
                "prov": "http://www.w3.org/ns/prov#",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                "bionexus": "https://agent-plugins.org/bionexus/prov#",
            },
            "@graph": [
                {
                    "@id": self.activity_id,
                    "@type": "prov:Activity",
                    "prov:startedAtTime": {"@type": "xsd:dateTime", "@value": self.start_time},
                    "prov:endedAtTime": {"@type": "xsd:dateTime", "@value": now},
                    "prov:wasAssociatedWith": {"@id": agent_id},
                    "bionexus:activityName": self.activity_name,
                    "bionexus:parameters": json.dumps(self.parameters),
                    "bionexus:environment": self.environment,
                },
                {"@id": agent_id, "@type": "prov:Agent", "prov:label": self.operator},
            ],
        }

        # Add input entities
        for inp in self.input_files:
            prov_doc["@graph"].append(
                {
                    "@id": inp["entity_id"],
                    "@type": "prov:Entity",
                    "prov:label": inp["file_name"],
                    "bionexus:sha256": inp["sha256"],
                    "bionexus:sizeBytes": inp["size_bytes"],
                    "bionexus:role": inp["role"],
                }
            )
            prov_doc["@graph"][0].setdefault("prov:used", []).append({"@id": inp["entity_id"]})

        # Add output entities
        for out in self.output_files:
            prov_doc["@graph"].append(
                {
                    "@id": out["entity_id"],
                    "@type": "prov:Entity",
                    "prov:label": out["file_name"],
                    "prov:wasGeneratedBy": {"@id": self.activity_id},
                    "bionexus:sha256": out["sha256"],
                    "bionexus:sizeBytes": out["size_bytes"],
                    "bionexus:role": out["role"],
                }
            )

        return prov_doc

    def finalize(self, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """Finalize provenance record and export W3C PROV JSON-LD and audit report."""
        now = datetime.now(timezone.utc).isoformat()
        prov_data = {
            "provenance_version": "1.1.0-research-sidecar",
            "compliance_note": ("SHA-256 + environment snapshot. Not 21 CFR Part 11, GxP, ALCOA+, or CLIA."),
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "operator": self.operator,
            "notes": self.notes,
            "start_time": self.start_time,
            "end_time": now,
            "parameters": self.parameters,
            "input_files": self.input_files,
            "output_files": self.output_files,
            "environment_snapshot": self.environment,
            "w3c_prov_o": self.generate_w3c_provo(),
        }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out_json = os.path.join(output_dir, "provenance_manifest.json")
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(prov_data, f, indent=2, ensure_ascii=False)
            print(f"FAIR Provenance manifest saved to: {out_json}")

        return prov_data
