"""
Unit tests for the BioNexus Capability Certification Program (BNS-010).

Validates:
1. The 14-criteria catalog and core subset.
2. Tiers are COMPUTED from evidence, never asserted (BNS-CF-002).
3. CERTIFIED requires all 14 criteria — structural honesty.
4. Honest reporting: current tier distribution and M4 gap are published.
5. Structural cross-checks re-verify contract-derived criteria.
6. CLI surface.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.certification import (
    _EVIDENCE,
    CERTIFICATION_CRITERIA,
    CORE_CRITERIA,
    FLAGSHIP_CAPABILITIES,
    CertificationRecord,
    CertificationTier,
    _clamp_flagship_external_static,
    certification_report,
    certify_capability,
    compute_tier,
)
from bionexus.cli import main as cli_main


def test_criteria_catalog_complete():
    """The certification program MUST define exactly the 14 criteria (BNS-010 §3)."""
    expected = {
        "reference_backend", "formal_input_contract", "invariants", "known_failure_modes",
        "positive_test", "negative_test", "adversarial_test", "public_reference_dataset",
        "independent_ground_truth", "parameter_perturbation", "degradation_test",
        "provenance_test", "cross_host_test", "external_reviewer",
    }
    assert set(CERTIFICATION_CRITERIA.keys()) == expected
    assert set(CORE_CRITERIA) <= expected
    assert len(CERTIFICATION_CRITERIA) == 14


def test_certified_requires_all_fourteen():
    """CERTIFIED MUST require all 14 criteria — no partial certification (BNS-CF-002)."""
    all_ok = {name: True for name in CERTIFICATION_CRITERIA}
    assert compute_tier(all_ok) == CertificationTier.CERTIFIED

    for missing in CERTIFICATION_CRITERIA:
        partial = dict(all_ok)
        partial[missing] = False
        assert compute_tier(partial) != CertificationTier.CERTIFIED, missing


def test_tier_ladder():
    """VALIDATED needs core; EXPERIMENTAL needs contract + one test class; else CONNECTOR-ONLY."""
    core_ok = {c: True for c in CORE_CRITERIA}
    core_ok.update({n: False for n in CERTIFICATION_CRITERIA if n not in CORE_CRITERIA})
    assert compute_tier(core_ok) == CertificationTier.VALIDATED

    minimal = {n: False for n in CERTIFICATION_CRITERIA}
    minimal["formal_input_contract"] = True
    minimal["positive_test"] = True
    assert compute_tier(minimal) == CertificationTier.EXPERIMENTAL

    empty = {n: False for n in CERTIFICATION_CRITERIA}
    assert compute_tier(empty) == CertificationTier.CONNECTOR_ONLY


def test_report_is_honest_about_current_state():
    """The report MUST publish real tiers and the M4 gap (BNS-CF-005)."""
    report = certification_report()
    tiers = report["tier_distribution"]
    assert set(tiers.keys()) == {"CERTIFIED", "VALIDATED", "EXPERIMENTAL", "CONNECTOR-ONLY"}

    # Honest current state: zero CERTIFIED; capabilities hold real evidence tiers
    assert report["certified_count"] == len(tiers["CERTIFIED"])
    assert report["m4_gap"] == max(0, report["m4_target_certified"] - report["certified_count"])
    assert len(tiers["VALIDATED"]) >= 5, "core-criteria capabilities must reach VALIDATED"
    assert "variant.acmg_classification" in tiers["VALIDATED"]
    assert "nextflow.pipeline_launch" in tiers["EXPERIMENTAL"]

    # Every record carries its blocking roadmap
    for cid, rec in report["records"].items():
        assert rec["tier"] in {t.value for t in CertificationTier}
        blocking = rec["blocking_for_certified"]
        assert len(blocking) == 14 - rec["satisfied_count"]
        if rec["tier"] != "CERTIFIED":
            assert blocking, f"{cid} must list its certification roadmap"


def test_structural_cross_check_prevents_drift():
    """Certification MUST re-verify contract-derived criteria live (BNS-CF-004)."""
    # The taxonomy and ABI must back the criteria the records claim
    for cid in certification_report()["records"]:
        rec = certify_capability(cid)
        if rec.criteria["known_failure_modes"].satisfied:
            assert rec.criteria["known_failure_modes"].evidence  # pointers, not vibes
        assert isinstance(rec, CertificationRecord)
    # A capability with unknown id must fail loudly
    try:
        certify_capability("does.not_exist")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_certification_cli(capsys):
    """CLI publishes the honest tier table and roadmap."""
    assert cli_main(["certification"]) == 0
    out = capsys.readouterr().out
    assert "CERTIFIED" in out
    assert "VALIDATED" in out
    assert "honest gap" in out
    assert "roadmap" in out
    assert "scrna.pseudobulk_de" in out


def test_flagship_static_cross_host_cannot_self_satisfy():
    """A headless trap comparison must not light cross_host_test by itself."""
    clamped = _clamp_flagship_external_static(
        {
            "cross_host_test": (True, "cross-host/COMPARISON.json", "headless"),
            "external_reviewer": (True, "review/SCIENTIFIC_REVIEW.json", "slots"),
        }
    )
    assert clamped["cross_host_test"][0] is False
    assert clamped["external_reviewer"][0] is False
    for capability_id in FLAGSHIP_CAPABILITIES:
        record = certify_capability(capability_id)
        assert record.criteria["cross_host_test"].satisfied is False, capability_id
        assert record.criteria["external_reviewer"].satisfied is False, capability_id
        assert "cross_host_test" in record.blocking_for_certified


def test_flagship_static_true_cannot_pass_certify(monkeypatch):
    """Removing today's False bits must still fail closed without an IVN raise."""
    patched = dict(_EVIDENCE["scrna.pseudobulk_de"])
    patched["cross_host_test"] = (True, "cross-host/COMPARISON.json", "headless")
    patched["external_reviewer"] = (True, "review/SCIENTIFIC_REVIEW.json", "slots")
    monkeypatch.setitem(_EVIDENCE, "scrna.pseudobulk_de", patched)
    record = certify_capability("scrna.pseudobulk_de")
    assert record.criteria["cross_host_test"].satisfied is False
    assert record.criteria["external_reviewer"].satisfied is False


def test_headless_comparison_pass_does_not_satisfy_cross_host():
    import json

    data = json.loads((_REPO_ROOT / "cross-host" / "COMPARISON.json").read_text(encoding="utf-8"))
    assert data["overall"]["conformance_verdict"] == "pass"
    assert certify_capability("scrna.pseudobulk_de").criteria["cross_host_test"].satisfied is False
