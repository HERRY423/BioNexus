"""Validation for the single authoritative BioNexus specification registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

_ID_PATTERN = re.compile(r"^BNS-(\d{3})$")


def validate_spec_registry(spec_dir: Path) -> list[str]:
    """Return all numbering, identity, and coverage errors in ``spec/registry.yaml``."""
    errors: list[str] = []
    registry_path = spec_dir / "registry.yaml"
    if not registry_path.is_file():
        return ["spec/registry.yaml is missing"]
    raw: Mapping[str, Any] = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    freeze = raw.get("numbering_freeze")
    freeze_n: int | None = None
    if not isinstance(freeze, dict) or not freeze.get("max_id"):
        errors.append("registry numbering_freeze.max_id is required")
    else:
        freeze_match = _ID_PATTERN.fullmatch(str(freeze.get("max_id", "")))
        if freeze_match is None:
            errors.append(f"invalid numbering_freeze.max_id: {freeze.get('max_id')!r}")
        else:
            freeze_n = int(freeze_match.group(1))
    documents = raw.get("documents", [])
    if not isinstance(documents, list):
        return errors + ["registry documents must be a list"]

    ids: list[str] = []
    files: list[str] = []
    numbers: list[int] = []
    for index, entry in enumerate(documents):
        if not isinstance(entry, dict):
            errors.append(f"document entry {index} is not an object")
            continue
        spec_id = str(entry.get("id", ""))
        filename = str(entry.get("file", ""))
        title = str(entry.get("title", "")).strip()
        match = _ID_PATTERN.fullmatch(spec_id)
        if not match:
            errors.append(f"invalid specification id: {spec_id!r}")
            continue
        ids.append(spec_id)
        files.append(filename)
        numbers.append(int(match.group(1)))
        if not title:
            errors.append(f"{spec_id} has no title")
        if not filename.startswith(f"{spec_id}-"):
            errors.append(f"{spec_id} filename does not preserve its identifier: {filename}")
        path = spec_dir / filename
        if not path.is_file():
            errors.append(f"{spec_id} registered file is missing: {filename}")
            continue
        first_heading = next((line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("#")), "")
        if spec_id not in first_heading:
            errors.append(f"{spec_id} is absent from the first heading of {filename}")

    if len(ids) != len(set(ids)):
        errors.append("duplicate specification identifier")
    if len(files) != len(set(files)):
        errors.append("duplicate specification filename")
    if numbers and sorted(numbers) != list(range(min(numbers), max(numbers) + 1)):
        errors.append("specification numbering contains a gap")
    if freeze_n is not None and numbers and max(numbers) > freeze_n:
        errors.append(
            f"specification freeze at BNS-{freeze_n:03d}; "
            f"BNS-{max(numbers):03d} exceeds the freeze"
        )
    actual = {path.name for path in spec_dir.glob("BNS-*.md")}
    registered = set(files)
    for filename in sorted(actual - registered):
        errors.append(f"unregistered specification file: {filename}")
    for filename in sorted(registered - actual):
        errors.append(f"registered specification file is absent: {filename}")
    index_path = spec_dir / "README.md"
    if not index_path.is_file():
        errors.append("spec/README.md document index is missing")
    else:
        entries = re.findall(
            r"^\|\s*\[(BNS-\d{3})\]\(([^)]+)\)",
            index_path.read_text(encoding="utf-8"), re.MULTILINE,
        )
        for spec_id, filename in zip(ids, files):
            matches = [target for index_id, target in entries if index_id == spec_id]
            if matches != [filename]:
                errors.append(f"{spec_id} index must link exactly once to {filename}")
        for spec_id, _ in entries:
            if spec_id not in ids:
                errors.append(f"unregistered specification in document index: {spec_id}")
    return errors
