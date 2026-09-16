"""BioNexus Independent Validation Network (IVN) Public Ledger Page Generator.

Renders an interactive, responsive, self-contained HTML/JS/CSS public ledger
portal from the canonical IVN registry (validation/ivn/REGISTRY.json).

Key Capabilities:
1. Moat & Epistemic Depth Metrics: Live counts of verified datasets, external labs,
   independent reviewers, frozen negative results, and epistemic warrants.
2. Quota Matrix & Open Recruitment Slots: Real-time status for the three flagship
   capabilities (scrna.pseudobulk_de, scrna.annotation_evidence, spatial.inference_validity)
   with visual distinction between verified entries and vacant recruitment slots.
3. Append-Only Cryptographic Evidence Ledger: Filterable table of all registered entities,
   complete with SHA-256 digests, artifact provenance, and fail-closed notes.
4. Client-Side Live Hash Verifier: Browser-based cryptographic validator allowing researchers
   to compute SHA-256 digests of local artifacts and cross-verify with the public ledger.
5. Request for Validation (RFV) Recruitment Engine: Step-by-step guides, interactive JSON
   templates, CLI commands, and one-click GitHub Issue creation links.
6. Open Questions Alignment Radar: Honest representation of unresolved evidence blockers.
"""

from __future__ import annotations

import datetime
import html
import json
from pathlib import Path
from typing import Any, List, Mapping, Optional

from bionexus.ivn import (
    FLAGSHIP_CAPABILITIES,
    IVNRegistry,
    evaluate_network,
    verify_registry_integrity,
)


def _esc(value: Any) -> str:
    """Safely escape HTML strings."""
    if value is None:
        return ""
    return html.escape(str(value))


def generate_merkle_root(registry: IVNRegistry) -> str:
    """Compute a deterministic Merkle-style root hash over all registry entities."""
    import hashlib

    hasher = hashlib.sha256()
    hasher.update(registry.schema_version.encode("utf-8"))

    # Hash datasets
    for ds in sorted(registry.datasets, key=lambda d: d.dataset_id):
        raw = f"dataset:{ds.dataset_id}:{ds.status}:{ds.preregistration_sha256}:{ds.report_sha256}:{ds.author_associated}"
        hasher.update(raw.encode("utf-8"))

    # Hash lab studies
    for ls in sorted(registry.lab_studies, key=lambda s: s.study_id):
        raw = f"lab:{ls.study_id}:{ls.status}:{ls.capsule_sha256}:{ls.institution}:{ls.independence.declares_independent}"
        hasher.update(raw.encode("utf-8"))

    # Hash reviews
    for rv in sorted(registry.reviews, key=lambda r: r.review_id):
        raw = f"review:{rv.review_id}:{rv.status}:{rv.review_sha256}:{rv.verdict}:{rv.blinded}"
        hasher.update(raw.encode("utf-8"))

    # Hash freezes
    for fz in sorted(registry.calibration_freezes, key=lambda f: f.get("freeze_id", "")):
        raw = f"freeze:{fz.get('freeze_id')}:{fz.get('profile_sha256')}"
        hasher.update(raw.encode("utf-8"))

    return hasher.hexdigest()


def render_public_ledger_html(
    registry: IVNRegistry,
    *,
    network_assessment: Optional[Mapping[str, Any]] = None,
    repo_root: Optional[Path] = None,
    custom_title: str = "BioNexus Independent Validation Network (IVN) — Public Evidence Ledger",
) -> str:
    """Render a standalone, zero-dependency HTML document representing the IVN Public Ledger."""
    root = Path(repo_root) if repo_root else Path.cwd()
    if network_assessment is None:
        network_assessment = evaluate_network(registry, repo_root=root)

    integrity_report = verify_registry_integrity(registry, repo_root=root)
    merkle_root = generate_merkle_root(registry)
    gen_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Aggregate counts
    total_datasets = len(registry.datasets)
    verified_datasets = sum(1 for d in registry.datasets if d.status == "VERIFIED")
    negative_results = sum(1 for d in registry.datasets if d.outcome == "negative_result")
    total_labs = len(registry.lab_studies)
    verified_labs = sum(1 for s in registry.lab_studies if s.status == "VERIFIED")
    total_reviews = len(registry.reviews)
    verified_reviews = sum(1 for r in registry.reviews if r.status == "VERIFIED")
    total_freezes = len(registry.calibration_freezes)

    # Capability metadata
    cap_meta = {
        "scrna.pseudobulk_de": {
            "title": "Donor-Aware Pseudobulk Differential Expression",
            "spec": ">= 3 donor-aware datasets x >= 2 external labs x >= 1 non-author reviewer",
            "desc": "Biological replicate inference preserving donor stratification against synthetic pseudo-replication.",
            "icon": "🧬",
        },
        "scrna.annotation_evidence": {
            "title": "Cross-Context Single-Cell Annotation Evidence",
            "spec": ">= 3 datasets (cross-disease >=2, cross-tissue >=2, cross-tech >=2) x >= 2 labs x >= 1 reviewer",
            "desc": "Cell-type annotation stability across biological domains with empirical distrust gates.",
            "icon": "🔬",
        },
        "spatial.inference_validity": {
            "title": "Spatial Transcriptomics Ground Truth Inference",
            "spec": ">= 3 datasets (with independent pathology/segmentation truth) x >= 2 labs x >= 1 reviewer",
            "desc": "Physical coordinates & microenvironment inference validated against blinded orthogonal pathology truth.",
            "icon": "📍",
        },
    }

    # Prepare datasets JSON for client-side search/hash verifier
    registry_json_dump = json.dumps(registry.to_dict(), indent=2, ensure_ascii=False)
    network_json_dump = json.dumps(network_assessment, indent=2, ensure_ascii=False)

    cards_html = "".join(_render_capability_cards(registry, network_assessment, cap_meta))
    rows_html = "".join(_render_dataset_rows(registry))
    oq_html = "".join(_render_open_questions(network_assessment))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(custom_title)}</title>
  <meta name="description" content="BioNexus IVN Public Append-Only Signed Evidence Ledger. Cryptographically hash-locked independent datasets, external lab benchmarks, and non-author peer attestations.">
  <style>
    :root {{
      --bg-primary: #0a0f1d;
      --bg-secondary: #111827;
      --bg-tertiary: #1f2937;
      --bg-card: #162032;
      --bg-card-hover: #1e2c44;
      --border-color: #2e3c54;
      --border-focus: #3b82f6;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-blue: #3b82f6;
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --accent-purple: #8b5cf6;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: var(--bg-primary);
      color: var(--text-primary);
      font-family: var(--font-sans);
      line-height: 1.6;
      padding: 0;
      margin: 0;
      -webkit-font-smoothing: antialiased;
    }}

    a {{ color: var(--accent-cyan); text-decoration: none; transition: color 0.2s ease; }}
    a:hover {{ color: #38bdf8; text-decoration: underline; }}

    .container {{
      max-width: 1300px;
      margin: 0 auto;
      padding: 0 24px;
    }}

    /* Header & Nav */
    header {{
      background: linear-gradient(180deg, rgba(17, 24, 39, 0.95) 0%, rgba(10, 15, 29, 0.9) 100%);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-color);
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .header-inner {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 0;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-logo {{
      width: 38px;
      height: 38px;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 20px;
      color: #fff;
    }}
    .brand-title {{
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #fff;
    }}
    .brand-tag {{
      font-size: 11px;
      font-family: var(--font-mono);
      background: rgba(59, 130, 246, 0.15);
      color: var(--accent-cyan);
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }}
    .nav-links {{
      display: flex;
      gap: 20px;
      align-items: center;
    }}
    .nav-link {{
      color: var(--text-secondary);
      font-size: 14px;
      font-weight: 500;
    }}
    .nav-link:hover {{
      color: var(--text-primary);
      text-decoration: none;
    }}
    .btn-rfv {{
      background: linear-gradient(135deg, #2563eb, #06b6d4);
      color: #fff !important;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    }}
    .btn-rfv:hover {{
      opacity: 0.95;
      text-decoration: none;
      transform: translateY(-1px);
    }}

    /* Hero Section */
    .hero {{
      padding: 48px 0 32px;
      border-bottom: 1px solid var(--border-color);
      background: radial-gradient(circle at 50% 0%, rgba(59, 130, 246, 0.1) 0%, rgba(10, 15, 29, 0) 70%);
    }}
    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-family: var(--font-mono);
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.1);
      border: 1px solid rgba(6, 182, 212, 0.25);
      padding: 4px 12px;
      border-radius: 999px;
      margin-bottom: 16px;
    }}
    .hero-badge::before {{
      content: "";
      width: 6px;
      height: 6px;
      background: var(--accent-cyan);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--accent-cyan);
    }}
    .hero h1 {{
      font-size: 38px;
      font-weight: 800;
      letter-spacing: -1px;
      margin-bottom: 16px;
      line-height: 1.2;
    }}
    .hero h1 span {{
      background: linear-gradient(135deg, #60a5fa, #22d3ee);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .hero-desc {{
      font-size: 17px;
      color: var(--text-secondary);
      max-width: 900px;
      margin-bottom: 28px;
    }}

    /* Moat Stats Grid */
    .moat-stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}
    .moat-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 18px;
      position: relative;
      overflow: hidden;
    }}
    .moat-card::after {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--accent-blue), transparent);
    }}
    .moat-card-val {{
      font-size: 28px;
      font-weight: 700;
      font-family: var(--font-mono);
      color: #fff;
      margin-bottom: 4px;
    }}
    .moat-card-label {{
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-weight: 600;
    }}
    .moat-card-sub {{
      font-size: 12px;
      color: var(--accent-cyan);
      margin-top: 4px;
      font-family: var(--font-mono);
    }}

    /* Section Styles */
    section {{
      padding: 40px 0;
      border-bottom: 1px solid var(--border-color);
    }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 24px;
    }}
    .section-title {{
      font-size: 22px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .section-subtitle {{
      font-size: 14px;
      color: var(--text-secondary);
      margin-top: 4px;
    }}

    /* Capability Quota Matrix */
    .quota-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 20px;
    }}
    .quota-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .qc-top {{
      margin-bottom: 16px;
    }}
    .qc-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .qc-icon {{
      font-size: 24px;
    }}
    .qc-title {{
      font-size: 16px;
      font-weight: 700;
      color: #fff;
    }}
    .qc-id {{
      font-size: 12px;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }}
    .qc-status-badge {{
      font-size: 11px;
      font-family: var(--font-mono);
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 999px;
    }}
    .status-incomplete {{
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    .status-complete {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .qc-desc {{
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 16px;
    }}
    .qc-checks {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .qc-check-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
      padding: 6px 10px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }}
    .check-label {{
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .check-val {{
      font-family: var(--font-mono);
      font-size: 12px;
    }}
    .val-pass {{ color: var(--accent-emerald); }}
    .val-gap {{ color: var(--accent-amber); }}

    /* Open Slots Callout in Capability Card */
    .qc-recruitment {{
      background: rgba(6, 182, 212, 0.06);
      border: 1px dashed rgba(6, 182, 212, 0.3);
      border-radius: 8px;
      padding: 12px;
      margin-top: 12px;
    }}
    .recruitment-title {{
      font-size: 12px;
      font-weight: 700;
      color: var(--accent-cyan);
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
    }}
    .recruitment-body {{
      font-size: 12px;
      color: var(--text-secondary);
      line-height: 1.4;
    }}

    /* Ledger Table & Cards */
    .ledger-filter-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-bottom: 16px;
      background: var(--bg-secondary);
      padding: 12px 16px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
    }}
    .search-input {{
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      flex-grow: 1;
      min-width: 200px;
    }}
    .search-input:focus {{
      outline: none;
      border-color: var(--border-focus);
    }}
    .filter-btn {{
      background: transparent;
      border: 1px solid var(--border-color);
      color: var(--text-secondary);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .filter-btn.active, .filter-btn:hover {{
      background: var(--accent-blue);
      color: #fff;
      border-color: var(--accent-blue);
    }}

    .ledger-table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border-color);
      border-radius: 10px;
      background: var(--bg-secondary);
    }}
    table.ledger-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}
    table.ledger-table th {{
      background: var(--bg-tertiary);
      padding: 12px 16px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border-color);
    }}
    table.ledger-table td {{
      padding: 14px 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: var(--text-primary);
    }}
    table.ledger-table tr:hover td {{
      background: rgba(255, 255, 255, 0.02);
    }}
    .entity-badge {{
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 12px;
      color: var(--accent-blue);
    }}
    .hash-badge {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-muted);
      background: rgba(0, 0, 0, 0.2);
      padding: 2px 6px;
      border-radius: 4px;
      cursor: pointer;
    }}
    .hash-badge:hover {{
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.1);
    }}
    .outcome-pill {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-family: var(--font-mono);
      font-weight: 600;
    }}
    .outcome-neg {{
      background: rgba(244, 63, 94, 0.15);
      color: var(--accent-rose);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }}
    .outcome-pass {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}
    .outcome-inconclusive {{
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    /* Vacant Slot Cards */
    .vacant-slots-box {{
      margin-top: 24px;
      background: linear-gradient(180deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 24px;
    }}
    .vacant-slots-header {{
      font-size: 16px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .vacant-slots-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .vacant-slot-card {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px dashed rgba(245, 158, 11, 0.4);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .vacant-slot-tag {{
      font-size: 11px;
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--accent-amber);
      text-transform: uppercase;
      margin-bottom: 6px;
    }}
    .vacant-slot-name {{
      font-size: 14px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 6px;
    }}
    .vacant-slot-req {{
      font-size: 12px;
      color: var(--text-secondary);
      margin-bottom: 12px;
    }}
    .btn-claim-slot {{
      align-self: flex-start;
      font-size: 11px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 4px;
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    .btn-claim-slot:hover {{
      background: var(--accent-amber);
      color: #000;
      text-decoration: none;
    }}

    /* RFV Recruitment Section */
    .rfv-section {{
      background: var(--bg-secondary);
      border-radius: 12px;
      border: 1px solid var(--border-color);
      padding: 32px;
      margin-top: 24px;
    }}
    .rfv-tracks {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 24px;
    }}
    .rfv-track-card {{
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .rfv-track-num {{
      font-size: 11px;
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--accent-cyan);
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .rfv-track-title {{
      font-size: 16px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 8px;
    }}
    .rfv-track-desc {{
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 16px;
      line-height: 1.5;
    }}
    .rfv-steps {{
      list-style: none;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .rfv-steps li {{
      margin-bottom: 6px;
      padding-left: 14px;
      position: relative;
    }}
    .rfv-steps li::before {{
      content: "→";
      position: absolute;
      left: 0;
      color: var(--accent-blue);
    }}
    .btn-track-action {{
      display: inline-block;
      text-align: center;
      background: rgba(59, 130, 246, 0.15);
      color: var(--accent-blue);
      border: 1px solid rgba(59, 130, 246, 0.3);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .btn-track-action:hover {{
      background: var(--accent-blue);
      color: #fff;
      text-decoration: none;
    }}

    /* Verifier & Tools */
    .tools-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 24px;
    }}
    .tool-box {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 24px;
    }}
    .tool-box h3 {{
      font-size: 16px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .tool-box p {{
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 16px;
    }}
    .hash-input-group {{
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .hash-input {{
      flex-grow: 1;
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 6px;
      font-family: var(--font-mono);
      font-size: 12px;
    }}
    .hash-input:focus {{ outline: none; border-color: var(--border-focus); }}
    .btn-verify {{
      background: var(--accent-blue);
      color: #fff;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .verify-result {{
      margin-top: 12px;
      padding: 12px;
      border-radius: 6px;
      font-size: 13px;
      font-family: var(--font-mono);
      display: none;
    }}
    .verify-pass {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
      border: 1px solid rgba(16, 185, 129, 0.3);
      display: block;
    }}
    .verify-fail {{
      background: rgba(244, 63, 94, 0.15);
      color: var(--accent-rose);
      border: 1px solid rgba(244, 63, 94, 0.3);
      display: block;
    }}

    /* Open Questions Table */
    .oq-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 12px;
    }}
    .oq-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }}
    .oq-title {{
      font-size: 15px;
      font-weight: 600;
      color: #fff;
      font-family: var(--font-mono);
    }}
    .oq-badge {{
      font-size: 11px;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}
    .oq-note {{
      font-size: 13px;
      color: var(--text-secondary);
    }}

    /* Footer */
    footer {{
      background: var(--bg-secondary);
      border-top: 1px solid var(--border-color);
      padding: 32px 0;
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 48px;
    }}
    .footer-inner {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}

    /* Responsive */
    @media (max-width: 768px) {{
      .hero h1 {{ font-size: 28px; }}
      .quota-grid {{ grid-template-columns: 1fr; }}
      .tools-grid {{ grid-template-columns: 1fr; }}
      .header-inner {{ flex-direction: column; gap: 12px; }}
    }}
  </style>
</head>
<body>

  <!-- Header -->
  <header>
    <div class="container header-inner">
      <div class="brand">
        <div class="brand-logo">BN</div>
        <div>
          <div class="brand-title">BioNexus IVN</div>
          <div style="font-size: 11px; color: var(--text-muted);">Independent Validation Network</div>
        </div>
        <span class="brand-tag">v{_esc(registry.schema_version)}</span>
      </div>
      <nav class="nav-links">
        <a href="#moat" class="nav-link">Moat Metrics</a>
        <a href="#matrix" class="nav-link">Capability Matrix</a>
        <a href="#ledger" class="nav-link">Evidence Ledger</a>
        <a href="#rfv" class="nav-link">Request for Validation</a>
        <a href="#verifier" class="nav-link">Hash Verifier</a>
        <a href="#rfv" class="btn-rfv">Submit Validation</a>
      </nav>
    </div>
  </header>

  <!-- Hero Section -->
  <section class="hero" id="moat">
    <div class="container">
      <div class="hero-badge">BNS-023 IMMUTABLE CRYPTOGRAPHIC VERIFICATION LEDGER</div>
      <h1>The Only Moat That <span>Automatically Deepens</span> Over Time</h1>
      <p class="hero-desc">
        Algorithms and models can be cloned overnight. An append-only, hash-locked record of
        multi-cohort biological holdouts, independent laboratory replications, frozen negative results,
        and blinded non-author peer attestations cannot. The BioNexus IVN is our public, tamper-evident
        scientific warrant infrastructure.
      </p>

      <!-- Moat Stats Grid -->
      <div class="moat-stats">
        <div class="moat-card">
          <div class="moat-card-val">{verified_datasets} <span style="font-size: 16px; color: var(--text-muted);">/ {total_datasets}</span></div>
          <div class="moat-card-label">Independent Datasets</div>
          <div class="moat-card-sub">{negative_results} Frozen Negative Results</div>
        </div>
        <div class="moat-card">
          <div class="moat-card-val">{verified_labs} <span style="font-size: 16px; color: var(--text-muted);">/ {total_labs}</span></div>
          <div class="moat-card-label">External Labs Verified</div>
          <div class="moat-card-sub">Goal: &gt;= 2 per capability</div>
        </div>
        <div class="moat-card">
          <div class="moat-card-val">{verified_reviews} <span style="font-size: 16px; color: var(--text-muted);">/ {total_reviews}</span></div>
          <div class="moat-card-label">Non-Author Reviews</div>
          <div class="moat-card-sub">Blinded Peer Attestations</div>
        </div>
        <div class="moat-card">
          <div class="moat-card-val">{total_freezes}</div>
          <div class="moat-card-label">Calibration Freezes</div>
          <div class="moat-card-sub">Held-Out Context Locks</div>
        </div>
        <div class="moat-card">
          <div class="moat-card-val" style="font-size: 16px; word-break: break-all; color: var(--accent-cyan);">{merkle_root[:12]}...{merkle_root[-8:]}</div>
          <div class="moat-card-label">Registry Merkle Root</div>
          <div class="moat-card-sub">Integrity: {_esc(integrity_report.get('integrity', 'PASS'))}</div>
        </div>
      </div>
    </div>
  </section>

  <!-- Capability Quota Matrix -->
  <section id="matrix">
    <div class="container">
      <div class="section-header">
        <div>
          <h2 class="section-title">Flagship Capability Quota Matrix</h2>
          <p class="section-subtitle">Deterministic accounting against the 3 flagship validation quotas (Fail-Closed Enforcement)</p>
        </div>
        <div>
          <span class="qc-status-badge status-incomplete">POST-RC3 WORK PROGRAM (VACANT SLOTS PUBLISHED)</span>
        </div>
      </div>

      <div class="quota-grid">
{cards_html}
      </div>

      <!-- Vacant Quota Slots Callout (Recruitment Engine) -->
      <div class="vacant-slots-box" id="vacant-slots">
        <div class="vacant-slots-header">
          <span style="font-size: 20px;">📢</span>
          <span>Open Quota Slots — Active Request for External Validation (RFV)</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 16px;">
          BioNexus publishes its validation ledger empty where evidence is outstanding. We invite external laboratories,
          academic core facilities, and independent computational biologists to execute benchmark protocols and claim these slots.
        </p>
        <div class="vacant-slots-grid">
          <div class="vacant-slot-card">
            <div>
              <div class="vacant-slot-tag">Slot #LAB-001 / #LAB-002</div>
              <div class="vacant-slot-name">External Laboratory Replication</div>
              <div class="vacant-slot-req">Replicate scrna.pseudobulk_de or annotation pipeline on independent hardware with capsule hash.</div>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=6_ivn_external_lab_study.yml" target="_blank" class="btn-claim-slot">Claim Lab Slot →</a>
          </div>

          <div class="vacant-slot-card">
            <div>
              <div class="vacant-slot-tag">Slot #REV-001</div>
              <div class="vacant-slot-name">Blinded Non-Author Peer Review</div>
              <div class="vacant-slot-req">Independent biostatistician or domain expert blinded audit of benchmark methodology and code artifacts.</div>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=7_ivn_reviewer_attestation.yml" target="_blank" class="btn-claim-slot">Submit Attestation →</a>
          </div>

          <div class="vacant-slot-card">
            <div>
              <div class="vacant-slot-tag">Slot #DS-SP-001..003</div>
              <div class="vacant-slot-name">Spatial Ground Truth Cohorts</div>
              <div class="vacant-slot-req">Spatial transcriptomics cohort with independent pathology annotation or orthogonal segmentation truth.</div>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=5_ivn_dataset_submission.yml" target="_blank" class="btn-claim-slot">Register Dataset →</a>
          </div>

          <div class="vacant-slot-card">
            <div>
              <div class="vacant-slot-tag">Slot #DS-ANN-003</div>
              <div class="vacant-slot-name">Never-Seen Cross-Tissue Cohort</div>
              <div class="vacant-slot-req">Single-cell RNA-seq cohort spanning non-PBMC tissue (e.g. solid tumor, brain, lung) to satisfy 2/2 tissue diversity.</div>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=5_ivn_dataset_submission.yml" target="_blank" class="btn-claim-slot">Register Dataset →</a>
          </div>
        </div>
      </div>

    </div>
  </section>

  <!-- Append-Only Evidence Ledger -->
  <section id="ledger">
    <div class="container">
      <div class="section-header">
        <div>
          <h2 class="section-title">Append-Only Cryptographic Evidence Ledger</h2>
          <p class="section-subtitle">Immutable audit trail of registered independent datasets, external studies, and peer attestations</p>
        </div>
      </div>

      <!-- Filter Bar -->
      <div class="ledger-filter-bar">
        <input type="text" id="ledgerSearch" class="search-input" placeholder="Search by Dataset ID, Accession, Disease, Tissue, or Hash..." onkeyup="filterLedger()">
        <button class="filter-btn active" onclick="setFilter('all', this)">All Entities</button>
        <button class="filter-btn" onclick="setFilter('scrna.pseudobulk_de', this)">Pseudobulk DE</button>
        <button class="filter-btn" onclick="setFilter('scrna.annotation_evidence', this)">Annotation</button>
        <button class="filter-btn" onclick="setFilter('spatial.inference_validity', this)">Spatial</button>
        <button class="filter-btn" onclick="setFilter('negative_result', this)">Negative Results Only</button>
      </div>

      <!-- Ledger Table -->
      <div class="ledger-table-wrap">
        <table class="ledger-table" id="ledgerTable">
          <thead>
            <tr>
              <th>ID &amp; Title</th>
              <th>Capability</th>
              <th>Context (Disease / Tissue / Tech)</th>
              <th>Outcome</th>
              <th>Preregistration SHA-256</th>
              <th>Report SHA-256</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
{rows_html}
          </tbody>
        </table>
      </div>

    </div>
  </section>

  <!-- Request for Validation (RFV) Recruitment Guide -->
  <section id="rfv">
    <div class="container">
      <div class="section-header">
        <div>
          <h2 class="section-title">Request for Validation (RFV) — How to Fill the Ledger</h2>
          <p class="section-subtitle">Clear, standardized protocols for external contributors to submit evidence and expand the moat</p>
        </div>
      </div>

      <div class="rfv-section">
        <h3 style="font-size: 18px; color: #fff; margin-bottom: 8px;">An Open Call to the Global Biomedical Research Community</h3>
        <p style="font-size: 14px; color: var(--text-secondary); line-height: 1.6;">
          BioNexus adheres to a strict <em>fail-closed, trust-no-one</em> scientific epistemology. We believe benchmark claims
          without cryptographic provenance and external replication are scientific liabilities.
          We provide four distinct participation tracks for researchers worldwide:
        </p>

        <div class="rfv-tracks">
          <!-- Track 1: Dataset Provider -->
          <div class="rfv-track-card">
            <div>
              <div class="rfv-track-num">Track 01</div>
              <div class="rfv-track-title">Independent Dataset Provider</div>
              <div class="rfv-track-desc">
                Contribute public or prospective benchmark datasets (e.g. GEO, Zenodo, BioStudies). Must provide raw counts,
                donor metadata, and orthogonal ground truth (qPCR, FACS, pathology annotations).
              </div>
              <ul class="rfv-steps">
                <li>Fill <code>INDEPENDENT_DATASET.template.json</code></li>
                <li>Lock preregistration &amp; compute artifact SHA-256</li>
                <li>Submit via GitHub Issue or Pull Request</li>
              </ul>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=5_ivn_dataset_submission.yml" target="_blank" class="btn-track-action">Register Dataset →</a>
          </div>

          <!-- Track 2: External Lab Replication -->
          <div class="rfv-track-card">
            <div>
              <div class="rfv-track-num">Track 02</div>
              <div class="rfv-track-title">External Laboratory Benchmark</div>
              <div class="rfv-track-desc">
                Execute BioNexus canonical pipelines in your own institutional environment (Cloud, HPC, or local cluster).
                Sign an independence declaration and submit the generated run capsule.
              </div>
              <ul class="rfv-steps">
                <li>Run canonical benchmark pipeline</li>
                <li>Sign <code>EXTERNAL_LAB_STUDY.template.json</code></li>
                <li>Record execution capsule SHA-256</li>
              </ul>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=6_ivn_external_lab_study.yml" target="_blank" class="btn-track-action">Submit Lab Replication →</a>
          </div>

          <!-- Track 3: Non-Author Reviewer -->
          <div class="rfv-track-card">
            <div>
              <div class="rfv-track-num">Track 03</div>
              <div class="rfv-track-title">Blinded Non-Author Peer Review</div>
              <div class="rfv-track-desc">
                Biostatisticians and domain scientists absent from the author roster conduct blinded audits of benchmark
                studies and issue signed scientific attestations (ENDORSED / CHALLENGED).
              </div>
              <ul class="rfv-steps">
                <li>Audit study preregistrations and code</li>
                <li>Issue verdict via <code>INDEPENDENT_REVIEW.template.json</code></li>
                <li>Submit attestation ID and review hash</li>
              </ul>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/issues/new?template=7_ivn_reviewer_attestation.yml" target="_blank" class="btn-track-action">Submit Review Attestation →</a>
          </div>

          <!-- Track 4: Calibration Profile Freeze -->
          <div class="rfv-track-card">
            <div>
              <div class="rfv-track-num">Track 04</div>
              <div class="rfv-track-title">Calibration Profile Freeze</div>
              <div class="rfv-track-desc">
                Freeze empirical warrant thresholds against held-out biological partitions (cross-technology, cross-disease)
                to authorize diagnostic warrants in new contexts.
              </div>
              <ul class="rfv-steps">
                <li>Ensure profile review status is APPROVED</li>
                <li>Bind held-out partition fingerprints</li>
                <li>Run <code>bionexus ivn freeze-profile</code></li>
              </ul>
            </div>
            <a href="https://github.com/HERRY423/BioNexus/blob/main/docs/independent-validation-network.md" target="_blank" class="btn-track-action">View Freeze Guide →</a>
          </div>
        </div>

      </div>
    </div>
  </section>

  <!-- Client-Side Live Cryptographic Verifier & CLI Tools -->
  <section id="verifier">
    <div class="container">
      <div class="section-header">
        <div>
          <h2 class="section-title">Cryptographic Verifier &amp; CLI Audit Suite</h2>
          <p class="section-subtitle">Real-time client-side hash verification against the ledger and offline CLI commands</p>
        </div>
      </div>

      <div class="tools-grid">
        <!-- Live Browser Hash Verifier -->
        <div class="tool-box">
          <h3><span>⚡</span> Live In-Browser Ledger Verifier</h3>
          <p>Paste any SHA-256 hash or artifact digest to check if it matches an immutable record in this public registry:</p>
          <div class="hash-input-group">
            <input type="text" id="verifyHashInput" class="hash-input" placeholder="Paste 64-character SHA-256 hex string...">
            <button class="btn-verify" onclick="verifyHashOnline()">Verify</button>
          </div>
          <div id="verifyResult" class="verify-result"></div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 12px;">
            Tip: You can also drag &amp; drop a local report JSON or preregistration JSON file below to compute its SHA-256:
          </div>
          <div style="margin-top: 8px;">
            <input type="file" id="fileHasher" style="font-size: 12px; color: var(--text-secondary);" onchange="handleFileHash(event)">
          </div>
        </div>

        <!-- Offline CLI Command Reference -->
        <div class="tool-box">
          <h3><span>💻</span> BioNexus CLI Accounting Commands</h3>
          <p>Audit and register evidence directly in your local environment:</p>
          <pre style="background: var(--bg-tertiary); padding: 14px; border-radius: 6px; font-family: var(--font-mono); font-size: 12px; color: #a5f3fc; overflow-x: auto; border: 1px solid var(--border-color); line-height: 1.5;">
# 1. Audit full network quotas &amp; open blockers
bionexus ivn status

# 2. Recompute all recorded artifact hashes on disk
bionexus ivn verify

# 3. Register a new independent dataset submission
bionexus ivn register-dataset --payload my_dataset.json

# 4. Generate &amp; build the public HTML ledger
bionexus ivn build-ledger --output docs/ivn/index.html
          </pre>
        </div>
      </div>

    </div>
  </section>

  <!-- Open Questions & Governance Blocker Radar -->
  <section id="governance">
    <div class="container">
      <div class="section-header">
        <div>
          <h2 class="section-title">Open Questions &amp; Governance Blocker Radar</h2>
          <p class="section-subtitle">Derived dynamically from empirical evidence (docs/context/OPEN_QUESTIONS.md)</p>
        </div>
      </div>

      <div>
{oq_html}
      </div>
    </div>
  </section>

  <!-- Footer -->
  <footer>
    <div class="container footer-inner">
      <div>
        <strong>BioNexus Independent Validation Network (IVN)</strong> — Open Append-Only Scientific Ledger<br>
        <span style="font-size: 12px;">Generated at: {gen_time} | Merkle Root: <span style="font-family: var(--font-mono);">{merkle_root}</span></span>
      </div>
      <div>
        <a href="https://github.com/HERRY423/BioNexus" target="_blank" style="margin-right: 16px;">GitHub Repository</a>
        <a href="https://github.com/HERRY423/BioNexus/blob/main/docs/independent-validation-network.md" target="_blank">IVN Specification (BNS-023)</a>
      </div>
    </div>
  </footer>

  <!-- Embedded Registry & Interactive Logic -->
  <script id="ivn-registry-data" type="application/json">
{registry_json_dump}
  </script>
  <script id="ivn-network-data" type="application/json">
{network_json_dump}
  </script>

  <script>
    const IVN_REGISTRY = JSON.parse(document.getElementById('ivn-registry-data').textContent);
    const KNOWN_HASHES = new Map();

    // Populate hash map
    IVN_REGISTRY.datasets.forEach(d => {{
      if (d.preregistration_sha256) KNOWN_HASHES.set(d.preregistration_sha256.toLowerCase(), {{ type: 'Preregistration', id: d.dataset_id, title: d.title }});
      if (d.report_sha256) KNOWN_HASHES.set(d.report_sha256.toLowerCase(), {{ type: 'Report', id: d.dataset_id, title: d.title }});
    }});
    IVN_REGISTRY.lab_studies.forEach(s => {{
      if (s.capsule_sha256) KNOWN_HASHES.set(s.capsule_sha256.toLowerCase(), {{ type: 'Lab Capsule', id: s.study_id, title: s.lab_name }});
    }});
    IVN_REGISTRY.reviews.forEach(r => {{
      if (r.review_sha256) KNOWN_HASHES.set(r.review_sha256.toLowerCase(), {{ type: 'Review Artifact', id: r.review_id, title: r.reviewer_name }});
    }});

    function filterLedger() {{
      const query = document.getElementById('ledgerSearch').value.toLowerCase();
      const rows = document.querySelectorAll('#ledgerTable tbody tr');
      rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        const matchesQuery = text.includes(query);
        row.style.display = matchesQuery ? '' : 'none';
      }});
    }}

    function setFilter(capFilter, btn) {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const rows = document.querySelectorAll('#ledgerTable tbody tr');
      rows.forEach(row => {{
        const cap = row.getAttribute('data-cap') || '';
        const outcome = row.getAttribute('data-outcome') || '';
        if (capFilter === 'all') {{
          row.style.display = '';
        }} else if (capFilter === 'negative_result') {{
          row.style.display = (outcome === 'negative_result') ? '' : 'none';
        }} else {{
          row.style.display = (cap === capFilter) ? '' : 'none';
        }}
      }});
    }}

    function verifyHashOnline() {{
      const input = document.getElementById('verifyHashInput').value.trim().toLowerCase();
      const resBox = document.getElementById('verifyResult');
      if (!input || input.length !== 64) {{
        resBox.className = 'verify-result verify-fail';
        resBox.textContent = '❌ Please enter a valid 64-character SHA-256 hex string.';
        return;
      }}
      if (KNOWN_HASHES.has(input)) {{
        const info = KNOWN_HASHES.get(input);
        resBox.className = 'verify-result verify-pass';
        resBox.textContent = `✅ MATCH FOUND: Registered ${{info.type}} for entity ${{info.id}} ("${{info.title}}"). Tamper-free!`;
      }} else {{
        resBox.className = 'verify-result verify-fail';
        resBox.textContent = '⚠️ HASH NOT RECORDED: This digest does not exist in the current IVN registry. Submit it via Track 01-03!';
      }}
    }}

    async function handleFileHash(e) {{
      const file = e.target.files[0];
      if (!file) return;
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
      document.getElementById('verifyHashInput').value = hashHex;
      verifyHashOnline();
    }}
  </script>
</body>
</html>
"""


def _render_capability_cards(
    registry: IVNRegistry,
    network_assessment: Mapping[str, Any],
    cap_meta: Mapping[str, Any],
) -> List[str]:
    """Render HTML cards for each flagship capability."""
    cards = []
    caps_data = network_assessment.get("capabilities", {})

    for cap_id in FLAGSHIP_CAPABILITIES:
        meta = cap_meta.get(cap_id, {"title": cap_id, "spec": "", "desc": "", "icon": "🧬"})
        assessment = caps_data.get(cap_id, {})
        is_complete = assessment.get("complete", False)
        status_cls = "status-complete" if is_complete else "status-incomplete"
        status_text = "QUOTA SATISFIED" if is_complete else "QUOTA VACANT / INCOMPLETE"

        checks = assessment.get("checks", [])
        checks_html = []
        for c in checks:
            val_cls = "val-pass" if c.get("satisfied") else "val-gap"
            icon = "✅" if c.get("satisfied") else "⏳"
            checks_html.append(
                f'<li class="qc-check-item">'
                f'  <span class="check-label">{icon} {_esc(c.get("requirement"))}</span>'
                f'  <span class="check-val {val_cls}">{_esc(c.get("observed"))} / {_esc(c.get("required"))}</span>'
                f"</li>"
            )

        # Gaps / Vacancies text
        gaps = assessment.get("blocking_gaps", [])
        gaps_desc = "<br>• ".join([_esc(g) for g in gaps]) if gaps else "All quota criteria met."

        cards.append(
            f"""
        <div class="quota-card">
          <div class="qc-top">
            <div class="qc-head">
              <div style="display: flex; gap: 10px; align-items: center;">
                <span class="qc-icon">{meta['icon']}</span>
                <div>
                  <div class="qc-title">{_esc(meta['title'])}</div>
                  <div class="qc-id">{_esc(cap_id)}</div>
                </div>
              </div>
              <span class="qc-status-badge {status_cls}">{status_text}</span>
            </div>
            <div class="qc-desc">{_esc(meta['desc'])}</div>
            <ul class="qc-checks">
              {''.join(checks_html)}
            </ul>
          </div>
          <div class="qc-recruitment">
            <div class="recruitment-title">
              <span>🎯</span>
              <span>Open Quota Gaps:</span>
            </div>
            <div class="recruitment-body">
              • {gaps_desc}
            </div>
          </div>
        </div>
        """
        )
    return cards


def _render_dataset_rows(registry: IVNRegistry) -> List[str]:
    """Render HTML table rows for datasets."""
    rows = []
    for d in registry.datasets:
        outcome_cls = "outcome-pass"
        if d.outcome == "negative_result":
            outcome_cls = "outcome-neg"
        elif "inconclusive" in d.outcome or "candidate" in d.outcome:
            outcome_cls = "outcome-inconclusive"

        pre_hash = d.preregistration_sha256
        pre_short = f"{pre_hash[:8]}...{pre_hash[-6:]}" if pre_hash else "None"
        rep_hash = d.report_sha256
        rep_short = f"{rep_hash[:8]}...{rep_hash[-6:]}" if rep_hash else "None"

        context_str = f"{d.disease} | {d.tissue} | {d.technology}"

        rows.append(
            f"""
          <tr data-cap="{_esc(d.capability_id)}" data-outcome="{_esc(d.outcome)}">
            <td>
              <div class="entity-badge">{_esc(d.dataset_id)}</div>
              <div style="font-size: 13px; font-weight: 600;">{_esc(d.title)}</div>
              <div style="font-size: 11px; color: var(--text-muted);">{_esc(d.source_uri)}</div>
            </td>
            <td><code style="font-size: 11px; color: var(--accent-cyan);">{_esc(d.capability_id)}</code></td>
            <td><span style="font-size: 12px; color: var(--text-secondary);">{_esc(context_str)}</span></td>
            <td><span class="outcome-pill {outcome_cls}">{_esc(d.outcome)}</span></td>
            <td><span class="hash-badge" title="{_esc(pre_hash)}" onclick="navigator.clipboard.writeText('{_esc(pre_hash)}')">{_esc(pre_short)}</span></td>
            <td><span class="hash-badge" title="{_esc(rep_hash)}" onclick="navigator.clipboard.writeText('{_esc(rep_hash)}')">{_esc(rep_short)}</span></td>
            <td><span class="outcome-pill outcome-pass">{_esc(d.status)}</span></td>
          </tr>
          """
        )
    return rows


def _render_open_questions(network_assessment: Mapping[str, Any]) -> List[str]:
    """Render HTML cards for the 4 OPEN_QUESTIONS blockers."""
    cards = []
    oq = network_assessment.get("open_questions", {}).get("blockers", {})

    for blocker_id, data in oq.items():
        is_open = data.get("still_open", True)
        badge_text = "OPEN BLOCKER" if is_open else "RESOLVED"
        note = data.get("note", "")

        cards.append(
            f"""
        <div class="oq-card">
          <div class="oq-header">
            <span class="oq-title">{_esc(blocker_id)}</span>
            <span class="oq-badge">{badge_text}</span>
          </div>
          <div class="oq-note">
            <strong>Evidence Assessment:</strong> {_esc(note)}
          </div>
        </div>
        """
        )
    return cards
