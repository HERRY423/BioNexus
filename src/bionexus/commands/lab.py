"""Lab command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _emit_cli_payload(payload: dict, as_json: bool = False) -> None:
    """Print a deterministic CLI result without implying unperformed work."""
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def handle_lims(args: argparse.Namespace) -> int:
    """Run local LIMS checks; refuse commands that would only simulate a sync."""
    if args.lims_action == "audit-pairing":
        from bionexus.lims_hub import C04PairingCustodianHub

        result = C04PairingCustodianHub().audit_manifest(args.manifest)
        _emit_cli_payload(result, args.json)
        return 0 if result.get("passed") else 1

    if args.lims_action == "export-asm":
        import json

        from bionexus.lims_hub import AllotropeASMLIMSBridge, LIMSConnectorType

        asm_p = Path(args.asm)
        if not asm_p.is_file():
            print(f"Error: ASM file not found at {args.asm}", file=sys.stderr)
            return 2
        try:
            asm_doc = json.loads(asm_p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Error: Invalid ASM JSON file: {exc}", file=sys.stderr)
            return 2

        bridge = AllotropeASMLIMSBridge()
        target_sys = LIMSConnectorType[args.target.upper()]
        res = bridge.export_asm_to_lims(
            asm_document=asm_doc,
            endpoint_url=args.endpoint,
            target_system=target_sys,
            schema_id=args.schema_id,
            plate_id=args.plate_id,
            project_id=args.project_id,
            auth_token=args.token,
            mock_response=args.mock,
        )
        if args.json:
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("=" * 60)
            print(f"BioNexus Allotrope ASM -> LIMS Export ({args.target})")
            print("=" * 60)
            print(f"Success:        {res.success}")
            print(f"Target Entity:  {res.target_entity_id}")
            print(f"Records Synced: {res.records_synced}")
            if res.errors:
                print(f"Errors:         {res.errors}")
            print(f"Receipt Hash:   {res.receipt.get('receipt_hash', 'none')}")
            print("=" * 60)
        return 0 if res.success else 1

    result = {
        "status": "REFUSED_NOT_CONFIGURED",
        "executed": False,
        "action": args.lims_action,
        "reason": (
            "Live LIMS transport and authenticated destination are not configured. "
            "BioNexus will not report a mock response as a completed laboratory sync."
        ),
    }
    _emit_cli_payload(result, args.json)
    return 2


def handle_ga4gh(args: argparse.Namespace) -> int:
    """Handle GA4GH standards subcommands (DRS v1.2.0, Phenopackets v2)."""
    import json

    from bionexus.ga4gh import create_drs_object, export_donor_phenopacket

    action = getattr(args, "ga4gh_action", None)
    if action == "drs-descriptor":
        f_p = Path(args.file)
        if not f_p.is_file():
            print(f"Error: Data file not found: {args.file}", file=sys.stderr)
            return 2
        drs_id = args.id or f_p.stem
        try:
            drs_obj = create_drs_object(
                file_path=f_p,
                drs_id=drs_id,
                authority=args.authority,
                mime_type=args.mime_type,
            )
            drs_dict = drs_obj.to_dict()
            print(json.dumps(drs_dict, indent=2, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"Error creating DRS object: {exc}", file=sys.stderr)
            return 1

    elif action == "phenopacket":
        diseases = []
        if args.disease:
            parts = args.disease.split(":", 2)
            if len(parts) >= 2:
                curie = f"{parts[0]}:{parts[1]}"
                label = parts[2] if len(parts) > 2 else curie
                diseases.append({"id": curie, "label": label})
        phenotypes = []
        if args.phenotype:
            parts = args.phenotype.split(":", 2)
            if len(parts) >= 2:
                curie = f"{parts[0]}:{parts[1]}"
                label = parts[2] if len(parts) > 2 else curie
                phenotypes.append({"id": curie, "label": label})

        try:
            pheno = export_donor_phenopacket(
                donor_id=args.donor_id,
                sex=args.sex,
                disease_terms=diseases or None,
                phenotype_terms=phenotypes or None,
            )
            pheno_dict = pheno.to_dict()
            if args.output:
                out_p = Path(args.output)
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.write_text(json.dumps(pheno_dict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"[OK] Phenopacket written to: {out_p}")
            if args.json or not args.output:
                print(json.dumps(pheno_dict, indent=2, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"Error creating Phenopacket: {exc}", file=sys.stderr)
            return 1

    return 0


def handle_instrument(args: argparse.Namespace) -> int:
    """Detect or locally ingest an instrument export with a bound receipt."""
    from bionexus.instrument_gateway import LaboratoryInstrumentGateway

    gateway = LaboratoryInstrumentGateway()
    if args.instrument_action == "detect":
        instrument_type, vendor = gateway.detect_instrument_type(args.file)
        exists = Path(args.file).is_file()
        result = {
            "status": "DETECTED" if exists else "REFUSED_MISSING_INPUT",
            "instrument_type": instrument_type.value,
            "vendor_model": vendor,
            "source_exists": exists,
        }
        _emit_cli_payload(result, args.json)
        return 0 if exists else 1

    result = gateway.ingest_file(args.file, output_path=args.output)
    payload = result.to_dict()
    _emit_cli_payload(payload, args.json)
    return 0 if result.success else 1


def handle_airgap(args: argparse.Namespace) -> int:
    """Evaluate the local zero-egress guard without claiming DLP certification."""
    from bionexus.airgap_guard import AirgapNetworkGuard, AirgapPolicyMode

    guard = AirgapNetworkGuard(mode=AirgapPolicyMode(args.mode))
    if args.airgap_action == "audit":
        result = guard.get_summary_report()
        result["status"] = "LOCAL_POLICY_DIAGNOSTIC_ONLY"
        result["certification"] = "NOT_ASSESSED"
        _emit_cli_payload(result, args.json)
        return 0

    permitted, reason, receipt = guard.evaluate_egress(args.url, payload=args.payload)
    result = {
        "status": "PERMITTED" if permitted else "ABSTAIN",
        "permitted": permitted,
        "reason": reason,
        "receipt": receipt,
        "certification": "NOT_ASSESSED",
    }
    _emit_cli_payload(result, args.json)
    return 0 if permitted else 1


def handle_compliance(args: argparse.Namespace) -> int:
    """Create or verify local hash records without asserting regulatory compliance."""
    from bionexus.compliance_ledger import ComplianceAuditLedger, ElectronicSignature

    ledger = ComplianceAuditLedger()
    if args.compliance_action == "sign":
        target = Path(args.target)
        if not target.is_file():
            result = {
                "status": "REFUSED_MISSING_INPUT",
                "signed": False,
                "target": str(target),
                "regulatory_compliance": "NOT_ASSESSED",
            }
            _emit_cli_payload(result, args.json)
            return 1
        signature = ledger.sign_artifact(
            signer_name=args.name,
            signer_email=args.email,
            signer_role=args.role,
            signing_reason=args.reason,
            artifact_path_or_bytes=target,
        )
        result = signature.to_dict()
        result["regulatory_compliance"] = "NOT_ASSESSED"
        _emit_cli_payload(result, args.json)
        return 0

    if args.compliance_action == "verify-sig":
        target = Path(args.target)
        signature_path = Path(args.signature_file)
        if not target.is_file() or not signature_path.is_file():
            result = {
                "status": "REFUSED_MISSING_INPUT",
                "verified": False,
                "regulatory_compliance": "NOT_ASSESSED",
            }
            _emit_cli_payload(result, args.json)
            return 1
        signature = ElectronicSignature(**json.loads(signature_path.read_text(encoding="utf-8")))
        verified, reason = ledger.verify_signature(signature, target)
        result = {
            "status": "VERIFIED_HASH_BINDING" if verified else "ABSTAIN",
            "verified": verified,
            "reason": reason,
            "regulatory_compliance": "NOT_ASSESSED",
        }
        _emit_cli_payload(result, args.json)
        return 0 if verified else 1

    result = {
        "status": "NOT_ASSESSED",
        "verified": False,
        "reason": "No persisted ledger was supplied; an empty in-memory ledger is not audit evidence.",
        "regulatory_compliance": "NOT_ASSESSED",
    }
    _emit_cli_payload(result, args.json)
    return 2


def handle_nextflow(args: argparse.Namespace) -> int:
    from bionexus.nextflow_bridge import create_nextflow_tool_receipt, harvest_nextflow_run

    action = getattr(args, "nextflow_action", "inspect")
    if action == "ingest":
        run_dir = getattr(args, "run_dir", None)
        if not run_dir:
            print("Error: Must provide --run-dir path to Nextflow execution directory")
            return 2
        p_name = getattr(args, "pipeline_name", None)
        sheet = getattr(args, "samplesheet", None)
        out_path = getattr(args, "output", None)

        try:
            receipt = create_nextflow_tool_receipt(run_dir, pipeline_name=p_name, samplesheet_path=sheet)
            if out_path:
                p = Path(out_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"[OK] Nextflow tool receipt written to: {p}")
            if getattr(args, "json", False) or not out_path:
                print(json.dumps(receipt, indent=2, ensure_ascii=False))
            return 0
        except Exception as e:
            print(f"Error harvesting Nextflow run: {e}")
            return 1

    elif action == "inspect":
        run_dir = getattr(args, "run_dir", None)
        if not run_dir:
            print("Error: Must provide --run-dir path to Nextflow execution directory")
            return 2
        try:
            summary = harvest_nextflow_run(run_dir)
            if getattr(args, "json", False):
                print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
            else:
                print("=" * 60)
                print(f"Nextflow Execution Summary: {summary.pipeline_name}")
                print("=" * 60)
                print(f"Status: {summary.execution_status}")
                print(
                    f"Processes: {summary.succeeded_processes}/{summary.total_processes} succeeded "
                    f"({summary.failed_processes} failed, {summary.cached_processes} cached)"
                )
                print(f"CPU Hours: {summary.total_cpu_hours} | Peak RSS: {summary.peak_rss_gb} GB")
                print("Samplesheet semantics: NOT_INSPECTED (generic provenance-only mode)")
                print("Scientific Evidence Effect: NONE")
                print(f"Primary Outputs: {len(summary.primary_outputs)} files indexed")
                print("=" * 60)
            return 0
        except Exception as e:
            print(f"Error inspecting Nextflow run: {e}")
            return 1

    elif action == "launch":
        import importlib.util

        script_path = (
            Path(__file__).resolve().parents[2]
            / "skills"
            / "nextflow-development"
            / "scripts"
            / "nfcore_launch.py"
        )
        if not script_path.is_file():
            print(f"Error: nfcore_launch.py not found at {script_path}")
            return 2
        spec = importlib.util.spec_from_file_location("nfcore_launch", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        pipeline = getattr(args, "pipeline", None)
        samplesheet = getattr(args, "samplesheet", None)
        outdir = getattr(args, "outdir", "results")
        output = getattr(args, "output", "run.sh")
        profile = getattr(args, "profile", "docker")

        cmd = mod.build_launch_command(
            pipeline=pipeline, samplesheet=samplesheet, outdir=outdir, profile=profile
        )
        dest = mod.write_launch_script(cmd, Path(output))
        print(f"[OK] Nextflow launch script generated at: {dest}")
        print(f"Command: {' '.join(cmd)}")
        return 0

    return 0


def register_lims_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 23. lims
    p_lims = subparsers.add_parser("lims", help="BioNexus LIMS Hub (BNS-LIMS-001) — Benchling, LabWare, C04 Pairing Connectors")
    lims_subs = p_lims.add_subparsers(dest="lims_action", help="LIMS actions")

    p_l_audit = lims_subs.add_parser("audit-pairing", help="Audit C04 custodian pairing manifest")
    p_l_audit.add_argument("manifest", help="Path to pairing manifest CSV")
    p_l_audit.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_sync = lims_subs.add_parser("sync-samples", help="Sync samples with generic REST LIMS")
    p_l_sync.add_argument("--url", default="https://lims.internal/api/v1", help="LIMS base URL")
    p_l_sync.add_argument("--samples", nargs="+", default=["SMP-001", "SMP-002"], help="Sample IDs")
    p_l_sync.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_export = lims_subs.add_parser("export-assay", help="Export plate assay results to Benchling")
    p_l_export.add_argument("--plate-id", default="PLT-001", help="Plate identifier")
    p_l_export.add_argument("--schema-id", default="sch_plate_reader", help="Benchling assay schema ID")
    p_l_export.add_argument("--wells", type=int, default=96, help="Well count")
    p_l_export.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_export_asm = lims_subs.add_parser("export-asm", help="Bridge Allotrope ASM instrument file to LIMS assay")
    p_l_export_asm.add_argument("--asm", required=True, help="Path to Allotrope ASM JSON file")
    p_l_export_asm.add_argument("--endpoint", default="https://api.benchling.com/v2/assay-results", help="Target LIMS endpoint URL")
    p_l_export_asm.add_argument("--target", default="BENCHLING", choices=["BENCHLING", "LABWARE", "SAPIO", "GENERIC_REST"], help="Target LIMS system")
    p_l_export_asm.add_argument("--schema-id", default="sch_plate_reader", help="Assay schema ID")
    p_l_export_asm.add_argument("--plate-id", default="PLT-001", help="Plate identifier")
    p_l_export_asm.add_argument("--project-id", default=None, help="LIMS project ID")
    p_l_export_asm.add_argument("--token", default=None, help="Bearer authorization token")
    p_l_export_asm.add_argument("--mock", action="store_true", help="Perform mock dispatch")
    p_l_export_asm.add_argument("--json", action="store_true", help="Output JSON report")
    return p_lims


def register_instrument_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 24. instrument
    p_inst = subparsers.add_parser("instrument", help="BioNexus Instrument Gateway (BNS-INST-001) — Plate Reader, NGS, Single-Cell Ingestion")
    inst_subs = p_inst.add_subparsers(dest="instrument_action", help="Instrument actions")

    p_i_detect = inst_subs.add_parser("detect", help="Auto-detect laboratory instrument file type")
    p_i_detect.add_argument("file", help="Path to instrument output file")
    p_i_detect.add_argument("--json", action="store_true", help="Output JSON result")

    p_i_ingest = inst_subs.add_parser("ingest", help="Ingest and standardize instrument file to Allotrope ASM")
    p_i_ingest.add_argument("file", help="Path to instrument output file")
    p_i_ingest.add_argument("-o", "--output", default=None, help="Output JSON/ASM path")
    p_i_ingest.add_argument("--json", action="store_true", help="Output JSON result")
    return p_inst


def register_airgap_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 25. airgap
    p_airgap = subparsers.add_parser("airgap", help="BioNexus Airgap & Zero-Egress DLP Guard (BNS-SEC-011)")
    airgap_subs = p_airgap.add_subparsers(dest="airgap_action", help="Airgap actions")

    p_a_audit = airgap_subs.add_parser("audit", help="Audit airgap policy and DLP metrics")
    p_a_audit.add_argument("--mode", default="AIRGAP_STRICT", choices=["AIRGAP_STRICT", "VPC_INTERNAL_ONLY", "ALLOWLIST_AUDITED", "OPEN_CONNECTED"])
    p_a_audit.add_argument("--json", action="store_true", help="Output JSON report")

    p_a_eval = airgap_subs.add_parser("evaluate", help="Evaluate destination egress permissions and DLP")
    p_a_eval.add_argument("url", help="Destination URL or hostname")
    p_a_eval.add_argument("--mode", default="AIRGAP_STRICT", choices=["AIRGAP_STRICT", "VPC_INTERNAL_ONLY", "ALLOWLIST_AUDITED", "OPEN_CONNECTED"])
    p_a_eval.add_argument("--payload", default=None, help="Payload string to inspect")
    p_a_eval.add_argument("--json", action="store_true", help="Output JSON report")
    return p_airgap


def register_compliance_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 26. compliance
    p_comp = subparsers.add_parser("compliance", help="BioNexus 21 CFR Part 11 & GxP Compliance Engine (BNS-COMP-001)")
    comp_subs = p_comp.add_subparsers(dest="compliance_action", help="Compliance actions")

    p_cmp_sign = comp_subs.add_parser("sign", help="Apply 21 CFR Part 11 electronic signature to artifact")
    p_cmp_sign.add_argument("target", help="Path to target artifact")
    p_cmp_sign.add_argument("--name", default="Dr. Alice Smith", help="Signer name")
    p_cmp_sign.add_argument("--email", default="alice.smith@lab.org", help="Signer email")
    p_cmp_sign.add_argument("--role", default="PI_SIGNER", choices=["PI_SIGNER", "QA_AUDITOR", "SYSTEM_ADMIN", "BIOINFORMATICIAN", "RESEARCHER"])
    p_cmp_sign.add_argument("--reason", default="APPROVAL_OF_SCIENTIFIC_EVIDENCE", help="Signing reason")
    p_cmp_sign.add_argument("--json", action="store_true", help="Output JSON signature")

    p_cmp_ver = comp_subs.add_parser("verify-sig", help="Verify 21 CFR Part 11 electronic signature")
    p_cmp_ver.add_argument("target", help="Path to target artifact")
    p_cmp_ver.add_argument("signature_file", help="Path to JSON signature file")
    p_cmp_ver.add_argument("--json", action="store_true", help="Output JSON verification")

    p_cmp_ledger = comp_subs.add_parser("audit-ledger", help="Audit GxP hash chain integrity")
    p_cmp_ledger.add_argument("--json", action="store_true", help="Output JSON report")
    return p_comp


def register_nextflow_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 27. nextflow (execution provenance and explicit launch preparation)
    p_nextflow = subparsers.add_parser(
        "nextflow", help="Passive Nextflow execution-provenance harvester and launch preparation (BNS-021)"
    )
    nf_subs = p_nextflow.add_subparsers(dest="nextflow_action", help="Nextflow actions")

    p_nf_ingest = nf_subs.add_parser(
        "ingest", help="Harvest a run directory and emit a hash-bound provenance-only receipt"
    )
    p_nf_ingest.add_argument("--run-dir", "-r", required=True, help="Path to Nextflow execution directory")
    p_nf_ingest.add_argument("--pipeline-name", "-p", default=None, help="Pipeline name (e.g. nf-core/rnaseq)")
    p_nf_ingest.add_argument(
        "--samplesheet",
        "-s",
        default=None,
        help="Optional explicit descriptive input; never creates scientific evidence factors",
    )
    p_nf_ingest.add_argument("-o", "--output", default=None, help="Output path for receipt JSON")
    p_nf_ingest.add_argument("--json", action="store_true", help="Output JSON receipt to stdout")

    p_nf_inspect = nf_subs.add_parser(
        "inspect", help="Inspect Nextflow run directory and display execution summary"
    )
    p_nf_inspect.add_argument("run_dir", help="Path to Nextflow execution directory")
    p_nf_inspect.add_argument("--json", action="store_true", help="Output execution summary as JSON")

    p_nf_launch = nf_subs.add_parser("launch", help="Prepare nf-core launch script and configurations")
    p_nf_launch.add_argument(
        "--pipeline",
        required=True,
        choices=[
            "rnaseq",
            "scrnaseq",
            "differentialabundance",
            "sarek",
            "spatialtranscriptomics",
            "ampliseq",
        ],
        help="nf-core pipeline name",
    )
    p_nf_launch.add_argument("--samplesheet", required=True, help="Path to input samplesheet.csv")
    p_nf_launch.add_argument("--outdir", default="results", help="Pipeline output directory")
    p_nf_launch.add_argument("-o", "--output", default="run.sh", help="Output path for run script")
    p_nf_launch.add_argument("--profile", default="docker", help="Execution profile (e.g. docker, singularity, slurm)")
    return p_nextflow


def register_ga4gh_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 28. ga4gh
    p_ga4gh = subparsers.add_parser("ga4gh", help="GA4GH Global Standards (DRS v1.2.0, Phenopackets v2)")
    ga4gh_subs = p_ga4gh.add_subparsers(dest="ga4gh_action", help="GA4GH actions")

    p_g_drs = ga4gh_subs.add_parser("drs-descriptor", help="Generate GA4GH DRS v1.2.0 object descriptor for data file")
    p_g_drs.add_argument("file", help="Path to data file")
    p_g_drs.add_argument("--id", default=None, help="DRS identifier (default: filename)")
    p_g_drs.add_argument("--authority", default="bionexus.local", help="DRS authority URI prefix")
    p_g_drs.add_argument("--mime-type", default=None, help="MIME type")
    p_g_drs.add_argument("--json", action="store_true", help="Output JSON object")

    p_g_pheno = ga4gh_subs.add_parser("phenopacket", help="Export donor/patient clinical phenotype as GA4GH Phenopacket v2")
    p_g_pheno.add_argument("donor_id", help="Donor / Subject identifier")
    p_g_pheno.add_argument("--sex", default="UNKNOWN_SEX", choices=["UNKNOWN_SEX", "FEMALE", "MALE", "OTHER_SEX"], help="Biological sex")
    p_g_pheno.add_argument("--disease", default=None, help="Disease CURIE:Label (e.g. MONDO:0005015:Diabetes)")
    p_g_pheno.add_argument("--phenotype", default=None, help="Phenotype CURIE:Label (e.g. HP:0001250:Seizure)")
    p_g_pheno.add_argument("-o", "--output", default=None, help="Output JSON file path")
    p_g_pheno.add_argument("--json", action="store_true", help="Output JSON phenopacket")
    return p_ga4gh
