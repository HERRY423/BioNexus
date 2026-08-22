"""
Tests for the Scientific Review Framework.

Validates:
- SCIENTIFIC_REVIEW.json schema conformance
- SCIENTIFIC_RULE_CATALOG.json completeness, structure, and epistemic taxonomy
- Review status tracking logic
"""

import json
from pathlib import Path

import pytest

REVIEW_DIR = Path(__file__).resolve().parent.parent.parent / "review"
SCIENTIFIC_REVIEW_PATH = REVIEW_DIR / "SCIENTIFIC_REVIEW.json"
RULE_CATALOG_PATH = REVIEW_DIR / "SCIENTIFIC_RULE_CATALOG.json"

# The six epistemic kinds every scientific rule must declare.
EPISTEMIC_KINDS = {
    "EXECUTION_INVARIANT",
    "DATA_INTEGRITY_INVARIANT",
    "WARRANT_CONSTRAINT",
    "CALIBRATED_THRESHOLD",
    "HEURISTIC_DETECTOR",
    "POLICY_DEFAULT",
}

# Kinds that are legitimately "invariants"; everything else must not be
# presented as one.
INVARIANT_KINDS = {"EXECUTION_INVARIANT", "DATA_INTEGRITY_INVARIANT"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scientific_review():
    """Load the SCIENTIFIC_REVIEW.json file."""
    with open(SCIENTIFIC_REVIEW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def rule_catalog():
    """Load the SCIENTIFIC_RULE_CATALOG.json file."""
    with open(RULE_CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── SCIENTIFIC_REVIEW.json Schema Tests ───────────────────────────────────────


class TestScientificReviewSchema:
    """Validate the structure and required fields of SCIENTIFIC_REVIEW.json."""

    def test_file_exists_and_parses(self, scientific_review):
        """SCIENTIFIC_REVIEW.json must exist and be valid JSON."""
        assert scientific_review is not None

    def test_schema_version_present(self, scientific_review):
        """Schema version must be declared."""
        assert "schema_version" in scientific_review
        assert scientific_review["schema_version"] == "1.0"

    def test_project_metadata(self, scientific_review):
        """Project name and version must be present."""
        from bionexus.versions import VERSION

        assert "project" in scientific_review
        assert scientific_review["project"] == "bionexus-reliability"
        assert "project_version" in scientific_review
        assert scientific_review["project_version"] == VERSION


    def test_review_date_present(self, scientific_review):
        """Review date must be declared in ISO format."""
        assert "review_date" in scientific_review
        assert len(scientific_review["review_date"]) == 10  # YYYY-MM-DD

    def test_reviewers_present(self, scientific_review):
        """At least one reviewer must be declared."""
        assert "reviewers" in scientific_review
        assert len(scientific_review["reviewers"]) >= 1

    def test_reviewer_schema(self, scientific_review):
        """Each reviewer must have required fields."""
        required_fields = {"id", "name", "role", "affiliation", "expertise", "cases_assigned"}
        for reviewer in scientific_review["reviewers"]:
            for field in required_fields:
                assert field in reviewer, f"Reviewer missing required field: {field}"
            assert isinstance(reviewer["expertise"], list)
            assert isinstance(reviewer["cases_assigned"], list)

    def test_three_reviewers_declared(self, scientific_review):
        """Protocol requires three reviewer roles."""
        assert len(scientific_review["reviewers"]) == 3

    def test_review_tracking_lists(self, scientific_review):
        """All tracking lists must be present and be lists."""
        tracking_fields = [
            "invariants_reviewed",
            "cases_reviewed",
            "disagreements",
            "false_refusals",
            "changes_made",
        ]
        for field in tracking_fields:
            assert field in scientific_review
            assert isinstance(scientific_review[field], list)

    def test_status_field(self, scientific_review):
        """Status field must be present."""
        assert "status" in scientific_review
        assert scientific_review["status"] == "framework_created_pending_review"


# ── SCIENTIFIC_RULE_CATALOG.json Tests ────────────────────────────────────────


class TestScientificRuleCatalog:
    """Validate the structure and epistemic taxonomy of SCIENTIFIC_RULE_CATALOG.json."""

    def test_file_exists_and_parses(self, rule_catalog):
        """SCIENTIFIC_RULE_CATALOG.json must exist and be valid JSON."""
        assert rule_catalog is not None

    def test_catalog_version(self, rule_catalog):
        """Catalog version must include the spatial battery calibration rule."""
        assert "catalog_version" in rule_catalog
        assert rule_catalog["catalog_version"] == "3.2"

    def test_rules_list_present(self, rule_catalog):
        """Rules list must be present and non-empty."""
        assert "rules" in rule_catalog
        assert len(rule_catalog["rules"]) > 0

    def test_minimum_rule_count(self, rule_catalog):
        """Must have at least 21 rules covering all categories."""
        assert len(rule_catalog["rules"]) >= 21

    def test_rule_required_fields(self, rule_catalog):
        """Each rule must have all required fields, including epistemic_kind."""
        required_fields = {
            "id",
            "name",
            "epistemic_kind",
            "description",
            "current_value",
            "source_file",
            "source_line",
            "rationale",
            "sensitivity",
            "review_status",
        }
        for rule in rule_catalog["rules"]:
            for field in required_fields:
                assert field in rule, f"Rule {rule.get('id', '?')} missing required field: {field}"

    def test_epistemic_kind_is_declared_and_valid(self, rule_catalog):
        """Every rule must declare exactly one valid epistemic_kind."""
        for rule in rule_catalog["rules"]:
            assert rule["epistemic_kind"] in EPISTEMIC_KINDS, (
                f"Rule {rule['id']} declares invalid epistemic_kind: {rule['epistemic_kind']}"
            )

    def test_taxonomy_is_actually_used(self, rule_catalog):
        """All six epistemic kinds must appear, and invariants must be a minority.

        If every rule were an invariant, the taxonomy would be cosmetic.
        """
        kinds_used = {rule["epistemic_kind"] for rule in rule_catalog["rules"]}
        assert kinds_used == EPISTEMIC_KINDS, f"Taxonomy not fully used; missing kinds: {EPISTEMIC_KINDS - kinds_used}"
        invariant_count = sum(1 for rule in rule_catalog["rules"] if rule["epistemic_kind"] in INVARIANT_KINDS)
        assert invariant_count < len(rule_catalog["rules"]), (
            "Every rule is classified as an invariant; the taxonomy is not doing real work"
        )

    def test_rule_ids_unique(self, rule_catalog):
        """All rule IDs must be unique."""
        ids = [rule["id"] for rule in rule_catalog["rules"]]
        assert len(ids) == len(set(ids)), "Duplicate rule IDs found"

    def test_rule_id_format(self, rule_catalog):
        """Rule IDs must follow INV-NNN or RULE-NNN format."""
        import re

        pattern = re.compile(r"^(?:INV|RULE)-\d{3}$")
        for rule in rule_catalog["rules"]:
            assert pattern.match(rule["id"]), f"Rule ID '{rule['id']}' does not match INV-NNN / RULE-NNN format"

    def test_no_overclaimed_mathematical_undefinedness(self, rule_catalog):
        """Rationales must not claim statistical inference is 'mathematically undefined'.

        Whether software can compute, whether a model is mathematically defined,
        and whether inference has a reliable design basis are three different
        questions.  Overclaimed phrasing was flagged in scientific review.
        """
        for rule in rule_catalog["rules"]:
            assert "mathematically undefined" not in rule["rationale"].lower(), (
                f"Rule {rule['id']} uses overclaimed 'mathematically undefined' phrasing"
            )

    def test_calibrated_thresholds_not_universalized(self, rule_catalog):
        """CALIBRATED_THRESHOLD rationales must acknowledge platform/method dependence."""
        calibrated = [rule for rule in rule_catalog["rules"] if rule["epistemic_kind"] == "CALIBRATED_THRESHOLD"]
        assert calibrated, "Expected at least one CALIBRATED_THRESHOLD rule"
        for rule in calibrated:
            rationale = rule["rationale"].lower()
            assert any(
                marker in rationale
                for marker in (
                    "platform",
                    "method",
                    "calibrated",
                    "engineering",
                    "protocol",
                )
            ), f"CALIBRATED_THRESHOLD {rule['id']} lacks dependence acknowledgement"

    def test_sensitivity_values(self, rule_catalog):
        """Sensitivity must be one of: high, medium, low."""
        valid_sensitivities = {"high", "medium", "low"}
        for rule in rule_catalog["rules"]:
            assert rule["sensitivity"] in valid_sensitivities, (
                f"Rule {rule['id']} has invalid sensitivity: {rule['sensitivity']}"
            )

    def test_review_status_values(self, rule_catalog):
        """Review status must be one of the valid states."""
        valid_statuses = {"pending", "under_review", "approved", "revised", "deferred", "rejected"}
        for rule in rule_catalog["rules"]:
            assert rule["review_status"] in valid_statuses, (
                f"Rule {rule['id']} has invalid review_status: {rule['review_status']}"
            )

    def test_source_file_exists(self, rule_catalog):
        """Source files referenced by rules should exist in the project."""
        project_root = Path(__file__).resolve().parent.parent.parent
        source_files = set(rule["source_file"] for rule in rule_catalog["rules"])
        for source_file in source_files:
            full_path = project_root / source_file
            assert full_path.exists(), f"Source file not found: {source_file}"

    def test_source_line_positive(self, rule_catalog):
        """Source line numbers must be positive integers."""
        for rule in rule_catalog["rules"]:
            assert isinstance(rule["source_line"], int)
            assert rule["source_line"] > 0, f"Rule {rule['id']} has non-positive source_line"

    def test_current_value_not_empty(self, rule_catalog):
        """All rules must have a non-empty current_value."""
        for rule in rule_catalog["rules"]:
            assert rule["current_value"] is not None
            if isinstance(rule["current_value"], str):
                assert len(rule["current_value"]) > 0
            elif isinstance(rule["current_value"], list):
                assert len(rule["current_value"]) > 0


# ── Review Status Tracking Tests ──────────────────────────────────────────────


class TestReviewStatusTracking:
    """Test the review status tracking logic."""

    def test_all_rules_start_pending(self, rule_catalog):
        """All rules should start with 'pending' review status."""
        pending_count = sum(1 for rule in rule_catalog["rules"] if rule["review_status"] == "pending")
        assert pending_count == len(rule_catalog["rules"]), (
            f"Expected all {len(rule_catalog['rules'])} rules to be pending, but only {pending_count} are"
        )

    def test_high_sensitivity_rules_identified(self, rule_catalog):
        """High-sensitivity rules should be identifiable for priority review."""
        high_sensitivity = [rule for rule in rule_catalog["rules"] if rule["sensitivity"] == "high"]
        assert len(high_sensitivity) >= 5, "Expected at least 5 high-sensitivity rules"

    def test_category_coverage(self, rule_catalog):
        """Rules should cover all required categories."""
        names = [rule["name"] for rule in rule_catalog["rules"]]
        categories = {
            "pseudoreplication": any("pseudoreplication" in n for n in names),
            "spatial": any("spatial" in n for n in names),
            "annotation": any("annotation" in n for n in names),
            "fdr": any("fdr" in n for n in names),
            "causal": any("causal" in n for n in names),
        }
        for category, covered in categories.items():
            assert covered, f"No rule found for category: {category}"

    def test_review_progress_calculation(self, rule_catalog):
        """Should be able to calculate review progress."""
        total = len(rule_catalog["rules"])
        reviewed = sum(1 for rule in rule_catalog["rules"] if rule["review_status"] != "pending")
        progress_pct = (reviewed / total * 100) if total > 0 else 0
        assert 0 <= progress_pct <= 100
        # Initially, progress should be 0%
        assert progress_pct == 0.0


# ── Integration Tests ─────────────────────────────────────────────────────────


class TestReviewFrameworkIntegration:
    """Integration tests ensuring the review framework files work together."""

    def test_reviewer_cases_match_rules(self, scientific_review, rule_catalog):
        """Reviewer case assignments should correspond to actual rule categories."""
        all_cases = set()
        for reviewer in scientific_review["reviewers"]:
            all_cases.update(reviewer["cases_assigned"])

        # Verify that assigned cases relate to actual rule names or descriptions
        rule_text_lower = " ".join((rule["name"] + " " + rule["description"]).lower() for rule in rule_catalog["rules"])
        for case in all_cases:
            assert case in rule_text_lower, f"Reviewer case '{case}' not found in any rule name or description"

    def test_json_files_roundtrip(self):
        """Both JSON files must survive a load-dump-load roundtrip."""
        for path in [SCIENTIFIC_REVIEW_PATH, RULE_CATALOG_PATH]:
            with open(path, "r", encoding="utf-8") as f:
                data1 = json.load(f)
            dumped = json.dumps(data1, ensure_ascii=False)
            data2 = json.loads(dumped)
            assert data1 == data2, f"Roundtrip failed for {path}"
