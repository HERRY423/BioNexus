"""Regression checks for development evidence and reachable MCP transport."""
import asyncio
import io
import json
from pathlib import Path

import pytest

from bionexus.claim_semantics import ClaimClass, DeterministicClaimParser
from bionexus.evidence_index import EvidenceIndex
from bionexus.mcp import client
from bionexus.mcp.tools import literature


def test_release_correction_keeps_original_snapshot_and_current_bindings():
    from scripts.check_trust_restoration import check

    root = Path(__file__).resolve().parents[2]
    result = check(root)
    assert result["status"] == "PASS", result["errors"]


def test_release_correction_rejects_mutated_predecessor(tmp_path):
    from scripts.check_trust_restoration import check

    record = tmp_path / "review/corrections.json"
    record.parent.mkdir()
    (tmp_path / "old.json").write_text("changed")
    record.write_text(json.dumps({"supersedes": {"path": "old.json", "sha256": "0" * 64},
                                 "scientific_authorization": "NONE", "records": []}))
    result = check(tmp_path, "review/corrections.json")
    assert "Prior correction record changed" in result["errors"]


@pytest.mark.parametrize("text", [
    "CXCL13+ T cells are enriched in tumor",
    "Macrophage activation was measured in these cells",
    "The origin of these tumor cells is unknown",
])
def test_descriptions_do_not_invent_causal_mechanisms(text):
    result = DeterministicClaimParser.parse(text)
    assert result.claim_class not in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)


def test_dispatch_reaches_guarded_http_boundary(monkeypatch):
    from bionexus.mcp_server import handle_rpc_request_async

    calls = []

    def transport(request, **kwargs):
        calls.append((request.full_url, kwargs))
        return io.BytesIO(b'{"esearchresult":{"idlist":[],"count":"0"}}')

    monkeypatch.setenv("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "1")
    monkeypatch.setattr(client, "guarded_urlopen", transport)
    response = asyncio.run(handle_rpc_request_async({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "search_pubmed", "arguments": {"query": "TP53"}},
    }))
    assert calls and "eutils.ncbi.nlm.nih.gov" in calls[0][0]
    assert "error" not in response
    assert not response["result"].get("isError")
    assert json.loads(response["result"]["content"][0]["text"])["articles"] == []


def test_abstract_transport_failure_is_not_empty_source(monkeypatch):
    async def summary(*args, **kwargs):
        return {"result": {"123": {"title": "Fixture"}}}

    def unavailable(*args, **kwargs):
        raise OSError("Transport unavailable")

    monkeypatch.setattr(literature, "_get_http", lambda: summary)
    monkeypatch.setattr(literature, "guarded_urlopen", unavailable)
    result = asyncio.run(literature.tool_get_pubmed_article("123"))
    assert result["abstract_status"] == "FETCH_FAILED"
    assert result["abstract_error"] == "OSError"


def test_development_reports_cannot_self_promote(tmp_path):
    paths = [
        "validation/pseudobulk/studies/BN-PB-IV-006/REPORT.json",
        "validation/annotation/studies/BN-ANN-IV-004/REPORT.json",
        "validation/spatial/studies/BN-SP-IV-002/REPORT.json",
        "cross-host/MULTI_LAB_DOSSIER.json", "review/SCIENTIFIC_REVIEW.json",
    ]
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "APPROVED", "independent": True,
                                    "standard_14_satisfied": True}), encoding="utf-8")
    index = EvidenceIndex.build_current_index(tmp_path)
    for identifier in (
        "BNC-PSEUDOBULK-HARD-TRUTH-DCA", "BNC-ANNOTATION-FACS-BLINDED",
        "BNC-SPATIAL-PATHOLOGY-VALIDITY", "BNC-CROSS-HOST-MULTI-LAB",
        "BNC-INDEPENDENT-PEER-REVIEW",
    ):
        item = index.conclusions[identifier]
        assert item.verdict not in ("PASS", "APPROVED", "VERIFIED")
        assert item.data["scientific_authorization"] == "NONE"
        assert item.downstream_nodes == []


def test_retracted_datasets_do_not_count():
    from bionexus.ivn import evaluate_network, load_registry

    root = Path(__file__).resolve().parents[2]
    registry = load_registry(root / "validation/ivn/REGISTRY.json")
    withdrawn = {"BN-PB-IV-006", "BN-ANN-IV-004", "BN-SP-IV-002"}
    assert all(d.status == "RETRACTED" for d in registry.datasets if d.dataset_id in withdrawn)
    assert evaluate_network(registry, repo_root=root)["network_status"] == "INCOMPLETE"


def test_signature_cli_does_not_fill_missing_schema(monkeypatch, tmp_path, capsys):
    from bionexus.cli import main
    from bionexus.compliance_ledger import ComplianceAuditLedger

    target = tmp_path / "result.txt"
    target.write_text("local fixture", encoding="utf-8")
    ledger = ComplianceAuditLedger()
    signed = ledger.sign_artifact(signer_name="Test fixture", signer_email="fixture@example.invalid",
                                  signer_role="PI_SIGNER", signing_reason="test", artifact_path_or_bytes=target).to_dict()
    signature = tmp_path / "signature.json"
    signature.write_text(json.dumps(signed), encoding="utf-8")
    assert main(["compliance", "verify-sig", str(target), str(signature), "--json"]) == 0
    valid = json.loads(capsys.readouterr().out)
    assert valid["external_identity_trust"] == "NOT_ESTABLISHED"
    signed.pop("schema_version")
    signature.write_text(json.dumps(signed), encoding="utf-8")
    assert main(["compliance", "verify-sig", str(target), str(signature), "--json"]) == 1


@pytest.mark.parametrize("document", [{}, {"summary": {"satisfied": 14, "verdict": "CERTIFIED"}}])
def test_empty_or_self_certified_reports_cannot_inherit_success(tmp_path, document):
    path = tmp_path / "validation/spatial/CERTIFICATION.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    spatial = tmp_path / "validation/spatial/studies/BN-SP-IV-001/REPORT.json"
    spatial.parent.mkdir(parents=True)
    spatial.write_text("{}", encoding="utf-8")
    index = EvidenceIndex.build_current_index(tmp_path)
    for identifier in ("BNC-SPATIAL-CAPABILITY-VALIDATED", "BNC-SP-001-TECH-ACCEPTANCE"):
        item = index.conclusions[identifier]
        assert item.verdict.startswith("NOT_ASSESSED")
        assert item.claim_boundary["supported"] == []


def test_current_certification_cannot_be_promoted_by_editing_summary(tmp_path):
    root = Path(__file__).resolve().parents[2]
    relative = "validation/pseudobulk/CERTIFICATION.json"
    report = json.loads((root / relative).read_text(encoding="utf-8"))
    report["summary"]["verdict"] = "CERTIFIED"
    report["summary"]["satisfied"] = 14
    for standard in report["standards"]:
        standard["satisfied"] = True
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(report), encoding="utf-8")
    item = EvidenceIndex.build_current_index(tmp_path).conclusions["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"]
    assert item.verdict.startswith("NOT_ASSESSED")


def test_certification_summary_does_not_reintroduce_old_scientific_metrics(tmp_path):
    root = Path(__file__).resolve().parents[2]
    relative = "validation/pseudobulk/CERTIFICATION.json"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes((root / relative).read_bytes())
    item = EvidenceIndex.build_current_index(tmp_path).conclusions["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"]
    assert item.verdict == "VALIDATED"
    supported = " ".join(item.claim_boundary["supported"])
    assert "0.66" not in supported
    assert "validation passed" not in supported.lower()
    assert "failures" in supported


@pytest.mark.parametrize("overlap", [None, 0.2, 0.5])
def test_reference_overlap_is_required_and_never_replaced_by_a_passing_default(tmp_path, overlap):
    path = tmp_path / "validation/pseudobulk/REPORT.json"
    path.parent.mkdir(parents=True)
    metrics = [{"name": "unrelated_metric", "observed": 1}]
    if overlap is not None:
        metrics.append({"name": "published_support_fraction", "observed": overlap})
    path.write_text(json.dumps({"status": "fail" if overlap == 0.2 else "pass",
                                "dataset": {"id": "fixture"}, "pipeline": {"id": "fixture"},
                                "metrics": metrics}), encoding="utf-8")
    item = EvidenceIndex.build_current_index(tmp_path).conclusions["BNC-PSEUDOBULK-GSE96583"]
    if overlap is None:
        assert item.verdict.startswith("NOT_ASSESSED")
        assert item.claim_boundary["supported"] == []
    else:
        assert str(overlap) in item.statement
        assert ">= 0.50" not in item.statement
        assert item.verdict == ("FAIL" if overlap == 0.2 else "PASS")
