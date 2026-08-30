"""Unit tests for the cross-session project ledger (bionexus.project)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.artifacts import RunBundle
from bionexus.cli import main
from bionexus.contracts import EvidenceCard
from bionexus.project import ProjectLedger, find_project_root


@pytest.fixture()
def ledger_root(tmp_path: Path) -> Path:
    return tmp_path / "myproject"


@pytest.fixture()
def ledger(ledger_root: Path) -> ProjectLedger:
    return ProjectLedger(ledger_root, create=True)


def _make_capsule(root: Path, name: str = "run_test") -> Path:
    bundle = RunBundle.create(
        root / name,
        capability_id="scrna.exploratory_clustering",
        skill_name="single-cell-rna-qc",
    )
    (bundle.results_dir / "out.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    bundle.add_result("out", bundle.results_dir / "out.csv", semantic_type="table", is_primary=True)
    bundle.attach_evidence_card(
        EvidenceCard(
            execution_state="EXECUTED",
            details={"execution_backend": "scanpy", "note": "Fixture capsule for ledger tests."},
        )
    )
    bundle.finalize()
    return root / name


def test_init_creates_ledger_file(ledger: ProjectLedger):
    assert ledger.path.is_file()
    assert ledger.data["ledger_version"] == "1.0"
    loaded = ProjectLedger(ledger.root)
    assert loaded.data["created_at"] == ledger.data["created_at"]


def test_load_missing_ledger_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ProjectLedger(tmp_path / "no-such-project")


def test_register_dataset_dedupes_by_content_hash(ledger: ProjectLedger, tmp_path: Path):
    ds1 = tmp_path / "copy1.h5ad"
    ds2 = tmp_path / "copy2.h5ad"
    ds1.write_text("matrix", encoding="utf-8")
    ds2.write_text("matrix", encoding="utf-8")

    first = ledger.register_dataset(ds1, semantic_type="h5ad")
    assert first["refused"] is False
    second = ledger.register_dataset(ds2, semantic_type="h5ad")
    assert second["refused"] is False
    assert second["deduplicated"] is True

    status = ledger.status()
    assert status["dataset_count"] == 1
    assert sorted(status["datasets"][0]["paths"]) == sorted([str(ds1), str(ds2)])


def test_register_dataset_refuses_missing_file(ledger: ProjectLedger, tmp_path: Path):
    payload = ledger.register_dataset(tmp_path / "ghost.h5ad")
    assert payload["refused"] is True


def test_register_run_verifies_and_records_capsule(ledger: ProjectLedger, tmp_path: Path):
    capsule = _make_capsule(tmp_path)
    payload = ledger.register_run(capsule)
    assert payload["refused"] is False, payload
    entry = payload["run"]
    assert entry["verified"] is True
    assert entry["capability_id"] == "scrna.exploratory_clustering"
    assert entry["conclusion_maturity_source"] == "capsule EvidenceCard (unmodified)"

    status = ledger.status()
    assert status["run_count"] == 1
    assert status["conclusion_maturity_counts"] == {"PRELIMINARY": 1}


def test_register_run_refuses_tampered_capsule(ledger: ProjectLedger, tmp_path: Path):
    capsule = _make_capsule(tmp_path)
    (capsule / "results" / "out.csv").write_text("a,b\n999,2\n", encoding="utf-8")
    payload = ledger.register_run(capsule)
    assert payload["refused"] is True
    assert "integrity verification" in payload["abstain_reason"]
    assert ledger.status()["run_count"] == 0


def test_register_run_refuses_duplicate_and_missing(ledger: ProjectLedger, tmp_path: Path):
    capsule = _make_capsule(tmp_path)
    assert ledger.register_run(capsule)["refused"] is False
    assert ledger.register_run(capsule)["refused"] is True
    assert ledger.register_run(tmp_path / "ghost")["refused"] is True


def test_status_markdown_lists_runs(ledger: ProjectLedger, tmp_path: Path):
    ledger.register_run(_make_capsule(tmp_path))
    md = ledger.status_markdown()
    assert "Run Capsules: **1**" in md
    assert "scrna.exploratory_clustering" in md


def test_find_project_root_walks_upwards(ledger: ProjectLedger, tmp_path: Path):
    nested = ledger.root / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == ledger.root.resolve()
    assert find_project_root(tmp_path / "unrelated") is None


# ------------------------------------------------------------------ CLI surface


def test_cli_project_lifecycle(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["project", "init", "--name", "Demo"]) == 0
    capsys.readouterr()
    assert (tmp_path / ".bionexus" / "project.json").is_file()
    assert main(["project", "init"]) == 1  # refuse silent reinit
    capsys.readouterr()

    data = tmp_path / "data.csv"
    data.write_text("x,y\n1,2\n", encoding="utf-8")
    assert main(["project", "register-dataset", str(data), "--semantic-type", "csv"]) == 0
    capsys.readouterr()

    bundle = RunBundle.create(tmp_path / "capsule", capability_id="ingest.test", skill_name="t")
    (bundle.results_dir / "r.txt").write_text("r", encoding="utf-8")
    bundle.add_result("r", bundle.results_dir / "r.txt", is_primary=True)
    bundle.finalize()
    assert main(["project", "register-run", str(tmp_path / "capsule")]) == 0
    capsys.readouterr()
    assert main(["project", "register-run", str(tmp_path / "capsule")]) == 1  # duplicate
    capsys.readouterr()

    assert main(["project", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["name"] == "Demo"
    assert status["dataset_count"] == 1
    assert status["run_count"] == 1


def test_cli_project_requires_init(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["project", "status"]) == 1


def test_cli_ingest_local(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "sample.txt"
    src.write_text("payload", encoding="utf-8")
    rc = main(["ingest", str(src), str(tmp_path / "stage"), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"verified": true' in out


def test_cli_chain_dry_run(tmp_path: Path, monkeypatch, capsys):
    import yaml

    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "chain.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "name": "cli-chain",
                "steps": [{"id": "s1", "command": [sys.executable, "-c", "print(1)"]}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["chain", str(spec), "--workdir", "runs", "--dry-run"]) == 0
    assert "PLANNED" in capsys.readouterr().out
