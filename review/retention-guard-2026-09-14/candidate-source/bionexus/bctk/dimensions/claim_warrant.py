"""Fail-closed Claim Warrant evaluator."""
from bionexus.bctk.dimensions._unassessed import unassessed_dimension
from bionexus.bctk.spec import ConformanceDimension, DimensionResult
from bionexus.bctk.targets import TargetDescriptor


def evaluate_claim_warrant(target: TargetDescriptor) -> DimensionResult:
    return unassessed_dimension(ConformanceDimension.CLAIM_WARRANT, target)
