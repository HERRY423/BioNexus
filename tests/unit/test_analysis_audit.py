"""
Unit tests for the BioNexus Static Scientific Analysis Audit (BNS-013,
firewall entry 2): rule families BFA-001..BFA-013 over notebooks and scripts.
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.analysis_audit import (
    audit_analysis,
    load_analysis_document,
    render_analysis_audit,
)
from bionexus.cli import main as cli_main


def _notebook(tmp_path: Path, code_cells, markdown=None, executed=True) -> Path:
    cells = []
    for i, src in enumerate(code_cells):
        cells.append(
            {
                "cell_type": "code",
                "execution_count": i + 1 if executed else None,
                "source": src.splitlines(keepends=True),
            }
        )
    for md in markdown or []:
        cells.append({"cell_type": "markdown", "source": md.splitlines(keepends=True)})
    p = tmp_path / "analysis.ipynb"
    p.write_text(json.dumps({"nbformat": 4, "cells": cells}), encoding="utf-8")
    return p


def test_pseudoreplication_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "import scanpy as sc\nadata = sc.read('sample.h5ad')",
            "sc.tl.rank_genes_groups(adata, groupby='condition', method='t-test')",
        ],
    )
    result = audit_analysis(nb)
    assert not result.passed
    finding = next(f for f in result.findings if f.rule_id == "BFA-001")
    assert finding.failure_id == "BN-F002"
    assert finding.severity == "FATAL"
    assert finding.evidence  # evidence line cited


def test_pseudobulk_not_flagged(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "pb = pseudobulk_aggregate(adata, groupby='donor_id')",
            "sc.tl.rank_genes_groups(adata, groupby='condition')",
        ],
    )
    result = audit_analysis(nb)
    assert not any(f.rule_id == "BFA-001" for f in result.findings)


def test_raw_log_confusion_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "sc.pp.normalize_total(adata)\nsc.pp.log1p(adata)",
            "from pydeseq2.dds import DDS\ndds = DDS(adata)",
        ],
    )
    result = audit_analysis(nb)
    finding = next(f for f in result.findings if f.rule_id == "BFA-002")
    assert finding.failure_id == "BN-F001"


def test_missing_fdr_is_advisory(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "from scipy.stats import ttest_ind\nt, p = ttest_ind(a, b)",
        ],
    )
    result = audit_analysis(nb)
    finding = next(f for f in result.findings if f.rule_id == "BFA-003")
    assert finding.severity == "ADVISORY"
    assert finding.failure_id == "BN-F005"


def test_fdr_present_not_flagged(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "from scipy.stats import ttest_ind\nfrom statsmodels.stats.multitest import multipletests",
            "t, p = ttest_ind(a, b)\nrej, q = multipletests(p, method='fdr_bh')[:2]",
        ],
    )
    result = audit_analysis(nb)
    assert not any(f.rule_id == "BFA-003" for f in result.findings)


def test_annotation_without_evidence_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "cell_type = {0: 'T cells', 1: 'B cells', 2: 'macrophages'}",
            "adata.obs['label'] = adata.obs['leiden'].map(cell_type)",
        ],
    )
    result = audit_analysis(nb)
    finding = next(f for f in result.findings if f.rule_id == "BFA-006")
    assert finding.failure_id == "BN-F003"


def test_spatial_coordinate_substitution_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        [
            "import squidpy as sq\nsq.gr.spatial_neighbors(adata, coord_type='generic', n_neighs=6)",
            "adata.obsm['spatial'] = adata.obsm['X_umap']",
        ],
    )
    result = audit_analysis(nb)
    finding = next(f for f in result.findings if f.rule_id == "BFA-009")
    assert finding.failure_id == "BN-F009"


def test_overclaimed_causality_in_markdown_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        ["sc.tl.leiden(adata, resolution=1.0)"],
        markdown=["## Results\n\nCluster 0 is CD4 T cell population confirmed."],
    )
    result = audit_analysis(nb)
    assert any(f.rule_id == "BFA-011" and f.severity == "FATAL" for f in result.findings)


def test_backend_substitution_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        ["import numpy as np\ncorr = np.corrcoef(x, y)"],
        markdown=["DESeq2 was run on the counts to produce the table above."],
    )
    result = audit_analysis(nb)
    finding = next(f for f in result.findings if f.rule_id == "BFA-012")
    assert finding.failure_id == "BN-F010"


def test_unexecuted_code_claim_detected(tmp_path):
    nb = _notebook(
        tmp_path,
        ["import scanpy as sc\nsc.pp.filter_cells(adata, min_genes=200)"],
        markdown=["We performed pseudobulk aggregation for the final figure."],
    )
    result = audit_analysis(nb)
    assert any(f.rule_id == "BFA-013" for f in result.findings)


def test_clean_script_passes_with_disclaimer(tmp_path):
    p = tmp_path / "clean.py"
    p.write_text(
        "import scanpy as sc\n"
        "sc.pp.normalize_total(adata)\n"
        "sc.pp.log1p(adata)\n"
        "sc.tl.score_genes(adata, gene_list=panel, score_name='panel_score')\n",
        encoding="utf-8",
    )
    result = audit_analysis(p)
    assert result.passed or all(f.severity == "ADVISORY" for f in result.findings)
    assert "NOT proof of validity" in result.disclaimer
    rendered = render_analysis_audit(result)
    assert "DISCLAIMER" in rendered
    assert "VERDICT" in rendered


def test_python_script_parsing(tmp_path):
    p = tmp_path / "script.py"
    p.write_text(
        "# we ran survival analysis on the cohort\n"
        "import numpy\n"
        "x = numpy.ones(3)\n",
        encoding="utf-8",
    )
    doc = load_analysis_document(p)
    assert doc.language == "python"
    assert doc.code_cells and doc.markdown_blocks


def test_cli_audit_notebook(tmp_path, capsys):
    nb = _notebook(
        tmp_path,
        [
            "sc.tl.rank_genes_groups(adata, groupby='condition')",
        ],
    )
    assert cli_main(["audit", str(nb)]) == 1
    out = capsys.readouterr().out
    assert "BFA-001" in out and "BN-F002" in out

    ok_nb = tmp_path / "ok.ipynb"
    ok_nb.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "cells": [
                    {"cell_type": "code", "execution_count": 1, "source": ["import scanpy as sc\n", "sc.pp.pca(adata)\n"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert cli_main(["audit", str(ok_nb), "--json"]) in (0, 1)
    payload = json.loads(capsys.readouterr().out)
    assert "findings" in payload and "disclaimer" in payload


def test_cli_audit_data_file_still_works(tmp_path):
    """Legacy data-file audit behavior is preserved for non-code artifacts."""
    csv = tmp_path / "matrix.csv"
    csv.write_text("1,2,3\n4,5,6\n", encoding="utf-8")
    rc = cli_main(["audit", str(csv)])
    assert rc in (0, 1)  # grade A/B -> 0; honest failures -> 1
