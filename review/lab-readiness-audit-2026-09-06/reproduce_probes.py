"""Bounded implementation probes. No biological analysis or network traffic."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bionexus.analysis_audit import AnalysisDocument, CodeCell, audit_analysis
from bionexus.evidence_model import assess_evidence, extract_evidence_factors
from bionexus.lims_hub import BenchlingConnector, LIMSConnectionConfig, LIMSConnectorType
from bionexus.pseudobulk_warrant import evaluate_pseudobulk_inferential_warrant


def main() -> None:
    sources = [
        "src/bionexus/pseudobulk_warrant.py", "src/bionexus/evidence_model.py",
        "src/bionexus/analysis_audit.py", "src/bionexus/lims_hub.py",
        "src/bionexus/debt.py", "src/bionexus/claim_semantics.py",
        "src/bionexus/tool_receipt.py",
    ]
    source_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    results = {
        "scope": "Direct Python API probes; not full tests, live-host tests, or biological validation",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": source_hashes,
        "public_pseudobulk_api": evaluate_pseudobulk_inferential_warrant(
            n_donors_per_group=3, is_interventional=True
        ).to_dict(),
    }
    factors = extract_evidence_factors({
        "min_replicates_per_condition": 3, "batch_corrected": True, "parameter_sweep": True,
    })
    results["declared_metadata_assessment"] = asdict(assess_evidence(satisfied_factors=factors))
    code = "sc.tl.rank_genes_groups(adata, groupby='condition')"
    results["static_audit"] = {}
    for label, source in [("plain", code), ("comment_added", "# TODO: pseudobulk later\n" + code)]:
        document = AnalysisDocument(path="in-memory.py", language="python", code_cells=[CodeCell(index=0, source=source)])
        with patch("bionexus.analysis_audit.load_analysis_document", return_value=document):
            audit = audit_analysis("in-memory.py")
            results["static_audit"][label] = {"passed": audit.passed, "rules": [f.rule_id for f in audit.findings]}
    connector = BenchlingConnector(LIMSConnectionConfig(
        connector_type=LIMSConnectorType.BENCHLING, auth_token="mock-test-token",
    ))
    results["lims_empty_measurement"] = connector.format_assay_payload("schema-test", "plate-test", [{}])
    response = Mock(status_code=200)
    response.json.return_value = {"assayResultIds": ["test"]}
    with patch.dict(os.environ, {"BIONEXUS_AIRGAP_MODE": "AIRGAP_STRICT", "BIONEXUS_EGRESS_MODE": "OFFLINE_STRICT"}), patch(
        "bionexus.lims_hub.requests.post", return_value=response
    ) as send:
        outcome = connector.export_assay_results(
            "schema-test", "plate-test", [{"well": "A1", "value": 1, "unit": "RFU", "sample_id": "test"}],
            mock_response=False,
        )
        results["lims_transport_boundary"] = {
            "requests_post_reached": send.called, "result_success": outcome.success, "real_network_calls": 0,
            "scope": "Direct connector API; network function replaced with an in-memory mock",
        }
    results["source_stable_during_probe"] = all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in source_hashes.items()
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
