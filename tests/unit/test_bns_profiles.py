import json
from pathlib import Path

from bionexus.bctk.profiles import ProfileStatus, evaluate_protocol_profiles
from bionexus.bctk.spec import ConformanceDimension, DimensionResult, DimensionStatus


def _dimension(dimension: ConformanceDimension, status: DimensionStatus) -> DimensionResult:
    return DimensionResult(dimension, status, 100.0, 1, 1, 0, [])


def test_profiles_fail_closed_on_unassessed_mandatory_dimension():
    dimensions = {
        dimension.value: _dimension(dimension, DimensionStatus.PASS)
        for dimension in ConformanceDimension
    }
    dimensions[ConformanceDimension.CROSS_HOST_CONSISTENCY.value] = _dimension(
        ConformanceDimension.CROSS_HOST_CONSISTENCY, DimensionStatus.NOT_ASSESSED
    )
    results = evaluate_protocol_profiles(dimensions)
    assert results["BNS-Core"].status == ProfileStatus.PASS
    assert results["BNS-Agent"].status == ProfileStatus.NOT_ASSESSED
    assert results["BNS-Validation"].status == ProfileStatus.NOT_ASSESSED
    assert results["BNS-Full"].status == ProfileStatus.NOT_ASSESSED
    assert all(result.certification_effect == "NONE" for result in results.values())


def test_profiles_do_not_average_away_failure():
    dimensions = {
        dimension.value: _dimension(dimension, DimensionStatus.PASS)
        for dimension in ConformanceDimension
    }
    dimensions[ConformanceDimension.ABSTENTION.value] = _dimension(
        ConformanceDimension.ABSTENTION, DimensionStatus.FAIL
    )
    results = evaluate_protocol_profiles(dimensions)
    assert results["BNS-Core"].status == ProfileStatus.FAIL
    assert results["BNS-Warrant"].status == ProfileStatus.FAIL
    assert results["BNS-Full"].status == ProfileStatus.FAIL


def test_unknown_profile_is_rejected():
    try:
        evaluate_protocol_profiles({}, ["BNS-Imaginary"])
    except ValueError as exc:
        assert "unknown BNS profiles" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")


def test_language_neutral_profile_manifest_matches_runtime_catalog():
    from bionexus.bctk.profiles import PROFILE_CATALOG

    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "standards/bns-conformance-profiles/profiles.json").read_text(encoding="utf-8"))
    observed = {
        profile_id: [dimension.value for dimension in profile.required_dimensions]
        for profile_id, profile in PROFILE_CATALOG.items()
    }
    assert manifest["profiles"] == observed
    assert manifest["certification_effect"] == "NONE"
