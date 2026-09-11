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

