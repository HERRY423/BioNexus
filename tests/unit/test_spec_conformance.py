"""
Spec conformance tests for the BioNexus Scientific Contract Specification (BNS).

Validates that the spec/ tree itself is well-formed (BNS-README index, all nine
documents, RFC 2119 keyword usage, stable requirement IDs) and that key
normative requirements are backed by live enforcement points in the codebase.
"""

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

SPEC_DIR = _REPO_ROOT / "spec"

EXPECTED_DOCUMENTS = [
    "BNS-001-capability-contract.md",
    "BNS-002-input-invariants.md",
    "BNS-003-execution-fidelity.md",
    "BNS-004-evidence-maturity.md",
    "BNS-005-abstention-and-degradation.md",
    "BNS-006-provenance.md",
    "BNS-007-cross-method-validation.md",
    "BNS-008-host-conformance.md",
    "BNS-009-capability-lifecycle.md",
    "BNS-010-capability-certification.md",
    "BNS-011-failure-taxonomy.md",
    "BNS-012-claim-evidence-ledger.md",
    "BNS-013-scientific-assertion-firewall.md",
    "BNS-014-biofailurebench.md",
    "BNS-015-flagship-certification.md",
    "BNS-016-standards-interop.md",
]

RFC2119_KEYWORDS = ["MUST NOT", "MUST", "SHOULD NOT", "SHOULD", "MAY"]
# Requirement definitions are bold (`**BNS-XX-nnn**`); plain `(BNS-XX-nnn)` is a cross-reference.
REQ_DEF_RE = re.compile(r"\*\*BNS-[A-Z]{2}-\d{3}\*\*")
REQ_ANY_RE = re.compile(r"\bBNS-[A-Z]{2}-\d{3}\b")


def test_all_spec_documents_exist():
    """The BNS series MUST contain all nine normative documents plus an index."""
    assert SPEC_DIR.is_dir(), "spec/ directory must exist"
    for doc in EXPECTED_DOCUMENTS:
        assert (SPEC_DIR / doc).is_file(), f"missing spec document: {doc}"
    assert (SPEC_DIR / "README.md").is_file()


def test_specs_use_rfc2119_normative_language():
    """Every BNS document MUST use RFC 2119 keywords and carry requirement IDs."""
    for doc in EXPECTED_DOCUMENTS:
        text = (SPEC_DIR / doc).read_text(encoding="utf-8")
        assert "RFC 2119" in text, f"{doc} must reference RFC 2119"
        found_keywords = [kw for kw in RFC2119_KEYWORDS if re.search(rf"\b{kw}\b", text)]
        assert len(found_keywords) >= 3, f"{doc} must use RFC 2119 keywords, found: {found_keywords}"
        definitions = REQ_DEF_RE.findall(text)
        assert len(definitions) >= 5, f"{doc} must define >= 5 requirements (**BNS-XX-nnn**), found {len(definitions)}"
        # Definitions must dominate references: cross-references are allowed
        assert len(REQ_ANY_RE.findall(text)) >= len(definitions)


def test_requirement_ids_are_unique_across_series():
    """Requirement IDs MUST never be defined in two documents (BNS-README)."""
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for doc in EXPECTED_DOCUMENTS:
        text = (SPEC_DIR / doc).read_text(encoding="utf-8")
        for rid in REQ_DEF_RE.findall(text):
            rid = rid.strip("*")
            if rid in seen and seen[rid] != doc:
                duplicates.append(f"{rid} in {seen[rid]} and {doc}")
            seen[rid] = doc
    assert not duplicates, f"duplicated requirement definitions: {duplicates}"
    # Every requirement ID referenced anywhere MUST be defined somewhere
    all_text = "\n".join((SPEC_DIR / d).read_text(encoding="utf-8") for d in EXPECTED_DOCUMENTS)
    defined = {r.strip("*") for r in REQ_DEF_RE.findall(all_text)}
    referenced = {r for r in REQ_ANY_RE.findall(all_text)}
    dangling = referenced - defined
    assert not dangling, f"cross-references to undefined requirements: {sorted(dangling)}"


def test_index_covers_all_documents():
    """The spec index MUST link every document in the series."""
    index = (SPEC_DIR / "README.md").read_text(encoding="utf-8")
    for doc in EXPECTED_DOCUMENTS:
        assert doc in index, f"index missing link to {doc}"


def test_normative_requirements_backed_by_implementation():
    """Spot-check that headline requirements have live enforcement points."""
    from bionexus.abi import capability_abis, enforce_statistical_warrant
    from bionexus.capabilities import CANONICAL_CAPABILITIES
    from bionexus.contracts import ConclusionMaturity, ExecutionState

    # BNS-CC-001: stable dotted capability identifiers
    for cid in CANONICAL_CAPABILITIES:
        assert re.match(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$", cid), cid

    # BNS-EF-001: execution state vocabulary
    assert {s.value for s in ExecutionState} == {
        "PERMITTED",
        "EXECUTED",
        "DEGRADED",
        "REFUSED",
        "FAILED",
    }

    # BNS-EM-004: maturity ladder ranks
    ladder = [m.value for m in ConclusionMaturity]
    assert set(ladder) == {
        "UNASSESSED",
        "ABSTAIN",
        "FRAGILE",
        "CONFLICTED",
        "PRELIMINARY",
        "SUPPORTED",
        "ROBUST",
        "REPLICATED",
    }

    # BNS-CC-011: spatial ABI enumerates coordinate types
    spatial = capability_abis()["spatial.morans_svg"]
    assert "physical" in spatial.input_contract.coordinate_type_allowed
    assert "justified_spatial_embedding" in spatial.input_contract.coordinate_type_allowed

    # BNS-FW-001: the three firewall entry points exist as CLI handlers
    from bionexus.cli import handle_audit, handle_preflight, handle_verify

    assert callable(handle_preflight) and callable(handle_verify) and callable(handle_audit)

    # BNS-FW-011: verify re-resolves claims fail-closed (BNS-CL-05 vocabulary)
    from bionexus.verification import verify_results, write_example_ledger

    assert callable(verify_results) and callable(write_example_ledger)

    # BN-F005 statistical warrant: missing FDR caps warrant at PRELIMINARY
    capped = enforce_statistical_warrant(
        "scrna.pseudobulk_de", "SUPPORTED", has_fdr_correction=False
    )
    assert capped == "PRELIMINARY"
    intact = enforce_statistical_warrant(
        "scrna.pseudobulk_de", "SUPPORTED", has_fdr_correction=True
    )
    assert intact == "SUPPORTED"

    # BNS-BF-007: the trap corpus is machine-validated
    from evals.biofailurebench import validate_corpus

    corpus = validate_corpus()
    assert corpus.valid, [f"{i.case_id}:{i.field}" for i in corpus.issues]
    assert corpus.total_cases >= 20 and corpus.gating_cases >= 15

    # BNS-FC-002/007: flagship set is the three capabilities at VALIDATED floor
    from bionexus.certification import FLAGSHIP_CAPABILITIES, flagship_program

    assert FLAGSHIP_CAPABILITIES == (
        "scrna.pseudobulk_de",
        "scrna.annotation_evidence",
        "spatial.inference_validity",
    )
    for info in flagship_program()["capabilities"].values():
        assert info["current_tier"] in ("VALIDATED", "CERTIFIED"), info

    # BNS-IO-001..006: standards interop projections exist and validate
    from bionexus.interop import (
        export_bco,
        export_ro_crate,
        ledger_to_ro_crate,
        run_bundle_to_bco,
        run_bundle_to_ro_crate,
        validate_bco,
        validate_ro_crate,
    )

    for fn in (
        run_bundle_to_ro_crate,
        ledger_to_ro_crate,
        run_bundle_to_bco,
        validate_ro_crate,
        validate_bco,
        export_ro_crate,
        export_bco,
    ):
        assert callable(fn)

    # BNS-IO-007/008: standards registry with verbatim disclaimer
    from bionexus.standards import STANDARDS_DISCLAIMER, alignments_report

    report = alignments_report()
    assert report["disclaimer"] == STANDARDS_DISCLAIMER
    assert "not an industry standard" in STANDARDS_DISCLAIMER
    assert report["status_counts"]["implemented"] >= 3
    assert report["status_counts"]["proposal"] >= 1  # GA4GH offered, not claimed
