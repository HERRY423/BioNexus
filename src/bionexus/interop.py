"""
BioNexus Standards Interoperability Projections (BNS-016).

BioNexus does NOT invent a proprietary research-data standard. The internal
Run Capsule stays internal; everything that crosses the boundary goes through
published community standards:

    Claim–Evidence Ledger ──> W3C PROV-O (ledger.to_jsonld, since 0.8)
    Run Capsule / Ledger  ──> RO-Crate 1.1 (+ Workflow Run Crate profiles)
    Run Capsule (bundle)  ──> Workflow Run RO-Crate Research Object directory
                              (inputs / software / execution / steps / outputs /
                              EvidenceCard / Claim Ledger, BNS-IO-014)
    Run Capsule           ──> BioCompute Object (IEEE 2791-2020)

Projections are deterministic, offline, and validated BEFORE they are handed
out: an export that fails structural validation is never written (fail-closed
interop, BNS-IO-004). The projection layer adds vocabulary, never removes it:
every BioNexus-specific fact (evidence maturity, failure taxonomy ids) rides
along inside standard containers rather than in side formats.

External references:
- RO-Crate 1.1            https://w3id.org/ro/crate/1.1
- Process Run Crate       https://w3id.org/ro/wfrun/process/0.5 (profile id)
- Workflow Run Crate      https://w3id.org/ro/wfrun/workflow/0.5 (profile id)
- Provenance Run Crate    https://w3id.org/ro/wfrun/provenance/0.5 (profile id)
- Workflow RO-Crate       https://w3id.org/workflowhub/workflow-ro-crate/1.0
- Workflow Run RO-Crate   https://www.researchobject.org/workflow-run-crate/
- IEEE 2791-2020 (BCO)    https://w3id.org/ieee/ieee-2791-std/schema/2791-2020
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.ledger import ClaimLedger
from bionexus.versions import PLUGIN_VERSION

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
RO_CRATE_PROFILE = "https://w3id.org/ro/crate/1.1"
PROCESS_RUN_CRATE_PROFILE = "https://w3id.org/ro/wfrun/process/0.5"
WORKFLOW_RO_CRATE_PROFILE = "https://w3id.org/workflowhub/workflow-ro-crate/draft"
BCO_SPEC_VERSION = "https://w3id.org/ieee/ieee-2791-std/schema/2791-2020"

# Workflow Run RO-Crate bundle export (BNS-IO-014). The bundle uses the
# published profile chain; sha256 and related terms resolve through the
# workflow-run extension context. BioNexus extension properties are compacted
# through an explicit local term map so standards tooling never has to accept
# absolute IRIs as JSON object keys.
WORKFLOW_RUN_CONTEXT = "https://w3id.org/ro/terms/workflow-run/context"
WORKFLOW_RO_CRATE_PROFILE_1_0 = "https://w3id.org/workflowhub/workflow-ro-crate/1.0"
WORKFLOW_RUN_CRATE_PROFILE = "https://w3id.org/ro/wfrun/workflow/0.5"
PROVENANCE_RUN_CRATE_PROFILE = "https://w3id.org/ro/wfrun/provenance/0.5"
FORMAL_PARAMETER_PROFILE = "https://bioschemas.org/profiles/FormalParameter/1.0-RELEASE"
BNS_NAMESPACE = "https://bionexus.dev/ns#"
BNS_CONTEXT = {
    "bnsEvidenceKind": f"{BNS_NAMESPACE}evidenceKind",
    "bnsMaturity": f"{BNS_NAMESPACE}maturity",
    "bnsValidationRole": f"{BNS_NAMESPACE}validationRole",
    "bnsEvidenceStatus": f"{BNS_NAMESPACE}evidenceStatus",
    "bnsExecutionState": f"{BNS_NAMESPACE}executionState",
    "bnsConclusionMaturity": f"{BNS_NAMESPACE}conclusionMaturity",
    "bnsInputIntegrity": f"{BNS_NAMESPACE}inputIntegrity",
    "bnsAssumptionValidity": f"{BNS_NAMESPACE}assumptionValidity",
    "bnsStatisticalSupport": f"{BNS_NAMESPACE}statisticalSupport",
    "bnsParameterRobustness": f"{BNS_NAMESPACE}parameterRobustness",
    "bnsCrossMethodConcordance": f"{BNS_NAMESPACE}crossMethodConcordance",
    "bnsExternalValidation": f"{BNS_NAMESPACE}externalValidation",
    "bnsRunStatus": f"{BNS_NAMESPACE}runStatus",
}
WORKFLOW_RUN_CRATE_CONTEXT = [RO_CRATE_CONTEXT, WORKFLOW_RUN_CONTEXT, BNS_CONTEXT]
BIONEXUS_AGENT_ID = "https://github.com/HERRY423/BioNexus"

_PROFILE_ENTITIES: Dict[str, Tuple[str, str]] = {
    PROCESS_RUN_CRATE_PROFILE: ("Process Run Crate", "0.5"),
    WORKFLOW_RUN_CRATE_PROFILE: ("Workflow Run Crate", "0.5"),
    PROVENANCE_RUN_CRATE_PROFILE: ("Provenance Run Crate", "0.5"),
    WORKFLOW_RO_CRATE_PROFILE_1_0: ("Workflow RO-Crate", "1.0"),
}

_COMPLETED_STATUS = "http://schema.org/ActionStatusType/CompletedActionStatus"
_FAILED_STATUS = "http://schema.org/ActionStatusType/FailedActionStatus"
_ACTIVE_STATUS = "http://schema.org/ActionStatusType/ActiveActionStatus"
_ACTION_STATUS_URIS = {
    _ACTIVE_STATUS,
    _COMPLETED_STATUS,
    _FAILED_STATUS,
    "http://schema.org/ActionStatusType/PotentialActionStatus",
    "http://schema.org/ActionStatusType/StuckActionStatus",
}

_ENCODING_FORMATS = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".jsonld": "application/ld+json",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".h5": "application/x-hdf5",
    ".h5ad": "application/x-hdf5",
    ".parquet": "application/x-parquet",
}

BCO_DOMAINS = (
    "provenance_domain",
    "usability_domain",
    "description_domain",
    "execution_domain",
    "io_domain",
    "parametric_domain",
)


# ==============================================================================
# Input loading (run capsule or ledger, auto-detected)
# ==============================================================================


def _looks_like_ledger(data: Dict[str, Any]) -> bool:
    return "claims" in data and "evidence" in data and "run_id" not in data


def load_interop_source(path: str | Path) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Load an export source: a run capsule (directory / run.json) or a ledger.

    Returns (kind, manifest, siblings) where kind is "run" or "ledger" and
    siblings carries adjacent descriptor files (inputs.json, environment.json)
    when available.
    """
    p = Path(path)
    run_file = p / "run.json" if p.is_dir() else p
    if run_file.is_file() and run_file.name == "run.json":
        manifest = json.loads(run_file.read_text(encoding="utf-8"))
        siblings: Dict[str, Any] = {}
        base = run_file.parent
        for rel in ("inputs.json", "parameters.json", "environment.json", "evidence.json"):
            f = base / rel
            if f.is_file():
                try:
                    siblings[rel.removesuffix(".json")] = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
        return "run", manifest, siblings

    ledger_file = p / "bionexus.ledger.json" if p.is_dir() else p
    if ledger_file.is_file():
        data = json.loads(ledger_file.read_text(encoding="utf-8"))
        if _looks_like_ledger(data):
            return "ledger", data, {}
    raise FileNotFoundError(
        f"No run capsule (run.json) or Claim–Evidence Ledger found at '{path}'."
    )


# ==============================================================================
# RO-Crate projections
# ==============================================================================


def run_bundle_to_ro_crate(manifest: Dict[str, Any], siblings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Project a BioNexus run capsule into an RO-Crate 1.1 document following the
    Workflow Run Crate conventions: the capability is the ComputationalWorkflow,
    the execution is a schema.org CreateAction with instrument/object/result,
    and profile conformance is declared via conformsTo (BNS-IO-001).
    """
    sib = siblings or {}
    run_id = manifest.get("run_id", "unknown-run")
    capability_id = manifest.get("capability_id", "unknown.capability")
    artifacts = manifest.get("artifacts", {})

    graph: List[Dict[str, Any]] = []
    crate_files: List[Dict[str, Any]] = []

    def file_entity(rel: str, name: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ent = {"@id": rel, "@type": "File", "name": name}
        if extra:
            ent.update(extra)
        return ent

    # Descriptor files shipped inside the capsule
    for rel, label in (
        ("run.json", "BioNexus Run Capsule master descriptor"),
        ("inputs.json", "Input manifest with SHA-256 hashes"),
        ("parameters.json", "Resolved execution parameters"),
        ("evidence.json", "EvidenceCard 2.0 (execution state and maturity)"),
        ("provenance.json", "W3C PROV-O provenance sidecar"),
        ("environment.json", "Pinned environment snapshot"),
        ("logs/pipeline.log", "Execution log"),
    ):
        ent = file_entity(rel, label)
        crate_files.append(ent)
        graph.append(ent)

    # Input data entities
    for name, inp in (sib.get("inputs") or {}).items():
        rel = f"#input/{name}"
        ent = {
            "@id": rel,
            "@type": "File",
            "name": name,
            "description": f"Input artifact ({inp.get('semantic_type', 'unspecified')})",
        }
        if inp.get("sha256"):
            ent["sha256"] = inp["sha256"]
        graph.append(ent)
        crate_files.append({"@id": rel})

    # Result data entities
    for res in artifacts.get("results", []):
        rel = res.get("path", "")
        if not rel:
            continue
        ent = file_entity(rel, res.get("name", Path(rel).name))
        if res.get("sha256"):
            ent["sha256"] = res["sha256"]
        ent["description"] = f"Result artifact ({res.get('semantic_type', 'unspecified')})"
        if artifacts.get("primary_result") == rel:
            ent["isPrimaryResult"] = True  # schema.org flag rendered as description below
            ent["description"] = "Primary result artifact"
        graph.append(ent)
        crate_files.append({"@id": rel})

    # Figure entities
    for fig in artifacts.get("figures", []):
        rel = fig.get("path", "")
        if not rel:
            continue
        ent = {
            "@id": rel,
            "@type": "MediaObject",
            "name": fig.get("title", Path(rel).name),
            "encodingFormat": fig.get("format", ""),
        }
        graph.append(ent)
        crate_files.append({"@id": rel})

    # Agents
    bionexus_agent = {
        "@id": "https://github.com/HERRY423/BioNexus",
        "@type": "SoftwareApplication",
        "name": "BioNexus",
        "softwareVersion": manifest.get("bionexus_version", PLUGIN_VERSION),
        "description": "The Scientific Reliability Layer for Agentic Biology",
    }
    graph.append(bionexus_agent)

    # The capability as a ComputationalWorkflow (Workflow RO-Crate conventions)
    workflow = {
        "@id": f"#workflow/{capability_id}",
        "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
        "conformsTo": {"@id": WORKFLOW_RO_CRATE_PROFILE},
        "name": capability_id,
        "description": (
            f"BioNexus capability contract '{capability_id}' "
            f"(skill: {manifest.get('skill_name', 'unknown')})"
        ),
        "programmingLanguage": "Python",
    }
    graph.append(workflow)

    # Evidence card as a contextual entity (maturity rides inside the crate)
    maturity = manifest.get("conclusion_maturity", "UNASSESSED")
    execution_state = manifest.get("execution_state", "PENDING")
    evidence_entity = {
        "@id": "#evidence-card",
        "@type": "CreativeWork",
        "name": "BioNexus EvidenceCard 2.0",
        "description": (
            f"execution_state={execution_state}; conclusion_maturity={maturity}"
        ),
    }
    graph.append(evidence_entity)

    # The execution as a CreateAction (Process Run Crate conventions)
    action: Dict[str, Any] = {
        "@id": f"#run/{run_id}",
        "@type": "CreateAction",
        "conformsTo": {"@id": PROCESS_RUN_CRATE_PROFILE},
        "instrument": {"@id": f"#workflow/{capability_id}"},
        "name": f"BioNexus execution {run_id}",
        "agent": {"@id": "https://github.com/HERRY423/BioNexus"},
        "startTime": manifest.get("timestamp_start"),
        "endTime": manifest.get("timestamp_end"),
        "description": (
            f"status={manifest.get('status', 'UNKNOWN')}; conclusion_maturity={maturity}"
        ),
    }
    objects = [{"@id": f"#input/{name}"} for name in (sib.get("inputs") or {})]
    results = [{"@id": r.get("path")} for r in artifacts.get("results", []) if r.get("path")]
    if objects:
        action["object"] = objects
    if results:
        action["result"] = results
    if str(manifest.get("status", "")).upper() in ("FAILED", "ERROR"):
        action["error"] = {"@id": "#error"}
        graph.append({"@id": "#error", "@type": "Thing", "name": manifest.get("status", "FAILED")})
    graph.append(action)

    # Root dataset
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"BioNexus Run Capsule: {run_id}",
        "description": (
            f"RO-Crate export of BioNexus run '{run_id}' for capability '{capability_id}'. "
            f"Execution state {execution_state}; conclusion maturity {maturity}."
        ),
        "mainEntity": {"@id": f"#workflow/{capability_id}"},
        "hasPart": crate_files,
        "mentions": [{"@id": f"#run/{run_id}"}, {"@id": "#evidence-card"}],
        "datePublished": manifest.get("timestamp_end"),
        "author": {"@id": "https://github.com/HERRY423/BioNexus"},
    }
    graph.insert(0, root)

    # Metadata descriptor (MUST be first in a serialized crate file; here it is
    # included as the conventional head entity of the graph)
    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": RO_CRATE_PROFILE},
    }
    graph.insert(0, descriptor)

    return {"@context": RO_CRATE_CONTEXT, "@graph": graph}


def ledger_to_ro_crate(ledger: ClaimLedger) -> Dict[str, Any]:
    """
    Project a Claim–Evidence Ledger into an RO-Crate 1.1 document: evidence
    refs and claims become contextual entities; support edges use schema.org
    isBasedOn (BNS-IO-002).
    """
    graph: List[Dict[str, Any]] = []

    for rid, ref in ledger.evidence.items():
        graph.append(
            {
                "@id": f"#evidence/{rid}",
                "@type": "CreativeWork",
                "name": rid,
                "additionalType": ref.kind,
                "description": f"{ref.summary or ref.kind} (maturity: {ref.maturity})",
            }
        )

    for cid, claim in ledger.claims.items():
        node: Dict[str, Any] = {
            "@id": f"#claim/{cid}",
            "@type": "CreativeWork",
            "name": claim.statement,
            "description": f"evidence_status: {claim.evidence_status}"
            + (f"; capability: {claim.capability_id}" if claim.capability_id else ""),
        }
        based_on = [f"#evidence/{r}" for r in (*claim.supported_by, *claim.depends_on) if r in ledger.evidence]
        if based_on:
            node["isBasedOn"] = [{"@id": b} for b in based_on]
        if claim.contradicted_by:
            node["disambiguatingDescription"] = "CONTRADICTED by: " + ", ".join(claim.contradicted_by)
        graph.append(node)

    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": "BioNexus Claim–Evidence Ledger",
        "description": (
            "RO-Crate export of a BioNexus Claim–Evidence Ledger (BNS-012). Claims are "
            "contextual entities with fail-closed evidence statuses; the PROV-O projection "
            "remains available via the ledger itself."
        ),
        "hasPart": [{"@id": f"#claim/{cid}"} for cid in ledger.claims],
        "mentions": [{"@id": f"#evidence/{rid}"} for rid in ledger.evidence],
    }
    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": RO_CRATE_PROFILE},
    }
    graph.insert(0, root)
    graph.insert(0, descriptor)
    return {"@context": RO_CRATE_CONTEXT, "@graph": graph}


def validate_ro_crate(doc: Dict[str, Any]) -> List[str]:
    """
    Structural RO-Crate 1.1 validation (offline, deterministic).

    Scope disclosure (BNS-IO-010): this checks the crate skeleton required by
    the specification — context, metadata descriptor, root Dataset, profile
    declarations, CreateAction wiring — NOT full JSON-LD expansion or the
    complete profile validators (ro-crate-validator integration is tracked in
    the standards registry).
    """
    errors: List[str] = []
    graph = doc.get("@graph")
    if doc.get("@context") != RO_CRATE_CONTEXT:
        errors.append(f"@context MUST be {RO_CRATE_CONTEXT}")
    if not isinstance(graph, list) or not graph:
        return errors + ["@graph must be a non-empty array"]

    by_id = {e.get("@id"): e for e in graph if isinstance(e, dict)}

    descriptor = by_id.get("ro-crate-metadata.json")
    if not descriptor:
        errors.append("missing ro-crate-metadata.json descriptor entity")
    else:
        if descriptor.get("@type") != "CreativeWork":
            errors.append("descriptor @type MUST be CreativeWork")
        if not descriptor.get("about"):
            errors.append("descriptor MUST point at the root entity via about")
        conforms = descriptor.get("conformsTo")
        if not (isinstance(conforms, dict) and conforms.get("@id") == RO_CRATE_PROFILE):
            errors.append(f"descriptor MUST declare conformsTo {RO_CRATE_PROFILE}")

    root = by_id.get("./")
    if not root:
        errors.append("missing root Dataset './'")
    else:
        if "Dataset" not in _as_type_list(root.get("@type")):
            errors.append("root entity './' MUST be a Dataset")
        if not root.get("name"):
            errors.append("root Dataset MUST carry a name")

    actions = [e for e in graph if isinstance(e, dict) and "CreateAction" in _as_type_list(e.get("@type"))]
    for act in actions:
        if not act.get("instrument"):
            errors.append(f"CreateAction '{act.get('@id')}' MUST reference an instrument")
        if act.get("conformsTo") is None and act.get("startTime") is None:
            errors.append(f"CreateAction '{act.get('@id')}' lacks both profile and timing information")
    return errors


def _as_type_list(t: Any) -> List[str]:
    if t is None:
        return []
    return [t] if isinstance(t, str) else list(t)


# ==============================================================================
# BioCompute Object (IEEE 2791-2020) projection
# ==============================================================================


def _bco_etag(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_bundle_to_bco(manifest: Dict[str, Any], siblings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Project a BioNexus run capsule into a BioCompute Object following the
    IEEE 2791-2020 six-domain structure (BNS-IO-003).
    """
    sib = siblings or {}
    run_id = manifest.get("run_id", "unknown-run")
    capability_id = manifest.get("capability_id", "unknown.capability")
    artifacts = manifest.get("artifacts", {})
    environment = sib.get("environment") or {}

    inputs = sib.get("inputs") or {}
    input_subdomain = [
        {
            "uri": {
                "filename": (inp.get("path") or name),
                "checksum": inp.get("sha256", ""),
            },
            "semantic_type": inp.get("semantic_type", "unspecified"),
        }
        for name, inp in inputs.items()
    ]
    output_subdomain = [
        {
            "uri": {"filename": res.get("path", ""), "checksum": res.get("sha256", "")},
            "semantic_type": res.get("semantic_type", "unspecified"),
        }
        for res in artifacts.get("results", [])
    ]

    software_prerequisites = [
        {"name": "BioNexus", "version": manifest.get("bionexus_version", PLUGIN_VERSION)}
    ]
    for pkg, version in (environment.get("packages") or {}).items():
        software_prerequisites.append({"name": pkg, "version": str(version)})

    parameters = sib.get("parameters") or {}
    parametric_domain = [
        {"param": str(k), "value": json.dumps(v, default=str), "step": "1"} for k, v in parameters.items()
    ]

    maturity = manifest.get("conclusion_maturity", "UNASSESSED")
    execution_state = manifest.get("execution_state", "PENDING")

    bco: Dict[str, Any] = {
        "spec_version": BCO_SPEC_VERSION,
        "provenance_domain": {
            "name": f"BioNexus run {run_id}",
            "version": manifest.get("bionexus_version", PLUGIN_VERSION),
            "created": manifest.get("timestamp_start"),
            "modified": manifest.get("timestamp_end"),
            "created_by": ["bionexus"],
            "review": [
                {
                    "status": "approved" if execution_state == "EXECUTED" else "unreviewed",
                    "reviewer_comment": (
                        f"Machine review by BioNexus fail-closed engine: execution_state={execution_state}, "
                        f"conclusion_maturity={maturity}"
                    ),
                }
            ],
        },
        "usability_domain": [
            f"BioNexus execution of capability '{capability_id}' (run {run_id}).",
            f"Execution state: {execution_state}; conclusion maturity: {maturity}.",
            "Research Use Only. This object describes a computation, not a clinical assertion.",
        ],
        "description_domain": {
            "keywords": [capability_id, manifest.get("skill_name", ""), "BioNexus", "fail-closed execution"],
            "pipeline_steps": [
                {
                    "step_number": 1,
                    "name": capability_id,
                    "description": f"BioNexus capability contract execution (run {run_id})",
                    "version": manifest.get("bionexus_version", PLUGIN_VERSION),
                }
            ],
        },
        "execution_domain": {
            "script": [
                {"uri": {"filename": "run.json", "checksum": ""}, "script_type": "bionexus-run-capsule-descriptor"}
            ],
            "script_driver": [{"name": "bionexus", "version": manifest.get("bionexus_version", PLUGIN_VERSION)}],
            "software_prerequisites": software_prerequisites,
            "external_data_endpoints": [],
            "environment_variables": {},
        },
        "io_domain": {
            "input_subdomain": input_subdomain,
            "output_subdomain": output_subdomain,
        },
        "parametric_domain": parametric_domain,
    }
    bco["etag"] = _bco_etag(json.dumps({k: v for k, v in bco.items()}, sort_keys=True, default=str))
    return bco


def validate_bco(doc: Dict[str, Any]) -> List[str]:
    """
    Structural IEEE 2791-2020 validation (offline, deterministic): all six
    domains present and non-degenerate, spec_version pinned, etag computed
    from content rather than asserted (BNS-IO-009).
    """
    errors: List[str] = []
    if doc.get("spec_version") != BCO_SPEC_VERSION:
        errors.append(f"spec_version MUST be {BCO_SPEC_VERSION}")
    etag = doc.get("etag")
    if not etag:
        errors.append("etag MUST be present and non-empty")

    for domain in BCO_DOMAINS:
        value = doc.get(domain)
        if domain in ("usability_domain", "parametric_domain"):
            if not isinstance(value, list):
                errors.append(f"{domain} MUST be an array")
            if domain == "usability_domain" and not value:
                errors.append("usability_domain MUST be a non-empty array of strings")
        elif not isinstance(value, dict):
            errors.append(f"{domain} MUST be an object")

    io = doc.get("io_domain")
    if isinstance(io, dict):
        for sub in ("input_subdomain", "output_subdomain"):
            if not isinstance(io.get(sub), list):
                errors.append(f"io_domain.{sub} MUST be an array")

    pd = doc.get("parametric_domain")
    if isinstance(pd, list):
        for item in pd:
            if not (isinstance(item, dict) and "param" in item and "value" in item):
                errors.append("each parametric_domain entry MUST carry param and value")

    if etag:
        recomputed = _bco_etag(json.dumps({k: v for k, v in doc.items() if k != "etag"}, sort_keys=True, default=str))
        if etag != recomputed:
            errors.append("etag does not match recomputed content hash (asserted, not computed)")
    return errors


# ==============================================================================
# High-level export API (fail-closed)
# ==============================================================================


def _default_out(path: str | Path, filename: str) -> Path:
    p = Path(path)
    base = p.parent if p.is_file() else p
    return base / filename


def export_ro_crate(path: str | Path, out_path: Optional[str | Path] = None) -> Tuple[Path, List[str]]:
    """
    Export a run capsule or ledger at `path` as an RO-Crate; validate before
    writing (BNS-IO-004: an invalid projection is never written to disk).
    """
    kind, manifest, siblings = load_interop_source(path)
    if kind == "ledger":
        doc = ledger_to_ro_crate(ClaimLedger.from_dict(manifest))
    else:
        doc = run_bundle_to_ro_crate(manifest, siblings)
    errors = validate_ro_crate(doc)
    if errors:
        raise ValueError("RO-Crate projection failed structural validation: " + "; ".join(errors))
    target = Path(out_path) if out_path else _default_out(path, "ro-crate-metadata.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target, errors


def export_bco(path: str | Path, out_path: Optional[str | Path] = None) -> Tuple[Path, List[str]]:
    """Export a run capsule at `path` as an IEEE 2791-2020 BCO (fail-closed)."""
    kind, manifest, siblings = load_interop_source(path)
    if kind != "run":
        raise ValueError(
            "BioCompute Objects describe computations: export a run capsule (run.json), "
            "not a Claim–Evidence Ledger. Ledger exports use RO-Crate / PROV-O."
        )
    doc = run_bundle_to_bco(manifest, siblings)
    errors = validate_bco(doc)
    if errors:
        raise ValueError("BCO projection failed structural validation: " + "; ".join(errors))
    target = Path(out_path) if out_path else _default_out(path, "bco.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target, errors


# ==============================================================================
# Workflow Run RO-Crate bundle export (BNS-IO-014)
#
# Packages a run capsule into a standard Research Object directory conforming
# to the Workflow Run RO-Crate profile family:
#   - Process Run Crate 0.5   (execution as CreateAction)          always
#   - Workflow Run Crate 0.5  (+ mainEntity ComputationalWorkflow) always
#   - Provenance Run Crate 0.5 (+ per-step tool/step executions)   when the
#     capsule records steps (RunBundle.record_step)
#
# Scope disclosure (honesty policy): this is structural conformance to the
# profile requirements cited in BNS-016 — the official ro-crate-validator and
# profile validators are not run here (tracked in the standards registry).
# All facts are projections of the sealed capsule; nothing is invented. In
# particular no human agent is asserted (agent is the executing software) and
# no evidence maturity is changed by the export.
# ==============================================================================


@dataclass
class _FilePlan:
    """A file to materialize inside the crate and the entity that describes it.

    `content` carries either a generated JSON document, or a marker dict
    (`__capsule_rel__` / `__ledger_source__`) resolved against the capsule
    directory at materialization time — the planner itself stays pure.
    """

    crate_rel: str
    entity_id: str
    content: Optional[Dict[str, Any]] = None


@dataclass
class _CratePlan:
    doc: Dict[str, Any]
    files: List[_FilePlan] = field(default_factory=list)


@dataclass
class CrateExportResult:
    """Outcome of a fail-closed Workflow Run RO-Crate bundle export."""

    crate_dir: Path
    metadata_path: Path
    zip_path: Optional[Path] = None
    files_copied: int = 0
    steps_projected: int = 0
    ledger_included: bool = False
    validation_errors: List[str] = field(default_factory=list)
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crate_dir": str(self.crate_dir),
            "metadata_path": str(self.metadata_path),
            "zip_path": str(self.zip_path) if self.zip_path else None,
            "files_copied": self.files_copied,
            "steps_projected": self.steps_projected,
            "ledger_included": self.ledger_included,
            "validation_errors": list(self.validation_errors),
            "verified": self.verified,
        }


def _safe_crate_name(name: str) -> str:
    cleaned = "".join("_" if c in '\\/:*?"<>|' or c.isspace() else c for c in str(name)).strip("._")
    return cleaned or "unnamed"


def _file_sha256(path: Path) -> str:
    """Raw-byte SHA-256 (crate checksums must match what standard consumers compute)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_lf_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON with LF newlines so crate bytes are identical across OSes."""
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def _action_status_uri(status: Any) -> str:
    s = str(status or "").upper()
    if s in ("FAILED", "ERROR"):
        return _FAILED_STATUS
    if s in ("COMPLETED", "OK", "SUCCESS"):
        return _COMPLETED_STATUS
    return _ACTIVE_STATUS


def _encoding_format_for(suffix: str) -> Optional[str]:
    return _ENCODING_FORMATS.get(Path(suffix).suffix.lower() or suffix.lower())


def _param_additional_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Float"
    if isinstance(value, str):
        return "Text"
    return "PropertyValue"


def _workflow_descriptor(manifest: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Materialized, honest stand-in for the capability contract (BNS-IO-014)."""
    return {
        "descriptor_kind": "bionexus.capability-descriptor.v1",
        "capability_id": manifest.get("capability_id", "unknown.capability"),
        "skill_name": manifest.get("skill_name", "unknown-skill"),
        "bionexus_version": manifest.get("bionexus_version", PLUGIN_VERSION),
        "bundle_schema_version": manifest.get("bundle_schema_version"),
        "description": (
            "Projection of the executed BioNexus capability as recorded in the sealed "
            "run capsule manifest. The normative capability contract lives in the "
            "BioNexus registry (bionexus.registry.yaml); this descriptor states what ran."
        ),
        "steps": [
            {"name": s.get("name", ""), "tool": s.get("tool", ""), "status": s.get("status", "")}
            for s in steps
        ],
    }


def plan_workflow_run_crate(
    manifest: Dict[str, Any],
    siblings: Optional[Dict[str, Any]] = None,
    *,
    steps: Optional[List[Dict[str, Any]]] = None,
    ledger: Optional[Dict[str, Any]] = None,
) -> _CratePlan:
    """
    Build the Workflow Run RO-Crate metadata document plus the file plan that
    materializes it as a Research Object directory. Pure and offline: no disk
    access, no timestamps beyond those recorded in the capsule (BNS-IO-006).
    """
    sib = siblings or {}
    steps = list(steps or [])
    run_id = str(manifest.get("run_id", "unknown-run"))
    capability_id = str(manifest.get("capability_id", "unknown.capability"))
    maturity = manifest.get("conclusion_maturity", "UNASSESSED")
    execution_state = manifest.get("execution_state", "PENDING")
    run_status = str(manifest.get("status", "UNKNOWN"))
    artifacts = manifest.get("artifacts", {}) or {}
    inputs = sib.get("inputs") or {}
    parameters = sib.get("parameters") or {}
    environment = sib.get("environment") or {}

    graph: List[Dict[str, Any]] = []
    files: List[_FilePlan] = []
    root_has_part: List[Dict[str, Any]] = []

    # ---- profile CreativeWork entities (referenced via root conformsTo) -----
    declared_profiles = [
        PROCESS_RUN_CRATE_PROFILE,
        WORKFLOW_RUN_CRATE_PROFILE,
        WORKFLOW_RO_CRATE_PROFILE_1_0,
    ]
    if steps:
        declared_profiles.insert(2, PROVENANCE_RUN_CRATE_PROFILE)
    for profile_id in declared_profiles:
        name, version = _PROFILE_ENTITIES[profile_id]
        graph.append({"@id": profile_id, "@type": "CreativeWork", "name": name, "version": version})

    # ---- workflow entity (materialized capability descriptor) ---------------
    workflow_rel = f"workflows/{_safe_crate_name(capability_id)}.json"
    files.append(
        _FilePlan(
            crate_rel=workflow_rel,
            entity_id=workflow_rel,
            content=_workflow_descriptor(manifest, steps),
        )
    )
    workflow: Dict[str, Any] = {
        "@id": workflow_rel,
        "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
        "name": capability_id,
        "description": (
            f"BioNexus capability '{capability_id}' (skill: "
            f"{manifest.get('skill_name', 'unknown')}) as executed in run {run_id}."
        ),
        "programmingLanguage": {"@id": "https://www.python.org/"},
    }
    graph.append(workflow)
    root_has_part.append({"@id": workflow_rel})

    # ---- input files + FormalParameters -------------------------------------
    input_object_refs: List[Dict[str, Any]] = []
    workflow_input_slots: List[Dict[str, Any]] = []
    for name in sorted(inputs):
        inp = inputs[name]
        crate_rel = f"data/inputs/{_safe_crate_name(name)}"
        original = inp.get("path") or ""
        if not original:
            raise ValueError(
                f"Input '{name}' has no recorded path; a Research Object must package "
                "the actual input bytes (fail-closed, BNS-IO-014)."
            )
        files.append(_FilePlan(crate_rel=crate_rel, entity_id=crate_rel, content={"__input_src__": original}))
        entity: Dict[str, Any] = {
            "@id": crate_rel,
            "@type": "File",
            "name": str(name),
            "description": f"Input artifact ({inp.get('semantic_type', 'unspecified')})",
        }
        if Path(original).name != str(name):
            entity["alternateName"] = Path(original).name
        fmt = _encoding_format_for(Path(original).suffix) if original else None
        if fmt:
            entity["encodingFormat"] = fmt
        if inp.get("sha256") and inp["sha256"] != "missing":
            entity["sha256"] = inp["sha256"]
        graph.append(entity)
        root_has_part.append({"@id": crate_rel})
        input_object_refs.append({"@id": crate_rel})
        param_id = f"#input-param/{_safe_crate_name(name)}"
        graph.append(
            {
                "@id": param_id,
                "@type": "FormalParameter",
                "additionalType": "File",
                "conformsTo": {"@id": FORMAL_PARAMETER_PROFILE},
                "name": str(name),
                "description": f"Input slot '{name}' ({inp.get('semantic_type', 'unspecified')})",
                "workExample": {"@id": crate_rel},
            }
        )
        workflow_input_slots.append({"@id": param_id})

    # ---- scalar parameters as FormalParameter + PropertyValue ---------------
    param_value_refs: List[Dict[str, Any]] = []
    for name in sorted(parameters):
        value = parameters[name]
        safe = _safe_crate_name(name)
        param_id = f"#param/{safe}"
        value_id = f"#param-value/{safe}"
        graph.append(
            {
                "@id": param_id,
                "@type": "FormalParameter",
                "additionalType": _param_additional_type(value),
                "conformsTo": {"@id": FORMAL_PARAMETER_PROFILE},
                "name": str(name),
                "description": f"Execution parameter '{name}' recorded in the run capsule",
                "workExample": {"@id": value_id},
            }
        )
        graph.append(
            {
                "@id": value_id,
                "@type": "PropertyValue",
                "name": str(name),
                "value": json.dumps(value, default=str),
                "exampleOfWork": {"@id": param_id},
            }
        )
        workflow_input_slots.append({"@id": param_id})
        param_value_refs.append({"@id": value_id})

    # ---- result + figure files ----------------------------------------------
    result_refs: List[Dict[str, Any]] = []
    workflow_output_slots: List[Dict[str, Any]] = []
    for res in artifacts.get("results", []):
        rel = res.get("path", "")
        if not rel:
            continue
        crate_rel = f"data/{rel}"
        files.append(_FilePlan(crate_rel=crate_rel, entity_id=crate_rel, content={"__result_rel__": rel}))
        entity = {
            "@id": crate_rel,
            "@type": "File",
            "name": res.get("name", Path(rel).name),
            "description": f"Result artifact ({res.get('semantic_type', 'unspecified')})",
        }
        if artifacts.get("primary_result") == rel:
            entity["description"] = f"Primary result artifact ({res.get('semantic_type', 'unspecified')})"
        fmt = _encoding_format_for(Path(rel).suffix)
        if fmt:
            entity["encodingFormat"] = fmt
        if res.get("sha256") and res["sha256"] != "pending":
            entity["sha256"] = res["sha256"]
        graph.append(entity)
        root_has_part.append({"@id": crate_rel})
        result_refs.append({"@id": crate_rel})
        param_id = f"#output-param/{_safe_crate_name(res.get('name', Path(rel).stem))}"
        graph.append(
            {
                "@id": param_id,
                "@type": "FormalParameter",
                "additionalType": "File",
                "conformsTo": {"@id": FORMAL_PARAMETER_PROFILE},
                "name": res.get("name", Path(rel).stem),
                "description": f"Output slot '{res.get('name', rel)}'",
                "workExample": {"@id": crate_rel},
            }
        )
        workflow_output_slots.append({"@id": param_id})
    for fig in artifacts.get("figures", []):
        rel = fig.get("path", "")
        if not rel:
            continue
        crate_rel = f"data/{rel}"
        files.append(_FilePlan(crate_rel=crate_rel, entity_id=crate_rel, content={"__result_rel__": rel}))
        entity = {
            "@id": crate_rel,
            "@type": "File",
            "name": fig.get("title", Path(rel).name),
            "description": "Figure artifact generated by the run",
        }
        fmt = fig.get("format") and _encoding_format_for("." + str(fig["format"]))
        if fmt:
            entity["encodingFormat"] = fmt
        if fig.get("sha256") and fig["sha256"] != "pending":
            entity["sha256"] = fig["sha256"]
        graph.append(entity)
        root_has_part.append({"@id": crate_rel})
        result_refs.append({"@id": crate_rel})

    workflow["input"] = workflow_input_slots
    workflow["output"] = workflow_output_slots

    # ---- software: engine, packages, language -------------------------------
    engine: Dict[str, Any] = {
        "@id": BIONEXUS_AGENT_ID,
        "@type": "SoftwareApplication",
        "name": "BioNexus",
        "softwareVersion": manifest.get("bionexus_version", PLUGIN_VERSION),
        "url": BIONEXUS_AGENT_ID,
        "description": "The Scientific Reliability Layer for Agentic Biology",
    }
    package_refs: List[Dict[str, Any]] = []
    for pkg in sorted(environment.get("packages") or {}):
        pkg_id = f"#pkg/{_safe_crate_name(pkg)}"
        graph.append(
            {
                "@id": pkg_id,
                "@type": "SoftwareApplication",
                "name": pkg,
                "softwareVersion": str(environment["packages"][pkg]),
            }
        )
        package_refs.append({"@id": pkg_id})
    if package_refs:
        engine["softwareRequirements"] = package_refs
    graph.append(engine)
    graph.append(
        {
            "@id": "https://www.python.org/",
            "@type": "ComputerLanguage",
            "name": "Python",
            "url": "https://www.python.org/",
        }
    )

    # ---- engine / tool / step provenance (Provenance Run Crate) -------------
    step_run_refs: List[Dict[str, Any]] = []
    if steps:
        tools: Dict[str, Dict[str, Any]] = {}
        for idx, step in enumerate(steps, start=1):
            tool_name = str(step.get("tool", "") or "unknown-tool")
            if tool_name not in tools:
                tool_id = f"#tool/{_safe_crate_name(tool_name)}"
                tool_entity = {
                    "@id": tool_id,
                    "@type": "SoftwareApplication",
                    "name": tool_name,
                }
                version = step.get("tool_version") or (environment.get("packages") or {}).get(tool_name)
                if version:
                    tool_entity["softwareVersion"] = str(version)
                tools[tool_name] = tool_entity
                graph.append(tool_entity)
        workflow["hasPart"] = [{"@id": t["@id"]} for t in tools.values()]
        workflow["@type"] = list(workflow["@type"]) + ["HowTo"]

        howto_ids: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps, start=1):
            step_name = str(step.get("name", f"step-{idx}"))
            safe = _safe_crate_name(step_name)
            tool_name = str(step.get("tool", "") or "unknown-tool")
            tool_id = tools[tool_name]["@id"]
            howto_id = f"#step/{idx}-{safe}"
            howto: Dict[str, Any] = {
                "@id": howto_id,
                "@type": "HowToStep",
                "position": idx,
                "name": step_name,
                "workExample": {"@id": tool_id},
            }
            if step.get("description"):
                howto["description"] = step["description"]
            graph.append(howto)
            howto_ids.append({"@id": howto_id})

            # Tool execution (CreateAction) for this step.
            object_refs = []
            for inp in step.get("inputs", []):
                if inp in inputs:
                    object_refs.append({"@id": f"data/inputs/{_safe_crate_name(inp)}"})
                else:
                    for res in artifacts.get("results", []):
                        if res.get("name") == inp and res.get("path"):
                            object_refs.append({"@id": f"data/{res['path']}"})
                            break
            result_refs_step = []
            for out in step.get("outputs", []):
                for res in artifacts.get("results", []):
                    if res.get("name") == out and res.get("path"):
                        result_refs_step.append({"@id": f"data/{res['path']}"})
                        break
            tool_run_id = f"#tool-run/{idx}-{safe}"
            tool_run: Dict[str, Any] = {
                "@id": tool_run_id,
                "@type": "CreateAction",
                "name": f"Execute {tool_name} (step '{step_name}')",
                "instrument": {"@id": tool_id},
            }
            if object_refs:
                tool_run["object"] = object_refs
            if result_refs_step:
                tool_run["result"] = result_refs_step
            if step.get("started_at"):
                tool_run["startTime"] = step["started_at"]
            if step.get("ended_at"):
                tool_run["endTime"] = step["ended_at"]
            status_uri = _action_status_uri(step.get("status"))
            tool_run["actionStatus"] = {"@id": status_uri}
            if step.get("error") and status_uri == _FAILED_STATUS:
                tool_run["error"] = step["error"]
            graph.append(tool_run)

            # Step execution (ControlAction) binding the HowToStep to tool runs.
            step_run_id = f"#step-run/{idx}-{safe}"
            step_run: Dict[str, Any] = {
                "@id": step_run_id,
                "@type": "ControlAction",
                "name": f"Workflow step '{step_name}'",
                "instrument": {"@id": howto_id},
                "object": [{"@id": tool_run_id}],
                "actionStatus": {"@id": status_uri},
            }
            if step.get("error") and status_uri == _FAILED_STATUS:
                step_run["error"] = step["error"]
            graph.append(step_run)
            step_run_refs.append({"@id": step_run_id})
        workflow["step"] = howto_ids

    # ---- capsule descriptor files --------------------------------------------
    for src_rel, crate_rel, label in (
        ("run.json", "metadata/run.json", "BioNexus Run Capsule master descriptor"),
        ("inputs.json", "metadata/inputs.json", "Input manifest with SHA-256 hashes"),
        ("parameters.json", "metadata/parameters.json", "Resolved execution parameters"),
        ("evidence.json", "metadata/evidence.json", "EvidenceCard 2.0 (execution state and maturity)"),
        ("provenance.json", "metadata/provenance.json", "W3C PROV-O provenance sidecar"),
        ("environment.json", "metadata/environment.json", "Pinned environment snapshot"),
        ("logs/pipeline.log", "logs/pipeline.log", "BioNexus execution log"),
    ):
        files.append(
            _FilePlan(
                crate_rel=crate_rel,
                entity_id=crate_rel,
                content={"__capsule_rel__": src_rel},
            )
        )
        entity: Dict[str, Any] = {"@id": crate_rel, "@type": "File", "name": Path(crate_rel).name}
        if src_rel == "logs/pipeline.log":
            entity["name"] = "pipeline.log"
            entity["description"] = label
            entity["about"] = {"@id": f"#run/{run_id}"}
        else:
            entity["description"] = label
        graph.append(entity)
        root_has_part.append({"@id": crate_rel})

    # ---- Claim–Evidence Ledger (embedded, never re-statused) -----------------
    mention_refs: List[Dict[str, Any]] = [{"@id": f"#run/{run_id}"}, {"@id": "#evidence-card"}]
    ledger_included = bool(ledger and (ledger.get("claims") or ledger.get("evidence")))
    if ledger_included:
        files.append(
            _FilePlan(
                crate_rel="metadata/claim-ledger.json",
                entity_id="metadata/claim-ledger.json",
                content={"__ledger_source__": True},
            )
        )
        graph.append(
            {
                "@id": "metadata/claim-ledger.json",
                "@type": "File",
                "name": "claim-ledger.json",
                "description": "BioNexus Claim–Evidence Ledger (BNS-012) machine-readable source",
            }
        )
        root_has_part.append({"@id": "metadata/claim-ledger.json"})
        for rid, ref in (ledger.get("evidence") or {}).items():
            graph.append(
                {
                    "@id": f"#evidence/{rid}",
                    "@type": "CreativeWork",
                    "name": str(rid),
                    "bnsEvidenceKind": ref.get("kind", ""),
                    "bnsMaturity": ref.get("maturity", ""),
                    "bnsValidationRole": ref.get("validation_role", ""),
                    "description": f"{ref.get('summary') or ref.get('kind', '')} "
                    f"(maturity: {ref.get('maturity', '')})",
                }
            )
            mention_refs.append({"@id": f"#evidence/{rid}"})
        for cid, claim in (ledger.get("claims") or {}).items():
            claim_entity: Dict[str, Any] = {
                "@id": f"#claim/{cid}",
                "@type": "CreativeWork",
                "name": str(claim.get("statement", cid)),
                "bnsEvidenceStatus": claim.get("evidence_status", ""),
                "description": f"evidence_status: {claim.get('evidence_status', '')}"
                + (f"; capability: {claim['capability_id']}" if claim.get("capability_id") else ""),
            }
            based_on = [
                {"@id": f"#evidence/{r}"}
                for r in (*claim.get("supported_by", []), *claim.get("depends_on", []))
                if r in (ledger.get("evidence") or {})
            ]
            if based_on:
                claim_entity["isBasedOn"] = based_on
            if claim.get("contradicted_by"):
                claim_entity["disambiguatingDescription"] = "CONTRADICTED by: " + ", ".join(
                    claim["contradicted_by"]
                )
            graph.append(claim_entity)
            mention_refs.append({"@id": f"#claim/{cid}"})

    # ---- EvidenceCard contextual entity (maturity rides inside the crate) ---
    evidence_entity: Dict[str, Any] = {
        "@id": "#evidence-card",
        "@type": "CreativeWork",
        "name": "BioNexus EvidenceCard 2.0",
        "about": {"@id": f"#run/{run_id}"},
        "description": f"execution_state={execution_state}; conclusion_maturity={maturity}",
        "bnsExecutionState": execution_state,
        "bnsConclusionMaturity": maturity,
    }
    evidence_sib = sib.get("evidence") or {}
    for dim, key in (
        ("input_integrity", "bnsInputIntegrity"),
        ("assumption_validity", "bnsAssumptionValidity"),
        ("statistical_support", "bnsStatisticalSupport"),
        ("parameter_robustness", "bnsParameterRobustness"),
        ("cross_method_concordance", "bnsCrossMethodConcordance"),
        ("external_validation", "bnsExternalValidation"),
    ):
        if evidence_sib.get(dim):
            evidence_entity[key] = evidence_sib[dim]
    graph.append(evidence_entity)

    # ---- main workflow run CreateAction --------------------------------------
    action: Dict[str, Any] = {
        "@id": f"#run/{run_id}",
        "@type": "CreateAction",
        "name": f"BioNexus execution {run_id}",
        "instrument": {"@id": workflow_rel},
        "agent": {"@id": BIONEXUS_AGENT_ID},
        "description": (
            f"status={run_status}; execution_state={execution_state}; "
            f"conclusion_maturity={maturity}"
        ),
        "bnsRunStatus": run_status,
        "bnsConclusionMaturity": maturity,
    }
    if manifest.get("timestamp_start"):
        action["startTime"] = manifest["timestamp_start"]
    if manifest.get("timestamp_end"):
        action["endTime"] = manifest["timestamp_end"]
    action_object = input_object_refs + param_value_refs
    if action_object:
        action["object"] = action_object
    if result_refs:
        action["result"] = result_refs
    action["actionStatus"] = {"@id": _action_status_uri(run_status)}
    if _action_status_uri(run_status) == _FAILED_STATUS:
        action["error"] = {"@id": "#error"}
        graph.append({"@id": "#error", "@type": "Thing", "name": run_status})
    graph.append(action)

    # ---- engine run OrganizeAction (required when steps are projected) ------
    if steps:
        engine_run: Dict[str, Any] = {
            "@id": f"#engine-run/{run_id}",
            "@type": "OrganizeAction",
            "name": f"BioNexus engine run for {run_id}",
            "instrument": {"@id": BIONEXUS_AGENT_ID},
            "object": step_run_refs,
            "result": {"@id": f"#run/{run_id}"},
            "actionStatus": {"@id": _action_status_uri(run_status)},
        }
        if manifest.get("timestamp_start"):
            engine_run["startTime"] = manifest["timestamp_start"]
        if manifest.get("timestamp_end"):
            engine_run["endTime"] = manifest["timestamp_end"]
        graph.append(engine_run)

    # ---- root Dataset --------------------------------------------------------
    root: Dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"BioNexus Run Capsule: {run_id}",
        "description": (
            f"Workflow Run RO-Crate export of BioNexus run '{run_id}' for capability "
            f"'{capability_id}'. Execution state {execution_state}; conclusion maturity "
            f"{maturity}. Research Use Only: this object describes a computation, not a "
            f"clinical assertion."
        ),
        "mainEntity": {"@id": workflow_rel},
        "hasPart": root_has_part,
        "mentions": mention_refs,
        "conformsTo": [{"@id": p} for p in declared_profiles],
        "author": {"@id": BIONEXUS_AGENT_ID},
        "license": {"@id": "https://www.apache.org/licenses/LICENSE-2.0"},
    }
    if manifest.get("timestamp_end"):
        root["datePublished"] = manifest["timestamp_end"]
    graph.insert(0, root)

    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": [{"@id": RO_CRATE_PROFILE}, {"@id": WORKFLOW_RO_CRATE_PROFILE_1_0}],
    }
    graph.insert(0, descriptor)

    doc = {"@context": WORKFLOW_RUN_CRATE_CONTEXT, "@graph": graph}
    return _CratePlan(doc=doc, files=files)


def run_bundle_to_workflow_run_crate(
    manifest: Dict[str, Any],
    siblings: Optional[Dict[str, Any]] = None,
    *,
    steps: Optional[List[Dict[str, Any]]] = None,
    ledger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Document-only Workflow Run RO-Crate projection of a run capsule."""
    return plan_workflow_run_crate(manifest, siblings, steps=steps, ledger=ledger).doc


def validate_workflow_run_crate(doc: Dict[str, Any]) -> List[str]:
    """
    Structural validation against the Workflow Run RO-Crate profile family
    (Process Run Crate 0.5 / Workflow Run Crate 0.5 / Workflow RO-Crate 1.0,
    plus Provenance Run Crate 0.5 when step executions are projected).
    Scope: the MUST-level requirements cited in BNS-016, not the official
    ro-crate-validator (BNS-IO-010).
    """
    errors: List[str] = []
    context = doc.get("@context")
    if context != WORKFLOW_RUN_CRATE_CONTEXT:
        errors.append(
            f"@context MUST be the profile contexts plus BioNexus term map {WORKFLOW_RUN_CRATE_CONTEXT}"
        )
    graph = doc.get("@graph")
    if not isinstance(graph, list) or not graph:
        return errors + ["@graph must be a non-empty array"]

    by_id = {e.get("@id"): e for e in graph if isinstance(e, dict)}

    def types_of(entity: Optional[Dict[str, Any]]) -> List[str]:
        if not entity:
            return []
        t = entity.get("@type")
        return [t] if isinstance(t, str) else list(t or [])

    def id_of(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            return value.get("@id")
        if isinstance(value, str):
            return value
        return None

    def ref_list(value: Any) -> List[str]:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        return [i for i in (id_of(v) for v in items) if i]

    descriptor = by_id.get("ro-crate-metadata.json")
    if not descriptor:
        errors.append("missing ro-crate-metadata.json descriptor entity")
    else:
        if "CreativeWork" not in types_of(descriptor):
            errors.append("descriptor @type MUST be CreativeWork")
        if id_of(descriptor.get("about")) != "./":
            errors.append("descriptor MUST point at the root entity via about")
        declared = set(ref_list(descriptor.get("conformsTo")))
        for required in (RO_CRATE_PROFILE, WORKFLOW_RO_CRATE_PROFILE_1_0):
            if required not in declared:
                errors.append(f"descriptor conformsTo MUST include {required}")

    root = by_id.get("./")
    if not root:
        return errors + ["missing root Dataset './'"]
    if "Dataset" not in types_of(root):
        errors.append("root entity './' MUST be a Dataset")
    if not root.get("name"):
        errors.append("root Dataset MUST carry a name")

    # Profile chain declared via root conformsTo, each pinned to a CreativeWork.
    declared_profiles = ref_list(root.get("conformsTo"))
    if WORKFLOW_RUN_CRATE_PROFILE not in declared_profiles:
        errors.append(f"root conformsTo MUST reference {WORKFLOW_RUN_CRATE_PROFILE}")
    for profile_id in declared_profiles:
        if profile_id in _PROFILE_ENTITIES:
            entity = by_id.get(profile_id)
            if not entity or "CreativeWork" not in types_of(entity):
                errors.append(f"profile {profile_id} MUST be described as a CreativeWork entity")
    for expected in (PROCESS_RUN_CRATE_PROFILE, WORKFLOW_RO_CRATE_PROFILE_1_0):
        if expected not in declared_profiles:
            errors.append(f"BNS-IO-014 bundle exports MUST declare {expected} in the root conformsTo")
    if PROVENANCE_RUN_CRATE_PROFILE not in declared_profiles and any(
        "ControlAction" in types_of(e) for e in graph if isinstance(e, dict)
    ):
        errors.append(
            "step executions MUST be declared via root conformsTo "
            f"reference to {PROVENANCE_RUN_CRATE_PROFILE}"
        )

    # mainEntity: ComputationalWorkflow (as a crate File).
    main_id = id_of(root.get("mainEntity"))
    main_entity = by_id.get(main_id) if main_id else None
    if not main_entity:
        errors.append("root Dataset MUST declare a resolvable mainEntity")
    else:
        main_types = types_of(main_entity)
        for required in ("File", "SoftwareSourceCode", "ComputationalWorkflow"):
            if required not in main_types:
                errors.append(f"mainEntity {main_id} MUST include {required} among its types")
        has_steps = any("HowToStep" in types_of(e) for e in graph if isinstance(e, dict))
        if has_steps and "HowTo" not in main_types:
            errors.append("mainEntity MUST include HowTo when HowToStep entities are present")

    # Action wiring.
    actions = [e for e in graph if isinstance(e, dict) and "CreateAction" in types_of(e)]
    if not actions:
        errors.append("crate MUST contain at least one CreateAction (the workflow run)")
    for act in actions:
        act_id = act.get("@id", "?")
        instrument_id = id_of(act.get("instrument"))
        if not instrument_id or instrument_id not in by_id:
            errors.append(f"CreateAction '{act_id}' MUST reference an existing instrument")
        status_ref = id_of(act.get("actionStatus"))
        if status_ref is not None and status_ref not in _ACTION_STATUS_URIS:
            errors.append(f"CreateAction '{act_id}' actionStatus MUST be an ActionStatusType URI")
        failed = status_ref == _FAILED_STATUS
        if act.get("error") is not None and not failed:
            errors.append(
                f"CreateAction '{act_id}' carries error but actionStatus is not FailedActionStatus"
            )
        for role in ("object", "result"):
            for ref in ref_list(act.get(role)):
                if ref.startswith("#"):
                    if ref not in by_id:
                        errors.append(f"CreateAction '{act_id}' {role} reference '{ref}' is unresolved")
                elif ref not in by_id:
                    errors.append(f"CreateAction '{act_id}' {role} data entity '{ref}' is missing")

    # Provenance Run Crate wiring (only when step executions are present).
    step_runs = [e for e in graph if isinstance(e, dict) and "ControlAction" in types_of(e)]
    if step_runs:
        for control in step_runs:
            cid = control.get("@id", "?")
            howto_id = id_of(control.get("instrument"))
            howto = by_id.get(howto_id) if howto_id else None
            if not howto or "HowToStep" not in types_of(howto):
                errors.append(f"ControlAction '{cid}' instrument MUST be a HowToStep")
            tool_runs = ref_list(control.get("object"))
            if not tool_runs:
                errors.append(f"ControlAction '{cid}' MUST reference its tool-run CreateAction(s)")
            for ref in tool_runs:
                target = by_id.get(ref)
                if not target or "CreateAction" not in types_of(target):
                    errors.append(f"ControlAction '{cid}' object '{ref}' MUST be a CreateAction")
        engine_runs = [e for e in graph if isinstance(e, dict) and "OrganizeAction" in types_of(e)]
        if not engine_runs:
            errors.append("Provenance Run Crate conformance requires an OrganizeAction engine run")
        for engine_run in engine_runs:
            eid = engine_run.get("@id", "?")
            instrument_id = id_of(engine_run.get("instrument"))
            target = by_id.get(instrument_id) if instrument_id else None
            if not target or "SoftwareApplication" not in types_of(target):
                errors.append(f"OrganizeAction '{eid}' instrument MUST be a SoftwareApplication")
            controls = ref_list(engine_run.get("object"))
            if not controls or any(
                "ControlAction" not in types_of(by_id.get(r)) for r in controls
            ):
                errors.append(f"OrganizeAction '{eid}' object MUST be ControlAction instances")
            result_id = id_of(engine_run.get("result"))
            result_target = by_id.get(result_id) if result_id else None
            if not result_target or "CreateAction" not in types_of(result_target):
                errors.append(f"OrganizeAction '{eid}' result MUST be the workflow run CreateAction")
        howtos = [e for e in graph if isinstance(e, dict) and "HowToStep" in types_of(e)]
        for howto in howtos:
            hid = howto.get("@id", "?")
            work_example = id_of(howto.get("workExample"))
            target = by_id.get(work_example) if work_example else None
            if not target or "SoftwareApplication" not in types_of(target):
                errors.append(f"HowToStep '{hid}' workExample MUST reference its tool")

    # Checksum hygiene: sha256 values must be hex digests when present.
    for entity in graph:
        sha = entity.get("sha256")
        if sha is not None and not (isinstance(sha, str) and len(sha) == 64):
            errors.append(f"entity '{entity.get('@id')}' sha256 MUST be a 64-character hex digest")
    return errors


def verify_workflow_run_crate(crate_dir: str | Path) -> List[str]:
    """
    Post-write verification of an exported crate: structural validation of the
    metadata document plus on-disk presence and SHA-256 agreement for every
    data entity it references (fail-closed export, BNS-IO-014).
    """
    crate = Path(crate_dir)
    metadata_file = crate / "ro-crate-metadata.json"
    if not metadata_file.is_file():
        return [f"missing ro-crate-metadata.json in {crate}"]
    try:
        doc = json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"ro-crate-metadata.json is not valid JSON: {exc}"]
    errors = validate_workflow_run_crate(doc)
    for entity in doc.get("@graph", []):
        if not isinstance(entity, dict):
            continue
        eid = str(entity.get("@id", ""))
        if (
            eid.startswith("#")
            or eid in ("./", "ro-crate-metadata.json")
            or "://" in eid
        ):
            continue
        target = crate / eid
        if not target.is_file():
            errors.append(f"data entity '{eid}' missing on disk in the exported crate")
            continue
        expected = entity.get("sha256")
        if isinstance(expected, str) and expected:
            if _file_sha256(target) != expected:
                errors.append(f"data entity '{eid}' checksum mismatch after export")
    return errors


def load_adjacent_ledger(run_dir: str | Path) -> Optional[Dict[str, Any]]:
    """Load an adjacent `bionexus.ledger.json` Claim–Evidence Ledger, if present."""
    adjacent = Path(run_dir) / "bionexus.ledger.json"
    if not adjacent.is_file():
        return None
    candidate = json.loads(adjacent.read_text(encoding="utf-8"))
    return candidate if _looks_like_ledger(candidate) else None


def export_workflow_run_crate(
    source: str | Path,
    out_dir: Optional[str | Path] = None,
    *,
    ledger_path: Optional[str | Path] = None,
    zip_archive: bool = False,
) -> CrateExportResult:
    """
    Export a run capsule as a Workflow Run RO-Crate Research Object directory.

    Fail-closed end to end (BNS-IO-004 / BNS-IO-014): the capsule's SHA-256
    integrity seal must verify, the projected metadata document must pass
    structural validation before anything is written, and the materialized
    crate is re-verified (structure + checksums) afterwards. Any failure
    leaves no partial crate on disk.
    """
    from bionexus.artifacts import verify_run_bundle

    kind, manifest, siblings = load_interop_source(source)
    if kind != "run":
        raise ValueError(
            "Workflow Run Crates describe computations: export a run capsule (run.json). "
            "A Claim–Evidence Ledger embeds via --ledger or exports via export_ro_crate."
        )

    run_dir = Path(source) if Path(source).is_dir() else Path(source).parent
    verification = verify_run_bundle(run_dir)
    if not verification.valid:
        detail = "; ".join(
            [f"missing: {verification.missing_files}"] if verification.missing_files else []
            + [f"tampered: {verification.tampered_files}"] if verification.tampered_files else []
        )
        raise ValueError(
            f"Run capsule '{run_dir}' failed integrity verification ({detail}); "
            "refusing to export a Research Object from an unsealed capsule."
        )

    ledger_doc: Optional[Dict[str, Any]] = None
    if ledger_path is not None:
        ledger_doc = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
        if not _looks_like_ledger(ledger_doc):
            raise ValueError(f"'{ledger_path}' is not a Claim–Evidence Ledger.")
    else:
        ledger_doc = load_adjacent_ledger(run_dir)

    steps = manifest.get("steps") or []
    plan = plan_workflow_run_crate(manifest, siblings, steps=steps, ledger=ledger_doc)

    run_id = str(manifest.get("run_id", "run"))
    crate_dir = Path(out_dir) if out_dir else run_dir.parent / f"{_safe_crate_name(run_id)}.ro-crate"
    if crate_dir.exists() and any(crate_dir.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty crate directory: {crate_dir}")

    def _cleanup() -> None:
        shutil.rmtree(crate_dir, ignore_errors=True)

    try:
        for plan_file in plan.files:
            target = crate_dir / plan_file.crate_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            content = plan_file.content or {}
            if "__capsule_rel__" in content:
                capsule_src = run_dir / str(content["__capsule_rel__"])
                if not capsule_src.is_file():
                    raise FileNotFoundError(f"capsule file missing during export: {capsule_src}")
                shutil.copyfile(capsule_src, target)
            elif "__input_src__" in content:
                # Inputs may live outside the capsule directory; their bytes were
                # hash-verified against the sealed capsule before this copy.
                recorded = Path(str(content["__input_src__"]))
                input_src = recorded if recorded.is_absolute() else (run_dir / recorded)
                if not input_src.is_file():
                    raise FileNotFoundError(f"input artifact missing during export: {input_src}")
                shutil.copyfile(input_src, target)
            elif "__result_rel__" in content:
                result_src = run_dir / str(content["__result_rel__"])
                if not result_src.is_file():
                    raise FileNotFoundError(f"result artifact missing during export: {result_src}")
                shutil.copyfile(result_src, target)
            elif "__ledger_source__" in content:
                ledger_src = (
                    Path(ledger_path) if ledger_path is not None else run_dir / "bionexus.ledger.json"
                )
                shutil.copyfile(ledger_src, target)
            else:
                _write_lf_json(target, content)

        # Seal every materialized data entity with its actual exported bytes.
        by_id = {e.get("@id"): e for e in plan.doc["@graph"] if isinstance(e, dict)}
        for plan_file in plan.files:
            entity = by_id.get(plan_file.entity_id)
            if entity is not None and "File" in (entity.get("@type") or []):
                entity["sha256"] = _file_sha256(crate_dir / plan_file.crate_rel)

        errors = validate_workflow_run_crate(plan.doc)
        if errors:
            _cleanup()
            raise ValueError(
                "Workflow Run Crate projection failed structural validation: " + "; ".join(errors)
            )
        metadata_path = crate_dir / "ro-crate-metadata.json"
        _write_lf_json(metadata_path, plan.doc)

        post_errors = verify_workflow_run_crate(crate_dir)
        if post_errors:
            _cleanup()
            raise ValueError(
                "Exported crate failed post-write verification: " + "; ".join(post_errors)
            )

        zip_path: Optional[Path] = None
        if zip_archive:
            zip_path = _write_crate_zip(crate_dir)
        return CrateExportResult(
            crate_dir=crate_dir,
            metadata_path=metadata_path,
            zip_path=zip_path,
            files_copied=len(plan.files),
            steps_projected=len(steps),
            ledger_included=ledger_doc is not None,
            validation_errors=[],
            verified=True,
        )
    except (OSError, ValueError):
        _cleanup()
        raise


def _write_crate_zip(crate_dir: Path) -> Path:
    """Deterministic zip of the crate (fixed entry timestamps, sorted paths)."""
    zip_path = crate_dir.parent / f"{crate_dir.name}.zip"
    entries = sorted(p for p in crate_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in entries:
            info = zipfile.ZipInfo(str(path.relative_to(crate_dir.parent)).replace("\\", "/"))
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    return zip_path
