"""
Tests for the Scientific Review Framework.

Validates:
- SCIENTIFIC_REVIEW.json schema conformance
- INVARIANTS_CATALOG.json completeness and structure
- Review status tracking logic
"""

import json
from pathlib import Path

import pytest

REVIEW_DIR = Path(__file__).resolve().parent.parent.parent / "review"
SCIENTIFIC_REVIEW_PATH = REVIEW_DIR / "SCIENTIFIC_REVIEW.json"
INVARIANTS_CATALOG_PATH = REVIEW_DIR / "INVARIANTS_CATALOG.json"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scientific_review():
    """Load the SCIENTIFIC_REVIEW.json file."""
    with open(SCIENTIFIC_REVIEW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def invariants_catalog():
    """Load the INVARIANTS_CATALOG.json file."""
    with open(INVARIANTS_CATALOG_PATH, "r", encoding="utf-8") as f:
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
        assert "project" in scientific_review
        assert scientific_review["project"] == "bionexus-reliability"
        assert "project_version" in scientific_review
        assert scientific_review["project_version"] == "0.10.0"

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


# ── INVARIANTS_CATALOG.json Tests ─────────────────────────────────────────────


class TestInvariantsCatalog:
    """Validate the structure and completeness of INVARIANTS_CATALOG.json."""

    def test_file_exists_and_parses(self, invariants_catalog):
        """INVARIANTS_CATALOG.json must exist and be valid JSON."""
        assert invariants_catalog is not None

    def test_catalog_version(self, invariants_catalog):
        """Catalog version must be declared."""
        assert "catalog_version" in invariants_catalog
        assert invariants_catalog["catalog_version"] == "1.0"

    def test_invariants_list_present(self, invariants_catalog):
        """Invariants list must be present and non-empty."""
        assert "invariants" in invariants_catalog
        assert len(invariants_catalog["invariants"]) > 0

    def test_minimum_invariant_count(self, invariants_catalog):
        """Must have at least 17 invariants covering all categories."""
        assert len(invariants_catalog["invariants"]) >= 17

    def test_invariant_required_fields(self, invariants_catalog):
        """Each invariant must have all required fields."""
        required_fields = {
            "id",
            "name",
            "description",
            "current_value",
            "source_file",
            "source_line",
            "rationale",
            "sensitivity",
            "review_status",
        }
        for inv in invariants_catalog["invariants"]:
            for field in required_fields:
                assert field in inv, f"Invariant {inv.get('id', '?')} missing required field: {field}"

    def test_invariant_ids_unique(self, invariants_catalog):
        """All invariant IDs must be unique."""
        ids = [inv["id"] for inv in invariants_catalog["invariants"]]
        assert len(ids) == len(set(ids)), "Duplicate invariant IDs found"

    def test_invariant_id_format(self, invariants_catalog):
        """Invariant IDs must follow INV-NNN format."""
        import re

        pattern = re.compile(r"^INV-\d{3}$")
        for inv in invariants_catalog["invariants"]:
            assert pattern.match(inv["id"]), f"Invariant ID '{inv['id']}' does not match INV-NNN format"

    def test_sensitivity_values(self, invariants_catalog):
        """Sensitivity must be one of: high, medium, low."""
        valid_sensitivities = {"high", "medium", "low"}
        for inv in invariants_catalog["invariants"]:
            assert inv["sensitivity"] in valid_sensitivities, (
                f"Invariant {inv['id']} has invalid sensitivity: {inv['sensitivity']}"
            )

    def test_review_status_values(self, invariants_catalog):
        """Review status must be one of the valid states."""
        valid_statuses = {"pending", "under_review", "approved", "revised", "deferred", "rejected"}
        for inv in invariants_catalog["invariants"]:
            assert inv["review_status"] in valid_statuses, (
                f"Invariant {inv['id']} has invalid review_status: {inv['review_status']}"
            )

    def test_source_file_exists(self, invariants_catalog):
        """Source files referenced by invariants should exist in the project."""
        project_root = Path(__file__).resolve().parent.parent.parent
        source_files = set(inv["source_file"] for inv in invariants_catalog["invariants"])
        for source_file in source_files:
            full_path = project_root / source_file
            assert full_path.exists(), f"Source file not found: {source_file}"

    def test_source_line_positive(self, invariants_catalog):
        """Source line numbers must be positive integers."""
        for inv in invariants_catalog["invariants"]:
            assert isinstance(inv["source_line"], int)
            assert inv["source_line"] > 0, f"Invariant {inv['id']} has non-positive source_line"

    def test_current_value_not_empty(self, invariants_catalog):
        """All invariants must have a non-empty current_value."""
        for inv in invariants_catalog["invariants"]:
            assert inv["current_value"] is not None
            if isinstance(inv["current_value"], str):
                assert len(inv["current_value"]) > 0
            elif isinstance(inv["current_value"], list):
                assert len(inv["current_value"]) > 0


# ── Review Status Tracking Tests ──────────────────────────────────────────────


class TestReviewStatusTracking:
    """Test the review status tracking logic."""

    def test_all_invariants_start_pending(self, invariants_catalog):
        """All invariants should start with 'pending' review status."""
        pending_count = sum(1 for inv in invariants_catalog["invariants"] if inv["review_status"] == "pending")
        assert pending_count == len(invariants_catalog["invariants"]), (
            f"Expected all {len(invariants_catalog['invariants'])} invariants to be pending, "
            f"but only {pending_count} are"
        )

    def test_high_sensitivity_invariants_identified(self, invariants_catalog):
        """High-sensitivity invariants should be identifiable for priority review."""
        high_sensitivity = [inv for inv in invariants_catalog["invariants"] if inv["sensitivity"] == "high"]
        assert len(high_sensitivity) >= 5, "Expected at least 5 high-sensitivity invariants"

    def test_category_coverage(self, invariants_catalog):
        """Invariants should cover all required categories."""
        names = [inv["name"] for inv in invariants_catalog["invariants"]]
        categories = {
            "pseudoreplication": any("pseudoreplication" in n for n in names),
            "spatial": any("spatial" in n for n in names),
            "annotation": any("annotation" in n for n in names),
            "fdr": any("fdr" in n for n in names),
            "causal": any("causal" in n for n in names),
        }
        for category, covered in categories.items():
            assert covered, f"No invariant found for category: {category}"

    def test_review_progress_calculation(self, invariants_catalog):
        """Should be able to calculate review progress."""
        total = len(invariants_catalog["invariants"])
        reviewed = sum(1 for inv in invariants_catalog["invariants"] if inv["review_status"] != "pending")
        progress_pct = (reviewed / total * 100) if total > 0 else 0
        assert 0 <= progress_pct <= 100
        # Initially, progress should be 0%
        assert progress_pct == 0.0


# ── Integration Tests ─────────────────────────────────────────────────────────


class TestReviewFrameworkIntegration:
    """Integration tests ensuring the review framework files work together."""

    def test_reviewer_cases_match_invariants(self, scientific_review, invariants_catalog):
        """Reviewer case assignments should correspond to actual invariant categories."""
        all_cases = set()
        for reviewer in scientific_review["reviewers"]:
            all_cases.update(reviewer["cases_assigned"])

        # Verify that assigned cases relate to actual invariant names or descriptions
        inv_text_lower = " ".join(
            (inv["name"] + " " + inv["description"]).lower()
            for inv in invariants_catalog["invariants"]
        )
        for case in all_cases:
            assert case in inv_text_lower, (
                f"Reviewer case '{case}' not found in any invariant name or description"
            )

    def test_json_files_roundtrip(self):
        """Both JSON files must survive a load-dump-load roundtrip."""
        for path in [SCIENTIFIC_REVIEW_PATH, INVARIANTS_CATALOG_PATH]:
            with open(path, "r", encoding="utf-8") as f:
                data1 = json.load(f)
            dumped = json.dumps(data1, ensure_ascii=False)
            data2 = json.loads(dumped)
            assert data1 == data2, f"Roundtrip failed for {path}"
