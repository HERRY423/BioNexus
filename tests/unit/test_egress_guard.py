"""
Unit tests for BioNexus Data Governance & Egress Guard (BNS-SEC-001..010).

Validates:
1. OFFLINE_STRICT mode blocks all external network/cloud MCP egress.
2. ALLOWLIST mode permits approved scientific knowledge domains with safe queries.
3. ALLOWLIST mode blocks unapproved external domains.
4. ALLOWLIST mode blocks raw count matrices, large payloads, and clinical PHI.
5. Secrets (GitHub tokens, API keys) are detected and blocked.
6. CONTROLLED_ACCESS_GENOMIC and RESTRICTED_CLINICAL_PHI data force local compute.
7. Cryptographic audit trail generation and response hashing.
8. CLI `bionexus security` commands (egress-policy, audit, sbom).
"""

from __future__ import annotations

import json
from pathlib import Path

from bionexus.cli import main as cli_main
from bionexus.egress_guard import (
    DataClassification,
    DataGovernanceGuard,
    EgressMode,
)


def test_offline_strict_blocks_all_egress(tmp_path: Path):
    """OFFLINE_STRICT mode must block all external network and cloud MCP egress."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.OFFLINE_STRICT, audit_log_path=audit_file)

    permitted, record = guard.evaluate_request(
        endpoint="https://pubmed.ncbi.nlm.nih.gov/api",
        purpose="Search interferon response literature",
        payload={"query": "IFNG stimulation"},
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "OFFLINE_STRICT" in (record.block_reason or "")


def test_allowlist_permits_safe_knowledge_queries(tmp_path: Path):
    """ALLOWLIST mode permits queries for public gene symbols and literature to approved domains."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    permitted, record = guard.evaluate_request(
        endpoint="https://rest.uniprot.org/uniprotkb/P04637",
        purpose="Fetch TP53 protein sequence metadata",
        payload={"accession": "P04637", "fields": "gene_names,sequence"},
    )
    assert permitted
    assert record.outcome == "PERMITTED"
    assert len(record.payload_sha256) == 64


def test_allowlist_blocks_unapproved_domains(tmp_path: Path):
    """ALLOWLIST mode strictly blocks arbitrary or untrusted domains."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    permitted, record = guard.evaluate_request(
        endpoint="https://untrusted-cloud-service.com/api/v1",
        purpose="Fetch external annotations",
        payload={"query": "CD4"},
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "not in approved scientific ALLOWLIST" in (record.block_reason or "")


def test_allowlist_blocks_raw_expression_matrices(tmp_path: Path):
    """ALLOWLIST mode blocks transmission of raw count matrices or cell-by-gene tables."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    prohibited_payload = {
        "gene": "TP53",
        "raw_counts": [10, 20, 0, 5, 12, 100],
        "cell_by_gene": {"cell_1": 4.5, "cell_2": 2.1},
    }
    permitted, record = guard.evaluate_request(
        endpoint="https://pubmed.ncbi.nlm.nih.gov/api",
        purpose="Differential expression analysis verification",
        payload=prohibited_payload,
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "Prohibited field" in (record.block_reason or "") or "expression matrix" in (record.block_reason or "")


def test_allowlist_blocks_clinical_phi(tmp_path: Path):
    """ALLOWLIST mode blocks payloads containing Protected Health Information (PHI)."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    phi_payload = {
        "patient_id": "PT_99214",
        "mrn": "MRN-1029384",
        "cohort": "triple_negative_breast_cancer",
    }
    permitted, record = guard.evaluate_request(
        endpoint="https://api.opentargets.io/v3/platform/public/association/filter",
        purpose="Target association query",
        payload=phi_payload,
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "PHI" in (record.block_reason or "")


def test_allowlist_blocks_hardcoded_secrets(tmp_path: Path):
    """Payloads accidentally containing API keys or GitHub tokens must be intercepted."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    leaked_secret_payload = {
        "query": "EGFR",
        "user_token": "ghp_1234567890abcdefghijklmnopqrstuvwxyz1234",
    }
    permitted, record = guard.evaluate_request(
        endpoint="https://rest.ensembl.org/lookup/symbol/homo_sapiens/EGFR",
        purpose="Gene lookup",
        payload=leaked_secret_payload,
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "credential" in (record.block_reason or "").lower() or "token" in (record.block_reason or "").lower()


def test_controlled_access_genomic_forces_offline(tmp_path: Path):
    """Data classified as CONTROLLED_ACCESS_GENOMIC or RESTRICTED_CLINICAL_PHI forces OFFLINE_STRICT."""
    audit_file = tmp_path / "egress.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    permitted, record = guard.evaluate_request(
        endpoint="https://clinicaltrials.gov/api/v2/studies",
        purpose="Cohort matching",
        payload={"disease": "glioblastoma"},
        data_classification=DataClassification.CONTROLLED_ACCESS_GENOMIC,
    )
    assert not permitted
    assert record.outcome == "BLOCKED"
    assert "strictly requires OFFLINE_STRICT" in (record.block_reason or "")


def test_cryptographic_audit_logging_and_response_hashing(tmp_path: Path):
    """Audit records write to JSONL ledger and support cryptographic response hashing."""
    audit_file = tmp_path / "audit_ledger.jsonl"
    guard = DataGovernanceGuard(mode=EgressMode.ALLOWLIST, audit_log_path=audit_file)

    permitted, record = guard.evaluate_request(
        endpoint="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        purpose="Literature search",
        payload={"term": "single-cell RNA sequencing"},
    )
    assert permitted

    # Simulate response receipt
    guard.record_response(record.record_id, {"count": 42000, "id_list": ["31234567", "32345678"]})

    trail = guard.get_audit_trail()
    assert len(trail) == 1
    assert trail[0].response_hash is not None
    assert len(trail[0].response_hash) == 64

    # Verify disk persistence
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    disk_data = json.loads(lines[0])
    assert disk_data["record_id"] == record.record_id
    assert disk_data["payload_sha256"] == record.payload_sha256


def test_cli_security_egress_policy_and_sbom(tmp_path: Path, capsys):
    """Verify CLI `bionexus security egress-policy`, `audit`, and `sbom` commands."""
    exit_code = cli_main(["security", "egress-policy"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Data Governance & Egress Policy" in out

    exit_code_json = cli_main(["security", "egress-policy", "--json"])
    assert exit_code_json == 0

    sbom_path = tmp_path / "test_sbom.json"
    exit_code_sbom = cli_main(["security", "sbom", "-o", str(sbom_path)])
    assert exit_code_sbom == 0
    assert sbom_path.is_file()
    sbom_data = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom_data["bomFormat"] == "CycloneDX"
    assert len(sbom_data["components"]) >= 10
