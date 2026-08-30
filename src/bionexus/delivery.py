"""
Delivery & export layer for BioNexus Run Capsules.

Closes the delivery/collaboration gap: capsules were machine-readable bundles
(CLI/JSON), but researchers needed *human- and journal-facing* deliverables — an
interactive report, a reproducibility notebook, and a supplementary-materials bundle —
without leaving the verified capsule lineage.

Exports (all pure stdlib, no new dependencies):

- ``render_html_report``: a self-contained interactive HTML report (inline CSS, native
  ``<details>`` sections, embedded figures as base64, dimension-grade chart as inline
  SVG, viewer hints for structure/sequence artifacts, integrity banner, RUO notice).
- ``render_notebook``: an nbformat-4.5 Jupyter notebook that re-loads the capsule,
  verifies artifact hashes, replays recorded parameters (and the recorded command for
  chain stages, printed rather than auto-executed), and inspects results.
- ``export_supplement``: a journal-style supplementary bundle (figures/, tables/,
  methods.md, data_availability.md, manifest.json with SHA-256 of every file).
  Refuses to bundle from a tampered capsule (fail-closed).
- ``build_methods_text``: capsule-level Methods text in the same activity-kind-aware,
  honesty-preserving spirit as the provenance skill's generator (scrna_qc / scvi /
  variant / structure / generic), composed from inputs.json, parameters.json,
  environment.json and evidence.json.

Every export carries the capsule's verification status. Exports never alter the
capsule itself.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.artifacts import verify_run_bundle
from bionexus.contracts import attach_meta, refuse
from bionexus.versions import PLUGIN_VERSION

PathLike = Any  # str | Path

_EMBED_MAX_BYTES = 5 * 1024 * 1024
_EMBED_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_STRUCTURE_SUFFIXES = {".pdb", ".cif", ".mmcif"}
_SEQUENCE_SUFFIXES = {".fasta", ".fa", ".fna", ".fastq"}
_TABULAR_SUFFIXES = {".csv", ".tsv", ".h5ad", ".parquet", ".json"}

_GRADE_COLORS = {
    "A": "#1a7f37",
    "B": "#0969da",
    "C": "#bf8700",
    "UNTESTED": "#8b949e",
    "UNASSESSED": "#8b949e",
    "NOT_APPLICABLE": "#d1d5da",
    "INSUFFICIENT": "#bf8700",
    "CONFLICTED": "#cf222e",
}

_RUO_NOTICE = (
    "Research Use Only. BioNexus is not certified under CLIA, CAP, or IVDR; outputs must "
    "never be used as the sole basis for clinical diagnostic or treatment decisions."
)


@dataclass
class CapsuleBundle:
    """Tolerant in-memory view of a Run Capsule's descriptor files."""

    capsule_dir: Path
    run: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return str(self.run.get("run_id", self.capsule_dir.name))

    @property
    def verified(self) -> bool:
        return bool(self.verification.get("valid"))


def load_capsule_bundle(capsule_dir: PathLike) -> CapsuleBundle:
    """Load a capsule's descriptor files, tolerating individual missing files."""
    base = Path(capsule_dir)
    run_file = base / "run.json" if base.is_dir() else base
    if base.is_file():
        base = base.parent
    if not run_file.is_file():
        raise FileNotFoundError(f"Run Capsule not found: {capsule_dir}")

    def _read(name: str) -> Dict[str, Any]:
        p = base / name
        if not p.is_file():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"_error": f"unparseable {name}"}

    bundle = CapsuleBundle(
        capsule_dir=base,
        run=_read("run.json"),
        inputs=_read("inputs.json"),
        parameters=_read("parameters.json"),
        evidence=_read("evidence.json"),
        provenance=_read("provenance.json"),
        environment=_read("environment.json"),
    )
    bundle.verification = verify_run_bundle(base).to_dict()
    return bundle


def _short(sha: Any, n: int = 12) -> str:
    s = str(sha or "")
    return s[:n] + ("…" if len(s) > n else "")


# ------------------------------------------------------------------- methods text


def _activity_kind(activity: str, params: Dict[str, Any]) -> str:
    text = f"{activity} {' '.join(str(k) for k in params)}".lower()
    if any(t in text for t in ("scrna", "single-cell", "single cell", "mad_", "doublet", "qc")):
        return "scrna_qc"
    if any(t in text for t in ("scvi", "n_latent", "scanvi")):
        return "scvi"
    if any(t in text for t in ("acmg", "variant", "hgvs")):
        return "variant"
    if any(t in text for t in ("dock", "pdb", "structure")):
        return "structure"
    if any(t in text for t in ("nextflow", "nf-core", "pipeline_execute")):
        return "pipeline"
    return "generic"


def build_methods_text(bundle: CapsuleBundle) -> str:
    """
    Deterministic capsule-level Methods text. Writes only what the capsule records:
    parameters, environment, and hashes. Never invents domain procedures for
    unrelated jobs.
    """
    run = bundle.run
    env = bundle.environment
    params = bundle.parameters
    packages = env.get("packages", {}) if isinstance(env.get("packages", {}), dict) else {}
    activity = run.get("capability_id", "custom.analysis")
    kind = _activity_kind(str(activity), params)

    lines: List[str] = [
        f"## Methods: {activity}",
        "",
        "### Computational environment and reproducibility",
        (
            f"Analyses were executed by BioNexus v{run.get('bionexus_version', PLUGIN_VERSION)} "
            f"via the `{run.get('skill_name', 'unknown')}` skill, in Python "
            f"{env.get('python_version', '3.10+')} on {env.get('os_name', 'an unspecified OS')} "
            f"({env.get('architecture', 'unknown architecture')})."
        ),
    ]
    if env.get("cuda_available"):
        lines.append(
            f"GPU acceleration used {env.get('cuda_device_name', 'a CUDA device')} (CUDA {env.get('cuda_version', 'N/A')})."
        )
    else:
        lines.append("No CUDA device was recorded for this run.")
    key_pkgs = {k: v for k, v in packages.items() if k in ("scanpy", "anndata", "squidpy", "scvi-tools", "pydeseq2", "numpy", "lifelines", "allotropy")}
    if key_pkgs:
        lines.append("Key package versions: " + ", ".join(f"{k} {v}" for k, v in sorted(key_pkgs.items())) + ".")

    lines.append("")
    if kind == "scrna_qc":
        lines.append(
            "Single-cell processing used the scverse gold chain with recorded parameters "
            "(see Parameters below). Cell-type labels were not assigned by this run unless a "
            "trained reference model is explicitly recorded in the parameters."
        )
    elif kind == "scvi":
        lines.append(
            f"Probabilistic latent modeling used scvi-tools with recorded hyperparameters "
            f"(n_latent={params.get('n_latent', 'not recorded')}, "
            f"n_layers={params.get('n_layers', 'not recorded')}) on raw counts."
        )
    elif kind == "variant":
        lines.append(
            "Variant interpretation applied caller-supplied ACMG/AMP evidence codes with the "
            "Tavtigian 2018 likelihood-ratio combination. No VEP/gnomAD query is implied by "
            "this text beyond what the capsule records."
        )
    elif kind == "structure":
        lines.append(
            "Structural coordinates were parsed from PDB/mmCIF sources; geometry used exact "
            "Kabsch superposition where recorded. Docking steps are reported only if those "
            "binaries appear in the recorded parameters."
        )
    elif kind == "pipeline":
        command = params.get("command")
        if isinstance(command, list) and command:
            lines.append(
                f"The nf-core pipeline was launched as: `{' '.join(str(c) for c in command)}`. "
                "Container engine status and profile are recorded in the capsule parameters."
            )
        else:
            lines.append("The pipeline launch command is recorded in the capsule parameters.")
    else:
        lines.append(
            f"Procedure summary is limited to the recorded parameters "
            f"(method={run.get('skill_name', 'unspecified')}); this text deliberately does "
            "not invent procedure details absent from the capsule."
        )

    lines.extend(["", "### Parameters"])
    if params:
        lines.append("```json")
        lines.append(json.dumps(params, indent=2, default=str))
        lines.append("```")
    else:
        lines.append("_No parameters were recorded._")

    lines.extend([
        "",
        "### Data lineage",
        "All artifact hashes are SHA-256. Hash recording is reproducibility evidence, not "
        "21 CFR Part 11 compliance.",
        "",
        "| Artifact | Role | Semantic type | SHA-256 |",
        "|---|---|---|---|",
    ])
    for name, item in bundle.inputs.items():
        lines.append(f"| `{name}` | input | {item.get('semantic_type', '-')} | `{_short(item.get('sha256'), 16)}` |")
    for item in run.get("artifacts", {}).get("results", []):
        lines.append(
            f"| `{item.get('name', item.get('path', '-'))}` | output | "
            f"{item.get('semantic_type', '-')} | `{_short(item.get('sha256'), 16)}` |"
        )

    evidence = bundle.evidence
    if evidence:
        lines.extend([
            "",
            "### Evidence summary",
            (
                f"Execution state: `{evidence.get('execution_state', 'UNASSESSED')}`; "
                f"conclusion maturity: `{bundle.run.get('conclusion_maturity', 'UNASSESSED')}`. "
                "Dimensions cross-method concordance and external validation are reported "
                "exactly as audited (or UNTESTED)."
            ),
        ])
    return "\n".join(lines)


# -------------------------------------------------------------------- HTML report


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _dimension_rows(evidence: Dict[str, Any]) -> List[tuple]:
    dimension_keys = [
        ("execution_fidelity", "1. Execution Fidelity"),
        ("input_integrity", "2. Input Integrity"),
        ("assumption_validity", "3. Assumption Validity"),
        ("statistical_support", "4. Statistical Support"),
        ("parameter_robustness", "5. Parameter Robustness"),
        ("cross_method_concordance", "6. Cross-Method Concordance"),
        ("external_validation", "7. External Validation"),
    ]
    rows = []
    for key, label in dimension_keys:
        value = evidence.get(key, "UNTESTED")
        if key == "execution_fidelity":
            value = evidence.get("execution_state", evidence.get("execution_fidelity", "UNASSESSED"))
        rows.append((label, str(value)))
    return rows


def _grade_svg(rows: List[tuple]) -> str:
    """Inline SVG bar chart of dimension grades (no external chart libraries)."""
    bar_w, gap, height = 78, 14, 120
    width = len(rows) * (bar_w + gap) + gap
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" style="max-width:100%">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    for i, (label, grade) in enumerate(rows):
        x = gap + i * (bar_w + gap)
        color = _GRADE_COLORS.get(grade.upper(), "#8b949e")
        bar_h = {"A": 90, "B": 68, "C": 46}.get(grade.upper(), 24)
        parts.append(f'<rect x="{x}" y="{height - bar_h - 18}" width="{bar_w}" height="{bar_h}" rx="4" fill="{color}"/>')
        parts.append(
            f'<text x="{x + bar_w / 2}" y="{height - bar_h - 6}" text-anchor="middle" '
            f'font-size="12" fill="#24292f">{_esc(grade)}</text>'
        )
        short_label = label.split(". ", 1)[-1]
        for li, word in enumerate(short_label.split()[:2]):
            parts.append(
                f'<text x="{x + bar_w / 2}" y="{height - 4 + li * 0}" text-anchor="middle" '
                f'font-size="9" fill="#57606a">{_esc(word[:11])}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _figure_embed(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg" and path.stat().st_size <= _EMBED_MAX_BYTES:
        return path.read_text(encoding="utf-8")
    if suffix in _EMBED_IMAGE_TYPES and path.stat().st_size <= _EMBED_MAX_BYTES:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return (
            f'<img src="data:{_EMBED_IMAGE_TYPES[suffix]};base64,{encoded}" '
            f'style="max-width:100%" alt="{_esc(path.name)}"/>'
        )
    return f"<p><em>Figure too large to embed ({path.stat().st_size} bytes): {_esc(path.name)}</em></p>"


def _viewer_hint(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in _STRUCTURE_SUFFIXES:
        return "3D structure viewer compatible (PDB/mmCIF)"
    if suffix in _SEQUENCE_SUFFIXES:
        return "Sequence/alignment viewer compatible"
    if suffix in _TABULAR_SUFFIXES:
        return "Tabular/analysis artifact"
    return "-"


def _figure_path(base: Path, rel: str) -> Optional[Path]:
    p = (base / rel).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def render_html_report(capsule_dir: PathLike, out_path: PathLike) -> Dict[str, Any]:
    """Render a self-contained interactive HTML report from a Run Capsule."""
    bundle = load_capsule_bundle(capsule_dir)
    base = bundle.capsule_dir
    run = bundle.run
    rows = _dimension_rows(bundle.evidence)

    fig_sections: List[str] = []
    for fig in run.get("artifacts", {}).get("figures", []):
        rel = fig.get("path", "")
        fpath = _figure_path(base, rel)
        if fpath is None:
            fig_sections.append(f'<p><em>Figure missing on disk: {_esc(rel)}</em></p>')
            continue
        fig_sections.append(
            f'<figure><h4>{_esc(fig.get("title", fpath.name))}</h4>{_figure_embed(fpath)}'
            f"<figcaption>{_esc(fig.get('description', ''))}</figcaption></figure>"
        )
    if not fig_sections:
        fig_sections.append("<p><em>No figures were recorded in this capsule.</em></p>")

    results_rows = "\n".join(
        f"<tr><td><code>{_esc(r.get('name', ''))}</code></td><td>{_esc(r.get('semantic_type', ''))}</td>"
        f"<td><code>{_esc(_short(r.get('sha256')))}</code></td><td>{_esc(r.get('size_bytes', 0))} B</td>"
        f"<td>{_esc(_viewer_hint(str(r.get('path', ''))))}</td></tr>"
        for r in run.get("artifacts", {}).get("results", [])
    ) or '<tr><td colspan="5"><em>No result artifacts recorded.</em></td></tr>'

    inputs_rows = "\n".join(
        f"<tr><td><code>{_esc(name)}</code></td><td>{_esc(item.get('semantic_type', ''))}</td>"
        f"<td><code>{_esc(_short(item.get('sha256')))}</code></td>"
        f"<td>{_esc('yes' if item.get('ingress_verified') or Path(str(item.get('path', ''))).is_file() else 'on-disk?')}</td></tr>"
        for name, item in bundle.inputs.items()
    ) or '<tr><td colspan="4"><em>No inputs recorded.</em></td></tr>'

    verification_banner = (
        '<div class="banner ok">Capsule integrity verified (SHA-256 artifact hashes intact).</div>'
        if bundle.verified
        else '<div class="banner warn"><strong>Integrity verification FAILED</strong> — '
        f"{_esc(', '.join(bundle.verification.get('missing_files', []) + bundle.verification.get('tampered_files', [])) or 'see bionexus run verify')}. "
        "Treat contents with suspicion.</div>"
    )

    status = run.get("status", "UNKNOWN")
    maturity = run.get("conclusion_maturity", "UNASSESSED")
    methods_md = build_methods_text(bundle)

    css = """
    :root{--bg:#f6f8fa;--fg:#24292f;--muted:#57606a;--line:#d0d7de;--ok:#1a7f37;--warn:#cf222e}
    body{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--fg);
         margin:0;background:var(--bg);line-height:1.5}
    main{max-width:960px;margin:0 auto;padding:24px 20px 60px}
    h1{font-size:1.45rem;margin:.2rem 0} h2{font-size:1.1rem;border-bottom:1px solid var(--line);padding-bottom:4px}
    .meta{color:var(--muted);font-size:.9rem}
    .badge{display:inline-block;border-radius:999px;padding:2px 10px;font-size:.75rem;font-weight:600;
           background:#dbeafe;color:#1e3a8a;margin-right:6px}
    .badge.ok{background:#dcfce7;color:#14532d}.badge.warn{background:#fee2e2;color:#7f1d1d}
    .banner{border-radius:8px;padding:10px 14px;margin:14px 0;font-size:.9rem}
    .banner.ok{background:#dcfce7;color:#14532d}.banner.warn{background:#fee2e2;color:#7f1d1d}
    details{background:#fff;border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:10px 16px}
    summary{cursor:pointer;font-weight:600}
    table{border-collapse:collapse;width:100%;font-size:.88rem;margin:8px 0}
    th,td{border:1px solid var(--line);padding:6px 8px;text-align:left}
    th{background:var(--bg)}
    code{background:#eff1f3;border-radius:4px;padding:1px 5px;font-size:.85em}
    pre{background:#0d1117;color:#e6edf3;padding:12px;border-radius:8px;overflow:auto;font-size:.82rem}
    pre code{background:none;color:inherit;padding:0}
    figure{margin:12px 0;text-align:center}figcaption{color:var(--muted);font-size:.82rem}
    footer{color:var(--muted);font-size:.78rem;margin-top:28px;border-top:1px solid var(--line);padding-top:12px}
    nav a{margin-right:12px;font-size:.85rem}
    @media print{details{break-inside:avoid}}
    """
    nav_items = ["Evidence", "Inputs", "Parameters", "Results", "Figures", "Methods", "Provenance"]
    nav = " ".join(f'<a href="#{n.lower()}">{n}</a>' for n in nav_items)

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>BioNexus Report — {_esc(bundle.run_id)}</title>
<style>{css}</style></head>
<body><main>
<header>
  <h1>BioNexus Run Report</h1>
  <div class="meta">{_esc(bundle.run_id)} · {_esc(run.get('capability_id', '-'))} ·
      skill <code>{_esc(run.get('skill_name', '-'))}</code> · BioNexus v{_esc(run.get('bionexus_version', PLUGIN_VERSION))}</div>
  <div style="margin:8px 0">
    <span class="badge {'ok' if status == 'COMPLETED' else 'warn'}">{_esc(status)}</span>
    <span class="badge">maturity: {_esc(maturity)}</span>
    <span class="badge">{_esc(run.get('timestamp_start', ''))}</span>
  </div>
  {verification_banner}
  <nav>{nav}</nav>
</header>

<details open id="evidence"><summary>EvidenceCard (7 dimensions)</summary>
  {_grade_svg(rows)}
  <table><tr><th>Dimension</th><th>Grade</th></tr>
  {''.join(f'<tr><td>{_esc(label)}</td><td><strong style="color:{_GRADE_COLORS.get(grade.upper(), "#8b949e")}">{_esc(grade)}</strong></td></tr>' for label, grade in rows)}
  </table>
</details>

<details open id="inputs"><summary>Inputs</summary>
  <table><tr><th>Name</th><th>Semantic type</th><th>SHA-256</th><th>On disk</th></tr>
  {inputs_rows}</table>
</details>

<details id="parameters"><summary>Parameters</summary>
  <pre><code>{_esc(json.dumps(bundle.parameters, indent=2, default=str))}</code></pre>
</details>

<details open id="results"><summary>Result artifacts</summary>
  <table><tr><th>Name</th><th>Type</th><th>SHA-256</th><th>Size</th><th>Viewer hint</th></tr>
  {results_rows}</table>
</details>

<details open id="figures"><summary>Figures</summary>
  {''.join(fig_sections)}
</details>

<details id="methods"><summary>Methods (generated)</summary>
  <pre style="background:#fff;color:var(--fg)"><code>{_esc(methods_md)}</code></pre>
</details>

<details id="provenance"><summary>Provenance (W3C PROV-O)</summary>
  <pre><code>{_esc(json.dumps(bundle.provenance, indent=2, default=str)[:6000])}</code></pre>
</details>

<footer>
  Generated by BioNexus v{_esc(PLUGIN_VERSION)} at {_esc(datetime.now(timezone.utc).isoformat())}
  from capsule <code>{_esc(bundle.run_id)}</code>. {_esc(_RUO_NOTICE)}
</footer>
</main></body></html>
"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return attach_meta(
        {
            "refused": False,
            "export": {
                "format": "html_report",
                "path": str(out),
                "run_id": bundle.run_id,
                "integrity_verified": bundle.verified,
                "size_bytes": out.stat().st_size,
            },
        },
        method="bionexus.delivery.render_html_report",
        backend="bionexus.delivery (stdlib)",
        limitations=[
            "The report mirrors the capsule; it adds no scientific interpretation.",
            "Self-contained HTML: figures ≤5 MB are embedded, larger ones are linked only.",
        ],
    )


# ----------------------------------------------------------------------- notebook


def _nb_cell(cell_type: str, source: str, cell_id: str) -> Dict[str, Any]:
    cell: Dict[str, Any] = {
        "cell_type": cell_type,
        "id": cell_id,
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def render_notebook(capsule_dir: PathLike, out_path: PathLike) -> Dict[str, Any]:
    """Render an nbformat-4.5 reproducibility notebook from a Run Capsule."""
    bundle = load_capsule_bundle(capsule_dir)
    run = bundle.run
    params_json = json.dumps(bundle.parameters, indent=2, default=str)

    rerun_cell = ""
    command = bundle.parameters.get("command")
    if isinstance(command, list) and command and all(isinstance(c, str) for c in command):
        cmd_repr = json.dumps(command)
        rerun_cell = f'''# Recorded chain/pipeline command. Review before re-running:
print({cmd_repr})
# subprocess.run({cmd_repr}, check=True)  # uncomment to execute on a capable host
'''

    primary = run.get("artifacts", {}).get("primary_result")
    load_result_cell = ""
    if primary:
        load_result_cell = f'''# Inspect the primary result artifact (requires pandas for tabular files):
result_path = CAPSULE / {primary!r}
print("exists:", result_path.exists())
try:
    import pandas as pd
    if result_path.suffix in (".csv", ".tsv", ".txt"):
        display(pd.read_csv(result_path, sep="\\t" if result_path.suffix == ".tsv" else ","))
except ImportError:
    print("pandas not installed; skipping tabular preview")
'''

    cells = [
        _nb_cell(
            "markdown",
            f"# BioNexus Reproducibility Notebook — {bundle.run_id}\n\n"
            f"- Capability: `{run.get('capability_id', '-')}`\n"
            f"- Skill: `{run.get('skill_name', '-')}`\n"
            f"- Executed: {run.get('timestamp_start', '-')} → {run.get('timestamp_end', '-')}\n"
            f"- Conclusion maturity: `{run.get('conclusion_maturity', 'UNASSESSED')}`\n\n"
            f"> {_RUO_NOTICE}",
            "intro",
        ),
        _nb_cell(
            "code",
            'import json\nfrom pathlib import Path\n\nCAPSULE = Path("%s")\nrun = json.loads((CAPSULE / "run.json").read_text())\nprint(run["run_id"], "|", run.get("capability_id"), "|", run.get("status"))' % str(bundle.capsule_dir.as_posix()),
            "load",
        ),
        _nb_cell(
            "code",
            "# Verify artifact integrity before trusting any content below.\n"
            "try:\n"
            "    from bionexus.artifacts import verify_run_bundle\n"
            "    v = verify_run_bundle(CAPSULE)\n"
            "    print('verified:', v.valid)\n"
            "    if not v.valid:\n"
            "        print('missing:', v.missing_files)\n"
            "        print('tampered:', v.tampered_files)\n"
            "except ImportError:\n"
            "    print('pip install bionexus to verify hashes programmatically')",
            "verify",
        ),
        _nb_cell(
            "code",
            f"# Recorded parameters:\nprint({params_json!r})",
            "params",
        ),
    ]
    if rerun_cell:
        cells.append(_nb_cell("code", rerun_cell, "rerun"))
    if load_result_cell:
        cells.append(_nb_cell("code", load_result_cell, "results"))
    cells.append(
        _nb_cell(
            "markdown",
            "## Notes\n\n- This notebook re-reads the capsule; it does not re-execute the analysis automatically.\n"
            "- Re-running analysis steps requires the original environment (see `environment.json`).\n"
            "- Methods text: `bionexus export methods <capsule>` or the HTML report.",
            "notes",
        )
    )

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
            "bionexus": {"run_id": bundle.run_id, "generated_at": datetime.now(timezone.utc).isoformat()},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
    return attach_meta(
        {
            "refused": False,
            "export": {
                "format": "notebook",
                "path": str(out),
                "run_id": bundle.run_id,
                "integrity_verified": bundle.verified,
                "cells": len(cells),
            },
        },
        method="bionexus.delivery.render_notebook",
        backend="bionexus.delivery (stdlib)",
        limitations=[
            "The notebook re-reads the capsule and prints recorded state; it does not "
            "auto-execute analysis steps.",
        ],
    )


# --------------------------------------------------------------------- supplement


def export_supplement(capsule_dir: PathLike, out_dir: PathLike) -> Dict[str, Any]:
    """
    Export a journal-style supplementary bundle. Refuses (fail-closed) when the source
    capsule fails integrity verification — supplements ship tamper-checked data only.
    """
    bundle = load_capsule_bundle(capsule_dir)
    if not bundle.verified:
        return refuse(
            method="bionexus.delivery.export_supplement",
            reason=(
                f"Capsule '{bundle.run_id}' failed integrity verification "
                f"(missing={bundle.verification.get('missing_files')}, "
                f"tampered={bundle.verification.get('tampered_files')}); refusing to build a "
                "supplementary bundle from unverified data."
            ),
            extra={"run_id": bundle.run_id, "verification": bundle.verification},
        )

    base = bundle.capsule_dir
    out = Path(out_dir)
    figures_dir = out / "figures"
    tables_dir = out / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    copied: List[Dict[str, str]] = []

    def _copy(src: Path, dest_dir: Path, role: str) -> None:
        dest = dest_dir / src.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            dest = dest_dir / f"{stem}_2{suffix}"
        shutil.copy2(src, dest)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        copied.append({"file": str(dest), "role": role, "sha256": digest, "size_bytes": dest.stat().st_size})

    for fig in bundle.run.get("artifacts", {}).get("figures", []):
        fpath = _figure_path(base, str(fig.get("path", "")))
        if fpath is not None:
            _copy(fpath, figures_dir, "figure")
    results = bundle.run.get("artifacts", {}).get("results", [])
    for item in results:
        rpath = _figure_path(base, str(item.get("path", "")))
        if rpath is None:
            continue
        is_primary = item.get("path") == bundle.run.get("artifacts", {}).get("primary_result")
        role = "primary_table" if is_primary else "table"
        if rpath.suffix.lower() in _TABULAR_SUFFIXES | _STRUCTURE_SUFFIXES | _SEQUENCE_SUFFIXES or is_primary:
            _copy(rpath, tables_dir, role)

    (out / "methods.md").write_text(build_methods_text(bundle) + "\n", encoding="utf-8")
    copied.append({"file": str(out / "methods.md"), "role": "methods", "sha256": hashlib.sha256((out / "methods.md").read_bytes()).hexdigest(), "size_bytes": (out / "methods.md").stat().st_size})

    availability = [
        "# Data availability",
        "",
        "| Artifact | Role | SHA-256 | Size (bytes) |",
        "|---|---|---|---|",
    ]
    for name, item in bundle.inputs.items():
        availability.append(f"| `{name}` | input (source data) | `{_short(item.get('sha256'), 32)}` | {item.get('size_bytes', '-')} |")
    for c in copied:
        availability.append(f"| `{Path(c['file']).name}` | {c['role']} | `{c['sha256'][:32]}` | {c['size_bytes']} |")
    availability.extend([
        "",
        "Source data are available from the corresponding author upon reasonable request. "
        "All shipped files carry SHA-256 digests above; verify before reuse.",
        "",
        _RUO_NOTICE,
    ])
    (out / "data_availability.md").write_text("\n".join(availability) + "\n", encoding="utf-8")

    manifest = {
        "schema": "bionexus.supplement/1.0",
        "run_id": bundle.run_id,
        "capability_id": bundle.run.get("capability_id"),
        "bionexus_version": PLUGIN_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integrity_verified": True,
        "files": copied,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return attach_meta(
        {
            "refused": False,
            "export": {
                "format": "supplement",
                "path": str(out),
                "run_id": bundle.run_id,
                "files": len(copied),
                "figures": len(list(figures_dir.iterdir())),
                "tables": len(list(tables_dir.iterdir())),
            },
        },
        method="bionexus.delivery.export_supplement",
        backend="bionexus.delivery (stdlib)",
        limitations=[
            "The bundle ships only files present in the verified capsule; source data "
            "availability wording must be reviewed by the authors.",
        ],
    )
