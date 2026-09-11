"""Command-line validation for Spatial Empirical Gold study artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from bionexus.spatial_empirical_gold import (
    SpatialGoldError,
    SpatialGoldObservationSet,
    SpatialGoldProgram,
    SpatialGoldStudyManifest,
    verify_spatial_gold_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bionexus-spatial-gold")
    parser.add_argument("--program-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory", help="Report three-platform empirical coverage gaps")
    study = subparsers.add_parser("validate-study", help="Validate a preregistered study manifest")
    study.add_argument("study_manifest", type=Path)
    artifacts = subparsers.add_parser("verify-artifacts", help="Read and hash every study evidence artifact")
    artifacts.add_argument("study_manifest", type=Path)
    artifacts.add_argument("artifact_map", type=Path, help="JSON object mapping manifest artifact URI to local path")
    artifacts.add_argument(
        "--observation-set",
        type=Path,
        help="Observation JSON whose per-record battery and adjudication bytes must be verified",
    )
    artifacts.add_argument(
        "--record-artifact-map",
        type=Path,
        help="JSON object mapping <record_id>:battery_run/adjudication_record to local path",
    )
    observations = subparsers.add_parser(
        "validate-observations", help="Validate battery/adjudication observations against a study"
    )
    observations.add_argument("study_manifest", type=Path)
    observations.add_argument("observation_set", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            payload = SpatialGoldProgram.load(args.program_root).inventory()
        elif args.command == "validate-study":
            manifest = SpatialGoldStudyManifest.load(args.study_manifest, program_root=args.program_root)
            payload = {
                "valid": True,
                "study_id": manifest.study_id,
                "platform": manifest.platform.value,
                "study_manifest_sha256": manifest.source_sha256,
                "metrics": list(manifest.metrics),
                "claim_status": "preregistered_contract_only",
            }
        elif args.command == "verify-artifacts":
            manifest = SpatialGoldStudyManifest.load(args.study_manifest, program_root=args.program_root)
            try:
                artifact_map = json.loads(args.artifact_map.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SpatialGoldError(f"invalid artifact_map JSON: {exc}") from exc
            if not isinstance(artifact_map, dict):
                raise SpatialGoldError("artifact_map must be a JSON object")
            if (args.observation_set is None) != (args.record_artifact_map is None):
                raise SpatialGoldError(
                    "--observation-set and --record-artifact-map are jointly required for a fit-eligible receipt"
                )
            observations = None
            record_artifact_map = None
            if args.observation_set is not None:
                observations = SpatialGoldObservationSet.load(
                    args.observation_set,
                    manifest,
                    program_root=args.program_root,
                )
                try:
                    record_artifact_map = json.loads(args.record_artifact_map.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise SpatialGoldError(f"invalid record_artifact_map JSON: {exc}") from exc
                if not isinstance(record_artifact_map, dict):
                    raise SpatialGoldError("record_artifact_map must be a JSON object")
            receipt = verify_spatial_gold_artifacts(
                manifest,
                artifact_map,
                observation_set=observations,
                record_artifact_paths=record_artifact_map,
            )
            payload = receipt.to_dict()
            payload["claim_status"] = (
                "full_record_bytes_verified_candidate_not_fitted"
                if receipt.verified
                else "study_artifacts_only_not_fit_eligible"
            )
        else:
            manifest = SpatialGoldStudyManifest.load(args.study_manifest, program_root=args.program_root)
            observations = SpatialGoldObservationSet.load(
                args.observation_set,
                manifest,
                program_root=args.program_root,
            )
            payload = {
                "valid": True,
                "study_id": manifest.study_id,
                "platform": manifest.platform.value,
                "study_manifest_sha256": manifest.source_sha256,
                "observation_artifact_sha256": observations.source_sha256,
                "record_count": len(observations.records),
                "claim_status": "observation_contract_valid_study_artifacts_not_verified",
            }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except (SpatialGoldError, OSError) as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "status": "incomplete_not_claim_ready",
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
