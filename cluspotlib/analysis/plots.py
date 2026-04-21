"""
ClusterBench Plots Module
Publication-quality (Nature/ACS style) — 300 dpi

Style guidelines:
  - figsize (9, 8), spine linewidth 3, ticks in-direction on all four sides
  - marker edgecolors="black", linewidths=1.5, s=100
  - parity line: black dashed ("k--")
  - large fonts: xlabel/ylabel 40, tick 25, MAE text 30

Plot types:
  plot_parity_elem   : global / tm12  — continuous colorbar based on atomic number (Z)
  plot_parity_size   : per_tm         — atom count represented with inferno colorbar
  plot_parity        : backward-compatibility wrapper
  plot_periodic_heatmap
  plot_total_bar
  plot_pareto
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch
from pathlib import Path


def _make_heatmap_cmap(higher_is_better: bool):
    """
    Truncated plasma colormap: purple (low) → orange (high).
    - higher_is_better=True : high values are orange (bright) → good
    - higher_is_better=False: low values are orange (bright) → good (reversed)
    """
    base = plt.colormaps.get_cmap("plasma")
    colors = base(np.linspace(0.15, 0.80, 256))
    cmap = LinearSegmentedColormap.from_list("plasma_trunc", colors)
    return cmap if higher_is_better else cmap.reversed()


plt.rcParams.update({
    "font.family":        "sans-serif",
    "font.sans-serif":    ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.linewidth":     3.0,
    "axes.spines.top":    True,
    "axes.spines.right":  True,
    "axes.spines.left":   True,
    "axes.spines.bottom": True,
    "xtick.direction":    "in",
    "ytick.direction":    "in",
    "xtick.top":          True,
    "ytick.right":        True,
    "xtick.major.size":   8.0,
    "ytick.major.size":   8.0,
    "xtick.minor.size":   4.5,
    "ytick.minor.size":   4.5,
    "xtick.major.width":  2.0,
    "ytick.major.width":  2.0,
    "xtick.minor.width":  1.2,
    "ytick.minor.width":  1.2,
    "legend.framealpha":  0.85,
    "legend.edgecolor":   "black",
    "legend.fontsize":    18,
    "axes.grid":          False,
    "axes.axisbelow":     True,
    "figure.facecolor":   "white",
    "axes.facecolor":     "white",
    "figure.dpi":         150,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
})

_FS_LABEL   = 40
_FS_TICK    = 25
_FS_MAE     = 28
_FS_LEGEND  = 20
_FS_LTITLE  = 22
_MARK_SIZE  = 100
_LINEWIDTHS = 1.5
_FIGSIZE    = (9, 8)


_ELEM_ORDER = [
    "H",  "He", "Li", "Be", "B",  "C",  "N",  "O",  "F",  "Ne",
    "Na", "Mg", "Al", "Si", "P",  "S",  "Cl", "Ar", "K",  "Ca",
    "Sc", "Ti", "V",  "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y",  "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I",  "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W",  "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U",  "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
]

try:
    from ase.data.colors import jmol_colors as _jmol_colors
    from ase.data import atomic_numbers as _atomic_numbers
    _USE_JMOL = True
except ImportError:
    _USE_JMOL = False

def _elem_color(elem: str):
    if "-" in str(elem):
        parts = str(elem).split("-")
        colors = [_elem_color(p) for p in parts]
        return tuple(float(np.mean([c[i] for c in colors])) for i in range(3))
    if _USE_JMOL:
        z = _atomic_numbers.get(str(elem), 0)
        if 0 < z < len(_jmol_colors):
            return tuple(_jmol_colors[z])
    return (0.45, 0.45, 0.45)


def _ensure_parent(path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _iqr_mask(arr: np.ndarray, factor: float = 5.0) -> np.ndarray:
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    return (arr >= q1 - factor * iqr) & (arr <= q3 + factor * iqr)


def _nice_limits(x: np.ndarray, y: np.ndarray, pad_frac: float = 0.05):
    m = np.isfinite(x) & np.isfinite(y)
    if not m.any():
        return -1.0, 1.0
    lo = float(min(x[m].min(), y[m].min()))
    hi = float(max(x[m].max(), y[m].max()))
    pad = pad_frac * (hi - lo) if hi > lo else 0.5
    return lo - pad, hi + pad


def _calc_metrics(x: np.ndarray, y: np.ndarray):
    mae = float(np.mean(np.abs(x - y)))
    rmse = float(np.sqrt(np.mean((x - y) ** 2)))
    ss_res = float(np.sum((x - y) ** 2))
    ss_tot = float(np.sum((x - float(np.mean(x))) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    return mae, rmse, r2


def _add_mae_box(ax, mae: float, rmse: float, r2: float, n: int = None, unit: str = "eV"):
    if n is None:
        txt = f"MAE: {mae:.3f} {unit}\nRMSE: {rmse:.3f} {unit}\n$R^2$: {r2:.3f}"
    else:
        txt = f"MAE: {mae:.3f} {unit}\nRMSE: {rmse:.3f} {unit}\n$R^2$: {r2:.3f}\n$n$: {int(n)}"

    ax.text(
        0.04, 0.96, txt,
        transform=ax.transAxes,
        fontsize=_FS_MAE,
        verticalalignment="top",
        bbox=dict(boxstyle="round", alpha=0.5, facecolor="white",
                  edgecolor="black", pad=0.5),
        zorder=100002,
    )


def _setup_parity_ax(ax, lo: float, hi: float):
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=2.0, zorder=100000)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")


def _apply_tick_style(ax):
    ax.tick_params(axis="both", which="major", labelsize=_FS_TICK)


_ELEM_Z: dict = {e: i + 1 for i, e in enumerate(_ELEM_ORDER)}


def _elem_z(elem: str) -> float:
    return float(_ELEM_Z.get(str(elem), 0))


def plot_parity_elem(
    dft_vals, mlip_vals, elements,
    title: str, xlabel: str, ylabel: str, save_path,
    dpi: int = 300,
    iqr_filter: bool = False,
    mlip_name: str = "",
    unit: str = "eV/atom",
):
    x = np.asarray(dft_vals, dtype=float)
    y = np.asarray(mlip_vals, dtype=float)
    e = np.asarray(elements, dtype=str)

    m = np.isfinite(x) & np.isfinite(y)
    x, y, e = x[m], y[m], e[m]
    if x.size == 0:
        return

    if iqr_filter:
        m2 = _iqr_mask(x) & _iqr_mask(y)
        x, y, e = x[m2], y[m2], e[m2]

    mae, rmse, r2 = _calc_metrics(x, y)
    lo, hi = _nice_limits(x, y)

    uniq_elems = sorted(set(e.tolist()), key=lambda el: _elem_z(el))
    n_leg = len(uniq_elems)
    ncol = max(1, min(3, (n_leg + 11) // 12))

    fig, ax = plt.subplots(figsize=_FIGSIZE)

    for el in uniq_elems:
        mask = (e == el)
        ax.scatter(
            x[mask], y[mask],
            color=_elem_color(el),
            label=el,
            s=_MARK_SIZE, alpha=0.85,
            edgecolors="black",
            linewidths=_LINEWIDTHS,
            rasterized=True,
        )

    leg = ax.legend(
        fontsize=10,
        ncol=ncol,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0,
        framealpha=0.9,
        handlelength=1.2,
        markerscale=1.1,
    )

    _setup_parity_ax(ax, lo, hi)
    ax.set_xlabel(xlabel, fontsize=_FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=_FS_LABEL)
    if title:
        ax.set_title(title, fontsize=20, fontweight="bold", pad=8)
    _apply_tick_style(ax)
    _add_mae_box(ax, mae, rmse, r2, n=x.size, unit=unit)

    fig.savefig(_ensure_parent(save_path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_parity_size(
    dft_vals, mlip_vals, sizes,
    title: str, xlabel: str, ylabel: str, save_path,
    dpi: int = 300,
    elem: str = None,
    iqr_filter: bool = False,
    mlip_name: str = "",
    unit: str = "eV/atom",
):
    x = np.asarray(dft_vals, dtype=float)
    y = np.asarray(mlip_vals, dtype=float)

    sz_raw = np.asarray(sizes, dtype=str)
    sz = np.array([float(s) if s.lstrip("-").replace(".", "").isdigit() else np.nan
                   for s in sz_raw])

    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(sz)
    x, y, sz = x[m], y[m], sz[m]
    if x.size == 0:
        return

    if iqr_filter:
        m2 = _iqr_mask(x) & _iqr_mask(y)
        x, y, sz = x[m2], y[m2], sz[m2]

    mae, rmse, r2 = _calc_metrics(x, y)
    lo, hi = _nice_limits(x, y)

    sz_min, sz_max = float(sz.min()), float(sz.max())
    norm = mcolors.Normalize(vmin=sz_min, vmax=sz_max)
    cmap = plt.get_cmap("inferno")

    fig, ax = plt.subplots(figsize=_FIGSIZE)

    sc = ax.scatter(
        x, y,
        c=sz,
        cmap=cmap,
        norm=norm,
        s=_MARK_SIZE, alpha=0.85,
        edgecolors="black",
        linewidths=_LINEWIDTHS,
        rasterized=True,
    )

    cbar_label = "Number of atoms" if elem is None else f"Number of atoms ({elem})"
    cbar = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label, fontsize=_FS_LABEL * 0.55)
    cbar.ax.tick_params(labelsize=_FS_TICK * 0.85)

    _setup_parity_ax(ax, lo, hi)
    ax.set_xlabel(xlabel, fontsize=_FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=_FS_LABEL)
    if title:
        ax.set_title(title, fontsize=20, fontweight="bold", pad=8)
    _apply_tick_style(ax)
    _add_mae_box(ax, mae, rmse, r2, n=x.size, unit=unit)

    fig.savefig(_ensure_parent(save_path), dpi=dpi)
    plt.close(fig)


def plot_parity(
    dft_vals, mlip_vals,
    title: str, xlabel: str, ylabel: str, save_path,
    dpi: int = 300,
    elements=None,
    sizes=None,
    elem: str = None,
    mlip_name: str = "",
    unit: str = "eV/atom",
):
    if elements is not None:
        plot_parity_elem(
            dft_vals, mlip_vals, elements,
            title, xlabel, ylabel, save_path,
            dpi=dpi, mlip_name=mlip_name, unit=unit
        )
        return

    if sizes is not None:
        plot_parity_size(
            dft_vals, mlip_vals, sizes,
            title, xlabel, ylabel, save_path,
            dpi=dpi, elem=elem, mlip_name=mlip_name, unit=unit
        )
        return

    x = np.asarray(dft_vals, dtype=float)
    y = np.asarray(mlip_vals, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if x.size == 0:
        return

    mae, rmse, r2 = _calc_metrics(x, y)
    lo, hi = _nice_limits(x, y)

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.scatter(
        x, y,
        s=_MARK_SIZE, alpha=0.85,
        edgecolors="black",
        linewidths=_LINEWIDTHS,
        rasterized=True
    )
    _setup_parity_ax(ax, lo, hi)
    ax.set_xlabel(xlabel, fontsize=_FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=_FS_LABEL)
    if title:
        ax.set_title(title, fontsize=20, fontweight="bold", pad=8)
    _apply_tick_style(ax)
    _add_mae_box(ax, mae, rmse, r2, n=x.size, unit=unit)

    fig.savefig(_ensure_parent(save_path), dpi=dpi)
    plt.close(fig)


PERIODIC_TABLE_POS = {
    "H":  (1, 1),  "He": (1, 18),
    "Li": (2, 1),  "Be": (2, 2),
    "B":  (2, 13), "C":  (2, 14), "N":  (2, 15), "O":  (2, 16), "F":  (2, 17), "Ne": (2, 18),
    "Na": (3, 1),  "Mg": (3, 2),
    "Al": (3, 13), "Si": (3, 14), "P":  (3, 15), "S":  (3, 16), "Cl": (3, 17), "Ar": (3, 18),
    "K":  (4, 1),  "Ca": (4, 2),
    "Sc": (4, 3),  "Ti": (4, 4),  "V":  (4, 5),  "Cr": (4, 6),  "Mn": (4, 7),
    "Fe": (4, 8),  "Co": (4, 9),  "Ni": (4, 10), "Cu": (4, 11), "Zn": (4, 12),
    "Ga": (4, 13), "Ge": (4, 14), "As": (4, 15), "Se": (4, 16), "Br": (4, 17), "Kr": (4, 18),
    "Rb": (5, 1),  "Sr": (5, 2),
    "Y":  (5, 3),  "Zr": (5, 4),  "Nb": (5, 5),  "Mo": (5, 6),  "Tc": (5, 7),
    "Ru": (5, 8),  "Rh": (5, 9),  "Pd": (5, 10), "Ag": (5, 11), "Cd": (5, 12),
    "In": (5, 13), "Sn": (5, 14), "Sb": (5, 15), "Te": (5, 16), "I":  (5, 17), "Xe": (5, 18),
    "Cs": (6, 1),  "Ba": (6, 2),
    "Hf": (6, 4),  "Ta": (6, 5),  "W":  (6, 6),  "Re": (6, 7),
    "Os": (6, 8),  "Ir": (6, 9),  "Pt": (6, 10), "Au": (6, 11), "Hg": (6, 12),
    "Tl": (6, 13), "Pb": (6, 14), "Bi": (6, 15), "Po": (6, 16), "At": (6, 17), "Rn": (6, 18),
    "La": (8, 3),  "Ce": (8, 4),  "Pr": (8, 5),  "Nd": (8, 6),  "Pm": (8, 7),
    "Sm": (8, 8),  "Eu": (8, 9),  "Gd": (8, 10), "Tb": (8, 11), "Dy": (8, 12),
    "Ho": (8, 13), "Er": (8, 14), "Tm": (8, 15), "Yb": (8, 16), "Lu": (8, 17),
}


def plot_periodic_heatmap(
    elem_metric_dict: dict,
    title: str,
    save_path,
    higher_is_better: bool = True,
    dpi: int = 300,
    vmin=None, vmax=None,
    count_dict=None,
):
    def _luminance(rgba):
        r, g, b, _ = rgba
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    vals = []
    for v in elem_metric_dict.values():
        try:
            fv = float(v)
            if np.isfinite(fv):
                vals.append(fv)
        except Exception:
            pass
    if not vals:
        return

    vmin = float(min(vals)) if vmin is None else float(vmin)
    vmax = float(max(vals)) if vmax is None else float(vmax)
    if vmax <= vmin:
        vmax = vmin + 1e-12

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_obj = _make_heatmap_cmap(higher_is_better)

    fig, ax = plt.subplots(figsize=(20, 9))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0.3, 18.7)
    ax.set_ylim(0.3, 9.7)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(title, fontsize=20, fontweight="bold", pad=14)

    _PAD   = 0.06   # cell inner padding
    _ROUND = 0.12   # corner rounding radius

    for elem, (row, col) in PERIODIC_TABLE_POS.items():
        val = elem_metric_dict.get(elem, None)
        ok = False
        if val is not None:
            try:
                val = float(val)
                ok = np.isfinite(val)
            except Exception:
                ok = False

        rgba     = cmap_obj(norm(val)) if ok else (0.88, 0.88, 0.90, 1.0)
        lum      = _luminance(rgba)
        txt_col  = "black" if lum > 0.50 else "white"
        strk_col = "white" if txt_col == "black" else "black"

        fx_main  = [pe.withStroke(linewidth=1.8, foreground=strk_col), pe.Normal()]
        fx_small = [pe.withStroke(linewidth=1.2, foreground=strk_col), pe.Normal()]

        # Rounded-corner cell
        ax.add_patch(FancyBboxPatch(
            (col - 0.5 + _PAD, row - 0.5 + _PAD),
            1 - 2 * _PAD, 1 - 2 * _PAD,
            boxstyle=f"round,pad=0,rounding_size={_ROUND}",
            facecolor=rgba, edgecolor="white", linewidth=1.4,
            zorder=2,
        ))

        # Atomic number (top-left)
        z = _elem_z(elem)
        if z > 0:
            ax.text(
                col - 0.5 + _PAD + 0.07, row - 0.5 + _PAD + 0.09,
                str(int(z)),
                ha="left", va="top",
                fontsize=5.5, color=txt_col,
                path_effects=fx_small, zorder=3,
            )

        # Element symbol
        ax.text(
            col, row - 0.10,
            elem,
            ha="center", va="center",
            fontsize=10.5, fontweight="bold",
            color=txt_col, path_effects=fx_main, zorder=3,
        )

        # Value
        label = f"{val:.3f}" if ok else "—"
        ax.text(
            col, row + 0.22,
            label,
            ha="center", va="center",
            fontsize=7.2,
            color=txt_col, path_effects=fx_main, zorder=3,
        )

        # n= (sample count)
        if count_dict is not None:
            n = int(count_dict.get(elem, 0) or 0)
            if n > 0:
                ax.text(
                    col, row + 0.42, f"n={n}",
                    ha="center", va="center",
                    fontsize=5.8,
                    color=txt_col, path_effects=fx_small, zorder=3,
                )

    # Lanthanide/Actinide * placeholders
    for (prow, pcol), mark in [((6, 3), "57–71"), ((7, 3), "89–103")]:
        ax.add_patch(FancyBboxPatch(
            (pcol - 0.5 + _PAD, prow - 0.5 + _PAD),
            1 - 2 * _PAD, 1 - 2 * _PAD,
            boxstyle=f"round,pad=0,rounding_size={_ROUND}",
            facecolor=(0.80, 0.80, 0.84, 1.0), edgecolor="white", linewidth=1.0,
            zorder=2,
        ))
        ax.text(pcol, prow, mark, ha="center", va="center",
                fontsize=6.0, color="#555555", zorder=3)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap_obj, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, orientation="horizontal",
                        fraction=0.025, pad=0.01, aspect=50,
                        shrink=0.6)
    cbar.ax.tick_params(labelsize=9)
    cbar.outline.set_linewidth(0.8)

    fig.tight_layout()
    fig.savefig(_ensure_parent(save_path), dpi=dpi, facecolor="white")
    plt.close(fig)


def plot_fwt_curve(
    model_curves: dict,
    save_path,
    dpi: int = 300,
):
    """
    Comparison plot of FwT(threshold) curves across models.
    Curves are sorted by AFwT (descending) and the legend is placed
    outside the axes on the right so it never overlaps the plot.

    Args:
        model_curves: {model_name: (thresholds_array, fwt_pct_array)}
    """
    if not model_curves:
        return

    items = []
    for name, (thresholds, fwt_pct) in model_curves.items():
        afwt = float(np.mean(fwt_pct))
        items.append((name, thresholds, fwt_pct, afwt))
    items.sort(key=lambda t: t[3], reverse=True)

    cmap = plt.get_cmap("tab20")
    linestyles = ["-", "--", ":"]
    fig, ax = plt.subplots(figsize=(13, 7))

    for i, (name, thresholds, fwt_pct, afwt) in enumerate(items):
        ax.plot(thresholds, fwt_pct,
                label=f"{name}  (AFwT={afwt:.1f}%)",
                linewidth=2.2,
                color=cmap(i % 20),
                linestyle=linestyles[(i // 20) % len(linestyles)])

    ax.set_xlabel("Force threshold (eV/Å)", fontsize=20)
    ax.set_ylabel("Force within threshold (%)", fontsize=20)
    ax.set_title("Force Accuracy within Threshold (FwT)", fontsize=18,
                 fontweight="bold", pad=10)
    ax.set_xlim(left=0)
    ax.set_ylim(0, 101)
    ax.grid(True, linewidth=0.7, alpha=0.4)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=14)
    ax.legend(fontsize=10,
              loc="upper left",
              bbox_to_anchor=(1.02, 1.0),
              frameon=True, framealpha=0.9,
              borderaxespad=0.0)

    fig.savefig(_ensure_parent(save_path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_total_bar(
    model_names, values,
    metric_name: str, ylabel: str, save_path,
    dpi: int = 300,
    ascending: bool = True,
):
    names = list(model_names)
    vals = np.asarray(values, dtype=float)
    n = min(len(names), len(vals))
    names, vals = names[:n], vals[:n]

    m = np.isfinite(vals)
    names = [nm for nm, ok in zip(names, m) if ok]
    vals = vals[m]
    if vals.size == 0:
        return

    order = np.argsort(vals) if ascending else np.argsort(vals)[::-1]
    names = [names[i] for i in order]
    vals = vals[order]

    cmap = plt.get_cmap("tab20")
    colors = [cmap(i % 20) for i in range(len(names))]

    fig_w = max(7.0, len(names) * 1.3)
    fig, ax = plt.subplots(figsize=(fig_w, 6.0))

    bars = ax.bar(names, vals.tolist(), color=colors,
                  width=0.6, edgecolor="black", linewidth=1.2)

    ax.set_ylabel(ylabel, fontsize=22)
    ax.set_title(f"Model Comparison — {metric_name}", fontsize=18, fontweight="bold")
    ax.grid(True, axis="y", linewidth=0.7, alpha=0.5)
    ax.set_axisbelow(True)

    vmax = float(vals.max()) if vals.size else 1.0
    vmin_v = float(vals.min()) if vals.size else 0.0
    ybot = min(0.0, vmin_v)
    # reserve 22% of the visible range above the tallest bar for text labels
    ytop_raw = vmax - ybot
    ytop = vmax + max(0.22 * ytop_raw, 0.22 * abs(vmax), 1e-3)
    ax.set_ylim(ybot, ytop)
    ax.tick_params(axis="both", labelsize=16)

    y0, y1 = ax.get_ylim()
    pad = 0.005 * (y1 - y0)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + pad,
                f"{float(val):.4f}",
                ha="center", va="bottom", fontsize=13,
                clip_on=False)

    ax.tick_params(axis="x", rotation=35, labelsize=14)
    for lab in ax.get_xticklabels():
        lab.set_ha("right")

    fig.tight_layout()
    fig.savefig(_ensure_parent(save_path), dpi=dpi)
    plt.close(fig)


def plot_pareto(
    model_names, x_vals, y_vals,
    title: str,
    xlabel: str,
    ylabel: str,
    save_path,
    dpi: int = 300,
    maximize_y: bool = False,
):
    """
    Pareto scatter plot across models.
    Each model gets a unique (color, marker) combination; Pareto-optimal
    models are overlaid with a bold star marker. Model names are shown
    as an outside legend on the right rather than as text annotations.
    """
    names = list(model_names)
    x = np.asarray(x_vals, dtype=float)
    y = np.asarray(y_vals, dtype=float)

    n = min(len(names), len(x), len(y))
    names, x, y = names[:n], x[:n], y[:n]

    m = np.isfinite(x) & np.isfinite(y)
    names = [nm for nm, ok in zip(names, m) if ok]
    x = x[m]
    y = y[m]
    if len(names) == 0:
        return

    idxs = list(range(len(names)))
    pareto = []
    for i in idxs:
        dominated = False
        for j in idxs:
            if j == i:
                continue
            if maximize_y:
                better_or_equal = (x[j] <= x[i]) and (y[j] >= y[i])
                strictly_better = (x[j] < x[i]) or (y[j] > y[i])
            else:
                better_or_equal = (x[j] <= x[i]) and (y[j] <= y[i])
                strictly_better = (x[j] < x[i]) or (y[j] < y[i])
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            pareto.append(i)

    pareto_sorted = sorted(pareto, key=lambda k: x[k])
    x_pf = x[pareto_sorted]
    y_pf = y[pareto_sorted]

    cmap = plt.get_cmap("tab20")
    markers = ["o", "s", "^", "v", "D", "p", "P", "X", "h", "<"]

    fig, ax = plt.subplots(figsize=(13, 8))

    for i, nm in enumerate(names):
        is_pf = i in pareto
        ax.scatter(
            x[i], y[i],
            s=110 if is_pf else 55,
            marker="*" if is_pf else markers[i % len(markers)],
            color=cmap(i % 20),
            edgecolors="black",
            linewidths=1.2 if is_pf else 0.8,
            label=str(nm),
            zorder=3 if is_pf else 2,
        )

    ax.plot(x_pf, y_pf, "k--", linewidth=1.8, zorder=1)

    ax.set_xlabel(xlabel, fontsize=22)
    ax.set_ylabel(ylabel, fontsize=22)
    if title:
        ax.set_title(title, fontsize=18, fontweight="bold", pad=8)
    ax.tick_params(axis="both", labelsize=14)
    ax.grid(True, linewidth=0.6, alpha=0.4)
    ax.set_axisbelow(True)

    ax.legend(fontsize=10,
              loc="upper left",
              bbox_to_anchor=(1.02, 1.0),
              frameon=True, framealpha=0.9,
              borderaxespad=0.0,
              title="Model (★ = Pareto-optimal)",
              title_fontsize=11)

    fig.savefig(_ensure_parent(save_path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)
