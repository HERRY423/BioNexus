"""Optional gold-standard backend detection.

Skills must call these probes instead of pretending a missing library is
running. Missing backends should refuse or emit a honestly named heuristic.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class BackendStatus:
    name: str
    available: bool
    import_name: str
    extra: Optional[str]
    note: str


# name -> (import_name, extras extra, note)
_OPTIONAL: Dict[str, tuple] = {
    "abnumber": ("abnumber", "structure", "IMGT/Chothia numbering via abnumber/ANARCI"),
    "esm": ("transformers", "plm", "ESM-2 masked LM via Hugging Face transformers"),
    "fair_esm": ("esm", "plm", "Official fair-esm package"),
    "lifelines": ("lifelines", "survival", "Kaplan-Meier and Cox PH"),
    "squidpy": ("squidpy", "spatial", "Spatial statistics and graphs"),
    "spatialdata": ("spatialdata", "spatial", "SpatialData I/O"),
    "biotite": ("biotite", "structure", "Structure I/O and geometry"),
    "viennarna": ("RNA", "biologics", "ViennaRNA RNAfold MFE"),
    "scanpy": ("scanpy", "goldchain", "scverse Scanpy"),
    "anndata": ("anndata", "goldchain", "AnnData"),
    "scvi": ("scvi", "scverse", "scvi-tools"),
    "harmonypy": ("harmonypy", "goldchain", "Harmony batch integration on PCA"),
    "leidenalg": ("leidenalg", "goldchain", "Leiden clustering via python-igraph"),
    "pydeseq2": ("pydeseq2", "deseq", "PyDESeq2 Wald tests on pseudobulk counts"),
    "sklearn": ("sklearn", None, "scikit-learn"),
    "allotropy": ("allotropy", "allotrope", "Allotrope ASM converter"),
}

_BINARIES = {
    "vina": "AutoDock Vina binary",
    "fpocket": "fpocket cavity detector",
    "anarci": "ANARCI antibody numbering",
    "nextflow": "Nextflow workflow runtime",
}


class BackendUnavailable(RuntimeError):
    """Raised when a required gold-standard backend is not installed."""


def is_module_available(import_name: str) -> bool:
    return importlib.util.find_spec(import_name) is not None


def _esm_gate_open() -> bool:
    return os.environ.get("BIONEXUS_ALLOW_ESM", "").strip() in {"1", "true", "TRUE"}


def is_available(name: str) -> bool:
    if name in {"esm", "fair_esm"}:
        if not _esm_gate_open():
            return False
        if name == "fair_esm":
            return is_module_available("esm")
        return is_module_available("transformers") or is_module_available("esm")
    if name in _BINARIES:
        return shutil.which(name) is not None
    spec = _OPTIONAL.get(name)
    if spec is None:
        return is_module_available(name)
    return is_module_available(spec[0])


def which_binary(name: str) -> Optional[str]:
    return shutil.which(name)


def probe(name: str) -> BackendStatus:
    if name in {"esm", "fair_esm"}:
        gated = _esm_gate_open()
        import_name = "esm" if name == "fair_esm" else "transformers"
        loaded = gated and is_available(name)
        note = (
            "ESM weights gated by BIONEXUS_ALLOW_ESM=1; not treated as available until then."
            if not gated
            else "ESM env gate is on; transformers/fair-esm may still fail to download weights."
        )
        return BackendStatus(name, loaded, import_name, "plm", note)
    if name in _BINARIES:
        path = shutil.which(name)
        return BackendStatus(
            name=name,
            available=path is not None,
            import_name=name,
            extra=None,
            note=f"{_BINARIES[name]}" + (f" ({path})" if path else " (not on PATH)"),
        )
    spec = _OPTIONAL.get(name)
    if spec is None:
        available = is_module_available(name)
        return BackendStatus(name, available, name, None, "undeclared probe")
    import_name, extra, note = spec
    return BackendStatus(name, is_module_available(import_name), import_name, extra, note)


def probe_all() -> Dict[str, BackendStatus]:
    names = list(_OPTIONAL.keys()) + list(_BINARIES.keys())
    return {name: probe(name) for name in names}


def require(name: str, *, for_method: str) -> None:
    status = probe(name)
    if not status.available:
        extra = f" Install extra: pip install 'bio-research[{status.extra}]'." if status.extra else ""
        raise BackendUnavailable(
            f"{for_method} requires backend '{name}' ({status.note}).{extra} "
            "Refusing to silently substitute a heuristic under this name."
        )
