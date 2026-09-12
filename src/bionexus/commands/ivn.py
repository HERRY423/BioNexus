"""Ivn command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
from pathlib import Path


def handle_debt(args: argparse.Namespace) -> int:
    """Handle the 'debt' command: Scientific Evidence Debt Engine (BNS-021)."""
    from bionexus.debt import (
        EvidenceDebtEngine,
        create_sample_debt_ledger,
        render_markdown_debt_report,
        render_mermaid_debt_dag,
        render_terminal_debt_report,
    )
    from bionexus.ledger import ClaimLedger

    action = getattr(args, "debt_action", "audit")
    target = getattr(args, "target", ".")

    # Load or generate ledger
    if action == "sample":
        ledger = create_sample_debt_ledger()
        out_p = Path(getattr(args, "output", None) or "sample_evidence_debt_ledger.json")
        ledger.save(out_p)
        if not getattr(args, "json", False):
            print(f"[INFO] Sample research ledger saved to: {out_p}")
    else:
        target_p = Path(target)
        if target_p.is_file() and target_p.suffix.lower() == ".json":
            ledger = ClaimLedger.load(target_p)
        elif target_p.is_dir():
            candidates = [
                target_p / "ledger.json",
                target_p / "claim-evidence-ledger.json",
                target_p / "sample_evidence_debt_ledger.json",
            ]
            found = next((c for c in candidates if c.is_file()), None)
            if found:
                ledger = ClaimLedger.load(found)
            else:
                ledger = create_sample_debt_ledger()
        else:
            ledger = create_sample_debt_ledger()

    report = EvidenceDebtEngine.audit_ledger(ledger)

    if action == "graph":
        print(render_mermaid_debt_dag(report, ledger))
        return 0

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    elif getattr(args, "markdown", False):
        md = render_markdown_debt_report(report)
        if getattr(args, "output", None):
            Path(args.output).write_text(md, encoding="utf-8")
            print(f"[INFO] Markdown debt report written to: {args.output}")
        else:
            print(md)
        return 0
    else:
        term = render_terminal_debt_report(report, verbose=getattr(args, "verbose", False))
        print(term)
        return 0


def handle_ivn(args: argparse.Namespace) -> int:
    """Independent Validation Network CLI (BNS-023)."""
    import json as ivn_json
    from dataclasses import replace as dc_replace
    from datetime import datetime as IvnDateTime
    from datetime import timezone as IvnTimezone
    from pathlib import Path as IvnPath

    from bionexus import ivn as ivn_mod
    from bionexus.calibration_freeze import (
        CalibrationFreezeError,
        CalibrationFreezeRecord,
        HeldOutContext,
        authorize_context,
        freeze_profile,
        profile_from_payload,
    )

    action = getattr(args, "ivn_action", "")
    repo_root = IvnPath(getattr(args, "repo_root", ".") or ".").resolve()
    registry_arg = getattr(args, "registry", None)
    as_json = getattr(args, "json", False)

    def _registry_path() -> IvnPath:
        return IvnPath(registry_arg) if registry_arg else ivn_mod.default_registry_path(repo_root)

    def _load_or_bootstrap():
        """status/verify require an existing registry; registration and freeze
        may bootstrap a fresh empty one (quotas stay unsatisfied either way)."""
        path = _registry_path()
        if path.is_file():
            return ivn_mod.load_registry(path)
        if action in ("register-dataset", "register-lab-study", "register-review", "freeze-profile"):
            return ivn_mod.IVNRegistry()
        raise ivn_mod.IVNError(f"IVN registry not found: {path}")

    def _read_json(path: str):
        payload_path = IvnPath(path)
        if not payload_path.is_file():
            raise FileNotFoundError(f"payload file not found: {payload_path}")
        return ivn_json.loads(payload_path.read_text(encoding="utf-8"))

    def _repo_artifact_path(path_value: str, label: str) -> IvnPath:
        if not path_value:
            raise ivn_mod.IVNError(f"{label} artifact path is required")
        candidate = IvnPath(path_value)
        artifact = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        try:
            artifact.relative_to(repo_root)
        except ValueError as exc:
            raise ivn_mod.IVNError(f"{label} artifact must be inside repo_root: {path_value}") from exc
        if not artifact.is_file():
            raise ivn_mod.IVNError(f"{label} artifact not found on disk: {path_value}")
        return artifact

    def _artifact_sha(path_value: str, label: str) -> str:
        if not path_value:
            return ""
        artifact = _repo_artifact_path(path_value, label)
        from bionexus.provenance import sha256_file

        return sha256_file(artifact)

    try:
        registry = _load_or_bootstrap()

        if action == "status":
            network = ivn_mod.evaluate_network(registry, repo_root=repo_root)
            if as_json:
                print(ivn_json.dumps(network, indent=2, ensure_ascii=False))
                return 0
            print("=" * 78)
            print("BioNexus Independent Validation Network (BNS-023)")
            print(f"Network status: {network['network_status']}")
            print(f"Quota per flagship: {network['quota']}")
            for capability_id, assessment in network["capabilities"].items():
                print()
                print(f"[{capability_id}]  complete={assessment['complete']}")
                for check in assessment["checks"]:
                    mark = "PASS" if check["satisfied"] else "GAP "
                    print(f"   {mark} {check['requirement']}: required {check['required']}, observed {check['observed']}")
                for gap in assessment["blocking_gaps"]:
                    print(f"   gap: {gap}")
                for excluded in assessment["excluded_datasets"]:
                    print(f"   excluded dataset {excluded['dataset_id']}: {excluded['reason']}")
                for excluded in assessment["excluded_lab_studies"]:
                    print(f"   excluded lab study {excluded['study_id']}: {excluded['reason']}")
                for excluded in assessment["excluded_reviews"]:
                    print(f"   excluded review {excluded['review_id']}: {excluded['reason']}")
            print()
            print("OPEN_QUESTIONS alignment (docs/context/OPEN_QUESTIONS.md):")
            for blocker_id, blocker in network["open_questions"]["blockers"].items():
                state = "OPEN" if blocker["still_open"] else "RESOLVED"
                print(f"   {state:<8s} {blocker_id}")
            return 0

        if action == "verify":
            report = ivn_mod.verify_registry_integrity(registry, repo_root=repo_root)
            if as_json:
                print(ivn_json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print(f"IVN registry integrity: {report['integrity']} ({report['checked_entities']} entities checked)")
                for item in report["drift"]:
                    print(f"   drift: {item['entity']} {item['artifact']} -> {item['problem']}")
            return 0 if report["integrity"] == "PASS" else 1

        if action in ("register-dataset", "register-lab-study", "register-review"):
            payload = _read_json(args.payload)
            if action == "register-dataset":
                entity = ivn_mod.IVNDataset.from_dict(payload)
                if any(d.dataset_id == entity.dataset_id for d in registry.datasets):
                    raise ivn_mod.IVNError(f"dataset id already registered: {entity.dataset_id}")
                entity = dc_replace(
                    entity,
                    preregistration_sha256=entity.preregistration_sha256
                    or _artifact_sha(entity.preregistration_path, "preregistration"),
                    report_sha256=entity.report_sha256 or _artifact_sha(entity.report_path, "report"),
                )
                registry = ivn_mod.IVNRegistry(
                    schema_version=registry.schema_version,
                    generated_at=registry.generated_at,
                    requirements=registry.requirements,
                    author_roster=registry.author_roster,
                    datasets=registry.datasets + (entity,),
                    lab_studies=registry.lab_studies,
                    reviews=registry.reviews,
                    calibration_freezes=registry.calibration_freezes,
                )
                registered_id = entity.dataset_id
            elif action == "register-lab-study":
                entity = ivn_mod.ExternalLabStudy.from_dict(payload)
                if any(s.study_id == entity.study_id for s in registry.lab_studies):
                    raise ivn_mod.IVNError(f"lab study id already registered: {entity.study_id}")
                entity = dc_replace(
                    entity,
                    capsule_sha256=entity.capsule_sha256 or _artifact_sha(entity.capsule_path, "capsule"),
                )
                registry = ivn_mod.IVNRegistry(
                    schema_version=registry.schema_version,
                    generated_at=registry.generated_at,
                    requirements=registry.requirements,
                    author_roster=registry.author_roster,
                    datasets=registry.datasets,
                    lab_studies=registry.lab_studies + (entity,),
                    reviews=registry.reviews,
                    calibration_freezes=registry.calibration_freezes,
                )
                registered_id = entity.study_id
            else:
                entity = ivn_mod.NonAuthorReview.from_dict(payload)
                if any(r.review_id == entity.review_id for r in registry.reviews):
                    raise ivn_mod.IVNError(f"review id already registered: {entity.review_id}")
                if registry.reviewer_is_author(entity):
                    raise ivn_mod.IVNError(
                        "refusing registration: reviewer matches the author roster "
                        "(or the roster is empty, so non-authorship cannot be established)"
                    )
                entity = dc_replace(
                    entity,
                    review_sha256=entity.review_sha256 or _artifact_sha(entity.review_path, "review"),
                    verification_receipt_path="",
                    verification_receipt_sha256="",
                    status=ivn_mod.EntityStatus.REGISTERED.value,
                )
                registry = ivn_mod.IVNRegistry(
                    schema_version=registry.schema_version,
                    generated_at=registry.generated_at,
                    requirements=registry.requirements,
                    author_roster=registry.author_roster,
                    datasets=registry.datasets,
                    lab_studies=registry.lab_studies,
                    reviews=registry.reviews + (entity,),
                    calibration_freezes=registry.calibration_freezes,
                )
                registered_id = entity.review_id
            registry.save(_registry_path())
            if as_json:
                print(ivn_json.dumps({"registered": registered_id, "action": action}, indent=2))
            else:
                print(f"Registered {action.removeprefix('register-')} '{registered_id}' into {_registry_path()}")
                print("Note: registration alone never satisfies a quota; only VERIFIED entities with")
                print("matching artifact hashes count toward the network assessment.")
            return 0

        if action == "verify-review":
            review_id = args.review_id
            matches = [review for review in registry.reviews if review.review_id == review_id]
            if not matches:
                raise ivn_mod.IVNError(f"review id is not registered: {review_id}")
            review = matches[0]
            if review.status != ivn_mod.EntityStatus.REGISTERED.value:
                raise ivn_mod.IVNError(
                    f"review must be REGISTERED before verification; found {review.status}"
                )
            if registry.reviewer_is_author(review):
                raise ivn_mod.IVNError(
                    "refusing verification: reviewer matches the author roster "
                    "(or the roster is empty, so non-authorship cannot be established)"
                )
            review_path = _repo_artifact_path(review.review_path, "review")
            actual_review_sha = ivn_mod.sha256_file(review_path)
            if actual_review_sha.lower() != review.review_sha256.lower():
                raise ivn_mod.IVNError("review artifact hash no longer matches the registered hash")
            review_payload = ivn_json.loads(review_path.read_text(encoding="utf-8"))
            checks = ivn_mod.validate_external_review_artifact(
                review,
                review_payload,
                expected_commit=args.expected_commit,
                repo_root=repo_root,
            )

            receipt_rel = getattr(args, "receipt_output", None) or (
                f"validation/ivn/reviews/{review.review_id}/VERIFICATION_RECEIPT.json"
            )
            receipt_candidate = IvnPath(receipt_rel)
            receipt_path = (
                receipt_candidate.resolve()
                if receipt_candidate.is_absolute()
                else (repo_root / receipt_candidate).resolve()
            )
            try:
                receipt_rel = str(receipt_path.relative_to(repo_root))
            except ValueError as exc:
                raise ivn_mod.IVNError("verification receipt must be inside repo_root") from exc
            if receipt_path.exists():
                raise ivn_mod.IVNError(f"refusing to overwrite verification receipt: {receipt_rel}")
            if not args.verified_by.strip():
                raise ivn_mod.IVNError("verified_by must name an accountable person or governance body")
            receipt = {
                "schema_version": "bionexus.ivn-review-verification.v1",
                "review_id": review.review_id,
                "decision": ivn_mod.EntityStatus.VERIFIED.value,
                "review_path": review.review_path,
                "review_sha256": actual_review_sha,
                "expected_commit": args.expected_commit.lower(),
                "verified_at": IvnDateTime.now(IvnTimezone.utc).isoformat(),
                "verified_by": args.verified_by,
                "checks": checks,
                "scope_note": (
                    "This receipt verifies provenance and required review fields only; it does not "
                    "endorse the verdict or establish external-laboratory replication."
                ),
                "notes": getattr(args, "notes", ""),
            }
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                ivn_json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            receipt_sha = ivn_mod.sha256_file(receipt_path)
            verified = dc_replace(
                review,
                verification_receipt_path=receipt_rel.replace("\\", "/"),
                verification_receipt_sha256=receipt_sha,
                reviewed_at=review_payload["reviewed_at"],
                status=ivn_mod.EntityStatus.VERIFIED.value,
            )
            registry = ivn_mod.IVNRegistry(
                schema_version=registry.schema_version,
                generated_at=registry.generated_at,
                requirements=registry.requirements,
                author_roster=registry.author_roster,
                datasets=registry.datasets,
                lab_studies=registry.lab_studies,
                reviews=tuple(verified if item.review_id == review_id else item for item in registry.reviews),
                calibration_freezes=registry.calibration_freezes,
            )
            registry.save(_registry_path())
            response = {
                "review_id": review.review_id,
                "status": verified.status,
                "review_sha256": actual_review_sha,
                "verification_receipt_path": verified.verification_receipt_path,
                "verification_receipt_sha256": receipt_sha,
                "checks": checks,
            }
            if as_json:
                print(ivn_json.dumps(response, indent=2, ensure_ascii=False))
            else:
                print(f"Verified review '{review.review_id}' with receipt {verified.verification_receipt_path}")
                print("The receipt verifies provenance and completeness, not scientific endorsement.")
            return 0

        if action == "freeze-profile":
            profile = profile_from_payload(_read_json(args.profile_json))
            contexts = [HeldOutContext.from_dict(item) for item in _read_json(args.held_out_json)]
            record = freeze_profile(
                profile,
                contexts,
                freeze_id=args.freeze_id,
                frozen_by=args.frozen_by,
                notes=getattr(args, "notes", ""),
            )
            if any(f.get("freeze_id") == record.freeze_id for f in registry.calibration_freezes):
                raise CalibrationFreezeError(f"freeze id already recorded: {record.freeze_id}")
            registry = ivn_mod.IVNRegistry(
                schema_version=registry.schema_version,
                generated_at=registry.generated_at,
                requirements=registry.requirements,
                author_roster=registry.author_roster,
                datasets=registry.datasets,
                lab_studies=registry.lab_studies,
                reviews=registry.reviews,
                calibration_freezes=registry.calibration_freezes + (record.to_dict(),),
            )
            registry.save(_registry_path())
            if as_json:
                print(ivn_json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
            else:
                print(f"Frozen {record.profile_id}:{record.profile_version} as {record.freeze_id}")
                print(f"  profile_sha256: {record.profile_sha256}")
                print(f"  held-out contexts bound: {len(record.held_out_contexts)}")
            return 0

        if action == "authorize":
            profile = profile_from_payload(_read_json(args.profile_json))
            context = HeldOutContext.from_dict(_read_json(args.context_json))
            freezes = [CalibrationFreezeRecord.from_dict(item) for item in registry.calibration_freezes]
            decision = authorize_context(profile, freezes, context)
            if as_json:
                print(ivn_json.dumps(decision, indent=2, ensure_ascii=False))
            else:
                print(f"Decision: {decision['decision']} (authorizing={decision['authorizing']})")
                print(f"  {decision['reason']}")
            return 0 if decision["authorizing"] else 1

        if action in ("build-ledger", "render-page", "render-ledger"):
            out_path = IvnPath(getattr(args, "output", None) or "docs/ivn/index.html")
            if not out_path.is_absolute():
                out_path = repo_root / out_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            network = ivn_mod.evaluate_network(registry, repo_root=repo_root)
            html_content = ivn_mod.render_public_ledger_html(
                registry, network_assessment=network, repo_root=repo_root
            )
            out_path.write_text(html_content, encoding="utf-8")
            if as_json:
                print(ivn_json.dumps({"status": "SUCCESS", "output": str(out_path), "bytes": len(html_content)}, indent=2))
            else:
                print(f"[OK] IVN Public Evidence Ledger built successfully: {out_path} ({len(html_content)} bytes)")
            return 0

        print(f"Error: unknown ivn action '{action}'")
        return 2
    except (
        ivn_mod.IVNError,
        CalibrationFreezeError,
        FileNotFoundError,
        ivn_json.JSONDecodeError,
    ) as exc:
        print(f"Error: {exc}")
        return 2


def register_ivn_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 9.5 ivn (Independent Validation Network, BNS-023)
    p_ivn = subparsers.add_parser(
        "ivn",
        help="Independent Validation Network: >= 3 independent datasets x >= 2 external labs x >= 1 non-author reviewer per flagship (BNS-023)",
    )
    ivn_subs = p_ivn.add_subparsers(dest="ivn_action", help="IVN actions")

    p_ivn_status = ivn_subs.add_parser(
        "status", help="Assess every flagship capability against the IVN quotas and OPEN_QUESTIONS blockers"
    )
    p_ivn_status.add_argument("--registry", default=None, help="Path to the IVN registry (default: validation/ivn/REGISTRY.json)")
    p_ivn_status.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_status.add_argument("--json", action="store_true", help="Output the full assessment as JSON")

    p_ivn_verify = ivn_subs.add_parser(
        "verify", help="Recompute every recorded artifact hash in the IVN registry (drift check)"
    )
    p_ivn_verify.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_verify.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_verify.add_argument("--json", action="store_true", help="Output the integrity report as JSON")

    for register_kind, register_help in (
        ("register-dataset", "Register an independent dataset (requires on-disk preregistration/report artifacts)"),
        ("register-lab-study", "Register an external-lab study executed against a registered dataset"),
        ("register-review", "Register a blinded non-author review (refuses author-roster overlap)"),
    ):
        p_reg = ivn_subs.add_parser(register_kind, help=register_help)
        p_reg.add_argument("--payload", required=True, help="Entity JSON payload (see validation/ivn/templates/)")
        p_reg.add_argument("--registry", default=None, help="Path to the IVN registry")
        p_reg.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
        p_reg.add_argument("--json", action="store_true", help="Output the registration receipt as JSON")

    p_ivn_verify_review = ivn_subs.add_parser(
        "verify-review",
        help="Promote one REGISTERED review after fail-closed artifact and blinding verification",
    )
    p_ivn_verify_review.add_argument("--review-id", required=True, help="Registered review id")
    p_ivn_verify_review.add_argument(
        "--expected-commit", required=True, help="Full immutable commit reviewed by the external reviewer"
    )
    p_ivn_verify_review.add_argument(
        "--verified-by", required=True, help="Named maintainer or governance body performing the check"
    )
    p_ivn_verify_review.add_argument(
        "--receipt-output",
        default=None,
        help="Repository-relative verification receipt path (default: alongside the review)",
    )
    p_ivn_verify_review.add_argument("--notes", default="", help="Verification notes")
    p_ivn_verify_review.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_verify_review.add_argument("--repo-root", default=".", help="Repository root for artifact paths")
    p_ivn_verify_review.add_argument("--json", action="store_true", help="Output the verification receipt summary")

    p_ivn_freeze = ivn_subs.add_parser(
        "freeze-profile", help="Freeze an APPROVED calibration profile to its held-out contexts (fail-closed)"
    )
    p_ivn_freeze.add_argument("--profile-json", required=True, help="Calibration profile JSON payload")
    p_ivn_freeze.add_argument("--held-out-json", required=True, help="JSON list of held-out context payloads")
    p_ivn_freeze.add_argument("--freeze-id", required=True, help="Unique freeze id")
    p_ivn_freeze.add_argument("--frozen-by", required=True, help="Accountable person or body performing the freeze")
    p_ivn_freeze.add_argument("--notes", default="", help="Freeze notes")
    p_ivn_freeze.add_argument("--registry", default=None, help="Path to the IVN registry (freezes are recorded there)")
    p_ivn_freeze.add_argument("--repo-root", default=".", help="Repository root used to resolve default registry path")
    p_ivn_freeze.add_argument("--json", action="store_true", help="Output the freeze record as JSON")

    p_ivn_authorize = ivn_subs.add_parser(
        "authorize", help="Fail-closed gate: may a calibration profile authorize this context? (requires an intact freeze)"
    )
    p_ivn_authorize.add_argument("--profile-json", required=True, help="Calibration profile JSON payload")
    p_ivn_authorize.add_argument("--context-json", required=True, help="Held-out context JSON payload")
    p_ivn_authorize.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_authorize.add_argument("--repo-root", default=".", help="Repository root used to resolve default registry path")
    p_ivn_authorize.add_argument("--json", action="store_true", help="Output the decision as JSON")

    p_ivn_build = ivn_subs.add_parser(
        "build-ledger",
        aliases=["render-page", "render-ledger"],
        help="Compile and render the standalone public IVN evidence ledger HTML portal (GitHub Pages ready)",
    )
    p_ivn_build.add_argument("-o", "--output", default="docs/ivn/index.html", help="Output path for HTML file (default: docs/ivn/index.html)")
    p_ivn_build.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_build.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_build.add_argument("--json", action="store_true", help="Output build summary as JSON")
    return p_ivn


def register_debt_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 22. debt (Scientific Evidence Debt Engine - BNS-021)
    p_debt = subparsers.add_parser("debt", help="BioNexus Scientific Evidence Debt Engine (BNS-021) — Track & Amortize Scientific Debt")
    debt_subs = p_debt.add_subparsers(dest="debt_action", help="Evidence debt actions")

    p_d_audit = debt_subs.add_parser("audit", help="Audit project evidence debt and epistemic keystones")
    p_d_audit.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")
    p_d_audit.add_argument("--json", action="store_true", help="Output machine-readable JSON debt report")
    p_d_audit.add_argument("--markdown", "--md", action="store_true", help="Output Markdown debt certificate")
    p_d_audit.add_argument("-o", "--output", default=None, help="Save report to file path")
    p_d_audit.add_argument("-v", "--verbose", action="store_true", help="Display detailed debt breakdown")

    p_d_payoff = debt_subs.add_parser("payoff", aliases=["schedule"], help="Compute optimal scientific debt repayment schedule")
    p_d_payoff.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")
    p_d_payoff.add_argument("--json", action="store_true", help="Output schedule as JSON")
    p_d_payoff.add_argument("--markdown", "--md", action="store_true", help="Output schedule as Markdown")

    p_d_graph = debt_subs.add_parser("graph", help="Generate Mermaid DAG visualization of evidence debt propagation")
    p_d_graph.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")

    p_d_sample = debt_subs.add_parser("sample", help="Generate and audit an exemplary 20-claim research debt ledger")
    p_d_sample.add_argument("-o", "--output", default="sample_evidence_debt_ledger.json", help="Save sample ledger JSON to file")
    p_d_sample.add_argument("--json", action="store_true", help="Output audit report as JSON")
    p_d_sample.add_argument("--markdown", "--md", action="store_true", help="Output audit report as Markdown")
