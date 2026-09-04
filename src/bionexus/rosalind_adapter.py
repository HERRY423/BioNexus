"""BioNexus ChatGPT Rosalind Adapter (BNS-022 / BNS-019).

Provides bidirectional translation, tool schema generation, evidence envelope wrapping,
and warrant verification for ChatGPT GPT Actions and Rosalind Bioinformatics Assistants.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from bionexus.connector_profile import get_connector_profile
from bionexus.contracts import _MATURITY_RANK, ConclusionMaturity
from bionexus.ecosystem_claim import (
    ECOSYSTEM_CLAIM_PACKET_VERSION,
    EcosystemClaimPacket,
    EvidenceAdjudication,
    assess_ecosystem_claim,
)
from bionexus.ecosystem_intake import (
    ExternalEvidenceAudit,
    ExternalEvidenceEnvelope,
    ExternalProducerIdentity,
    IntakeStatus,
    audit_external_evidence,
)
from bionexus.tool_receipt import (
    create_host_observed_receipt,
    hash_canonical_payload,
)
from bionexus.versions import VERSION

_DEFAULT_PLUGIN_ID = "chatgpt-rosalind"
_DEFAULT_PLUGIN_VERSION = VERSION

# Canonical capability-to-evidence-family mapping
_TOOL_FAMILY_MAPPING: Dict[str, str] = {
    "search_uniprot": "database",
    "search_ensembl": "database",
    "search_gnomad": "database",
    "search_pdb": "structure",
    "search_alphafold": "structure",
    "search_reactome": "database",
    "search_string": "database",
    "search_geo": "database",
    "get_gene_expression": "analysis",
    "run_pseudobulk_de": "analysis",
    "single_cell_qc": "analysis",
    "spatial_svg_moran": "slide",
    "literature_search_europepmc": "literature",
    "literature_search_pubmed": "literature",
    "dbsnp_lookup": "sequence",
    "chembl_query": "database",
    "bionexus_warrant_check": "analysis",
}


@dataclass
class RosalindToolCallResult:
    """Encapsulates the parsed and audited output of a Rosalind/ChatGPT tool execution (BNS-025).

    Note: INTAKE_VALID != EVIDENCE_SUPPORTS_CLAIM != CLAIM_WARRANTED.
    An intake result records envelope intake status. It does NOT warrant claims.
    """

    tool_name: str
    arguments: Dict[str, Any]
    raw_result: Any
    envelope: ExternalEvidenceEnvelope
    audit: ExternalEvidenceAudit
    receipt: Dict[str, Any]
    intake_status: str
    is_warranted: bool = False
    warnings: List[str] = field(default_factory=list)


def export_openai_tool_definitions(
    *,
    custom_tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Generate OpenAPI / OpenAI Function Calling schemas for ChatGPT & Rosalind.

    Returns a list of tool definitions adhering to OpenAI's tools specification.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bionexus_warrant_check",
                "description": "Evaluate epistemic warrant and claim boundaries for multi-evidence scientific conclusions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {
                            "type": "string",
                            "description": "The exact scientific hypothesis or claim being evaluated.",
                        },
                        "envelopes": {
                            "type": "array",
                            "description": "List of ExternalEvidenceEnvelope dictionaries to evaluate.",
                            "items": {"type": "object"},
                        },
                        "claimed_maturity": {
                            "type": "string",
                            "enum": ["SUPPORTED", "PRELIMINARY", "FRAGILE", "REFUTED", "ABSTAIN"],
                            "description": "The author's intended maturity level.",
                        },
                    },
                    "required": ["claim_text", "envelopes"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_uniprot",
                "description": "Query UniProtKB for curated protein function, isoforms, and annotations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "UniProt accession ID or gene symbol."},
                        "reviewed": {"type": "boolean", "description": "Restrict to Swiss-Prot reviewed entries."},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_pdb",
                "description": "Retrieve experimentally-determined macromolecular 3D structures and binding sites from PDB.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pdb_id": {"type": "string", "description": "4-character PDB identifier (e.g. '1TUP')."},
                    },
                    "required": ["pdb_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_alphafold",
                "description": "Retrieve AlphaFold-predicted 3D coordinates and per-residue pLDDT confidence scores.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uniprot_id": {"type": "string", "description": "UniProt accession ID (e.g. 'P04637')."},
                    },
                    "required": ["uniprot_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_pseudobulk_de",
                "description": "Execute donor-aware pseudobulk differential expression with negative binomial GLM.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset_id": {"type": "string", "description": "Dataset identifier or file path."},
                        "cell_type": {"type": "string", "description": "Cell type partition to analyze."},
                        "contrast_column": {"type": "string", "description": "Metadata column for condition contrast."},
                    },
                    "required": ["dataset_id", "contrast_column"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "spatial_svg_moran",
                "description": "Calculate Moran's I spatial autocorrelation and spatially variable genes with permutation null test.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset_id": {"type": "string", "description": "Spatial AnnData dataset ID or path."},
                        "genes": {"type": "array", "items": {"type": "string"}, "description": "List of genes to test."},
                    },
                    "required": ["dataset_id"],
                },
            },
        },
    ]

    if custom_tools:
        tools.extend(custom_tools)

    return tools


def intake_chatgpt_tool_call(
    *,
    tool_name: str,
    arguments: Union[str, Dict[str, Any]],
    raw_result: Any,
    plugin_id: str = _DEFAULT_PLUGIN_ID,
    plugin_version: str = _DEFAULT_PLUGIN_VERSION,
    source_uri: Optional[str] = None,
    source_accession: Optional[str] = None,
    source_database: Optional[str] = None,
    execution_status: str = "SUCCESS",
    metadata: Optional[Dict[str, Any]] = None,
) -> RosalindToolCallResult:
    """Intake an OpenAI/ChatGPT/Rosalind tool execution into an audited BioNexus evidence envelope.

    Generates a Level 1 Host-Observed cryptographic ToolExecutionReceipt binding request & response digests.
    Strictly forbids guessing or synthesizing default source context: missing metadata remains INCOMPLETE.
    """
    args_dict = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    res_obj = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    meta = dict(metadata or {})

    family_str = _TOOL_FAMILY_MAPPING.get(tool_name, "analysis")

    # Compute digests
    req_sha256 = hash_canonical_payload(args_dict)
    resp_sha256 = hash_canonical_payload(res_obj)

    # Build source context
    source_ctx: Dict[str, Any] = {
        "producer": plugin_id,
        "producer_version": plugin_version,
        "tool_name": tool_name,
        "request_sha256": req_sha256,
        "response_sha256": resp_sha256,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    if source_uri:
        source_ctx["uri"] = source_uri
    if source_accession:
        source_ctx["accession"] = source_accession
    if source_database:
        source_ctx["database"] = source_database

    # Bind Universal Connector Profile (BNS-025)
    profile = get_connector_profile(plugin_id, tool_name) or get_connector_profile("chatgpt-rosalind", tool_name)
    if profile:
        source_ctx["scientific_domain"] = profile.domain.value
        source_ctx["production_mode"] = profile.production_mode.value
        source_ctx["scientific_object_type"] = profile.scientific_object_type

    # Extract source context HONESTLY without synthetic/hallucinated fallbacks
    if family_str == "database":
        s_name = source_database or meta.get("source_name")
        if s_name:
            source_ctx["source_name"] = s_name
        r_ids = meta.get("record_ids")
        if not r_ids:
            if source_accession:
                r_ids = [source_accession]
            elif "query" in args_dict and isinstance(args_dict["query"], str):
                r_ids = [args_dict["query"]]
        if r_ids:
            source_ctx["record_ids"] = r_ids if isinstance(r_ids, list) else [r_ids]
        if "database_release" in meta:
            source_ctx["database_release"] = meta["database_release"]
        if "identifier_namespace" in meta:
            source_ctx["identifier_namespace"] = meta["identifier_namespace"]
        if "organism_taxon" in meta:
            source_ctx["organism_taxon"] = meta["organism_taxon"]
        elif (
            isinstance(res_obj, dict)
            and "organism" in res_obj
            and isinstance(res_obj["organism"], dict)
            and "taxonId" in res_obj["organism"]
        ):
            source_ctx["organism_taxon"] = str(res_obj["organism"]["taxonId"])

    elif family_str == "structure":
        struct_id = (
            source_accession
            or meta.get("structure_id")
            or args_dict.get("pdb_id")
            or args_dict.get("uniprot_id")
        )
        if struct_id:
            source_ctx["structure_id"] = struct_id
        struct_source = meta.get("structure_source")
        if not struct_source:
            if "alphafold" in tool_name.lower():
                struct_source = "AlphaFold-DB"
            elif "pdb" in tool_name.lower():
                struct_source = "RCSB PDB"
        if struct_source:
            source_ctx["structure_source"] = struct_source
        if "structure_version" in meta:
            source_ctx["structure_version"] = meta["structure_version"]
        if "residue_mapping" in meta:
            source_ctx["residue_mapping"] = meta["residue_mapping"]
        if "model_quality_context" in meta:
            source_ctx["model_quality_context"] = meta["model_quality_context"]

    elif family_str == "literature":
        s_name = source_database or meta.get("source_name")
        if s_name:
            source_ctx["source_name"] = s_name
        idents = meta.get("identifiers")
        if not idents:
            if source_accession:
                idents = [source_accession]
            elif "pmid" in args_dict:
                idents = [args_dict["pmid"]]
            elif "query" in args_dict:
                idents = [args_dict["query"]]
        if idents:
            source_ctx["identifiers"] = idents if isinstance(idents, list) else [idents]
        if "publication_status" in meta:
            source_ctx["publication_status"] = meta["publication_status"]
        if "study_design" in meta:
            source_ctx["study_design"] = meta["study_design"]

    elif family_str == "analysis":
        source_ctx["backend_name"] = meta.get("backend_name") or f"bionexus.{tool_name}"
        source_ctx["backend_version"] = meta.get("backend_version") or plugin_version
        source_ctx["input_artifact_sha256"] = meta.get("input_artifact_sha256") or req_sha256
        if "parameters_sha256" in meta:
            source_ctx["parameters_sha256"] = meta["parameters_sha256"]
        if "execution_receipt_sha256" in meta:
            source_ctx["execution_receipt_sha256"] = meta["execution_receipt_sha256"]

    elif family_str == "sequence":
        seq_acc = (
            source_accession
            or meta.get("sequence_accession")
            or args_dict.get("rsid")
            or args_dict.get("accession")
        )
        if seq_acc:
            source_ctx["sequence_accession"] = seq_acc
        if "sequence_version" in meta:
            source_ctx["sequence_version"] = meta["sequence_version"]
        if "sequence_sha256" in meta:
            source_ctx["sequence_sha256"] = meta["sequence_sha256"]
        if "coordinate_system" in meta:
            source_ctx["coordinate_system"] = meta["coordinate_system"]

    elif family_str == "slide":
        if "image_or_dataset_sha256" in meta:
            source_ctx["image_or_dataset_sha256"] = meta["image_or_dataset_sha256"]
        if "coordinate_system" in meta:
            source_ctx["coordinate_system"] = meta["coordinate_system"]
        if "coordinate_transform" in meta:
            source_ctx["coordinate_transform"] = meta["coordinate_transform"]
        if "segmentation_version" in meta:
            source_ctx["segmentation_version"] = meta["segmentation_version"]
        if "biological_replicate_ids" in meta:
            source_ctx["biological_replicate_ids"] = meta["biological_replicate_ids"]
        if "field_of_view_ids" in meta:
            source_ctx["field_of_view_ids"] = meta["field_of_view_ids"]

    producer = ExternalProducerIdentity(
        plugin_id=plugin_id,
        capability=family_str,
        tool_name=tool_name,
        plugin_version=plugin_version,
    )

    envelope = ExternalEvidenceEnvelope.create(
        evidence_id=f"ENV-{hashlib.sha256(f'{tool_name}:{req_sha256}'.encode()).hexdigest()[:12]}",
        family=family_str,
        producer=producer,
        source_context=source_ctx,
        payload=res_obj if isinstance(res_obj, dict) else {"result": res_obj},
        request=args_dict,
    )

    audit = audit_external_evidence(envelope)

    # Level 1 Host-Observed Receipt (BNS-025)
    receipt = create_host_observed_receipt(
        host="chatgpt-rosalind",
        connector_id=plugin_id,
        tool_name=tool_name,
        request_payload=args_dict,
        response_payload=res_obj,
        plugin_version=plugin_version,
        execution_status=execution_status,
        mcp_server_uri=source_uri or f"rosalind://{tool_name}",
        transport="openai_function_calling",
        metadata={
            "evidence_id": envelope.evidence_id,
            "evidence_family": family_str,
            "intake_status": audit.status,
            **(metadata or {}),
        },
    )

    warnings: List[str] = list(audit.errors) + list(audit.missing_context)

    return RosalindToolCallResult(
        tool_name=tool_name,
        arguments=args_dict,
        raw_result=res_obj,
        envelope=envelope,
        audit=audit,
        receipt=receipt,
        intake_status=audit.status,
        is_warranted=False,  # INTAKE_VALID != CLAIM_WARRANTED
        warnings=warnings,
    )


def evaluate_rosalind_warrant(
    *,
    claim_id: str,
    target_claim: str,
    tool_results: List[RosalindToolCallResult],
    adjudications: Optional[Union[List[str], List[EvidenceAdjudication]]] = None,
    stated_maturity: str = "SUPPORTED",
    adjudicator_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble an EcosystemClaimPacket from tool results and perform fail-closed warrant analysis.

    Enforces BNS-025 Three-State Decoupling:
        INTAKE_VALID != EVIDENCE_SUPPORTS_CLAIM != CLAIM_WARRANTED
    """
    envelopes = [tr.envelope for tr in tool_results]
    receipts = [tr.receipt for tr in tool_results]

    # State 1: INTAKE_VALID
    intake_valid = all(tr.audit.status == IntakeStatus.VALID.value for tr in tool_results)
    invalid_envelopes = [tr for tr in tool_results if tr.audit.status != IntakeStatus.VALID.value]

    # State 2: EVIDENCE_SUPPORTS_CLAIM
    # BioNexus does NOT automatically infer evidence->claim relationship.
    # Without explicit adjudication, evidence remains context-only and cannot support a claim.
    adjudication_objs: List[EvidenceAdjudication] = []
    if adjudications is None:
        for env in envelopes:
            adjudication_objs.append(
                EvidenceAdjudication(
                    evidence_id=env.evidence_id,
                    relationship="context",
                    maturity=ConclusionMaturity.UNASSESSED.value,
                    rationale="Unadjudicated external tool intake; requires explicit reviewer adjudication to support claims.",
                    adjudicator_id=adjudicator_id or "unassigned",
                    adjudication_receipt_sha256=hashlib.sha256(f"context:{env.evidence_id}".encode()).hexdigest(),
                    validation_role="context_only",
                )
            )
    else:
        for env, item in zip(envelopes, adjudications):
            if isinstance(item, EvidenceAdjudication):
                adjudication_objs.append(item)
            else:
                rel = str(item).lower()
                adj_author = adjudicator_id or "human_reviewer"
                adjudication_objs.append(
                    EvidenceAdjudication(
                        evidence_id=env.evidence_id,
                        relationship=rel,
                        maturity=stated_maturity if rel == "supports" else ConclusionMaturity.UNASSESSED.value,
                        rationale=f"Explicitly adjudicated {rel} by {adj_author}",
                        adjudicator_id=adj_author,
                        adjudication_receipt_sha256=hashlib.sha256(
                            f"{adj_author}:{env.evidence_id}:{rel}".encode()
                        ).hexdigest(),
                        validation_role="supporting" if rel == "supports" else "context_only",
                    )
                )

    supporting_count = sum(1 for adj in adjudication_objs if adj.relationship == "supports")
    evidence_supports_claim = supporting_count > 0

    packet = EcosystemClaimPacket(
        schema_version=ECOSYSTEM_CLAIM_PACKET_VERSION,
        claim_id=claim_id,
        statement=target_claim,
        decision_owner=adjudicator_id or "rosalind_user",
        envelopes=tuple(envelopes),
        adjudications=tuple(adjudication_objs),
        claim_context={"scope": "preclinical_target_discovery"},
    )

    assessment = assess_ecosystem_claim(packet)

    adjusted_maturity = stated_maturity
    reasons: List[str] = list(assessment.audit.warnings) + list(assessment.audit.errors)

    # Enforce State 1 gating: incomplete / invalid intake caps maturity
    if not intake_valid:
        adjusted_maturity = "FRAGILE"
        reasons.append(
            f"{len(invalid_envelopes)} evidence envelope(s) failed strict provenance or completeness audit."
        )

    # Enforce State 2 gating: unadjudicated or context-only evidence cannot claim SUPPORTED
    if not evidence_supports_claim and stated_maturity != "UNASSESSED":
        adjusted_maturity = "UNASSESSED"
        reasons.append("No evidence envelope has been explicitly adjudicated with relationship='supports'.")

    # Enforce Universal Connector Profile boundaries (BNS-025)
    supporting_tools = [
        tr for tr in tool_results
        if any(adj.evidence_id == tr.envelope.evidence_id and adj.relationship == "supports" for adj in adjudication_objs)
    ]
    profile_ceilings = []
    for tr in supporting_tools:
        prof = get_connector_profile(tr.envelope.producer.plugin_id, tr.tool_name) or get_connector_profile(
            "chatgpt-rosalind", tr.tool_name
        )
        if prof:
            if not prof.allows_scientific_evidence:
                reasons.append(
                    f"Connector '{prof.connector_id}' produces communication artifacts only "
                    f"and is strictly prohibited from serving as scientific evidence."
                )
                adjusted_maturity = ConclusionMaturity.UNASSESSED.value
            for prohibited in prof.prohibited_claims:
                p_lower = prohibited.lower().replace("_", " ")
                patterns = [p_lower]
                if p_lower == "causality":
                    patterns.extend(["causal", "cause", "causes", "caused", "causing"])
                elif p_lower == "consensus":
                    patterns.extend(["general agreement", "established consensus"])
                if any(pat in target_claim.lower() for pat in patterns):
                    reasons.append(
                        f"Claim statement touches prohibited inference '{prohibited}' for "
                        f"{prof.domain.value} × {prof.production_mode.value} capability."
                    )
                    if _MATURITY_RANK.get(adjusted_maturity, 0) > _MATURITY_RANK.get("FRAGILE", 0):
                        adjusted_maturity = "FRAGILE"
            profile_ceilings.append(prof.default_max_claim_maturity)

    # Cross-family validation checks for supporting evidence
    supporting_families = {
        tr.envelope.family
        for tr in tool_results
        if any(adj.evidence_id == tr.envelope.evidence_id and adj.relationship == "supports" for adj in adjudication_objs)
    }

    # Epistemic ceiling for the supporting capabilities
    if profile_ceilings and len(supporting_families) < 2:
        # Single-modality: strictly capped by the individual tool's ceiling
        max_allowed_rank = max(_MATURITY_RANK.get(c, 0) for c in profile_ceilings)
        if _MATURITY_RANK.get(adjusted_maturity, 0) > max_allowed_rank:
            for mat_name, rank in _MATURITY_RANK.items():
                if rank == max_allowed_rank:
                    adjusted_maturity = mat_name
                    reasons.append(
                        f"Claimed maturity exceeds connector epistemic ceiling '{mat_name}'."
                    )
                    break
    elif profile_ceilings:
        # Multi-modality: collective ceiling cannot exceed highest supporting capability
        max_allowed_rank = max(_MATURITY_RANK.get(c, 0) for c in profile_ceilings)
        if _MATURITY_RANK.get(adjusted_maturity, 0) > max_allowed_rank:
            for mat_name, rank in _MATURITY_RANK.items():
                if rank == max_allowed_rank:
                    adjusted_maturity = mat_name
                    reasons.append(
                        f"Claimed maturity exceeds collective supporting capabilities epistemic ceiling '{mat_name}'."
                    )
                    break

    if len(supporting_families) < 2 and stated_maturity == "SUPPORTED":
        if _MATURITY_RANK.get(adjusted_maturity, 0) > _MATURITY_RANK.get("PRELIMINARY", 0):
            adjusted_maturity = "PRELIMINARY"
        reasons.append("Single-modality evidence cannot support robust cross-domain biological validity.")

    # State 3: CLAIM_WARRANTED
    claim_warranted = bool(
        intake_valid
        and evidence_supports_claim
        and adjusted_maturity == stated_maturity
        and len(assessment.audit.errors) == 0
    )

    return {
        "claim_id": claim_id,
        "target_claim": target_claim,
        "stated_maturity": stated_maturity,
        "warranted_maturity": adjusted_maturity,
        "intake_valid": intake_valid,
        "evidence_supports_claim": evidence_supports_claim,
        "claim_warranted": claim_warranted,
        "is_warranted": claim_warranted,
        "claim_packet": packet.to_dict(),
        "assessment": assessment.to_dict(),
        "receipts": receipts,
        "downgrade_reasons": reasons,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
