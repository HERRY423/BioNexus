"""One-off generator for validation/ivn/REGISTRY.json (run from repo root).

Records the six preregistered, hash-verified studies that exist after rc3 as
IVN dataset entities, with honest coverage metadata and no external-lab or
reviewer entries (none are verified). Re-run only when intentionally
regenerating the registry.
"""

import datetime
import json
import pathlib
import subprocess
import sys

REPO_ROOT = next(
    (parent for parent in pathlib.Path(__file__).resolve().parents if (parent / "src" / "bionexus").is_dir()),
    pathlib.Path.cwd(),
)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.provenance import sha256_file


def sha(path: str) -> str:
    """Use the verifier's canonical cross-platform text hashing rule."""
    return sha256_file(pathlib.Path(path))


STUDIES = {
    "BN-PB-IV-002": (
        "validation/pseudobulk/independent/PREREGISTRATION.json",
        "validation/pseudobulk/independent/REPORT.json",
    ),
    "BN-PB-IV-004": (
        "validation/pseudobulk/studies/BN-PB-IV-004/PREREGISTRATION.json",
        "validation/pseudobulk/studies/BN-PB-IV-004/REPORT.json",
    ),
    "BN-PB-IV-005": (
        "validation/pseudobulk/studies/BN-PB-IV-005/PREREGISTRATION.json",
        "validation/pseudobulk/studies/BN-PB-IV-005/REPORT.json",
    ),
    "BN-ANN-IV-001": (
        "validation/annotation/studies/BN-ANN-IV-001/PREREGISTRATION.json",
        "validation/annotation/studies/BN-ANN-IV-001/REPORT.json",
    ),
    "BN-ANN-IV-003": (
        "validation/annotation/studies/BN-ANN-IV-003/PREREGISTRATION.json",
        "validation/annotation/studies/BN-ANN-IV-003/REPORT.json",
    ),
    "BN-SP-IV-001": (
        "validation/spatial/studies/BN-SP-IV-001/PREREGISTRATION.json",
        "validation/spatial/studies/BN-SP-IV-001/REPORT.json",
    ),
}

DATASETS = [
    {
        "dataset_id": "BN-PB-IV-002",
        "capability_id": "scrna.pseudobulk_de",
        "title": "Donor-aware pseudobulk DE independent validation on Kang 2018 IFN-beta PBMC",
        "source_uri": "https://www.ncbi.nlm.nih.gov/geo/ GSE96583 (kang2018_pbmc_ifnb)",
        "accession": "GSE96583",
        "disease": "systemic_lupus_erythematosus",
        "tissue": "PBMC_blood",
        "technology": "10x_chromium_3prime_droplet",
        "author_associated": False,
        "donor_aware": True,
        "outcome": "negative_result",
        "preregistration_path": STUDIES["BN-PB-IV-002"][0],
        "report_path": STUDIES["BN-PB-IV-002"][1],
        "status": "VERIFIED",
        "notes": (
            "Frozen negative result (bionexus.negative-result-freeze.v1): independent "
            "biological validation not supported on this cohort. A negative outcome is "
            "retained evidence; it does not by itself satisfy external-lab or reviewer quotas."
        ),
    },
    {
        "dataset_id": "BN-PB-IV-004",
        "capability_id": "scrna.pseudobulk_de",
        "title": "Blinded multi-cohort platform holdout (C02 Parse-10M context + C04 prospective independent-lab collection)",
        "source_uri": "GEO GSE96583 (frozen signature source) + parse10m_pbmc_ifnb_natural_v1 + prospective independent-laboratory collection",
        "accession": "",
        "disease": "healthy_donor_control",
        "tissue": "PBMC_blood",
        "technology": "parse_scRNAseq_plus_10x_chromium_3prime",
        "author_associated": False,
        "donor_aware": True,
        "outcome": "negative_result",
        "preregistration_path": STUDIES["BN-PB-IV-004"][0],
        "report_path": STUDIES["BN-PB-IV-004"][1],
        "status": "VERIFIED",
        "notes": (
            "Preregistration-locked blinded analysis; whole-PBMC prospective cohort "
            "concordance 0.5532 < 0.65, frozen as negative_result. Data collected at an "
            "independent laboratory, but the blinded analysis was executed by the BioNexus "
            "team, so this is dataset evidence only — no external-lab quota credit."
        ),
    },
    {
        "dataset_id": "BN-PB-IV-005",
        "capability_id": "scrna.pseudobulk_de",
        "title": "Blinded prospective GLP-core-facility holdout (C05, 12 paired donors)",
        "source_uri": "prospective healthy PBMC multi-arm trial at certified GLP core facility",
        "accession": "",
        "disease": "healthy_donor_control",
        "tissue": "PBMC_blood",
        "technology": "10x_chromium_3prime_v3.1",
        "author_associated": False,
        "donor_aware": True,
        "outcome": "negative_result",
        "preregistration_path": STUDIES["BN-PB-IV-005"][0],
        "report_path": STUDIES["BN-PB-IV-005"][1],
        "status": "VERIFIED",
        "notes": (
            "Preregistration-locked blinded analysis; frozen negative_result. Sample "
            "collected at an external GLP core facility; analysis executed internally, so "
            "no external-lab quota credit."
        ),
    },
    {
        "dataset_id": "BN-ANN-IV-001",
        "capability_id": "scrna.annotation_evidence",
        "title": "CITE-seq sorted PBMC annotation-distrust gate (pbmc_10k discovery, pbmc_5k holdout)",
        "source_uri": "https://cf.10xgenomics.com pbmc_10k_protein_v3 / pbmc_5k_protein_v3",
        "accession": "",
        "disease": "healthy_donor_control",
        "tissue": "PBMC_blood",
        "technology": "CITE-seq_10x_protein_v3",
        "author_associated": False,
        "donor_aware": False,
        "outcome": "endpoints_met_inconclusive",
        "preregistration_path": STUDIES["BN-ANN-IV-001"][0],
        "report_path": STUDIES["BN-ANN-IV-001"][1],
        "status": "VERIFIED",
        "notes": (
            "All endpoints passed but maximum_maturity FRAGILE (independent_ground_truth "
            "false): counts as an executed independent dataset, not as blinding or truth evidence."
        ),
    },
    {
        "dataset_id": "BN-ANN-IV-003",
        "capability_id": "scrna.annotation_evidence",
        "title": "Azimuth PBMC external-reference mapping successor (raw-count locked, non-blinded)",
        "source_uri": "https://azimuth.hubmapconsortium.org PBMC reference",
        "accession": "",
        "disease": "healthy_donor_control",
        "tissue": "PBMC_blood",
        "technology": "azimuth_reference_mapping_10x",
        "author_associated": False,
        "donor_aware": False,
        "outcome": "positive_candidate",
        "preregistration_path": STUDIES["BN-ANN-IV-003"][0],
        "report_path": STUDIES["BN-ANN-IV-003"][1],
        "status": "VERIFIED",
        "notes": (
            "CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED: met all locked endpoints but is "
            "explicitly non-blinded to label distributions; counts as an executed independent "
            "dataset only."
        ),
    },
    {
        "dataset_id": "BN-SP-IV-001",
        "capability_id": "spatial.inference_validity",
        "title": "Xenium V1 human kidney tiny — real-instrument technical acceptance",
        "source_uri": "https://www.10xgenomics.com Xenium_V1_Protein_Human_Kidney_tiny_outs",
        "accession": "",
        "disease": "non_diseased_reference",
        "tissue": "kidney",
        "technology": "xenium_in_situ",
        "author_associated": False,
        "donor_aware": False,
        "outcome": "technical_acceptance_pass",
        "truth_provenance": {
            "kind": "none",
            "provider": "not_applicable",
            "independent_of_authors": False,
            "blinded_to_system_outputs": False,
            "artifact": "",
            "artifact_sha256": "",
        },
        "preregistration_path": STUDIES["BN-SP-IV-001"][0],
        "report_path": STUDIES["BN-SP-IV-001"][1],
        "status": "VERIFIED",
        "notes": (
            "REAL_INSTRUMENT_TECHNICAL_ACCEPTANCE on a tiny instrument sample; "
            "public_reference_dataset false and NO independent pathology/segmentation truth "
            "yet, so it does not count toward the spatial independent-dataset quota."
        ),
    },
]

for dataset in DATASETS:
    pre = dataset["preregistration_path"]
    rep = dataset["report_path"]
    dataset["preregistration_sha256"] = sha(pre)
    dataset["report_sha256"] = sha(rep)

identities = subprocess.run(
    ["git", "log", "--format=%an|%ae"], capture_output=True, text=True, check=True
).stdout.split()
roster: dict = {}
for line in identities:
    name, email = line.split("|", 1)
    entry = roster.setdefault(name, {"name": name, "identifiers": []})
    if email not in entry["identifiers"]:
        entry["identifiers"].append(email)

REGISTRY = {
    "schema_version": "bionexus.ivn.registry.v1",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "requirements": {},
    "author_roster": list(roster.values()),
    "datasets": DATASETS,
    "lab_studies": [],
    "reviews": [],
    "calibration_freezes": [],
    "_honesty": {
        "external_labs": (
            "No verified external-lab studies exist. Registered frameworks and reviewer "
            "slots do not count as completed evidence (OPEN_QUESTIONS: cross-host and "
            "independent review are incomplete)."
        ),
        "reviews": (
            "No verified non-author reviews exist. The withdrawn BN-PB-IV-004/005 "
            "biostatistician attestations were invalidated by the Phase-1 Trust Reset and "
            "are not re-registered here."
        ),
        "calibration": (
            "Zero APPROVED empirical calibration profiles are packaged, therefore zero "
            "profiles are frozen on held-out contexts."
        ),
        "adoption": (
            "External adoption and governance remain unestablished; no schema or local "
            "test is treated as adoption or endorsement."
        ),
    },
}

out = pathlib.Path("validation/ivn/REGISTRY.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(REGISTRY, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", out, "| roster entries:", len(roster), "| datasets:", len(DATASETS))
