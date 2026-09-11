"""Publication-style plotting helpers for academic figures.

This module provides deterministic wrappers around matplotlib so generated plots
stay visually consistent with the figures4papers house style.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Sequence

import matplotlib.pyplot as plt
import numpy as np


PALETTE: Final[dict[str, str]] = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "red_1": "#F6CFCB",
    "red_2": "#E9A6A1",
    "red_strong": "#B64342",
    "neutral": "#CFCECE",
    "highlight": "#FFD700",
    "teal": "#42949E",
    "violet": "#9A4D8E",
}

DEFAULT_COLORS: Final[list[str]] = [
    PALETTE["blue_main"],
    PALETTE["green_3"],
    PALETTE["red_strong"],
    PALETTE["teal"],
    PALETTE["violet"],
    PALETTE["neutral"],
]

_VECTOR_FORMATS: Final[set[str]] = {"pdf", "svg", "eps"}
_RASTER_FORMATS: Final[set[str]] = {"png", "jpg", "jpeg", "tif", "tiff"}
_SUPPORTED_FORMATS: Final[set[str]] = _VECTOR_FORMATS | _RASTER_FORMATS


@dataclass(frozen=True)
class FigureStyle:
    """Global matplotlib style configuration."""

    font_size: int = 16
    axes_linewidth: float = 2.5
    use_tex: bool = False
    font_family: tuple[str, ...] = ("DejaVu Sans", "Helvetica", "Arial", "sans-serif")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[scientific_figure_pro] {message}")


def _as_1d_array(name: str, values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    _require(arr.ndim == 1, f"'{name}' must be 1D, got shape {arr.shape}")
    _require(arr.size > 0, f"'{name}' cannot be empty")
    return arr


def _as_2d_array(name: str, values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    _require(arr.ndim == 2, f"'{name}' must be 2D, got shape {arr.shape}")
    _require(arr.size > 0, f"'{name}' cannot be empty")
    return arr


def apply_publication_style(style: FigureStyle | None = None) -> None:
    """Apply publication-focused rcParams globally."""

    cfg = style or FigureStyle()
    plt.rcParams.update(
        {
            "text.usetex": cfg.use_tex,
            "font.family": "sans-serif",
            "font.sans-serif": list(cfg.font_family),
            "font.size": cfg.font_size,
            "axes.labelsize": cfg.font_size,
            "axes.titlesize": cfg.font_size + 2,
            "axes.linewidth": cfg.axes_linewidth,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "legend.frameon": False,
            "legend.fontsize": max(8, cfg.font_size - 2),
            "xtick.direction": "out",
            "ytick.direction": "out",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.bbox": "tight",
            "savefig.transparent": False,
        }
    )


def create_subplots(
    nrows: int = 1,
    ncols: int = 1,
    figsize: tuple[float, float] | None = None,
    **kwargs: Any,
) -> tuple[plt.Figure, np.ndarray]:
    """Create figure and return flattened axes array."""

    _require(nrows > 0 and ncols > 0, "nrows and ncols must be positive")
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, **kwargs)
    return fig, np.atleast_1d(np.array(axes, dtype=object)).flatten()


def finalize_figure(
    fig: plt.Figure,
    out_path: str | Path,
    formats: Sequence[str] | None = None,
    dpi: int = 300,
    close: bool = True,
    pad: float = 0.05,
    **kwargs: Any,
) -> list[Path]:
    """Save figure to one or many formats with consistent defaults."""

    path = Path(out_path)
    extensions = list(formats) if formats else []
    if not extensions:
        extensions = [path.suffix.lstrip(".")] if path.suffix else ["pdf", "svg", "eps"]

    base = path.with_suffix("") if path.suffix else path
    base.parent.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for ext in extensions:
        normalized_ext = ext.lower().strip(".")
        _require(normalized_ext in _SUPPORTED_FORMATS, f"unsupported format: {normalized_ext}")

        target = base.with_suffix(f".{normalized_ext}")
        save_opts: dict[str, Any] = {
            "format": normalized_ext,
            "bbox_inches": "tight",
            "pad_inches": pad,
        }
        if normalized_ext in _RASTER_FORMATS:
            save_opts["dpi"] = dpi
        save_opts.update(kwargs)

        fig.savefig(target, **save_opts)
        saved_paths.append(target)

    if close:
        plt.close(fig)
    return saved_paths


def make_trend(
    ax: plt.Axes,
    x: Sequence[float],
    y_series: Sequence[Sequence[float]],
    labels: Sequence[str],
    colors: Sequence[str] | None = None,
    ylabel: str | None = None,
    xlabel: str | None = None,
    show_shadow: bool = True,
) -> None:
    """Draw trend lines with optional uncertainty shadows."""

    x_arr = _as_1d_array("x", x)
    _require(len(y_series) == len(labels), "y_series and labels must have same length")
    color_map = list(colors) if colors else DEFAULT_COLORS

    for idx, y in enumerate(y_series):
        y_arr = _as_1d_array(f"y_series[{idx}]", y)
        _require(len(y_arr) == len(x_arr), f"series {idx} length mismatch with x")

        color = color_map[idx % len(color_map)]
        if show_shadow:
            span = float(np.ptp(y_arr))
            band = 0.03 * (span if span > 0 else 1.0)
            ax.fill_between(x_arr, y_arr - band, y_arr + band, color=color, alpha=0.10, linewidth=0)
        ax.plot(x_arr, y_arr, label=labels[idx], color=color, linewidth=2.5, alpha=0.92)

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.legend()


def make_grouped_bar(
    ax: plt.Axes,
    categories: Sequence[str],
    series: Sequence[Sequence[float]],
    labels: Sequence[str],
    ylabel: str = "Value",
    colors: Sequence[str] | None = None,
    annotate: bool = False,
) -> Any:
    """Draw grouped bars with readable defaults for papers."""

    data = _as_2d_array("series", series)
    n_series, n_categories = data.shape
    _require(len(categories) == n_categories, "categories length must match series width")
    _require(len(labels) == n_series, "labels length must match number of series")

    x = np.arange(n_categories)
    total_width = 0.8
    width = total_width / n_series
    color_map = list(colors) if colors else DEFAULT_COLORS

    last_bars = None
    for idx in range(n_series):
        offset = (idx - (n_series - 1) / 2) * width
        bars = ax.bar(
            x + offset,
            data[idx],
            width,
            label=labels[idx],
            color=color_map[idx % len(color_map)],
            edgecolor="black",
            linewidth=1.2,
        )
        last_bars = bars
        if annotate:
            annotate_bars(ax, bars)

    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.legend()
    return last_bars


def annotate_bars(
    ax: plt.Axes,
    bars: Any,
    fmt: str = "{:.2f}",
    fontsize: int = 10,
    padding: float = 3,
) -> None:
    """Annotate numeric values above each bar."""

    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt.format(height),
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, padding),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=fontsize,
        )


def make_heatmap(
    ax: plt.Axes,
    matrix: Sequence[Sequence[float]],
    x_labels: Sequence[str] | None = None,
    y_labels: Sequence[str] | None = None,
    cmap: str = "magma",
    cbar_label: str | None = None,
    annotate: bool = False,
) -> Any:
    """Draw heatmap with optional labels and value annotations."""

    data = _as_2d_array("matrix", matrix)
    image = ax.imshow(data, cmap=cmap, aspect="auto", interpolation="nearest")

    if x_labels:
        ax.set_xticks(np.arange(len(x_labels)))
        ax.set_xticklabels(x_labels, rotation=45, ha="right")
    if y_labels:
        ax.set_yticks(np.arange(len(y_labels)))
        ax.set_yticklabels(y_labels)

    if cbar_label:
        cbar = ax.figure.colorbar(image, ax=ax)
        cbar.set_label(cbar_label)

    if annotate:
        threshold = float((np.max(data) + np.min(data)) / 2)
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                val = float(data[i, j])
                text_color = "white" if val < threshold else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", color=text_color, fontsize=9)

    return image


def make_scatter(
    ax: plt.Axes,
    x: Sequence[float],
    y: Sequence[float],
    label: str | None = None,
    color: str | None = None,
    size: float = 50,
    alpha: float = 0.7,
) -> None:
    """Draw publication-style scatter plot."""

    x_arr = _as_1d_array("x", x)
    y_arr = _as_1d_array("y", y)
    _require(len(x_arr) == len(y_arr), "x and y must have same length")

    ax.scatter(
        x_arr,
        y_arr,
        s=size,
        label=label,
        color=color or PALETTE["blue_main"],
        alpha=alpha,
        edgecolors="white",
        linewidth=0.5,
    )
    if label:
        ax.legend()


def make_sphere_illustration(
    ax: plt.Axes,
    light_dir: tuple[float, float, float] = (-0.5, 0.5, 0.8),
    resolution: int = 128,
    alpha: float = 0.75,
) -> None:
    """Draw 2D shaded sphere for conceptual panels."""

    xs = np.linspace(-1.0, 1.0, resolution)
    ys = np.linspace(-1.0, 1.0, resolution)
    x, y = np.meshgrid(xs, ys)
    radius2 = x**2 + y**2
    mask = radius2 <= 1.0

    z = np.zeros_like(x)
    z[mask] = np.sqrt(1.0 - radius2[mask])

    norm = np.sqrt(x**2 + y**2 + z**2) + 1e-12
    nx, ny, nz = x / norm, y / norm, z / norm

    light = np.asarray(light_dir, dtype=np.float64)
    light = light / (np.linalg.norm(light) + 1e-12)
    intensity = np.maximum(0.0, nx * light[0] + ny * light[1] + nz * light[2])

    shade = np.ones_like(x) * 0.2
    shade[mask] = np.clip(0.25 + 0.85 * intensity[mask], 0.0, 1.0)

    ax.imshow(shade, cmap="gray", origin="lower", extent=[-1, 1, -1, 1], vmin=0, vmax=1, alpha=alpha)
    ax.set_axis_off()


def demo() -> None:
    """Generate a small demo figure to verify helper behavior."""

    rng = np.random.default_rng(7)
    apply_publication_style(FigureStyle(font_size=14, axes_linewidth=2.2))
    fig, axes = create_subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    x = np.arange(1, 101)
    y1 = 0.45 + 0.45 * (1 - np.exp(-x / 28.0)) + rng.normal(0, 0.006, len(x))
    y2 = 0.43 + 0.40 * (1 - np.exp(-x / 35.0)) + rng.normal(0, 0.007, len(x))
    make_trend(axes[0], x, [y1, y2], ["Model A", "Model B"], ylabel="Score", xlabel="Epoch")
    axes[0].set_title("A. Trend")

    make_grouped_bar(
        axes[1],
        categories=["Speed", "Accuracy", "Stability"],
        series=[[85, 90, 86], [82, 88, 91]],
        labels=["Method A", "Method B"],
        ylabel="Metric",
        annotate=True,
    )
    axes[1].set_title("B. Grouped Bars")

    mat = rng.normal(size=(8, 8))
    mat = np.corrcoef(mat)
    make_heatmap(axes[2], mat, cmap="magma", cbar_label="Correlation")
    axes[2].set_title("C. Heatmap")

    make_sphere_illustration(axes[3])
    axes[3].set_title("D. Sphere")

    finalize_figure(fig, Path(__file__).with_name("scientific_figure_demo"), formats=["png", "pdf"], dpi=300)


if __name__ == "__main__":
    demo()
