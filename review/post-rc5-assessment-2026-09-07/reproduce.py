"""Read-only source audit probes; all counterexamples are synthetic and local.

Run from the repository root. This does not run biological analyses, send
network requests, or modify tracked scientific evidence.
"""
import copy
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from bionexus.analysis_audit import audit_analysis
from bionexus.de_audit import audit_differential_expression
from bionexus.de_audit_extract import extract_rank_genes_groups
from bionexus.evidence_index import EvidenceIndex
from bionexus.lims_hub import BenchlingConnector, LIMSConnectionConfig, LIMSConnectorType

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
results = {}


def summarize(result):
    return {
        "status": result.overall_status,
        "passed": result.passed,
        "maturity": result.claim_boundary.overall_maturity,
        "allowed": result.claim_boundary.allowed_scope,
        "findings": [f.rule_id for f in result.findings],
        "missing_checks": [c.check_id for c in result.checks if c.status.value == "MISSING_EVIDENCE"],
        "execution": result.execution_record.to_dict(),
    }


metadata = pd.DataFrame({"donor": [f"D{i}" for i in range(6)], "condition": ["A"]*3+["B"]*3})
plain_table = pd.DataFrame({"gene": ["G1"], "pvalue": [0.01], "padj": [0.02]})
schema_table = plain_table.assign(baseMean=100.0)
for label, kwargs in {
    "no_inputs": {},
    "metadata_only": {"sample_metadata": metadata},
    "plain_table_and_metadata": {"de_table": plain_table, "sample_metadata": metadata},
    "schema_column_only_upgrade": {"de_table": schema_table, "sample_metadata": metadata},
    "causal_claim_same_table": {"de_table": schema_table, "sample_metadata": metadata, "claim_text": "G1 causes disease and is a proven therapeutic target."},
    "invalid_probability_table": {"de_table": schema_table.assign(pvalue=-0.1, padj=-0.2), "sample_metadata": metadata},
    "null_result": {"de_table": pd.DataFrame({"gene": [f"G{i}" for i in range(101)], "pvalue": [0.01]*101, "padj": [0.5]*101, "baseMean": [100.0]*101}), "sample_metadata": metadata, "claim_text": "No genes were significant after FDR correction."},
}.items():
    results[label] = summarize(audit_differential_expression(**kwargs))

rgg = {
    "names": np.array([("IFITM1",), ("STAT1",)], dtype=[("A", "O")]),
    "pvals": np.array([(0.01,), (0.02,)], dtype=[("A", "f8")]),
    "pvals_adj": np.array([(0.02,), (0.03,)], dtype=[("A", "f8")]),
    "logfoldchanges": np.array([(1.0,), (2.0,)], dtype=[("A", "f8")]),
    "params": {"method": "wilcoxon", "groupby": "condition", "corr_method": "benjamini-hochberg"},
}
with patch.dict("sys.modules", {"scanpy": None}):
    extracted = extract_rank_genes_groups(SimpleNamespace(uns={"rank_genes_groups": rgg}))
results["scanpy_structured_array"] = {"scope": "Unified reader fallback probe. A separate AnnData structured-array integration test passed after NUMBA_CACHE_DIR was redirected into the writable workspace; the initial import stalled in numba cache creation.", "error": extracted.error, "records": extracted.frame.to_dict(orient="records")}

de_call = "sc.tl.rank_genes_groups(adata, groupby='condition')\n"
static_sources = {
    "plain": de_call,
    "string_literal": "note = 'pseudobulk later'\n" + de_call,
    "dead_branch": "if False:\n    pseudobulk_aggregate(adata)\n" + de_call,
    "unrelated_groupby": "summary = metadata.groupby('donor').size()\n" + de_call,
    "unrelated_pseudobulk": "pb = pseudobulk_aggregate(other_adata)\n" + de_call,
}
results["static_audit"] = {}
for label, source in static_sources.items():
    target = OUT / ("fixture_" + label + ".py")
    target.write_text(source, encoding="utf-8")
    result = audit_analysis(target)
    results["static_audit"][label] = {"passed": result.passed, "findings": [f.rule_id for f in result.findings]}

index = EvidenceIndex.load(ROOT / "validation/EVIDENCE_INDEX.json")
mutated = copy.deepcopy(index)
changed_hashes = 0
for entry in mutated.conclusions.values():
    entry.data = {}  # Restrict this probe to source hashes; no data-byte verification claim.
    for source in entry.source_files:
        entry.source_files[source] = "0"*64
        changed_hashes += 1
check = mutated.verify_index_integrity(ROOT)
results["tampered_source_hashes"] = {"changed_hashes": changed_hashes, **check}

verdict_probe = copy.deepcopy(index)
entry = verdict_probe.conclusions["BNC-PSEUDOBULK-GSE96583"]
verdict_probe.conclusions = {entry.conclusion_id: entry}
entry.data = {}
entry.verdict = "NOT_PASS"
results["incompatible_verdict_substring"] = verdict_probe.verify_index_integrity(ROOT)

conn = BenchlingConnector(LIMSConnectionConfig(connector_type=LIMSConnectorType.BENCHLING, project_id="synthetic_project"))
try:
    conn.format_assay_payload("schema", "plate", [{}])
    results["empty_lims_measurement"] = {"rejected": False}
except (ValueError, TypeError) as exc:
    results["empty_lims_measurement"] = {"rejected": True, "error": str(exc)}
with patch("bionexus.lims_hub.requests.post") as post:
    exported = conn.export_assay_results("schema", "plate", [{"well": "A1", "value": 1, "unit": "RFU", "sample_id": "synthetic"}], mock_response=False)
    results["live_lims_excluded"] = {"success": exported.success, "post_called": post.called, "metadata": exported.metadata}

source_paths = ["src/bionexus/de_audit.py", "src/bionexus/de_audit_extract.py", "src/bionexus/analysis_audit.py", "src/bionexus/evidence_index.py", "src/bionexus/lims_hub.py"]
payload = {
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "python": platform.python_version(),
    "scope": "Synthetic source behavior probes, not independent biological or real-host validation.",
    "source_sha256": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths},
    "results": results,
}
(OUT/"probe-results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(payload, indent=2, ensure_ascii=False))
