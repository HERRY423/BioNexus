"""Fail-closed Input State Honesty evaluator."""
from bionexus.bctk.dimensions._unassessed import unassessed_dimension
from bionexus.bctk.spec import ConformanceDimension, DimensionResult
from bionexus.bctk.targets import TargetDescriptor


def evaluate_input_honesty(target: TargetDescriptor) -> DimensionResult:
    return unassessed_dimension(ConformanceDimension.INPUT_STATE_HONESTY, target)
