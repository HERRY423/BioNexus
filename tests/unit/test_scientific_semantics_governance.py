"""Governance firewalls for BNS-022 neutral scientific semantics stewardship."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import yaml

from bionexus.bctk.reporters import BadgeIssuanceSuspended, generate_svg_badge
from bionexus.bctk.spec import ConformanceTier
from bionexus.spec_registry import validate_spec_registry

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_ROOT = REPOSITORY_ROOT / "governance" / "scientific-semantics"


def load_governance_validator():
    path = REPOSITORY_ROOT / "scripts" / "validate_semantic_governance.py"
    spec = importlib.util.spec_from_file_location("bns022_governance_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def governance_copy(tmp_path: Path) -> Path:
    target = tmp_path / "governance"
    shutil.copytree(GOVERNANCE_ROOT, target)
    return target


def test_current_governance_state_is_truthful_and_valid() -> None:
    validator = load_governance_validator()
    assert validator.validate_governance(GOVERNANCE_ROOT) == []

    model = read_json(GOVERNANCE_ROOT / "governance-model.json")
    roster = read_json(GOVERNANCE_ROOT / "council-roster.json")
    adoption = read_json(GOVERNANCE_ROOT / "institutional-adoption-registry.json")
    assurance = read_json(GOVERNANCE_ROOT / "assurance-registry.json")
    assert model["status"] == roster["status"] == "FORMING"
    assert model["independence_claim"] == "NOT_YET_ESTABLISHED"
    assert roster["members"] == []
    assert adoption["verified_active_organization_count"] == 0
    assert adoption["declarations"] == []
    assert assurance["status"] == "SUSPENDED_NO_INDEPENDENT_BODY"
    assert assurance["recognized_assessment_bodies"] == []
    assert assurance["certificates"] == []
    assert assurance["badge_issuance_enabled"] is False


def test_reserved_technical_commercial_and_certification_actions_do_not_overlap() -> None:
    model = read_json(GOVERNANCE_ROOT / "governance-model.json")
    powers = model["powers"]
    allowed = {name: set(power["allowed_actions"]) for name, power in powers.items()}
    assert allowed["technical"].isdisjoint(allowed["commercial"])
    assert allowed["technical"].isdisjoint(allowed["certification"])
    assert allowed["commercial"].isdisjoint(allowed["certification"])
    assert model["exclusive_action_owners"] == {
        "approve_semantic_specification": "technical",
        "approve_registry_release": "technical",
        "manage_namespace": "technical",
        "set_product_price": "commercial",
        "operate_products": "commercial",
        "recognize_assessment_body": "certification",
        "assess_named_implementation": "certification",
        "issue_certificate": "certification",
    }


def test_empty_roster_cannot_be_relabelled_independent(tmp_path: Path) -> None:
    root = governance_copy(tmp_path)
    model = read_json(root / "governance-model.json")
    roster = read_json(root / "council-roster.json")
    model.update(
        status="ACTIVE_INDEPENDENT",
        independence_claim="INDEPENDENT_GATES_VERIFIED",
        normative_effect="COUNCIL_ADOPTED",
    )
    roster.update(
        status="ACTIVE_INDEPENDENT",
        independence_claim="INDEPENDENT_GATES_VERIFIED",
        formation_gate_status="MET",
        unmet_gates=[],
    )
    write_json(root / "governance-model.json", model)
    write_json(root / "council-roster.json", roster)

    errors = load_governance_validator().validate_governance(root)
    assert any("fails formation gates" in error for error in errors)


def test_commercial_operator_cannot_take_technical_release_power(tmp_path: Path) -> None:
    root = governance_copy(tmp_path)
    model = read_json(root / "governance-model.json")
    model["powers"]["commercial"]["allowed_actions"].append("approve_registry_release")
    write_json(root / "governance-model.json", model)

    errors = load_governance_validator().validate_governance(root)
    assert any("reserved actions overlap" in error for error in errors)


def test_certification_cannot_activate_without_independent_cab_and_council(tmp_path: Path) -> None:
    root = governance_copy(tmp_path)
    model = read_json(root / "governance-model.json")
    assurance = read_json(root / "assurance-registry.json")
    model["assurance_state"].update(
        status="OPERATIONAL",
        badge_issuance_enabled=True,
        certificate_registry_enabled=True,
    )
    assurance.update(status="OPERATIONAL", badge_issuance_enabled=True)
    write_json(root / "governance-model.json", model)
    write_json(root / "assurance-registry.json", assurance)

    errors = load_governance_validator().validate_governance(root)
    assert any("no recognized independent CAB" in error for error in errors)
    assert any("before independent Council formation" in error for error in errors)


def test_adoption_count_cannot_be_increased_without_declaration(tmp_path: Path) -> None:
    root = governance_copy(tmp_path)
    adoption = read_json(root / "institutional-adoption-registry.json")
    adoption["verified_active_organization_count"] = 1
    write_json(root / "institutional-adoption-registry.json", adoption)

    errors = load_governance_validator().validate_governance(root)
    assert any("adoption active count" in error for error in errors)


def test_badging_remains_fail_closed() -> None:
    with pytest.raises(BadgeIssuanceSuspended):
        generate_svg_badge(ConformanceTier.GOLD)


def test_bns022_is_registered_without_mutating_frozen_bns019_release() -> None:
    assert validate_spec_registry(REPOSITORY_ROOT / "spec") == []
    registry = yaml.safe_load((REPOSITORY_ROOT / "spec" / "registry.yaml").read_text(encoding="utf-8"))
    assert registry["documents"][-1]["id"] == "BNS-022"
    release = read_json(REPOSITORY_ROOT / "standards" / "scientific-semantic-conventions" / "release-manifest.json")
    assert release["version"] == "0.1.0"
    assert release["release_digest_sha256"] == "b3164afe6ccd69dc9d7738c2ee58195ac65862701e29f9db1f98c12e1a97e934"


def test_public_entrypoints_parse_and_preserve_forming_boundary() -> None:
    paths = [
        REPOSITORY_ROOT / ".github" / "ISSUE_TEMPLATE" / "6_scientific_semantics_rfc.yml",
        REPOSITORY_ROOT / ".github" / "ISSUE_TEMPLATE" / "7_scientific_semantics_council_nomination.yml",
        REPOSITORY_ROOT / ".github" / "ISSUE_TEMPLATE" / "8_scientific_semantics_adoption.yml",
        REPOSITORY_ROOT / ".github" / "workflows" / "bns022-governance.yml",
    ]
    documents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
    assert all(isinstance(document, dict) for document in documents)
    rfc_text = paths[0].read_text(encoding="utf-8")
    nomination_text = paths[1].read_text(encoding="utf-8")
    assert "not accepted Council decisions" in rfc_text
    assert "Nomination does not create a Council seat" in nomination_text
