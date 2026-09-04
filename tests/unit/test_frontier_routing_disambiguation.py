"""Regression and neighboring controls for explicit statistical intent."""

import pytest

from bionexus.intent_router import extract_scientific_capability, route_scientific_intent


@pytest.mark.parametrize(
    "query",
    [
        "Run Moran's I spatial autocorrelation using my UMAP embedding coordinates as spatial coordinates",
        "Compute Moran’s I for marker genes after Leiden clustering",
        "Calculate Moran I on PCA embedding coordinates",
    ],
)
def test_explicit_spatial_statistic_reaches_coordinate_gate(query):
    decision = route_scientific_intent(
        query, data_metadata={"n_spatial_spots": 200, "coordinate_type": "umap_embedding"}
    )
    assert decision.matched_capability.id == "spatial.morans_svg"
    assert decision.status.value == "ABSTAIN"
    assert "embedding" in " ".join(decision.violations)


@pytest.mark.parametrize(
    "query,capability",
    [
        (
            "Find differentially expressed marker genes between cluster 0 and cluster 1 with 3 replicates per condition",
            "scrna.exploratory_clustering",
        ),
        ("Find marker genes between clusters A versus B", "scrna.exploratory_clustering"),
        ("Run pseudobulk DE between cluster 0 and cluster 1", "scrna.pseudobulk_de"),
        ("Find condition-specific genes between cluster 0 and cluster 1", "scrna.pseudobulk_de"),
        ("Leiden cluster my Visium data and compute Moran's I for marker genes", "spatial.morans_svg"),
        ("Find marker genes using UMAP embedding and Leiden clustering", "scrna.exploratory_clustering"),
    ],
)
def test_contrast_and_statistic_determine_capability(query, capability):
    assert extract_scientific_capability(query).id == capability


def test_spatial_backend_absence_still_refuses(monkeypatch):
    from bionexus.backends import BackendStatus

    monkeypatch.setattr(
        "bionexus.capabilities.probe",
        lambda name: BackendStatus(name=name, available=False, import_name=name, extra="spatial", note="test: absent"),
    )
    decision = route_scientific_intent("Compute Moran's I for marker genes", data_metadata={"n_spatial_spots": 100})
    assert decision.status.value == "ABSTAIN"
