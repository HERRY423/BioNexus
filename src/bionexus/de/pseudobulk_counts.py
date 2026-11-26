"""Donor-by-condition count summaries for a single cell population."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PseudobulkLibraries:
    cell_type: str | None
    levels: tuple[str, ...]
    counts: np.ndarray
    condition: np.ndarray
    donors: list[str]
    cells: list[int]
    zero_libraries: list[dict[str, str]]

    @property
    def donors_by_condition(self) -> dict[str, int]:
        return {level: int(np.count_nonzero(self.condition == level)) for level in self.levels}

    def power_inputs(self, min_mean: float = 10.0) -> dict[str, Any]:
        """Summarize depth and within-condition NB moments on a common library scale."""
        n_by_group = self.donors_by_condition
        result: dict[str, Any] = {"donors_by_condition": n_by_group, "zero_libraries": self.zero_libraries}
        if not self.cells:
            return result
        lib = self.counts.sum(axis=1)
        size_factors = lib / np.exp(np.mean(np.log(lib)))
        norm = self.counts / size_factors[:, None]
        means = norm.mean(axis=0)
        cells = min(self.cells)
        result.update(cells_per_sample=cells, mean_count_per_cell=float(np.median(means[means > 0]) / cells))
        if min(n_by_group.values()) < 2:
            return result
        moments = []
        for level in self.levels:
            group = norm[self.condition == level]
            m = group.mean(axis=0)
            keep = m >= min_mean
            variance = group[:, keep].var(axis=0, ddof=1)
            moments.append((variance - m[keep]) / m[keep]**2)
        terms = np.concatenate(moments)
        if terms.size and np.isfinite(terms).all():
            result["dispersion"] = max(0., float(terms.mean()))
        return result


def collect_libraries(matrix: Any, obs: pd.DataFrame, *, d_col: str, c_col: str, ct_col: str | None,
                      cell_type: str | None, levels: tuple[str, ...], min_cells: int) -> PseudobulkLibraries:
    """Sum raw counts by eligible donor and condition, keeping dense storage at donor resolution."""
    if len(obs) != matrix.shape[0]:
        raise ValueError("细胞元数据与计数矩阵行数不一致。")
    selected = obs[c_col].astype("string").isin(levels)
    if cell_type is not None:
        if ct_col is None or ct_col not in obs:
            raise ValueError("目标细胞类型缺少观测标签。")
        selected &= obs[ct_col].astype("string").eq(cell_type)
    positions = np.flatnonzero(selected.fillna(False).to_numpy(dtype=bool))
    design = obs.iloc[positions][[c_col, d_col]].astype("string")
    if design[d_col].isna().any() or design[d_col].str.strip().eq("").any():
        raise ValueError("目标细胞缺少供体标识。")
    libraries, conditions, donors, cells, zero = [], [], [], [], []
    for (condition, donor), offsets in design.groupby([c_col, d_col], observed=True, sort=False).indices.items():
        if len(offsets) < min_cells:
            continue
        counts = np.asarray(matrix[positions[offsets]].sum(axis=0, dtype=np.float64)).reshape(-1)
        total = counts.sum()
        if not np.isfinite(total):
            raise ValueError("供体计数总和超出数值范围。")
        if total == 0:
            zero.append({"condition": str(condition), "donor": str(donor)})
        else:
            libraries.append(counts)
            conditions.append(str(condition))
            donors.append(str(donor))
            cells.append(len(offsets))
    matrix_pb = np.vstack(libraries) if libraries else np.empty((0, matrix.shape[1]))
    return PseudobulkLibraries(cell_type, levels, matrix_pb, np.asarray(conditions, dtype=str), donors, cells, zero)
