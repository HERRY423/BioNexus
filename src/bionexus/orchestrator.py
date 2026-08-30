"""
Run Capsule chain orchestration for BioNexus.

Closes the orchestration gap: the Run Capsule artifact contract (``bionexus.artifacts``)
defined how *single* stages hand off to the next agent, but nothing executed a chain of
stages end-to-end. This module consumes a declarative chain specification (YAML or JSON),
executes its stages in topological order, wraps every stage in a full Run Capsule, and
aborts fail-closed on the first failing stage.

Honesty invariants:
- A failing stage marks the whole chain FAILED; downstream stages are recorded as
  ``SKIPPED_FAIL_CLOSED`` — the chain never reports partial success.
- Stage commands are argv lists executed without a shell (``shell=False`` always).
- The orchestrator guarantees execution fidelity and provenance capture only. It does
  not validate the *scientific* validity of a stage; that remains the responsibility of
  the stage's own capability contract and EvidenceCard.
- This is not a replacement for Nextflow / Airflow / Snakemake; it is the connective
  tissue between BioNexus capsule-producing stages.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from bionexus.artifacts import RunBundle
from bionexus.contracts import (
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    ExecutionState,
    attach_meta,
)

PathLike = Union[str, Path]

DEFAULT_STEP_TIMEOUT_SECONDS = 3600


class ChainValidationError(ValueError):
    """Raised when a chain specification is structurally invalid."""


@dataclass
class ChainStep:
    """One executable stage of a chain."""

    id: str
    name: str
    command: List[str]
    depends_on: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], index: int) -> "ChainStep":
        if not isinstance(raw, dict):
            raise ChainValidationError(f"Step #{index} must be a mapping, got {type(raw).__name__}")
        step_id = str(raw.get("id") or "").strip()
        if not step_id:
            raise ChainValidationError(f"Step #{index} is missing required field 'id'")
        command = raw.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
            raise ChainValidationError(
                f"Step '{step_id}': 'command' must be a non-empty list of strings (argv, no shell string)"
            )
        if command[0].startswith("sudo"):
            raise ChainValidationError(f"Step '{step_id}': privilege escalation (sudo) is not permitted in chains")
        depends_on = raw.get("depends_on") or []
        if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
            raise ChainValidationError(f"Step '{step_id}': 'depends_on' must be a list of step ids")
        inputs = raw.get("inputs") or []
        if not isinstance(inputs, list) or not all(isinstance(i, str) for i in inputs):
            raise ChainValidationError(f"Step '{step_id}': 'inputs' must be a list of file paths")
        timeout = int(raw.get("timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS))
        if timeout <= 0:
            raise ChainValidationError(f"Step '{step_id}': 'timeout_seconds' must be positive")
        return cls(
            id=step_id,
            name=str(raw.get("name") or step_id),
            command=list(command),
            depends_on=list(depends_on),
            inputs=list(inputs),
            timeout_seconds=timeout,
        )


@dataclass
class ChainSpec:
    """A validated chain specification."""

    name: str
    steps: List[ChainStep]
    source: str = "<memory>"

    @classmethod
    def from_mapping(cls, raw: Dict[str, Any], source: str = "<memory>") -> "ChainSpec":
        if not isinstance(raw, dict):
            raise ChainValidationError("Chain spec root must be a mapping")
        name = str(raw.get("name") or "bionexus-chain").strip()
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ChainValidationError("Chain spec must declare a non-empty 'steps' list")
        steps = [ChainStep.from_dict(raw_step, i) for i, raw_step in enumerate(raw_steps)]
        spec = cls(name=name, steps=steps, source=source)
        spec._validate()
        return spec

    @classmethod
    def load(cls, path: PathLike) -> "ChainSpec":
        p = Path(path)
        if not p.is_file():
            raise ChainValidationError(f"Chain spec file not found: {p}")
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                raw = yaml.safe_load(text)
            except yaml.YAMLError as e:
                raise ChainValidationError(f"Invalid YAML chain spec: {e}") from e
        else:
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as e:
                raise ChainValidationError(f"Invalid JSON chain spec: {e}") from e
        return cls.from_mapping(raw, source=str(p))

    def _validate(self) -> None:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ChainValidationError(f"Duplicate step ids in chain: {dupes}")
        known = set(ids)
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in known:
                    raise ChainValidationError(f"Step '{step.id}' depends on unknown step '{dep}'")
            if step.id in step.depends_on:
                raise ChainValidationError(f"Step '{step.id}' depends on itself")
        self.topological_order()

    def topological_order(self) -> List[ChainStep]:
        """Deterministic (insertion-stable) topological ordering; raises on cycles."""
        remaining = {s.id: s for s in self.steps}
        order: List[ChainStep] = []
        done: set[str] = set()
        while remaining:
            ready = [s for s in self.steps if s.id in remaining and all(d in done for d in s.depends_on)]
            if not ready:
                cyclic = sorted(remaining.keys())
                raise ChainValidationError(f"Dependency cycle detected among steps: {cyclic}")
            for step in ready:
                order.append(step)
                done.add(step.id)
                remaining.pop(step.id)
        return order


@dataclass
class StepOutcome:
    """Execution record for one stage of the chain."""

    step_id: str
    status: str  # EXECUTED | FAILED | SKIPPED_FAIL_CLOSED
    capsule_dir: Optional[str] = None
    returncode: Optional[int] = None
    duration_seconds: Optional[float] = None
    conclusion_maturity: Optional[str] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "capsule_dir": self.capsule_dir,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "conclusion_maturity": self.conclusion_maturity,
            "note": self.note,
        }


def _build_step_evidence(returncode: int, command: List[str]) -> EvidenceCard:
    """Execution-fidelity-only EvidenceCard for a completed stage process."""
    if returncode == 0:
        card = EvidenceCard(
            execution_state=ExecutionState.EXECUTED.value,
            input_integrity=DimensionGrade.UNTESTED.value,
            assumption_validity=DimensionGrade.UNTESTED.value,
            statistical_support=DimensionGrade.UNTESTED.value,
            parameter_robustness=DimensionGrade.UNTESTED.value,
            cross_method_concordance=DimensionGrade.UNTESTED.value,
            external_validation=DimensionGrade.UNTESTED.value,
            details={
                "execution_backend": "subprocess",
                "note": (
                    "Process executed successfully. Scientific validity is owned by the stage's "
                    "own capability contract, not by the orchestrator."
                ),
            },
        )
    else:
        card = EvidenceCard(
            execution_state=ExecutionState.FAILED.value,
            input_integrity=DimensionGrade.UNTESTED.value,
            assumption_validity=DimensionGrade.UNTESTED.value,
            statistical_support=DimensionGrade.UNTESTED.value,
            parameter_robustness=DimensionGrade.UNTESTED.value,
            cross_method_concordance=DimensionGrade.UNTESTED.value,
            external_validation=DimensionGrade.UNTESTED.value,
            details={"execution_backend": "subprocess", "returncode": returncode},
        )
    return card


def run_chain(
    spec: Union[ChainSpec, PathLike],
    workdir: PathLike,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute a chain spec in topological order, one Run Capsule per stage.

    Returns an ``attach_meta`` payload with the chain report (``chain`` key) and writes
    ``chain_summary.json`` into ``workdir``. On any stage failure the chain aborts
    fail-closed: remaining stages are recorded as ``SKIPPED_FAIL_CLOSED``.
    """
    if isinstance(spec, (str, Path)):
        spec = ChainSpec.load(spec)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    plan = spec.topological_order()
    if dry_run:
        report = {
            "chain_name": spec.name,
            "chain_status": "PLANNED",
            "planned_order": [s.id for s in plan],
            "steps": [StepOutcome(step_id=s.id, status="PLANNED").to_dict() for s in plan],
        }
        return attach_meta(
            {"chain": report},
            method="bionexus.orchestrator.run_chain",
            backend="bionexus.orchestrator",
            limitations=["Dry run only. No stage was executed."],
        )

    outcomes: List[StepOutcome] = []
    chain_status = "COMPLETED"
    for step in plan:
        capsule_dir = work / step.id
        already_failed = chain_status != "COMPLETED"
        if already_failed:
            outcomes.append(
                StepOutcome(
                    step_id=step.id,
                    status="SKIPPED_FAIL_CLOSED",
                    note=f"Skipped because an earlier stage failed (depends_on={step.depends_on or '[]'}).",
                )
            )
            continue

        bundle = RunBundle.create(
            capsule_dir,
            capability_id=f"chain.{spec.name}.{step.id}",
            skill_name="research-workflow-orchestrator",
            run_id=f"chain_{spec.name}_{step.id}",
        )
        bundle.record_parameters(
            command=step.command,
            depends_on=step.depends_on,
            timeout_seconds=step.timeout_seconds,
        )
        for input_path in step.inputs:
            bundle.record_input(Path(input_path).name, input_path, semantic_type="chain_input")

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(  # noqa: S603 - argv list, shell=False by design
                step.command,
                capture_output=True,
                text=True,
                timeout=step.timeout_seconds,
                shell=False,
                check=False,
            )
            returncode = int(proc.returncode)
            stdout_tail = (proc.stdout or "")[-4000:]
            stderr_tail = (proc.stderr or "")[-4000:]
        except subprocess.TimeoutExpired:
            returncode = -1
            stdout_tail = ""
            stderr_tail = f"Stage '{step.id}' timed out after {step.timeout_seconds}s (fail-closed)."
        except FileNotFoundError as e:
            returncode = -1
            stdout_tail = ""
            stderr_tail = f"Stage executable not found: {e}"
        except OSError as e:
            returncode = -1
            stdout_tail = ""
            stderr_tail = f"OS error while launching stage: {e}"
        duration = round(time.perf_counter() - t0, 3)

        (bundle.logs_dir / "stage_stderr.log").write_text(stderr_tail, encoding="utf-8")
        (bundle.logs_dir / "stage_stdout.log").write_text(stdout_tail, encoding="utf-8")

        card = _build_step_evidence(returncode, step.command)
        bundle.attach_evidence_card(card)
        if returncode == 0:
            bundle.log(f"Stage '{step.id}' completed successfully in {duration}s.")
            bundle.finalize(status="COMPLETED")
            outcomes.append(
                StepOutcome(
                    step_id=step.id,
                    status="EXECUTED",
                    capsule_dir=str(capsule_dir),
                    returncode=0,
                    duration_seconds=duration,
                    conclusion_maturity=card.synthesize_status(),
                )
            )
        else:
            bundle.log(f"Stage '{step.id}' FAILED (returncode={returncode}). Chain aborts fail-closed.")
            bundle.finalize(status="FAILED")
            outcomes.append(
                StepOutcome(
                    step_id=step.id,
                    status="FAILED",
                    capsule_dir=str(capsule_dir),
                    returncode=returncode,
                    duration_seconds=duration,
                    conclusion_maturity=card.synthesize_status(),
                    note=(stderr_tail or f"Exit code {returncode}")[:500],
                )
            )
            chain_status = "FAILED"

    report = {
        "chain_name": spec.name,
        "chain_status": chain_status,
        "spec_source": spec.source,
        "planned_order": [s.id for s in plan],
        "steps": [o.to_dict() for o in outcomes],
    }
    (work / "chain_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    limitations = [
        "The orchestrator captures execution fidelity and provenance only; scientific validity "
        "is owned by each stage's capability contract.",
        "Not a replacement for Nextflow / Airflow / Snakemake.",
    ]
    if chain_status == "FAILED":
        limitations.append(
            "One or more stages failed: downstream stages were skipped fail-closed. "
            "The chain result must NOT be reported as a completed analysis."
        )
    return attach_meta(
        {"chain": report},
        method="bionexus.orchestrator.run_chain",
        backend="bionexus.orchestrator",
        evidence_grade="A" if chain_status == "COMPLETED" else "abstain",
        execution_state=(
            ExecutionState.EXECUTED.value if chain_status == "COMPLETED" else ExecutionState.FAILED.value
        ),
        limitations=limitations,
        abstain=chain_status == "FAILED",
        abstain_reason=None if chain_status == "COMPLETED" else "Chain aborted fail-closed after a stage failure.",
        conclusion_maturity=(
            ConclusionMaturity.PRELIMINARY.value
            if chain_status == "COMPLETED"
            else ConclusionMaturity.ABSTAIN.value
        ),
    )
