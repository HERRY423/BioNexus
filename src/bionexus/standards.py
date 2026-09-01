"""
BioNexus Standards Alignment Registry (BNS-016 §standards engagement).

Honest positioning, machine-readable (BNS-IO-007/008):

> BioNexus is NOT an industry standard and does not claim to be one.
> The BNS specification series is an implementation proposal — discussable,
> criticizable, contributable. Standards status is earned when other projects
> start adopting the vocabulary, schemas, and tests; it is never declared.

Statuses are a closed vocabulary and MUST reflect reality:
- implemented  shipped, tested projection/conformance in this repository
- aligned       follows the external spec where it is used (no false claim of
                conformance testing against the full official validator)
- proposal      BioNexus material offered into an external forum (not adopted)
- tracked       engagement venue monitored; no material offered yet

Implementation and independent verification are separate axes. A shipped
projection does not become externally adopted merely because a third-party
validator accepts a deterministic conformance fixture.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

STANDARDS_DISCLAIMER = (
    "BioNexus is not an industry standard and does not claim to be one. The BNS series is an "
    "implementation proposal; standards status is earned by external adoption of its vocabulary, "
    "schemas, and tests — never declared."
)

STATUSES = ("implemented", "aligned", "proposal", "tracked")
VERIFICATION_STATUSES = ("repository_tested", "third_party_tool_validated", "not_assessed")


@dataclass(frozen=True)
class StandardAlignment:
    """One external standard and BioNexus's honest relationship to it."""

    key: str
    name: str
    url: str
    status: str  # STATUSES
    role: str  # what BioNexus uses it for / contributes to it
    since: str = ""
    verification: str = "not_assessed"

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"Unknown alignment status '{self.status}' (must be one of {STATUSES})")
        if self.verification not in VERIFICATION_STATUSES:
            raise ValueError(
                f"Unknown verification status '{self.verification}' "
                f"(must be one of {VERIFICATION_STATUSES})"
            )


ALIGNMENTS: Dict[str, StandardAlignment] = {
    a.key: a
    for a in [
        StandardAlignment(
            key="prov-o",
            name="W3C PROV-O",
            url="https://www.w3.org/TR/prov-o/",
            status="implemented",
            role="Claim–Evidence Ledger JSON-LD projection and provenance sidecars",
            since="0.8.0",
            verification="repository_tested",
        ),
        StandardAlignment(
            key="ro-crate",
            name="RO-Crate 1.1",
            url="https://w3id.org/ro/crate/1.1",
            status="implemented",
            role=(
                "Run capsules and ledgers exported as crates; the Workflow Run fixture is "
                "accepted by the pinned official roc-validator profile chain"
            ),
            since="0.10.0",
            verification="third_party_tool_validated",
        ),
        StandardAlignment(
            key="workflow-run-crate",
            name="Workflow Run RO-Crate (Process/Workflow/Provenance Run Crate 0.5 + Workflow RO-Crate 1.0)",
            url="https://w3id.org/ro/wfrun/workflow/0.5",
            status="implemented",
            role=(
                "Execution provenance: document projections plus full Research Object "
                "bundle exports (inputs, software, execution, steps, outputs, EvidenceCard, "
                "Claim Ledger), with CI validation by official roc-validator 0.11.2 at "
                "REQUIRED severity across the inherited five-profile chain (BNS-IO-010)"
            ),
            since="0.10.0",
            verification="third_party_tool_validated",
        ),
        StandardAlignment(
            key="bco",
            name="BioCompute Object (IEEE 2791-2020)",
            url="https://w3id.org/ieee/ieee-2791-std/schema/2791-2020",
            status="implemented",
            role="Six-domain computation objects exported from run capsules (structural validation)",
            since="0.10.0",
            verification="repository_tested",
        ),
        StandardAlignment(
            key="bioschemas",
            name="Bioschemas",
            url="https://bioschemas.org/",
            status="aligned",
            role="Crate root Datasets use Bioschemas-compatible schema.org typing; profile validation not yet run",
        ),
        StandardAlignment(
            key="nf-core",
            name="nf-core / Nextflow",
            url="https://nf-co.re/",
            status="tracked",
            role=(
                "Zero-touch RO-Crate artifact-annotation proof of concept revised after external "
                "architecture feedback; no public proposal receipt or nf-core adoption claim"
            ),
        ),
        StandardAlignment(
            key="ga4gh-ai-workstream",
            name="GA4GH Artificial Intelligence Work Stream",
            url="https://www.ga4gh.org/",
            status="tracked",
            role=(
                "Contribution packet ready but not submitted: capability contracts, evidence "
                "boundaries, refusal semantics, host conformance, BioFailureBench tests; "
                "submission requires a named human participant"
            ),
        ),
        StandardAlignment(
            key="elixir",
            name="ELIXIR",
            url="https://elixir-europe.org/",
            status="tracked",
            role="Engagement venue for interoperability and provenance communities",
        ),
        StandardAlignment(
            key="scverse",
            name="scverse",
            url="https://scverse.org/",
            status="tracked",
            role="Engagement venue for the single-cell Python ecosystem",
        ),
        StandardAlignment(
            key="bioconductor",
            name="Bioconductor",
            url="https://bioconductor.org/",
            status="tracked",
            role="Engagement venue for R-side failure vocabulary and workflows",
        ),
        StandardAlignment(
            key="workflowhub",
            name="WorkflowHub",
            url="https://workflowhub.eu/",
            status="tracked",
            role="RO-Crate / Workflow RO-Crate interchange target for shared workflow runs",
        ),
    ]
}


def alignments_report() -> Dict[str, Any]:
    """Machine-readable alignment report with the verbatim disclaimer."""
    counts: Dict[str, int] = {s: 0 for s in STATUSES}
    for a in ALIGNMENTS.values():
        counts[a.status] += 1
    return {
        "disclaimer": STANDARDS_DISCLAIMER,
        "status_counts": counts,
        "alignments": {k: asdict(a) for k, a in ALIGNMENTS.items()},
    }


def render_alignments() -> str:
    """Render the alignment table with the mandatory disclaimer."""
    lines: List[str] = []
    lines.append("=== BioNexus Standards Alignment (BNS-016) ===")
    lines.append("")
    lines.append(f'"{STANDARDS_DISCLAIMER}"')
    lines.append("")
    lines.append("| Standard | Status | Verification | Role in BioNexus | Since |")
    lines.append("|---|---|---|---|---|")
    for a in ALIGNMENTS.values():
        lines.append(
            f"| [{a.name}]({a.url}) | `{a.status}` | `{a.verification}` | "
            f"{a.role} | {a.since or '-'} |"
        )
    lines.append("")
    lines.append("Statuses: `implemented` shipped+tested here | `aligned` follows the spec in use |")
    lines.append("`proposal` offered into an external forum | `tracked` venue monitored.")
    lines.append(
        "Verification is separate: `third_party_tool_validated` is technical conformance, "
        "not certification, endorsement, or adoption."
    )
    return "\n".join(lines)
