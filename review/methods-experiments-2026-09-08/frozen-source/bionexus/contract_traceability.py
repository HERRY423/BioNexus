"""Offline BNS requirement-to-evidence traceability.

This module audits declared evidence.  It does not execute tools, decide what a
researcher should do next, or infer that a test passed merely because its file
exists.  Executed evidence must be supplied through a content-bound receipt.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

_REQUIREMENT_RE = re.compile(r"(?<![A-Z0-9-])(BNS-[A-Z0-9]+-\d+[A-Z]?)(?![A-Z0-9])")
_DEFINITION_RE = re.compile(r"^\s*[-*]\s+\*\*(BNS-[A-Z0-9]+-\d+[A-Z]?)\b")
_NORMATIVE_RE = re.compile(r"\b(MUST NOT|SHOULD NOT|MUST|SHOULD|MAY)\b")


class EvidenceKind(str, Enum):
    IMPLEMENTATION = "implementation"
    TEST = "test"
    EVALUATION = "evaluation"
    DOCUMENTATION = "documentation"
    GAP = "gap"


class EvidenceState(str, Enum):
    INVALID_REFERENCE = "invalid_reference"
    DOCUMENTED_ONLY = "documented_only"
    DECLARED_UNVERIFIED = "declared_unverified"
    IMPLEMENTATION_BOUND = "implementation_bound"
    TESTED = "tested"
    EVALUATED = "evaluated"
    ACKNOWLEDGED_GAP = "acknowledged_gap"


_STATE_RANK = {
    EvidenceState.INVALID_REFERENCE: -1,
    EvidenceState.ACKNOWLEDGED_GAP: 0,
    EvidenceState.DOCUMENTED_ONLY: 1,
    EvidenceState.DECLARED_UNVERIFIED: 2,
    EvidenceState.IMPLEMENTATION_BOUND: 3,
    EvidenceState.TESTED: 4,
    EvidenceState.EVALUATED: 5,
}


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    document: str
    line: int
    normative_level: str
    text: str


@dataclass(frozen=True)
class EvidenceDeclaration:
    kind: EvidenceKind
    target: str
    note: str = ""


@dataclass(frozen=True)
class ExecutionReceipt:
    """An explicit record of successful execution bound to exact file bytes."""

    receipt_id: str
    evidence_kind: EvidenceKind
    command: str
    passed_targets: tuple[str, ...]
    artifact_sha256: Mapping[str, str]
    outcome: str = "passed"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionReceipt":
        return cls(
            receipt_id=str(value["receipt_id"]),
            evidence_kind=EvidenceKind(value["evidence_kind"]),
            command=str(value.get("command", "")),
            passed_targets=tuple(str(item) for item in value.get("passed_targets", [])),
            artifact_sha256={str(k): str(v) for k, v in value.get("artifact_sha256", {}).items()},
            outcome=str(value.get("outcome", "passed")),
        )


@dataclass(frozen=True)
class ResolvedEvidence:
    declaration: EvidenceDeclaration
    reference_valid: bool
    executed: bool
    reason: str


@dataclass(frozen=True)
class RequirementTrace:
    requirement: Requirement
    state: EvidenceState
    evidence: tuple[ResolvedEvidence, ...] = ()


@dataclass(frozen=True)
class TraceabilityReport:
    traces: tuple[RequirementTrace, ...]
    duplicate_requirement_ids: tuple[str, ...] = ()
    unknown_manifest_ids: tuple[str, ...] = ()

    @property
    def total_requirements(self) -> int:
        return len(self.traces)

    def count(self, state: EvidenceState) -> int:
        return sum(trace.state == state for trace in self.traces)

    def coverage(self) -> dict[str, float | int]:
        total = self.total_requirements

        def fraction(predicate: Any) -> float:
            return 0.0 if total == 0 else sum(bool(predicate(trace)) for trace in self.traces) / total

        def has_valid(trace: RequirementTrace, kind: EvidenceKind | None = None, *, executed: bool = False) -> bool:
            return any(
                item.reference_valid
                and (kind is None or item.declaration.kind == kind)
                and (not executed or item.executed)
                and item.declaration.kind != EvidenceKind.GAP
                for item in trace.evidence
            )

        return {
            "requirements": total,
            "reference_coverage": fraction(lambda trace: has_valid(trace)),
            "implementation_reference_coverage": fraction(
                lambda trace: has_valid(trace, EvidenceKind.IMPLEMENTATION)
            ),
            "executed_test_coverage": fraction(
                lambda trace: has_valid(trace, EvidenceKind.TEST, executed=True)
            ),
            "executed_evaluation_coverage": fraction(
                lambda trace: has_valid(trace, EvidenceKind.EVALUATION, executed=True)
            ),
            "invalid_references": self.count(EvidenceState.INVALID_REFERENCE),
            "acknowledged_gaps": self.count(EvidenceState.ACKNOWLEDGED_GAP),
            "unspecified_normative_levels": sum(
                trace.requirement.normative_level == "UNSPECIFIED" for trace in self.traces
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.coverage(),
            "duplicate_requirement_ids": list(self.duplicate_requirement_ids),
            "unknown_manifest_ids": list(self.unknown_manifest_ids),
            "traces": [
                {
                    "requirement": asdict(trace.requirement),
                    "state": trace.state.value,
                    "evidence": [
                        {
                            "kind": item.declaration.kind.value,
                            "target": item.declaration.target,
                            "note": item.declaration.note,
                            "reference_valid": item.reference_valid,
                            "executed": item.executed,
                            "reason": item.reason,
                        }
                        for item in trace.evidence
                    ],
                }
                for trace in self.traces
            ],
        }


def discover_requirements(spec_dir: str | Path) -> tuple[list[Requirement], list[str]]:
    """Discover all normative requirement paragraphs without prefix de-duplication."""

    directory = Path(spec_dir)
    requirements: list[Requirement] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for path in sorted(directory.glob("BNS-*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            # Only a normative definition bullet creates a requirement.  Cross
            # references and conformance tables may repeat the same ID while
            # also containing RFC-2119 words; treating them as definitions
            # creates false duplicates and unstable totals.
            match = _DEFINITION_RE.search(lines[index])
            if not match:
                index += 1
                continue
            requirement_id = match.group(1)
            paragraph = [lines[index].strip()]
            cursor = index + 1
            while cursor < len(lines):
                line = lines[cursor]
                if not line.strip() or _DEFINITION_RE.search(line):
                    break
                if line.startswith("#") or line.startswith("|"):
                    break
                paragraph.append(line.strip())
                cursor += 1
            text = " ".join(part for part in paragraph if part)
            levels = _NORMATIVE_RE.findall(text)
            if requirement_id in seen:
                duplicates.append(requirement_id)
            else:
                seen.add(requirement_id)
                requirements.append(
                    Requirement(
                        requirement_id=requirement_id,
                        document=path.name,
                        line=index + 1,
                        normative_level=levels[0] if levels else "UNSPECIFIED",
                        text=text,
                    )
                )
            index = max(cursor, index + 1)
    return requirements, sorted(set(duplicates))


def load_manifest(path: str | Path) -> dict[str, list[EvidenceDeclaration]]:
    manifest_path = Path(path)
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("requirements", raw)
    if not isinstance(entries, Mapping):
        raise ValueError("Traceability manifest must map requirement IDs to evidence declarations")
    result: dict[str, list[EvidenceDeclaration]] = {}
    for requirement_id, value in entries.items():
        declarations = value.get("evidence", []) if isinstance(value, Mapping) else value
        if not isinstance(declarations, Sequence) or isinstance(declarations, (str, bytes)):
            raise ValueError(f"Evidence for {requirement_id} must be a list")
        result[str(requirement_id)] = [
            EvidenceDeclaration(
                kind=EvidenceKind(item["kind"]),
                target=str(item.get("target", "")),
                note=str(item.get("note", "")),
            )
            for item in declarations
        ]
    return result


def load_receipts(path: str | Path | None) -> list[ExecutionReceipt]:
    if path is None:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw.get("receipts", raw)
    if not isinstance(entries, list):
        raise ValueError("Receipt document must contain a list")
    return [ExecutionReceipt.from_dict(item) for item in entries]


def _sha256_raw(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_file(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _split_target(target: str) -> tuple[str, str | None]:
    file_part, separator, selector = target.partition("::")
    return file_part.replace("\\", "/"), selector if separator else None


def _python_symbols(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return set()
    symbols: set[str] = set()

    def visit(body: Iterable[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}.{node.name}" if prefix else node.name
                symbols.add(name)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name)

    visit(tree.body)
    return symbols


def _reference_valid(root: Path, declaration: EvidenceDeclaration) -> tuple[bool, Path | None, str]:
    if declaration.kind == EvidenceKind.GAP:
        return True, None, "explicitly acknowledged gap"
    file_part, selector = _split_target(declaration.target)
    path = _safe_file(root, file_part)
    if path is None or not path.is_file():
        return False, path, "target file is missing or outside repository root"
    if selector is not None:
        if path.suffix != ".py":
            return False, path, "selectors are supported only for Python source/test files"
        if selector not in _python_symbols(path):
            return False, path, f"Python symbol/test node '{selector}' was not found"
    return True, path, "reference resolves"


def _has_valid_receipt(
    declaration: EvidenceDeclaration,
    path: Path | None,
    receipts: Sequence[ExecutionReceipt],
) -> bool:
    if path is None or declaration.kind not in {EvidenceKind.TEST, EvidenceKind.EVALUATION}:
        return False
    expected_hash = _sha256_raw(path)
    file_part, _ = _split_target(declaration.target)
    for receipt in receipts:
        if receipt.evidence_kind != declaration.kind or receipt.outcome != "passed":
            continue
        if declaration.target not in receipt.passed_targets:
            continue
        if receipt.artifact_sha256.get(file_part) == expected_hash:
            return True
    return False


def audit_traceability(
    *,
    repo_root: str | Path,
    spec_dir: str | Path,
    manifest: Mapping[str, Sequence[EvidenceDeclaration]],
    receipts: Sequence[ExecutionReceipt] = (),
) -> TraceabilityReport:
    root = Path(repo_root).resolve()
    requirements, duplicates = discover_requirements(spec_dir)
    known_ids = {requirement.requirement_id for requirement in requirements}
    traces: list[RequirementTrace] = []

    for requirement in requirements:
        declarations = tuple(manifest.get(requirement.requirement_id, ()))
        resolved: list[ResolvedEvidence] = []
        for declaration in declarations:
            valid, path, reason = _reference_valid(root, declaration)
            executed = valid and _has_valid_receipt(declaration, path, receipts)
            resolved.append(ResolvedEvidence(declaration, valid, executed, reason))

        if any(not item.reference_valid for item in resolved):
            state = EvidenceState.INVALID_REFERENCE
        elif any(item.declaration.kind == EvidenceKind.GAP for item in resolved):
            state = EvidenceState.ACKNOWLEDGED_GAP
        elif not resolved:
            state = EvidenceState.DOCUMENTED_ONLY
        else:
            states = [EvidenceState.DECLARED_UNVERIFIED]
            if any(item.declaration.kind == EvidenceKind.IMPLEMENTATION for item in resolved):
                states.append(EvidenceState.IMPLEMENTATION_BOUND)
            if any(item.declaration.kind == EvidenceKind.TEST and item.executed for item in resolved):
                states.append(EvidenceState.TESTED)
            if any(item.declaration.kind == EvidenceKind.EVALUATION and item.executed for item in resolved):
                states.append(EvidenceState.EVALUATED)
            state = max(states, key=_STATE_RANK.__getitem__)
        traces.append(RequirementTrace(requirement, state, tuple(resolved)))

    return TraceabilityReport(
        traces=tuple(traces),
        duplicate_requirement_ids=tuple(duplicates),
        unknown_manifest_ids=tuple(sorted(set(manifest) - known_ids)),
    )
