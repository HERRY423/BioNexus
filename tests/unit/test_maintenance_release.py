"""Guard the manual-release source/artifact tag boundary in workflow configuration."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_manual_and_tag_release_share_one_target():
    workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["build-and-release"]
    target = job["env"]["RELEASE_TAG"]
    assert "github.event_name == 'workflow_dispatch'" in target
    assert "inputs.tag_name" in target and "github.ref_name" in target
    assert "default" not in workflow["on"]["workflow_dispatch"]["inputs"]["tag_name"]
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    release = next(step for step in job["steps"] if step.get("uses", "").startswith("softprops/action-gh-release@"))
    assert checkout["with"]["ref"] == "refs/tags/${{ env.RELEASE_TAG }}"
    assert release["with"]["tag_name"] == "${{ env.RELEASE_TAG }}"
    gate = next(step["run"] for step in job["steps"] if step.get("name") == "Version SSOT Check")
    assert 'git rev-parse HEAD' in gate and 'refs/tags/${TAG}^{commit}' in gate


def test_compatibility_gate_runs_on_source_and_installed_wheel():
    ci = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    release = yaml.load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert any("check_de_bundle_contract.py" in s.get("run", "") for s in ci["jobs"]["lint"]["steps"])
    wheel = next(s["run"] for s in release["jobs"]["build-and-release"]["steps"] if s.get("name") == "Clean-Venv Wheel Verification")
    assert wheel.index("cd .wheelws") < wheel.index("check_de_bundle_contract.py --installed")
