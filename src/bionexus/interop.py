"""
BioNexus Standards Interoperability Projections (BNS-016).

BioNexus does NOT invent a proprietary research-data standard. The internal
Run Capsule stays internal; everything that crosses the boundary goes through
published community standards:

    Claim–Evidence Ledger ──> W3C PROV-O (ledger.to_jsonld, since 0.8)
    Run Capsule / Ledger  ──> RO-Crate 1.1 (+ Workflow Run Crate profiles)
    Run Capsule           ──> BioCompute Object (IEEE 2791-2020)

Projections are deterministic, offline, and validated BEFORE they are handed
out: an export that fails structural validation is never written (fail-closed
interop, BNS-IO-004). The projection layer adds vocabulary, never removes it:
every BioNexus-specific fact (evidence maturity, failure taxonomy ids) rides
along inside standard containers rather than in side formats.

External references:
- RO-Crate 1.1            https://w3id.org/ro/crate/1.1
- Workflow Run Crate      https://w3id.org/ro/wfrun/process/0.5 (profile id)
- Workflow RO-Crate       https://w3id.org/workflowhub/workflow-ro-crate/draft
- IEEE 2791-2020 (BCO)    https://w3id.org/ieee/ieee-2791-std/schema/2791-2020
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.ledger import ClaimLedger
from bionexus.versions import PLUGIN_VERSION

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
RO_CRATE_PROFILE = "https://w3id.org/ro/crate/1.1"
PROCESS_RUN_CRATE_PROFILE = "https://w3id.org/ro/wfrun/process/0.5"
WORKFLOW_RO_CRATE_PROFILE = "https://w3id.org/workflowhub/workflow-ro-crate/draft"
BCO_SPEC_VERSION = "https://w3id.org/ieee/ieee-2791-std/schema/2791-2020"

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
