"""Unit tests for data governance (bionexus.governance): classification + egress policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.cli import main
from bionexus.governance import (
    GOVERNANCE_SIDECAR_SUFFIX,
    check_egress_policy,
    classify_dataset,
    detect_sensitivity_signals,
    iter_governed_endpoints,
    zone_for_endpoint,
)


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    p = tmp_path / "cohort_counts.h5ad"
    p.write_bytes(b"ann-data-bytes")
    return p


# ----------------------------------------------------------------- classification


def test_undeclared_defaults_to_internal(dataset: Path):
    payload = classify_dataset(dataset, write_sidecar=False)
    rec = payload["classification"]
    assert rec["effective_tier"] == "INTERNAL"
    assert rec["declared_tier"] is None
    assert rec["signals_detected"] == []


def test_phi_signals_cap_declared_tier(tmp_path: Path):
    p = tmp_path / "patient_metadata.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    payload = classify_dataset(p, declared_tier="PUBLIC", write_sidecar=False)
    rec = payload["classification"]
    assert rec["signal_capped"] is True
    assert rec["effective_tier"] == "SENSITIVE"
    assert "patient" in rec["signals_detected"]


def test_declared_restriction_never_lowered_by_signals(tmp_path: Path):
    p = tmp_path / "diagnosis_summary.txt"
    p.write_text("x", encoding="utf-8")
    payload = classify_dataset(p, declared_tier="SENSITIVE", write_sidecar=False)
    assert payload["classification"]["effective_tier"] == "SENSITIVE"
    payload = classify_dataset(p, declared_tier="RESTRICTED", write_sidecar=False)
    assert payload["classification"]["effective_tier"] == "RESTRICTED"


def test_metadata_signals_count(tmp_path: Path):
    p = tmp_path / "samples.tsv"
    p.write_text("x", encoding="utf-8")
    signals = detect_sensitivity_signals(p, {"cohort_note": "collected at city hospital"})
    assert "hospital" in signals


def test_sidecar_is_written_and_hash_bound(dataset: Path, tmp_path: Path):
    payload = classify_dataset(dataset)
    rec = payload["classification"]
    sidecar = Path(rec["sidecar"])
    assert sidecar.is_file()
    assert sidecar.name == dataset.name + GOVERNANCE_SIDECAR_SUFFIX
    on_disk = json.loads(sidecar.read_text(encoding="utf-8"))
    assert on_disk["sha256"] == rec["sha256"]
    assert len(on_disk["sha256"]) == 64


def test_classify_refuses_missing_file_and_bad_tier(tmp_path: Path):
    assert classify_dataset(tmp_path / "ghost.csv", write_sidecar=False)["refused"] is True
    p = tmp_path / "ok.csv"
    p.write_text("x", encoding="utf-8")
    payload = classify_dataset(p, declared_tier="TOP_SECRET", write_sidecar=False)
    assert payload["refused"] is True


# ------------------------------------------------------------------ policy matrix


@pytest.mark.parametrize(
    "tier,zone,ack,expected",
    [
        ("PUBLIC", "EXTERNAL", False, "PERMITTED"),
        ("INTERNAL", "LOCAL", False, "PERMITTED"),
        ("INTERNAL", "EXTERNAL", False, "DEGRADED_ADVISORY"),
        ("SENSITIVE", "LOCAL", False, "PERMITTED"),
        ("SENSITIVE", "ORGANIZATION", False, "DEGRADED_ADVISORY"),
        ("SENSITIVE", "EXTERNAL", False, "ABSTAIN"),
        ("RESTRICTED", "EXTERNAL", False, "ABSTAIN"),
        ("RESTRICTED", "ORGANIZATION", False, "ABSTAIN"),
        ("RESTRICTED", "LOCAL", False, "ABSTAIN"),
        ("RESTRICTED", "LOCAL", True, "PERMITTED"),
    ],
)
def test_policy_matrix(tier, zone, ack, expected):
    payload = check_egress_policy(tier, zone, allow_restricted_local_ack=ack)
    assert payload["policy"]["decision"] == expected, payload
    if expected == "ABSTAIN":
        assert payload["policy"]["remedies"], "abstentions must carry actionable remedies"


def test_policy_refuses_unknown_tier_or_zone():
    assert check_egress_policy("TOP_SECRET", "LOCAL")["refused"] is True
    assert check_egress_policy("PUBLIC", "MOON")["refused"] is True


def test_zone_for_endpoint_mapping():
    assert zone_for_endpoint("pubmed") == "EXTERNAL"
    assert zone_for_endpoint("chembl") == "EXTERNAL"
    assert zone_for_endpoint("bionexus-local-mcp") == "LOCAL"
    assert zone_for_endpoint("local") == "LOCAL"
    # Unknown endpoints resolve conservatively to EXTERNAL.
    assert zone_for_endpoint("totally-unknown-endpoint") == "EXTERNAL"


def test_iter_governed_endpoints_covers_local_and_hosted():
    endpoints = {e["endpoint"]: e["zone"] for e in iter_governed_endpoints()}
    assert endpoints["bionexus-local-mcp"] == "LOCAL"
    assert endpoints["pubmed"] == "EXTERNAL"


def test_sensitive_plus_hosted_endpoint_abstains():
    from bionexus.governance import assert_query_permitted

    payload = assert_query_permitted("SENSITIVE", "pubmed")
    assert payload["policy"]["decision"] == "ABSTAIN"
    assert payload["policy"]["endpoint"] == "pubmed"
    assert payload["policy"]["zone"] == "EXTERNAL"


# ---------------------------------------------------------------------- CLI


def test_cli_data_classify_and_policy(tmp_path: Path, capsys):
    p = tmp_path / "patient_x.csv"
    p.write_text("a\n1\n", encoding="utf-8")
    assert main(["data-classify", str(p), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["classification"]["effective_tier"] == "SENSITIVE"  # signal cap
    capsys.readouterr()

    assert main(["policy", "check", "--tier", "SENSITIVE", "--endpoint", "pubmed", "--json"]) == 1
    capsys.readouterr()
    assert main(["policy", "check", "--tier", "PUBLIC", "--endpoint", "pubmed", "--json"]) == 0
    capsys.readouterr()
    assert main(["policy", "check", "--tier", "RESTRICTED", "--endpoint", "local", "--ack-restricted-local", "--json"]) == 0


def test_cli_concordance_and_external_validation(tmp_path: Path, capsys):
    primary = tmp_path / "markers.csv"
    primary.write_text("names,scores\n" + "\n".join(f"g{i},{i}" for i in range(20)) + "\n", encoding="utf-8")
    orthogonal = tmp_path / "de.csv"
    orthogonal.write_text("gene,stat\n" + "\n".join(f"g{i},{i * 3}" for i in range(20)) + "\n", encoding="utf-8")
    assert main(["concordance", str(primary), str(orthogonal), "--top-k", "5", "--json"]) == 0
    assert '"grade": "A"' in capsys.readouterr().out

    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"gold": ["g1", "g2", "g3"]}), encoding="utf-8")
    predicted = tmp_path / "pred.csv"
    predicted.write_text("gene,score\ng1,9\ng2,8\ng3,7\ng4,1\n", encoding="utf-8")
    assert main(["external-validation", str(predicted), str(truth), "--truth-key", "gold", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audit"]["recall"] == 1.0


def test_cli_concordance_conflict_exits_nonzero(tmp_path: Path):
    primary = tmp_path / "a.csv"
    primary.write_text("names,scores\n" + "\n".join(f"g{i},{i}" for i in range(20)) + "\n", encoding="utf-8")
    reversed_table = tmp_path / "b.csv"
    reversed_table.write_text("gene,stat\n" + "\n".join(f"g{i},{19 - i}" for i in range(20)) + "\n", encoding="utf-8")
    assert main(["concordance", str(primary), str(reversed_table), "--json"]) == 1
