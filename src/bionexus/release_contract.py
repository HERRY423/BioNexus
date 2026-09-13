"""Validate a frozen support surface and human-supplied GA activation record.

Record validation cannot authenticate a person's identity or invent acceptance.
"""
from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

from bionexus.validation_history import read_object

SCOPE_PATH = "src/bionexus/data/core-support.v1.json"


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not re.search(r"PENDING|TODO|TBD|PLACEHOLDER|<|>", value, re.I)


REQUIRED_ACCEPTANCE_CATEGORIES = (
    "core_quality",
    "de_contract",
    "installed_wheel",
    "static_checks",
    "validation_history",
    "evidence_index",
)


def check_release(root: Path, version: str) -> dict[str, Any]:
    errors: list[str] = []
    stable = re.fullmatch(r"1\.\d+\.\d+", version) is not None
    recognized = stable or re.fullmatch(r"1\.\d+\.\d+-(?:rc|alpha|beta)\.\d+", version) is not None
    try:
        if not recognized:
            raise ValueError("Unsupported release version; cannot infer prerelease or GA")
        scope_path = root / SCOPE_PATH
        scope = read_object(scope_path)
        if (scope.get("schema") != "bionexus.core-support.v1"
                or scope.get("contract_id") != "bionexus.core-1-supported-surface.v1"
                or scope.get("scientific_authorization") != "NONE"
                or scope.get("status") != "FROZEN_SCOPE_SUPPORT_NOT_ACTIVATED"):
            raise ValueError("Invalid frozen support contract")
        for key in ("supported_cli", "supported_python", "supported_schemas", "experimental", "non_goals"):
            values = scope.get(key)
            if not isinstance(values, list) or not values or not all(_text(v) for v in values) or len(set(values)) != len(values):
                raise ValueError(f"Invalid support scope: {key}")
        for key, expected in (("support_months", 12), ("previous_minor_critical_backport_days", 90),
                              ("eol_notice_days", 90), ("api_removal_minimum_minor_releases", 2),
                              ("api_removal_minimum_months", 6)):
            if type(scope.get(key)) is not int or scope[key] != expected:
                raise ValueError(f"Contract policy drift: {key}")
        if stable:
            record = read_object(root / "release/GA_ACTIVATION.json")
            if record.get("schema") != "bionexus.ga-activation.v1" or record.get("status") != "ACTIVATED":
                raise ValueError("GA support has not been activated by named maintainers")
            # The 1.x support clock starts once, at the first 1.0 GA. A minor or
            # patch release must not silently restart a twelve-month promise.
            if record.get("version") != "1.0.0" or record.get("scientific_authorization") != "NONE":
                raise ValueError("Activation version or authority mismatch")
            # Hash canonical LF bytes so the same release contract travels across OSes.
            if record.get("scope_sha256") != hashlib.sha256(scope_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest():
                raise ValueError("Activation does not bind the supported scope")
            start = date.fromisoformat(record["release_date"])
            end = date.fromisoformat(record["support_end_date"])
            anniversary = date(start.year + 1, start.month, min(start.day, calendar.monthrange(start.year + 1, start.month)[1]))
            if end != anniversary:
                raise ValueError("Support window must be 12 calendar months")
            people = record.get("maintainers")
            if not isinstance(people, list) or not people:
                raise ValueError("Named accepting maintainers are required")
            for person in people:
                if (not isinstance(person, dict) or not _text(person.get("name"))
                        or person.get("accepted") is not True or not _text(person.get("acceptance_reference"))
                        or date.fromisoformat(person["accepted_on"]) > start):
                    raise ValueError("Invalid or missing maintainer acceptance")
            if not _text(record.get("release_security_contact")):
                raise ValueError("Release/security contact required")
            if not isinstance(record.get("limitations"), list) or not record["limitations"] or not all(_text(x) for x in record["limitations"]):
                raise ValueError("Explicit limitations required")
            checks = record.get("verification_records")
            if not isinstance(checks, list) or not checks:
                raise ValueError("Hash-bound verification records required")
            seen_categories = set()
            for check in checks:
                if not isinstance(check, dict) or not _text(check.get("path")) or not _text(check.get("sha256")):
                    raise ValueError("Invalid verification record format")
                path = root / check["path"]
                path.resolve().relative_to(root.resolve())
                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != check["sha256"]:
                    raise ValueError("Verification record missing or modified")
                cat = check.get("category")
                if not _text(cat) or cat not in REQUIRED_ACCEPTANCE_CATEGORIES:
                    raise ValueError(f"Unrecognized or missing acceptance category: {cat}")
                seen_categories.add(cat)
                if check.get("status") != "PASSED":
                    raise ValueError(f"Acceptance category '{cat}' did not pass: status={check.get('status')}")
                if check.get("candidate_version") != record.get("version"):
                    raise ValueError(f"Acceptance record '{cat}' candidate version mismatch: expected {record.get('version')}")
            missing_categories = set(REQUIRED_ACCEPTANCE_CATEGORIES) - seen_categories
            if missing_categories:
                raise ValueError(f"Missing required acceptance categories: {sorted(missing_categories)}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {
        "schema": "bionexus.release-contract-check.v1",
        "version": version,
        "status": "BLOCKED" if errors else ("ACTIVATION_RECORD_VALID" if stable else "RC_SCOPE_VALID"),
        "errors": errors,
        "identity_authentication": "NOT_PERFORMED",
        "maintainer_signoff_verification": "MANUAL_INSPECTION_REQUIRED",
        "scientific_authorization": "NONE",
    }
