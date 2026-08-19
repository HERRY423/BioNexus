"""
Optional gold-standard backend detection and lifecycle management for BioNexus.

Provides deterministic health probes and state taxonomy:
- installed: backend present and version-compatible
- missing: backend not installed in environment
- partial: partial stack available (e.g. anndata without squidpy)
- incompatible_version: installed version below required minimum
- missing_model_weights: ML/PLM model weights unavailable or gated
- missing_external_binary: external CLI tool not found on PATH

Skills must call these probes instead of pretending a missing library is
running. Missing backends should cleanly refuse or emit an honestly named heuristic.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class BackendState(str, Enum):
    """Lifecycle and availability state of an optional backend."""

    INSTALLED = "installed"
    MISSING = "missing"
    PARTIAL = "partial"
    INCOMPATIBLE_VERSION = "incompatible_version"
    MISSING_WEIGHTS = "missing_model_weights"
    MISSING_BINARY = "missing_external_binary"


@dataclass(frozen=True)
class BackendStatus:
    """Detailed health status report for an optional backend."""

    name: str
    available: bool
    import_name: str
    extra: Optional[str]
    note: str
    state: BackendState = BackendState.MISSING
    version: Optional[str] = None
    min_version: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


# Package name -> (import_name, extras_group, min_version, description)
_OPTIONAL: Dict[str, tuple] = {
    "abnumber": ("abnumber", "structure", "0.3.0", "IMGT/Chothia numbering via abnumber/ANARCI"),
    "esm": ("transformers", "plm", "4.36.0", "ESM-2 masked LM via Hugging Face transformers"),
    "fair_esm": ("esm", "plm", "2.0.0", "Official fair-esm package"),
    "lifelines": ("lifelines", "survival", "0.27.0", "Kaplan-Meier and Cox PH"),
    "squidpy": ("squidpy", "spatial", "1.3.0", "Spatial statistics and graphs"),
    "spatialdata": ("spatialdata", "spatial", "0.2.0", "SpatialData I/O"),
    "biotite": ("biotite", "structure", "0.39.0", "Structure I/O and geometry"),
    "viennarna": ("RNA", "biologics", "2.6.0", "ViennaRNA RNAfold MFE"),
    "scanpy": ("scanpy", "goldchain", "1.10.0", "scverse Scanpy"),
    "anndata": ("anndata", "goldchain", "0.9.0", "AnnData"),
    "scvi": ("scvi", "scverse", "1.0.0", "scvi-tools deep generative models"),
    "torch": ("torch", "scverse", "2.0.0", "PyTorch deep learning"),
    "harmonypy": ("harmonypy", "goldchain", "0.0.9", "Harmony batch integration on PCA"),
    "leidenalg": ("leidenalg", "goldchain", "0.10.0", "Leiden clustering via python-igraph"),
    "pydeseq2": ("pydeseq2", "deseq", "0.4.0", "PyDESeq2 Wald tests on pseudobulk counts"),
    "sklearn": ("sklearn", None, "1.2.0", "scikit-learn"),
    "allotropy": ("allotropy", "allotrope", "0.1.30", "Allotrope ASM converter"),
}

_BINARIES: Dict[str, str] = {
    "vina": "AutoDock Vina binary",
    "fpocket": "fpocket cavity detector",
    "anarci": "ANARCI antibody numbering",
    "nextflow": "Nextflow workflow runtime",
    "samtools": "SAMtools HTSlib binary",
    "bedtools": "bedtools genomic interval binary",
    "clustalo": "Clustal Omega sequence alignment binary",
    "pymol": "PyMOL molecular visualization binary",
}


class BackendUnavailable(RuntimeError):
    """Raised when a required gold-standard backend is not installed, incompatible, or missing."""


class IncompatibleVersion(BackendUnavailable):
    """Raised when an installed backend does not meet minimum version requirements."""


def is_module_available(import_name: str) -> bool:
    """Check if a python module spec can be located."""
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def get_package_version(import_name: str) -> Optional[str]:
    """Retrieve installed version of a package via importlib or module attribute."""
    # 1. Try importlib.metadata
    for candidate in [import_name, import_name.replace("_", "-")]:
        try:
            return importlib.metadata.version(candidate)
        except Exception:
            pass

    # 2. Try module.__version__
    try:
        mod = importlib.import_module(import_name)
        return getattr(mod, "__version__", None)
    except Exception:
        return None


def is_version_compatible(current_version: Optional[str], min_version: Optional[str]) -> bool:
    """Compare semver or numeric version strings."""
    if not min_version:
        return True
    if not current_version:
        return False

    def parse_parts(v_str: str) -> Tuple[int, ...]:
        clean = v_str.split("+")[0].split("rc")[0].split("a")[0].split("b")[0].strip()
        parts = []
        for p in clean.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts)

    try:
        curr_parts = parse_parts(current_version)
        min_parts = parse_parts(min_version)
        # Pad shorter tuple with zeros
        length = max(len(curr_parts), len(min_parts))
        curr_padded = curr_parts + (0,) * (length - len(curr_parts))
        min_padded = min_parts + (0,) * (length - len(min_parts))
        return curr_padded >= min_padded
    except Exception:
        return True


def _esm_gate_open() -> bool:
    """Check if ESM PLM model weights execution is permitted by environment gate."""
    return os.environ.get("BIONEXUS_ALLOW_ESM", "").strip() in {"1", "true", "TRUE"}


def is_available(name: str) -> bool:
    """Quick boolean check if a named backend or binary is ready for execution."""
    status = probe(name)
    return status.available


def which_binary(name: str) -> Optional[str]:
    """Locate binary executable on PATH."""
    return shutil.which(name)


def probe_binary(name: str) -> Tuple[bool, Optional[str]]:
    """Inspect binary presence on PATH."""
    path = shutil.which(name)
    return path is not None, path


def probe_model_weights(name: str) -> Tuple[bool, str]:
    """Check whether deep learning model weights/gates are available."""
    if name in {"esm", "fair_esm"}:
        if not _esm_gate_open():
            return False, "ESM weights gated by BIONEXUS_ALLOW_ESM=1; not treated as available until enabled."
        # If gate is on, check if transformers or fair-esm is installed
        has_pkg = is_module_available("transformers") or is_module_available("esm")
        if not has_pkg:
            return False, "ESM gate enabled, but 'transformers' / 'esm' package is missing."
        return True, "ESM env gate is enabled and model package is installed."
    return True, "No model weights required."


def probe(name: str) -> BackendStatus:
    """
    Exhaustively probe a backend across installed, missing, partial,
    incompatible version, missing model weights, and missing external binary states.
    """
    # 1. External Binaries
    if name in _BINARIES:
        path = shutil.which(name)
        available = path is not None
        state = BackendState.INSTALLED if available else BackendState.MISSING_BINARY
        desc = _BINARIES[name]
        note = f"{desc} ({path})" if available else f"{desc} (not found on PATH)"
        return BackendStatus(
            name=name,
            available=available,
            import_name=name,
            extra=None,
            note=note,
            state=state,
            diagnostics={"binary_path": path},
        )

    # 2. ML / PLM Model Backends
    if name in {"esm", "fair_esm"}:
        import_name = "esm" if name == "fair_esm" else "transformers"
        min_ver = "2.0.0" if name == "fair_esm" else "4.36.0"
        pkg_present = is_module_available(import_name)
        weights_ready, weight_note = probe_model_weights(name)

        if not _esm_gate_open():
            state = BackendState.MISSING_WEIGHTS
            available = False
            note = "ESM weights gated by BIONEXUS_ALLOW_ESM=1; not treated as available until then."
        elif not pkg_present:
            state = BackendState.MISSING
            available = False
            note = f"Package '{import_name}' is not installed. Install with 'pip install bionexus-reliability[plm]'."
        elif not weights_ready:
            state = BackendState.MISSING_WEIGHTS
            available = False
            note = weight_note
        else:
            ver = get_package_version(import_name)
            ver_ok = is_version_compatible(ver, min_ver)
            if not ver_ok:
                state = BackendState.INCOMPATIBLE_VERSION
                available = False
                note = f"Installed {import_name} version {ver} is below required {min_ver}."
            else:
                state = BackendState.INSTALLED
                available = True
                note = weight_note

        return BackendStatus(
            name=name,
            available=available,
            import_name=import_name,
            extra="plm",
            note=note,
            state=state,
            version=get_package_version(import_name) if pkg_present else None,
            min_version=min_ver,
            diagnostics={"weights_ready": weights_ready, "esm_gate": _esm_gate_open()},
        )

    # 3. Standard Python Packages
    spec = _OPTIONAL.get(name)
    if spec is None:
        available = is_module_available(name)
        ver = get_package_version(name) if available else None
        state = BackendState.INSTALLED if available else BackendState.MISSING
        return BackendStatus(
            name=name,
            available=available,
            import_name=name,
            extra=None,
            note="Undeclared probe",
            state=state,
            version=ver,
        )

    import_name, extra, min_ver, desc = spec
    pkg_present = is_module_available(import_name)

    if not pkg_present:
        # Check if partial stack exists (e.g. for scvi, check if torch is present)
        is_partial = False
        if name == "scvi" and is_module_available("torch"):
            is_partial = True
        elif name == "squidpy" and is_module_available("anndata"):
            is_partial = True
        elif name == "leidenalg" and is_module_available("igraph"):
            is_partial = True

        state = BackendState.PARTIAL if is_partial else BackendState.MISSING
        note = f"{desc} (missing '{import_name}'). Install with: pip install 'bionexus[{extra}]'."
        return BackendStatus(
            name=name,
            available=False,
            import_name=import_name,
            extra=extra,
            note=note,
            state=state,
            min_version=min_ver,
        )

    # Package is present, check version
    ver = get_package_version(import_name)
    ver_ok = is_version_compatible(ver, min_ver)

    if not ver_ok:
        state = BackendState.INCOMPATIBLE_VERSION
        note = f"{desc} version {ver} is installed, but minimum {min_ver} is required."
        available = False
    else:
        state = BackendState.INSTALLED
        note = f"{desc} ({ver}) is ready."
        available = True

    return BackendStatus(
        name=name,
        available=available,
        import_name=import_name,
        extra=extra,
        note=note,
        state=state,
        version=ver,
        min_version=min_ver,
    )


def probe_all() -> Dict[str, BackendStatus]:
    """Probe all known packages and binaries."""
    names = list(_OPTIONAL.keys()) + list(_BINARIES.keys())
    return {name: probe(name) for name in names}


def require(name: str, *, for_method: str, min_version: Optional[str] = None) -> None:
    """
    Enforce backend availability and version requirements.
    Raises BackendUnavailable or IncompatibleVersion if preconditions fail.
    """
    status = probe(name)
    if not status.available:
        extra_hint = f" Install extra: pip install 'bionexus[{status.extra}]'." if status.extra else ""
        if status.state == BackendState.INCOMPATIBLE_VERSION:
            raise IncompatibleVersion(
                f"{for_method} requires backend '{name}' >= {status.min_version}, "
                f"but version {status.version} was found.{extra_hint}"
            )
        elif status.state == BackendState.MISSING_BINARY:
            raise BackendUnavailable(
                f"{for_method} requires external binary '{name}' ({status.note}). "
                "Ensure it is installed and added to PATH."
            )
        elif status.state == BackendState.MISSING_WEIGHTS:
            raise BackendUnavailable(f"{for_method} requires model weights for '{name}' ({status.note}).")
        else:
            raise BackendUnavailable(
                f"{for_method} requires backend '{name}' ({status.note}).{extra_hint} "
                "Refusing to silently substitute a heuristic under this name."
            )
    if min_version and status.version:
        if not is_version_compatible(status.version, min_version):
            raise IncompatibleVersion(
                f"{for_method} requires backend '{name}' >= {min_version}, but version {status.version} was found."
            )
