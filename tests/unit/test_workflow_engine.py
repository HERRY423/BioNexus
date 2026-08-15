"""
Unit tests for Scientific Research Workflow Engine and Hypothesis Tracker.
"""

from pathlib import Path

# Add skill script directories to path
SKILL_ROOT = Path(__file__).parent.parent.parent / "skills" / "research-workflow-orchestrator" / "scripts"
import sys

sys.path.insert(0, str(SKILL_ROOT))

from hypothesis_tracker import HypothesisTracker
from workflow_engine import WorkflowEngine


def test_workflow_dag_validation():
    """Verify topological sorting and DAG validation for workflow templates."""
    template_path = Path(__file__).parent.parent.parent / "skills" / "research-workflow-orchestrator" / "templates" / "drug_target_discovery.yml"
    assert template_path.exists()

    engine = WorkflowEngine(str(template_path))
    exec_order = engine.validate_dag()
    assert len(exec_order) == len(engine.steps)
    # Check that prerequisite steps come before downstream steps
    assert exec_order.index("target_disease_association") < exec_order.index("protein_characterization")
    assert exec_order.index("target_disease_association") < exec_order.index("hypothesis_synthesis")


def test_workflow_parameter_interpolation():
    """Verify variable interpolation inside workflow arguments."""
    template_path = Path(__file__).parent.parent.parent / "skills" / "research-workflow-orchestrator" / "templates" / "drug_target_discovery.yml"
    engine = WorkflowEngine(str(template_path))
    engine.context = {
        "disease_name": "Melanoma",
        "target_associations": [{"name": "BRAF", "id": "ENSG00000157764"}]
    }

    interpolated = engine.interpolate_params("{disease_name} therapeutic target")
    assert interpolated == "Melanoma therapeutic target"

    nested_interp = engine.interpolate_params("{target_associations.0.name}")
    assert nested_interp == "BRAF"


def test_hypothesis_tracker_bayesian_evaluation():
    """Verify Bayesian posterior probability calculation and evidence logging."""
    tracker = HypothesisTracker("Inhibition of BRAF V600E leads to melanoma regression", prior_probability=0.5)
    tracker.add_evidence("Genetic association", score=0.9, weight=0.35, direction="support", source="ClinVar")
    tracker.add_evidence("Dabrafenib bioactivity", score=0.85, weight=0.30, direction="support", source="ChEMBL")
    tracker.add_evidence("Clinical trial efficacy", score=0.80, weight=0.25, direction="support", source="ClinicalTrials.gov")

    report = tracker.evaluate()
    assert report["status"] == "SUPPORTED"
    assert report["posterior_probability"] > 0.85
    assert report["num_evidence_items"] == 3

    md_output = tracker.to_markdown()
    assert "BRAF V600E" in md_output
    assert "🟢 Support" in md_output
