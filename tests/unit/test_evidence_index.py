"""Unit tests for BioNexus Evidence Index and Upstream Invalidation/Recomputation Engine."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from bionexus.evidence_index import EvidenceIndex


class TestEvidenceIndexBuildAndIntegrity:
    """Tests for index construction, integrity, and JSON serialization."""

    def test_build_current_index_contains_flagships(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        assert len(index.conclusions) >= 8

        # Verify key conclusion nodes exist
        assert "BNC-SP-001-TECH-ACCEPTANCE" in index.conclusions
        assert "BNC-SPATIAL-CAPABILITY-VALIDATED" in index.conclusions
        assert "BNC-PSEUDOBULK-GSE96583" in index.conclusions
        assert "BNC-PSEUDOBULK-INDEP-002" in index.conclusions
        assert "BNC-PSEUDOBULK-CAPABILITY-VALIDATED" in index.conclusions
        assert "BNC-ANNOTATION-AZIMUTH-003" in index.conclusions
        assert "BNC-ANNOTATION-CAPABILITY-VALIDATED" in index.conclusions
        assert "BNC-CROSS-HOST-CONCORDANCE" in index.conclusions

    def test_verify_index_integrity_passes_on_disk(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        res = index.verify_index_integrity(_REPO_ROOT)
        assert res["passed"] is True, f"Integrity failed: {res['errors']}"
        assert res["checked_count"] > 0

    def test_round_trip_json_serialization(self, tmp_path: Path):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        tmp_file = tmp_path / "EVIDENCE_INDEX.json"
        index.save(tmp_file)

        loaded = EvidenceIndex.load(tmp_file)
        assert len(loaded.conclusions) == len(index.conclusions)
        for cid, entry in index.conclusions.items():
            loaded_entry = loaded.conclusions[cid]
            assert loaded_entry.statement == entry.statement
            assert loaded_entry.verdict == entry.verdict
            assert loaded_entry.rules == entry.rules
            assert loaded_entry.dependencies == entry.dependencies

    def test_verify_index_fails_when_source_hashes_corrupted(self):
        """Address user scenario: corrupting in-memory source hashes must trigger failure."""
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        corrupted_count = 0
        for entry in index.conclusions.values():
            for path_key in entry.source_files:
                entry.source_files[path_key] = "0" * 64
                corrupted_count += 1
        assert corrupted_count >= 19

        res = index.verify_index_integrity(_REPO_ROOT)
        assert res["passed"] is False
        assert len(res["errors"]) >= 19
        assert all("hash mismatch" in err.lower() for err in res["errors"])

    def test_verify_index_fails_when_report_verdict_mismatches(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        entry = index.conclusions["BNC-SP-001-TECH-ACCEPTANCE"]
        entry.verdict = "FAIL"

        res = index.verify_index_integrity(_REPO_ROOT)
        assert res["passed"] is False
        assert any("verdict mismatch" in err.lower() for err in res["errors"])

    def test_verify_index_fails_when_unauthorized_host_claimed(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        entry = index.conclusions["BNC-CROSS-HOST-CONCORDANCE"]
        entry.host["real_host_certified"] = True

        res = index.verify_index_integrity(_REPO_ROOT)
        assert res["passed"] is False
        assert any("host certification" in err.lower() for err in res["errors"])

    def test_verify_index_fails_when_verdict_substring_clash(self):
        """P1: Substring containment like 'NOT_PASS' vs 'PASS' must strictly fail."""
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        entry = index.conclusions["BNC-PSEUDOBULK-GSE96583"]
        entry.verdict = "NOT_PASS"

        res = index.verify_index_integrity(_REPO_ROOT)
        assert res["passed"] is False
        assert any("verdict mismatch" in err.lower() for err in res["errors"])

    def test_verify_index_fails_when_report_verdict_missing(self, tmp_path: Path):
        """P1: Report lacking a verdict must fail-closed."""
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        entry = index.conclusions["BNC-SP-001-TECH-ACCEPTANCE"]
        # Point to a report with no verdict
        empty_rep = tmp_path / "EMPTY_REPORT.json"
        empty_rep.write_text('{"unrelated_field": 123}\n', encoding="utf-8")
        entry.report_version["report_path"] = str(empty_rep.relative_to(tmp_path))

        res = index.verify_index_integrity(tmp_path)
        assert res["passed"] is False
        assert any("missing verdict" in err.lower() for err in res["errors"])


class TestUpstreamChangeAnalysis:
    """Tests distinguishing between invalidated conclusions and recomputation needed."""

    def test_source_code_change_triggers_recomputation_not_invalidation(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        impact = index.assess_upstream_changes(
            repo_root=_REPO_ROOT,
            changed_files=["evals/spatial_instrument_validation.py"],
            broken_rules=[],
        )

        recompute_ids = [r["conclusion_id"] for r in impact.requires_recomputation]
        invalid_ids = [inv["conclusion_id"] for inv in impact.invalidated_conclusions]

        # Spatial study must require recomputation
        assert "BNC-SP-001-TECH-ACCEPTANCE" in recompute_ids
        # Downstream spatial capability must also require recomputation via propagation
        assert "BNC-SPATIAL-CAPABILITY-VALIDATED" in recompute_ids
        # No rules were broken, so zero invalidations
        assert len(invalid_ids) == 0

    def test_rule_violation_triggers_invalidation(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        impact = index.assess_upstream_changes(
            repo_root=_REPO_ROOT,
            changed_files=[],
            broken_rules=["INV-011"],
        )

        invalid_ids = [inv["conclusion_id"] for inv in impact.invalidated_conclusions]

        # Invariant INV-011 broken -> spatial technical acceptance invalidated
        assert "BNC-SP-001-TECH-ACCEPTANCE" in invalid_ids
        # Downstream spatial capability invalidated
        assert "BNC-SPATIAL-CAPABILITY-VALIDATED" in invalid_ids

    def test_unaffected_conclusions_remain_stable(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        impact = index.assess_upstream_changes(
            repo_root=_REPO_ROOT,
            changed_files=["evals/spatial_instrument_validation.py"],
            broken_rules=[],
        )

        unaffected = set(impact.unaffected_conclusions)
        # Pseudobulk and Annotation should be completely unaffected
        assert "BNC-PSEUDOBULK-GSE96583" in unaffected
        assert "BNC-PSEUDOBULK-INDEP-002" in unaffected
        assert "BNC-ANNOTATION-AZIMUTH-003" in unaffected
        assert "BNC-ANNOTATION-CAPABILITY-VALIDATED" in unaffected

    def test_report_metadata_update_triggers_metadata_update_not_recomputation(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        impact = index.assess_upstream_changes(
            repo_root=_REPO_ROOT,
            changed_files=["validation/spatial/studies/BN-SP-IV-001/REPORT.json"],
            broken_rules=[],
        )

        meta_ids = [m["conclusion_id"] for m in impact.metadata_updates]
        assert "BNC-SP-001-TECH-ACCEPTANCE" in meta_ids
        recompute_ids = [r["conclusion_id"] for r in impact.requires_recomputation]
        assert "BNC-SP-001-TECH-ACCEPTANCE" not in recompute_ids
        assert len(impact.invalidated_conclusions) == 0

    def test_scientific_code_change_triggers_recomputation_not_metadata_update(self):
        index = EvidenceIndex.build_current_index(_REPO_ROOT)
        impact = index.assess_upstream_changes(
            repo_root=_REPO_ROOT,
            changed_files=["evals/spatial_instrument_validation.py"],
            broken_rules=[],
        )

        recompute_ids = [r["conclusion_id"] for r in impact.requires_recomputation]
        assert "BNC-SP-001-TECH-ACCEPTANCE" in recompute_ids
        meta_ids = [m["conclusion_id"] for m in impact.metadata_updates]
        assert "BNC-SP-001-TECH-ACCEPTANCE" not in meta_ids
        assert len(impact.invalidated_conclusions) == 0

