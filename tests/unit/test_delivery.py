"""Unit tests for the delivery/export layer (bionexus.delivery)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.artifacts import RunBundle
from bionexus.cli import main
from bionexus.contracts import EvidenceCard
from bionexus.delivery import (
    build_methods_text,
    export_supplement,
    load_capsule_bundle,
    render_html_report,
    render_notebook,
)

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _make_capsule(root: Path, name: str = "run_deliver") -> Path:
    bundle = RunBundle.create(root / name, capability_id="scrna.exploratory_clustering", skill_name="single-cell-rna-qc")
    data = root / "input.h5ad"
    data.write_text("ann-data", encoding="utf-8")
    bundle.record_input("counts", data, semantic_type="h5ad")
    bundle.record_parameters(resolution=1.2, n_top_genes=60, mad_counts=3.0)

    table = bundle.results_dir / "markers.csv"
    table.write_text("gene,score\ncd3d,9.1\nms4a1,7.4\n", encoding="utf-8")
    bundle.add_result("markers", table, semantic_type="table", is_primary=True)

    fig = bundle.figures_dir / "umap_clusters.png"
    fig.write_bytes(_PNG_1PX)
    bundle.add_figure("UMAP clusters", fig, description="UMAP of Leiden clusters")

    bundle.attach_evidence_card(
        EvidenceCard(
            execution_state="EXECUTED",
            cross_method_concordance="B",
            details={"execution_backend": "scanpy", "concordance_notes": "Spearman rho=0.83 vs pseudobulk."},
        )
    )
    bundle.finalize()
    return root / name


@pytest.fixture()
def capsule(tmp_path: Path) -> Path:
    return _make_capsule(tmp_path)


# ------------------------------------------------------------------ bundle loading


def test_load_capsule_bundle_reads_all_descriptors(capsule: Path):
    bundle = load_capsule_bundle(capsule)
    assert bundle.run_id.endswith("scrna_exploratory_clustering")
    assert bundle.verified is True
    assert bundle.inputs["counts"]["semantic_type"] == "h5ad"
    assert bundle.parameters["resolution"] == 1.2
    assert bundle.evidence["execution_state"] == "EXECUTED"


def test_load_capsule_bundle_missing_file():
    with pytest.raises(FileNotFoundError):
        load_capsule_bundle(Path("no_such_capsule_dir"))


# --------------------------------------------------------------------- methods text


def test_methods_text_is_activity_aware_and_hash_bound(capsule: Path):
    bundle = load_capsule_bundle(capsule)
    text = build_methods_text(bundle)
    assert "## Methods: scrna.exploratory_clustering" in text
    assert "scverse" in text  # scrna_qc kind
    assert "resolution" in text  # parameters recorded
    assert "21 CFR Part 11" in text  # honest limitation
    # Data lineage table lists input and output hashes
    assert "counts" in text
    assert "markers" in text


def test_methods_text_generic_kind_does_not_invent_procedures(tmp_path: Path):
    bundle = RunBundle.create(tmp_path / "run_generic", capability_id="custom.thing", skill_name="generic-skill")
    bundle.finalize()
    text = build_methods_text(load_capsule_bundle(tmp_path / "run_generic"))
    assert "deliberately does not invent" in text


# ----------------------------------------------------------------------- HTML report


def test_html_report_is_self_contained(capsule: Path, tmp_path: Path):
    out = tmp_path / "report.html"
    payload = render_html_report(capsule, out)
    assert payload["refused"] is False
    html_text = out.read_text(encoding="utf-8")

    assert out.exists() and payload["export"]["integrity_verified"] is True
    assert "run_deliver" in html_text
    assert "data:image/png;base64," in html_text  # figure embedded, no external asset
    assert "<details" in html_text  # interactive sections
    assert "Research Use Only" in html_text
    assert "Cross-Method Concordance" in html_text and ">B<" in html_text  # audited dim 6 grade shown
    assert "Integrity verification FAILED" not in html_text
    # no external scripts/styles referenced
    for token in ('src="http', 'href="http', "@import"):
        assert token not in html_text


def test_html_report_warns_on_tampered_capsule(capsule: Path, tmp_path: Path):
    (capsule / "results" / "markers.csv").write_text("gene,score\nTAMPERED,1\n", encoding="utf-8")
    out = tmp_path / "report.html"
    render_html_report(capsule, out)
    html_text = out.read_text(encoding="utf-8")
    assert "Integrity verification FAILED" in html_text


def test_html_report_viewer_hints(tmp_path: Path):
    bundle = RunBundle.create(tmp_path / "run_struct", capability_id="structure.test", skill_name="protein-structure-analysis")
    pdb = bundle.results_dir / "model.pdb"
    pdb.write_text("ATOM      1  CA  ALA A   1\n", encoding="utf-8")
    bundle.add_result("model", pdb, semantic_type="structure", is_primary=True)
    bundle.finalize()
    out = tmp_path / "report.html"
    render_html_report(tmp_path / "run_struct", out)
    assert "3D structure viewer compatible" in out.read_text(encoding="utf-8")


# ------------------------------------------------------------------------ notebook


def test_notebook_is_valid_nbformat_with_verification_cells(capsule: Path, tmp_path: Path):
    out = tmp_path / "reproduce.ipynb"
    payload = render_notebook(capsule, out)
    assert payload["refused"] is False
    nb = json.loads(out.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    sources = ["".join(c["source"]) for c in nb["cells"]]
    assert any("verify_run_bundle" in s for s in sources)
    assert any("resolution" in s for s in sources)  # recorded parameters replayed
    assert any("markers.csv" in s for s in sources)  # primary result inspection
    assert any("Research Use Only" in s for s in nb["cells"][0]["source"])


def test_notebook_includes_rerun_cell_for_chain_capsules(tmp_path: Path):
    from bionexus.orchestrator import run_chain

    spec = tmp_path / "chain.yaml"
    spec.write_text(
        "name: demo-chain\nsteps:\n  - id: s1\n    command: [echo, hello]\n",
        encoding="utf-8",
    )
    run_chain(spec, tmp_path / "runs")
    out = tmp_path / "nb.ipynb"
    render_notebook(tmp_path / "runs" / "s1", out)
    sources = ["".join(c["source"]) for c in json.loads(out.read_text(encoding="utf-8"))["cells"]]
    assert any('"echo"' in s and "subprocess" in s for s in sources)


# ---------------------------------------------------------------------- supplement


def test_supplement_bundle_ships_verified_artifacts(capsule: Path, tmp_path: Path):
    out = tmp_path / "supplement"
    payload = export_supplement(capsule, out)
    assert payload["refused"] is False
    assert (out / "methods.md").is_file()
    assert (out / "data_availability.md").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "figures" / "umap_clusters.png").is_file()
    assert (out / "tables" / "markers.csv").is_file()

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity_verified"] is True
    shipped = {Path(f["file"]).name: f["sha256"] for f in manifest["files"]}
    assert len(shipped["umap_clusters.png"]) == 64

    availability = (out / "data_availability.md").read_text(encoding="utf-8")
    assert "counts" in availability and "umap_clusters.png" in availability


def test_supplement_refuses_tampered_capsule(capsule: Path, tmp_path: Path):
    (capsule / "results" / "markers.csv").write_text("gene,score\nTAMPERED,1\n", encoding="utf-8")
    payload = export_supplement(capsule, tmp_path / "supplement")
    assert payload["refused"] is True
    assert "integrity verification" in payload["abstain_reason"]
    assert not (tmp_path / "supplement").exists()


# ----------------------------------------------------------------------------- CLI


def test_cli_export_all_and_methods(capsule: Path, tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["export", "all", str(capsule), "-o", str(out_dir)]) == 0
    assert (out_dir / "report.html").is_file()
    assert (out_dir / "reproduce.ipynb").is_file()
    assert (out_dir / "supplement" / "manifest.json").is_file()
    capsys.readouterr()

    assert main(["export", "methods", str(capsule)]) == 0
    methods_out = capsys.readouterr().out
    assert "## Methods:" in methods_out


def test_cli_export_supplement_refuses_tampered(capsule: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (capsule / "results" / "markers.csv").write_text("gene,score\nTAMPERED,1\n", encoding="utf-8")
    assert main(["export", "supplement", str(capsule), "-o", str(tmp_path / "supp")]) == 1
    assert not (tmp_path / "supp").exists()
