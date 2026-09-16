"""Fail-closed Backend Identity evaluator."""
from bionexus.bctk.dimensions._unassessed import unassessed_dimension
from bionexus.bctk.spec import ConformanceDimension, DimensionResult
from bionexus.bctk.targets import TargetDescriptor


def evaluate_backend_identity(target: TargetDescriptor) -> DimensionResult:
    return unassessed_dimension(ConformanceDimension.BACKEND_IDENTITY, target)
