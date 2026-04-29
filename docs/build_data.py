"""
ClusPot site — xlsx → data.json builder.

Run any time results.xlsx changes:
    python build_data.py
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("/home/khshin/ClusPot_analysis")
XLSX = ROOT / "clusterbench" / "analysis" / "results.xlsx"
OUT  = ROOT / "site" / "data.json"

# (key, raw xlsx col, short label, unit, lower_is_better, group, target)
# `target` is the property the metric measures, used for display: "MAE (E_form, eV/atom)"
METRICS = [
    ("E_form_MAE",     "E_form MAE (eV/atom)",  "MAE",      "eV/atom", True,  "energy",     "E_form"),
    ("E_form_RMSE",    "E_form RMSE (eV/atom)", "RMSE",     "eV/atom", True,  "energy",     "E_form"),
    ("E_form_R2",      "E_form R²",             "R²",       "",        False, "energy",     "E_form"),
    ("E_form_Pearson", "E_form Pearson",        "Pearson",  "",        False, "energy",     "E_form"),
    ("E_form_Spearman","E_form Spearman",       "Spearman", "",        False, "energy",     "E_form"),
    ("Force_MAE",      "Force MAE (eV/Å)",      "MAE",      "eV/Å",    True,  "force",      "Force"),
    ("Force_RMSE",     "Force RMSE (eV/Å)",     "RMSE",     "eV/Å",    True,  "force",      "Force"),
    ("Force_R2",       "Force R²",              "R²",       "",        False, "force",      "Force"),
    ("Force_Pearson",  "Force Pearson",         "Pearson",  "",        False, "force",      "Force"),
    ("Force_Spearman", "Force Spearman",        "Spearman", "",        False, "force",      "Force"),
    ("Force_cosine",   "Force cosine",          "Cosine",   "",        False, "force",      "Force"),
    ("AFwT",           "AFwT",                  "AFwT",     "%",       False, "robustness", ""),
    ("Anomaly_pct",    "Anomaly (%)",           "Anomaly rate", "%",   True,  "robustness", ""),
    ("Time_med",       "Time_med (s)",          "Time / step (median)", "s", True, "efficiency", ""),
    ("Time_mean",      "Time_mean (s)",         "Time / step (mean)",   "s", True, "efficiency", ""),
    ("Time_total",     "Time_total (s)",        "Total time",           "s", True, "efficiency", ""),
]
COL_TO_KEY = {col: key for key, col, *_ in METRICS}

# per-element metrics (subset of METRICS that exist in per-model sheets)
ELEM_METRIC_COLS = [
    "E_form MAE (eV/atom)", "E_form RMSE (eV/atom)", "E_form R²",
    "E_form Pearson", "E_form Spearman",
    "Force MAE (eV/Å)", "Force RMSE (eV/Å)", "Force R²",
    "Force Pearson", "Force Spearman", "Force cosine",
    "Time_mean (s)", "Time_med (s)",
]


def _num(v):
    """Return float or None for any cell. Strips ASE '-' placeholder."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s in ("", "-", "nan", "NaN"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _fwt_threshold(col: str) -> float | None:
    m = re.match(r"FwT@([\d.]+)", col)
    return float(m.group(1)) if m else None


def main() -> None:
    xl = pd.ExcelFile(XLSX)
    sheets = xl.sheet_names
    print(f"sheets: {sheets}")

    summary = pd.read_excel(XLSX, sheet_name="summary")
    summary["Model"] = summary["Model"].ffill()
    fwt = pd.read_excel(XLSX, sheet_name="fwt_curves")
    fwt["Model"] = fwt["Model"].ffill()

    models = list(summary["Model"].dropna().unique())
    datasets = list(summary["Dataset"].dropna().unique())
    print(f"models: {len(models)}  datasets: {datasets}")

    # ── summary block ────────────────────────────────────────────────────────
    summary_block: dict = {}
    for _, row in summary.iterrows():
        m, d = row["Model"], row["Dataset"]
        if pd.isna(m) or pd.isna(d):
            continue
        bucket = summary_block.setdefault(m, {}).setdefault(d, {})
        for key, col, *_ in METRICS:
            if col in summary.columns:
                bucket[key] = _num(row[col])
        bucket["N_normal"]  = _num(row.get("N_normal"))
        bucket["N_anomaly"] = _num(row.get("N_anomaly"))
        bucket["N_missed"]  = _num(row.get("N_missed"))

    # ── fwt block ────────────────────────────────────────────────────────────
    fwt_cols = [(c, _fwt_threshold(c)) for c in fwt.columns]
    fwt_cols = [(c, t) for c, t in fwt_cols if t is not None]

    fwt_block: dict = {}
    for _, row in fwt.iterrows():
        m, d = row["Model"], row["Dataset"]
        if pd.isna(m) or pd.isna(d):
            continue
        pts = []
        for c, t in fwt_cols:
            v = _num(row[c])
            if v is not None:
                pts.append({"threshold": t, "pct": v})
        if pts:
            fwt_block.setdefault(m, {})[d] = pts

    # ── per-model element block ──────────────────────────────────────────────
    elements_block: dict = {}
    active_elements: set[str] = set()
    for m in models:
        if m not in sheets:
            continue
        df = pd.read_excel(XLSX, sheet_name=m)
        df["Dataset"] = df["Dataset"].ffill()
        for _, row in df.iterrows():
            d   = row.get("Dataset")
            t   = row.get("Type")
            el  = row.get("Element")
            if pd.isna(d) or pd.isna(el) or pd.isna(t):
                continue
            active_elements.add(el)
            ds_block = elements_block.setdefault(m, {}).setdefault(d, {})
            entry = ds_block.setdefault(el, {})
            slot = entry.setdefault(t, {})
            slot["N_samples"] = _num(row.get("N_samples"))
            for col in ELEM_METRIC_COLS:
                if col in df.columns:
                    slot[COL_TO_KEY.get(col, col)] = _num(row[col])

    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_models": len(models),
            "datasets": datasets,
            "active_elements": sorted(active_elements),
            "metrics": [
                {"key": k, "col": c, "label": l, "unit": u,
                 "lower_better": lb, "group": g, "target": t}
                for k, c, l, u, lb, g, t in METRICS
            ],
            "fwt_thresholds": [t for _, t in fwt_cols],
        },
        "models":   models,
        "summary":  summary_block,
        "fwt":      fwt_block,
        "elements": elements_block,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n✓ wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"  models: {len(models)}   active elements: {len(active_elements)}")


if __name__ == "__main__":
    main()
