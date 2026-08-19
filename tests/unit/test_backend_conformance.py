"""
Unit tests for Backend Identity Conformance (BNS-EF-012..016, BN-F010).

Validates the anti-masquerading invariant: declared_backend == observed_backend,
machine-provably. Every capability answers claimed / observed / entry point /
version / fingerprint / fallback, and any identity violation resolves to BLOCK.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backend_conformance import (
    BackendIdentityState,
    backend_identity_summary,
    verify_all_backend_identity,
    verify_backend_identity,
)
from bionexus.capabilities import (
    ALL_CAPABILITIES,
    CANONICAL_CAPABILITIES,
    BackendRequirement,
    CapabilityContract,
)
from bionexus.cli import main as cli_main


def test_installed_canonical_backend_is_conformant():
    """An installed declared backend with all entry points resolved is CONFORMANT."""
    from bionexus.backends import is_available

    cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
    if not is_available("pydeseq2"):
        return
    r = verify_backend_identity(cap)
    assert r.state == BackendIdentityState.CONFORMANT
    assert r.action == "RUN PERMITTED (identity)"
    assert r.claimed_backend == "pydeseq2"
    assert r.observed_backend == "pydeseq2"
    assert r.version is not None
    assert r.entry_points_resolved == list(cap.backend.entry_points)
    assert r.entry_points_missing == []
    assert r.execution_fingerprint
    assert r.fallback is False
    assert r.failure_mode_ids == []


def test_missing_backend_is_not_installed_not_bn_f010():
    """A missing backend executes nothing: NOT_INSTALLED + ABSTAIN, never BN-F010."""
    from bionexus.backends import is_available

    if is_available("lifelines"):
        return
    r = verify_backend_identity(ALL_CAPABILITIES["survival.kaplan_meier"])
    assert r.state == BackendIdentityState.NOT_INSTALLED
    assert r.action == "ABSTAIN"
    assert r.failure_mode_ids == []
    assert r.fallback is False


def test_masquerade_distribution_mismatch_blocks():
    """An import name served by a different distribution is BN-F010 BLOCK."""
    cap = CapabilityContract(
        id="test.masquerade_probe",
        display_name="Masquerade probe",
        backend=BackendRequirement(
            canonical_name="pandas",  # the claim
            import_name="json",       # the reality: stdlib json, not pandas
            minimum_version="0.0.1",
        ),
    )
    r = verify_backend_identity(cap)
    assert r.state == BackendIdentityState.MASQUERADE
    assert r.action == "BLOCK"
    assert "BN-F010" in r.failure_mode_ids
    assert r.fallback is False


def test_missing_entry_point_blocks():
    """The right distribution without the declared API surface is still a masquerade."""
    from bionexus.backends import is_available

    if not is_available("pydeseq2"):
        return
    cap = CapabilityContract(
        id="test.entry_point_probe",
        display_name="Entry point probe",
        backend=BackendRequirement(
            canonical_name="pydeseq2",
            import_name="pydeseq2",
            minimum_version="0.4.0",
            entry_points=("pydeseq2.this_symbol_does_not_exist",),
        ),
    )
    r = verify_backend_identity(cap)
    assert r.state == BackendIdentityState.MASQUERADE
    assert r.action == "BLOCK"
    assert r.entry_points_missing == ["pydeseq2.this_symbol_does_not_exist"]
    assert "BN-F010" in r.failure_mode_ids


def test_incompatible_version_blocks():
    """A version below the declared minimum breaks the identity contract."""
    cap = CapabilityContract(
        id="test.version_probe",
        display_name="Version probe",
        backend=BackendRequirement(
            canonical_name="pydeseq2",
            import_name="pydeseq2",
            minimum_version="99.99.99",
        ),
    )
    from bionexus.backends import is_module_available

    if not is_module_available("pydeseq2"):
        return
    r = verify_backend_identity(cap)
    assert r.state == BackendIdentityState.INCOMPATIBLE_VERSION
    assert r.action == "BLOCK"
    assert "BN-F010" in r.failure_mode_ids


def test_wrong_claim_on_importable_package_blocks():
    """Witness must match the CLAIM: claiming numpy while importing pandas is a
    masquerade even though pandas is importable (candidate-set tightening)."""
    from bionexus.backends import is_module_available

    if not (is_module_available("pandas") and is_module_available("numpy")):
        return
    cap = CapabilityContract(
        id="test.claim_mismatch_probe",
        display_name="Claim mismatch probe",
        backend=BackendRequirement(
            canonical_name="numpy",   # the claim
            import_name="pandas",     # the reality
            minimum_version="0.0.1",
        ),
    )
    r = verify_backend_identity(cap)
    assert r.state == BackendIdentityState.MASQUERADE
    assert r.action == "BLOCK"
    assert "BN-F010" in r.failure_mode_ids


def test_in_tree_backend_version_witness():
    """In-tree bionexus.* backends are version-witnessed by the imported
    bionexus package itself, so cluster/bigdata are CONFORMANT when installed."""
    r = verify_backend_identity(ALL_CAPABILITIES["cluster.hpc_dispatch"])
    assert r.state == BackendIdentityState.CONFORMANT
    # The observed distribution is 'bionexus' from a source checkout (no dist
    # metadata) or 'bionexus-reliability' when the PyPI package is installed.
    assert r.observed_backend in ("bionexus", "bionexus-reliability")
    assert r.version is not None
    assert r.failure_mode_ids == []


def test_all_canonical_capabilities_answer_identity():
    """Every canonical capability emits a complete identity statement."""
    reports = verify_all_backend_identity(include_frontier=True)
    cap_ids = {r.capability_id for r in reports}
    assert set(CANONICAL_CAPABILITIES) <= cap_ids
    for r in reports:
        assert r.state in BackendIdentityState
        assert r.fallback is False  # structural invariant: no hidden fallback ever
        assert r.action in ("RUN PERMITTED (identity)", "BLOCK", "ABSTAIN")
        if r.state == BackendIdentityState.CONFORMANT:
            assert r.execution_fingerprint
            assert r.observed_backend

    summary = backend_identity_summary(reports)
    assert summary["total"] == len(reports)
    assert summary["fallback_reports"] == 0
    assert summary["verdict"] in ("PASS", "BLOCK")


def test_backend_identity_cli(capsys):
    rc = cli_main(["backend-identity", "--capability", "scrna.pseudobulk_de", "--json"])
    out = capsys.readouterr().out
    assert '"capability_id": "scrna.pseudobulk_de"' in out
    assert '"fallback": false' in out
    assert rc in (0, 1)  # 0 conformant, 1 blocked, never a crash

    rc_unknown = cli_main(["backend-identity", "--capability", "nope.nope"])
    assert rc_unknown == 2
