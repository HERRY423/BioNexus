#!/usr/bin/env python3
"""Fail-closed audit for Scientific Semantics neutral governance records."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOVERNANCE_ROOT = REPOSITORY_ROOT / "governance" / "scientific-semantics"


def read_object(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: cannot read JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label}: must be a JSON object")
        return {}
    return value


def validate_document(root: Path, document_name: str, schema_name: str, errors: list[str]) -> dict[str, Any]:
    document = read_object(root / document_name, document_name, errors)
    schema = read_object(root / "schemas" / schema_name, schema_name, errors)
    if document and schema:
        for issue in sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in issue.path) or "<root>"
            errors.append(f"{document_name}:{location}: {issue.message}")
    return document


def council_gate_failures(root: Path, model: dict[str, Any], roster: dict[str, Any], errors: list[str]) -> list[str]:
    gates = model.get("council_formation_gates", {})
    members = [member for member in roster.get("members", []) if member.get("voting") is True]
    count = len(members)
    failures: list[str] = []
    if count < gates.get("minimum_voting_seats", 7) or count > gates.get("maximum_voting_seats", 11):
        failures.append("voting_seat_count")
    if not count:
        failures.extend(
            [
                "non_bionexus_majority",
                "single_employer_cap",
                "commercial_vendor_cap",
                "representation_mix",
                "independent_chair",
                "current_disclosures",
            ]
        )
    else:
        non_bionexus = sum(not member.get("bionexus_affiliated", True) for member in members) / count
        if non_bionexus + 1e-12 < gates.get("minimum_non_bionexus_fraction", 1):
            failures.append("non_bionexus_majority")
        employer_fraction = max(Counter(member.get("employer_group") for member in members).values()) / count
        if employer_fraction - 1e-12 > gates.get("maximum_single_employer_fraction", 0):
            failures.append("single_employer_cap")
        vendor_fraction = sum(member.get("commercial_vendor_affiliated", True) for member in members) / count
        if vendor_fraction - 1e-12 > gates.get("maximum_commercial_vendor_fraction", 0):
            failures.append("commercial_vendor_cap")

        representations = Counter(
            representation for member in members for representation in member.get("representations", [])
        )
        required = {
            "institutional_end_user": gates.get("minimum_institutional_end_user_seats", 2),
            "implementation_interoperability": gates.get("minimum_implementation_interoperability_seats", 2),
            "statistics_methods": gates.get("minimum_statistics_methods_seats", 1),
            "ontology_data_stewardship": gates.get("minimum_ontology_data_stewardship_seats", 1),
        }
        if any(representations[key] < minimum for key, minimum in required.items()):
            failures.append("representation_mix")

        member_by_id = {member.get("member_id"): member for member in members}
        chair = member_by_id.get(roster.get("chair_member_id"))
        if chair is None or chair.get("bionexus_affiliated") is not False:
            failures.append("independent_chair")
        if any(not member.get("disclosure_current") for member in members):
            failures.append("current_disclosures")
        for member in members:
            disclosure_path = root / str(member.get("disclosure_path", ""))
            if not disclosure_path.is_file():
                errors.append(f"missing member disclosure: {member.get('member_id')} -> {disclosure_path}")
                if "current_disclosures" not in failures:
                    failures.append("current_disclosures")
                continue
            disclosure = read_object(disclosure_path, f"disclosure for {member.get('member_id')}", errors)
            try:
                disclosure_expired = date.fromisoformat(str(disclosure.get("expires_on"))) < date.today()
            except ValueError:
                disclosure_expired = True
            if (
                disclosure.get("person_id") != member.get("member_id")
                or disclosure.get("role") != "council_member"
                or disclosure.get("bionexus_affiliated") != member.get("bionexus_affiliated")
                or disclosure.get("commercial_vendor_affiliated") != member.get("commercial_vendor_affiliated")
                or disclosure_expired
            ):
                errors.append(f"member disclosure is stale or inconsistent: {member.get('member_id')}")
                if "current_disclosures" not in failures:
                    failures.append("current_disclosures")

    observer_ids = roster.get("selection_observer_ids", [])
    if len(set(observer_ids)) < gates.get("independent_selection_observers_required", 2):
        failures.append("independent_selection_observers")
    member_ids = {member.get("member_id") for member in roster.get("members", [])}
    disclosures_by_person: dict[str, dict[str, Any]] = {}
    for path in (root / "disclosures").glob("*.json"):
        document = read_object(path, path.name, errors)
        if document.get("person_id"):
            disclosures_by_person[str(document["person_id"])] = document
    for observer_id in observer_ids:
        disclosure = disclosures_by_person.get(observer_id, {})
        try:
            disclosure_expired = date.fromisoformat(str(disclosure.get("expires_on"))) < date.today()
        except ValueError:
            disclosure_expired = True
        if (
            observer_id in member_ids
            or disclosure.get("role") != "selection_observer"
            or disclosure.get("bionexus_affiliated") is not False
            or disclosure.get("commercial_vendor_affiliated") is not False
            or disclosure_expired
        ):
            errors.append(f"selection observer is missing, conflicted, or stale: {observer_id}")
            if "independent_selection_observers" not in failures:
                failures.append("independent_selection_observers")
    opened = roster.get("nomination_opened_on")
    closed = roster.get("nomination_closed_on")
    try:
        nomination_days = (date.fromisoformat(closed) - date.fromisoformat(opened)).days
    except (TypeError, ValueError):
        nomination_days = -1
    if nomination_days < gates.get("minimum_public_nomination_days", 30):
        failures.append("public_nomination_period")
    return list(dict.fromkeys(failures))


def validate_governance(root: Path = DEFAULT_GOVERNANCE_ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for schema_path in sorted((root / "schemas").glob("*.schema.json")):
        schema = read_object(schema_path, schema_path.name, errors)
        if schema:
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:  # jsonschema exposes several schema-error subclasses
                errors.append(f"{schema_path.name}: invalid JSON Schema: {exc}")

    model = validate_document(root, "governance-model.json", "governance-model.schema.json", errors)
    roster = validate_document(root, "council-roster.json", "council-roster.schema.json", errors)
    adoption = validate_document(
        root,
        "institutional-adoption-registry.json",
        "institutional-adoption-registry.schema.json",
        errors,
    )
    assurance = validate_document(root, "assurance-registry.json", "assurance-registry.schema.json", errors)
    if not all((model, roster, adoption, assurance)):
        return errors

    powers = model["powers"]
    allowed_by_power = {name: set(value["allowed_actions"]) for name, value in powers.items()}
    for name, value in powers.items():
        overlap = set(value["allowed_actions"]) & set(value["prohibited_actions"])
        if overlap:
            errors.append(f"power {name} both allows and prohibits: {sorted(overlap)}")
    names = sorted(allowed_by_power)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = allowed_by_power[left] & allowed_by_power[right]
            if overlap:
                errors.append(f"reserved actions overlap between {left} and {right}: {sorted(overlap)}")
    for action, owner in model["exclusive_action_owners"].items():
        if action not in allowed_by_power[owner]:
            errors.append(f"exclusive owner {owner} does not allow action {action}")
        for other in set(powers) - {owner}:
            if action not in set(powers[other]["prohibited_actions"]):
                errors.append(f"exclusive action {action} is not prohibited for {other}")

    gate_failures = council_gate_failures(root, model, roster, errors)
    if model["status"] != roster["status"]:
        errors.append("model and roster council status differ")
    if model["independence_claim"] != roster["independence_claim"]:
        errors.append("model and roster independence claims differ")
    if model["status"] == "ACTIVE_INDEPENDENT":
        if gate_failures:
            errors.append(f"active independent council fails formation gates: {gate_failures}")
        if model["independence_claim"] != "INDEPENDENT_GATES_VERIFIED":
            errors.append("active council lacks verified independence claim")
        if roster["formation_gate_status"] != "MET" or roster["unmet_gates"]:
            errors.append("active roster does not record all formation gates as met")
    else:
        if model["independence_claim"] == "INDEPENDENT_GATES_VERIFIED":
            errors.append("non-active council claims verified independence")
        if roster["independence_claim"] == "INDEPENDENT_GATES_VERIFIED":
            errors.append("non-active roster claims verified independence")
        if not roster["unmet_gates"]:
            errors.append("forming or suspended roster must disclose unmet gates")
        expected_gate_status = "NOT_MET" if model["status"] == "FORMING" else "SUSPENDED"
        if roster["formation_gate_status"] != expected_gate_status:
            errors.append(f"{model['status']} roster must use formation_gate_status={expected_gate_status}")
        if model["normative_effect"] == "COUNCIL_ADOPTED":
            errors.append("non-active council cannot claim Council-adopted normative effect")

    active_declarations = [
        item for item in adoption["declarations"] if item["status"] == "active" and item["role"] != "standards_liaison"
    ]
    if adoption["verified_active_organization_count"] != len(active_declarations):
        errors.append("institutional adoption active count does not match declarations")
    if model["institutional_adoption_state"]["verified_active_organization_count"] != len(active_declarations):
        errors.append("governance model adoption count does not match registry")
    adoption_schema = read_object(root / "schemas" / "adoption-declaration.schema.json", "adoption schema", errors)
    for item in adoption["declarations"]:
        path = root / item["declaration_path"]
        document = read_object(path, item["declaration_id"], errors)
        if document and adoption_schema:
            for issue in Draft202012Validator(adoption_schema).iter_errors(document):
                errors.append(f"{path}:{issue.message}")
        if document and document.get("declaration_id") != item["declaration_id"]:
            errors.append(f"adoption declaration ID mismatch: {path}")
        if document:
            for field in ("organization", "role", "status", "expires_on"):
                if document.get(field) != item.get(field):
                    errors.append(f"adoption declaration {field} mismatch: {path}")
            if document.get("status") == "active":
                try:
                    declared = datetime.fromisoformat(str(document["declared_at"]).replace("Z", "+00:00")).astimezone(
                        timezone.utc
                    )
                    expires = date.fromisoformat(str(document["expires_on"]))
                except (KeyError, TypeError, ValueError):
                    errors.append(f"active adoption has invalid dates: {path}")
                else:
                    if expires < date.today():
                        errors.append(f"active adoption is expired: {path}")
                    if (expires - declared.date()).days > 550:
                        errors.append(f"adoption validity exceeds 18 months: {path}")
    listed_adoption_paths = {item["declaration_path"] for item in adoption["declarations"]}
    actual_adoption_paths = {path.relative_to(root).as_posix() for path in (root / "adopters").glob("*.json")}
    if listed_adoption_paths != actual_adoption_paths:
        errors.append(
            "adoption registry inventory mismatch; "
            f"unlisted={sorted(actual_adoption_paths - listed_adoption_paths)}, "
            f"missing={sorted(listed_adoption_paths - actual_adoption_paths)}"
        )

    recognized = [item for item in assurance["recognized_assessment_bodies"] if item["status"] == "recognized"]
    assurance_state = model["assurance_state"]
    if assurance_state["recognized_assessment_body_count"] != len(recognized):
        errors.append("governance model recognized CAB count does not match assurance registry")
    body_schema = read_object(root / "schemas" / "assurance-body.schema.json", "assurance body schema", errors)
    for item in assurance["recognized_assessment_bodies"]:
        path = root / item["record_path"]
        document = read_object(path, item["body_id"], errors)
        if document and body_schema:
            for issue in Draft202012Validator(body_schema).iter_errors(document):
                errors.append(f"{path}:{issue.message}")
        if document and document.get("body_id") != item["body_id"]:
            errors.append(f"assurance body ID mismatch: {path}")
    listed_body_paths = {item["record_path"] for item in assurance["recognized_assessment_bodies"]}
    actual_body_paths = {path.relative_to(root).as_posix() for path in (root / "assurance-bodies").glob("*.json")}
    if listed_body_paths != actual_body_paths:
        errors.append(
            "assurance body registry inventory mismatch; "
            f"unlisted={sorted(actual_body_paths - listed_body_paths)}, "
            f"missing={sorted(listed_body_paths - actual_body_paths)}"
        )

    operational = assurance["status"] == "OPERATIONAL"
    if assurance_state["status"] != assurance["status"]:
        errors.append("governance model assurance status does not match assurance registry")
    if assurance_state["badge_issuance_enabled"] != assurance["badge_issuance_enabled"]:
        errors.append("governance model badge state does not match assurance registry")
    if operational:
        if not recognized:
            errors.append("operational assurance has no recognized independent CAB")
        if model["status"] != "ACTIVE_INDEPENDENT":
            errors.append("assurance cannot operate before independent Council formation")
        if assurance["badge_issuance_enabled"] is not True:
            errors.append("operational assurance registry has badging disabled inconsistently")
        if assurance_state["certificate_registry_enabled"] is not True:
            errors.append("operational assurance has certificate registry disabled inconsistently")
    else:
        if assurance["badge_issuance_enabled"] is not False:
            errors.append("suspended assurance cannot enable badging")
        if assurance["certificates"]:
            errors.append("suspended assurance registry cannot contain certificates")
        if assurance_state["badge_issuance_enabled"] is not False:
            errors.append("suspended governance model cannot enable badging")
        if assurance_state["certificate_registry_enabled"] is not False:
            errors.append("suspended governance model cannot enable certificate registry")

    decision_schema = read_object(root / "schemas" / "decision-record.schema.json", "decision schema", errors)
    for path in sorted((root / "decisions").glob("*.json")):
        document = read_object(path, path.name, errors)
        if document and decision_schema:
            for issue in Draft202012Validator(decision_schema).iter_errors(document):
                errors.append(f"{path}:{issue.message}")
        if document.get("authority") == "interim_draft_stewards" and document.get("status") == "accepted":
            errors.append(f"interim draft stewards cannot accept a decision: {path.name}")
        if document.get("authority") == "scientific_semantics_council" and model["status"] != "ACTIVE_INDEPENDENT":
            errors.append(f"Council decision exists before Council formation: {path.name}")

    disclosure_schema = read_object(
        root / "schemas" / "conflict-disclosure.schema.json", "conflict disclosure schema", errors
    )
    for path in sorted((root / "disclosures").glob("*.json")):
        document = read_object(path, path.name, errors)
        if document and disclosure_schema:
            for issue in Draft202012Validator(disclosure_schema).iter_errors(document):
                errors.append(f"{path}:{issue.message}")

    reporter = root.parents[1] / "src" / "bionexus" / "bctk" / "reporters.py"
    try:
        reporter_source = reporter.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot verify BCTK badge suspension: {exc}")
    else:
        if not operational and "raise BadgeIssuanceSuspended" not in reporter_source:
            errors.append("BCTK reporter no longer fails closed on badge generation")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--governance-root", type=Path, default=DEFAULT_GOVERNANCE_ROOT)
    args = parser.parse_args(argv)
    errors = validate_governance(args.governance_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    model = json.loads((args.governance_root / "governance-model.json").read_text(encoding="utf-8"))
    print(
        "VALID "
        f"{model['governance_id']} status={model['status']} "
        f"independence={model['independence_claim']} "
        f"assurance={model['assurance_state']['status']} "
        f"adopters={model['institutional_adoption_state']['verified_active_organization_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
