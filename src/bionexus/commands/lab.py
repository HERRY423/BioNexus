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

