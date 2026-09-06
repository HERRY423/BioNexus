"""Fail-closed Failure Handling evaluator."""
from bionexus.bctk.dimensions._unassessed import unassessed_dimension
from bionexus.bctk.spec import ConformanceDimension, DimensionResult
from bionexus.bctk.targets import TargetDescriptor


def evaluate_failure_handling(target: TargetDescriptor) -> DimensionResult:
    return unassessed_dimension(ConformanceDimension.FAILURE_HANDLING, target)
