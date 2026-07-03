"""
ClusPot site — xlsx → data.json builder.

Reads two analysis xlsx files (mono + bimetallic) and produces a single
data.json keyed by system. Run any time either xlsx changes:

    python build_data.py
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Inputs / output ──────────────────────────────────────────────────────────
ROOT = Path("/home/khshin/ClusPot_analysis")
OUT  = ROOT / "site" / "data.json"

# Each entry: (system_key, label, xlsx path, element-column kind)
#   kind = "single" → Element column holds a symbol like "Fe"
#   kind = "pair"   → Element column holds "Ag-Au" (binary alloy pair)
SYSTEMS = [
    ("mono", "Monometallic",
     ROOT / "clusterbench" / "analysis" / "results.xlsx",
     "single"),
    ("bi",   "Bimetallic",
     Path("/DATA/user_scratch/khshin/ClusPot_bimetallic/clusterbench/analysis/results.xlsx"),
     "pair"),
]

# (key, raw xlsx col, short label, unit, lower_is_better, group, target)
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
    # derived diagnosis metrics (injected from paper/scripts jsons, not xlsx)
    ("E_eff",          "E_eff (eV/atom)",       "E_eff (E + force cost)", "eV/atom", True, "diagnosis", ""),
    ("Offset_share",   "Removable offset (%)",  "Removable offset share", "%",      True, "diagnosis", ""),
]
COL_TO_KEY = {col: key for key, col, *_ in METRICS}

ELEM_METRIC_COLS = [
    "E_form MAE (eV/atom)", "E_form RMSE (eV/atom)", "E_form R²",
    "E_form Pearson", "E_form Spearman",
    "Force MAE (eV/Å)", "Force RMSE (eV/Å)", "Force R²",
    "Force Pearson", "Force Spearman", "Force cosine",
    "Time_mean (s)", "Time_med (s)",
]


def _num(v):
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


def _fwt_threshold(col: str):
    m = re.match(r"FwT@([\d.]+)", col)
    return float(m.group(1)) if m else None


def _canon_pair(label: str) -> str:
    """Return alphabetically-ordered canonical pair key, e.g. 'Au-Ag' → 'Ag-Au'."""
    parts = [p.strip() for p in str(label).split("-") if p.strip()]
    if len(parts) != 2:
        return str(label)
    a, b = sorted(parts)
    return f"{a}-{b}"


def build_system(system_key: str, xlsx: Path, kind: str) -> dict:
    print(f"\n── {system_key.upper()} · {xlsx} ──")
    if not xlsx.exists():
        print(f"  ! xlsx not found, skipping")
        return None

    xl = pd.ExcelFile(xlsx)
    sheets = xl.sheet_names

    summary = pd.read_excel(xlsx, sheet_name="summary")
    summary["Model"] = summary["Model"].ffill()
    fwt = pd.read_excel(xlsx, sheet_name="fwt_curves") if "fwt_curves" in sheets else None
    if fwt is not None:
        fwt["Model"] = fwt["Model"].ffill()

    models = list(summary["Model"].dropna().unique())
    datasets = list(summary["Dataset"].dropna().unique())
    print(f"  models: {len(models)}  datasets: {datasets}")

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
    fwt_block: dict = {}
    fwt_thresholds: list = []
    if fwt is not None:
        fwt_cols = [(c, _fwt_threshold(c)) for c in fwt.columns]
        fwt_cols = [(c, t) for c, t in fwt_cols if t is not None]
        fwt_thresholds = [t for _, t in fwt_cols]
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

    # ── per-model element / pair block ──────────────────────────────────────
    detail_block: dict = {}            # {model: {dataset: {key: {type: {...}}}}}
    active_keys: set[str] = set()      # element symbols (mono) or pair keys (bi)
    active_elements: set[str] = set()  # for bi: unique elements that participate

    for m in models:
        if m not in sheets:
            continue
        df = pd.read_excel(xlsx, sheet_name=m)
        df["Dataset"] = df["Dataset"].ffill()
        for _, row in df.iterrows():
            d   = row.get("Dataset")
            t   = row.get("Type")
            el  = row.get("Element")
            if pd.isna(d) or pd.isna(el) or pd.isna(t):
                continue
            if kind == "pair":
                key = _canon_pair(el)
                a, b = key.split("-") if "-" in key else (key, key)
                active_elements.add(a)
                active_elements.add(b)
            else:
                key = str(el)
                active_elements.add(key)
            active_keys.add(key)
            ds_block = detail_block.setdefault(m, {}).setdefault(d, {})
            entry = ds_block.setdefault(key, {})
            slot = entry.setdefault(t, {})
            slot["N_samples"] = _num(row.get("N_samples"))
            for col in ELEM_METRIC_COLS:
                if col in df.columns:
                    slot[COL_TO_KEY.get(col, col)] = _num(row[col])

    # ── size-dependence block (emitted by ClusterAnalysis as its own sheet) ──
    size_block = _size_from_sheet(xlsx, sheets, models)

    out = {
        "kind":            kind,
        "models":          models,
        "n_models":        len(models),
        "datasets":        datasets,
        "active_elements": sorted(active_elements),
        "summary":         summary_block,
        "fwt":             fwt_block,
        "fwt_thresholds":  fwt_thresholds,
    }
    if size_block:
        out["size"] = size_block
    if kind == "pair":
        out["active_pairs"] = sorted(active_keys)
        out["pairs"]        = detail_block
    else:
        out["elements"] = detail_block

    print(f"  ✓ summary={len(summary_block)} models, "
          f"{'pairs' if kind == 'pair' else 'elements'}={len(active_keys)}")
    return out


# size_dependence sheet columns (emitted by ClusterAnalysis)
_SIZE_COLS = {
    "n":      "Cluster size (n_atoms)",
    "median": "Median |ΔE_form| (meV/atom)",
    "q1":     "Q1 |ΔE_form| (meV/atom)",
    "q3":     "Q3 |ΔE_form| (meV/atom)",
    "count":  "Count",
}


def _size_from_sheet(xlsx: Path, sheets, models) -> dict | None:
    """Build the size-dependence block straight from the ``size_dependence``
    sheet that ClusterAnalysis now emits (median/Q1/Q3/count per n_atoms,
    meV/atom). Returns {"sizes": [...], "models": {model: {median,q1,q3,count}}}
    or None if the sheet is absent."""
    if "size_dependence" not in sheets:
        return None
    df = pd.read_excel(xlsx, sheet_name="size_dependence")
    df["Model"] = df["Model"].ffill()
    model_set = set(models)

    per_model: dict = {}
    sizes_seen: set = set()
    for _, row in df.iterrows():
        m = row.get("Model")
        n = _num(row.get(_SIZE_COLS["n"]))
        if pd.isna(m) or m not in model_set or n is None:
            continue
        n = int(n)
        sizes_seen.add(n)
        per_model.setdefault(m, {})[n] = (
            _num(row.get(_SIZE_COLS["median"])),
            _num(row.get(_SIZE_COLS["q1"])),
            _num(row.get(_SIZE_COLS["q3"])),
            _num(row.get(_SIZE_COLS["count"])),
        )
    if not per_model:
        return None

    sizes = sorted(sizes_seen)
    idx = {n: i for i, n in enumerate(sizes)}
    out_models: dict = {}
    for m, by_n in per_model.items():
        med = [None] * len(sizes)
        q1  = [None] * len(sizes)
        q3  = [None] * len(sizes)
        cnt = [0]    * len(sizes)
        for n, (a, b, c, d) in by_n.items():
            i = idx[n]
            med[i] = round(a, 2) if a is not None else None
            q1[i]  = round(b, 2) if b is not None else None
            q3[i]  = round(c, 2) if c is not None else None
            cnt[i] = int(d) if d is not None else 0
        out_models[m] = {"median": med, "q1": q1, "q3": q3, "count": cnt}
    print(f"  · size-dependence: {len(out_models)} models, sizes {sizes[0]}–{sizes[-1]}")
    return {"sizes": sizes, "models": out_models}


def _inject_diagnosis_metrics(mono: dict) -> None:
    """E_eff = E_MAE + ||dF||_vec_MAE^2/(2k) and removable-offset share, from
    the paper-grade jsons (anchor_curve_strict / force_structure / kmeas).
    Values verified against data sources at analysis time; here we only join."""
    base = Path("/home/khshin/ClusPot_analysis/paper/scripts")
    try:
        anchor = json.loads((base / "out_anchor_curve_strict.json").read_text())["per_model"]
        force = json.loads((base / "out_force_structure.json").read_text())
        k = json.loads((base / "out_kmeas.json").read_text())["k_global"]
    except FileNotFoundError as e:
        print(f"  ! diagnosis metrics skipped ({e})")
        return
    n = 0
    for m, buckets in mono.get("summary", {}).items():
        qcd = buckets.get("qcd_cluster")
        if not qcd or m not in anchor or m not in force:
            continue
        emae = qcd.get("E_form_MAE")
        raw, ref = anchor[m]["raw"], anchor[m]["ref_evenodd"]
        if emae is None or abs(raw - emae) > 2e-3:
            print(f"  ! diagnosis skip {m}: anchor raw {raw} vs xlsx {emae}")
            continue
        e_eff = emae + force[m]["vec_mae"] ** 2 / (2 * k)
        share = (raw - ref) / raw * 100
        for ds in ("qcd_cluster", "total"):
            if ds in buckets:
                buckets[ds]["E_eff"] = round(e_eff, 4)
                buckets[ds]["Offset_share"] = round(share, 1)
        n += 1
    print(f"  · diagnosis metrics injected for {n} models (k={k:.3f})")


def main() -> None:
    systems_block: dict = {}
    for key, label, xlsx, kind in SYSTEMS:
        sys_data = build_system(key, xlsx, kind)
        if sys_data is None:
            continue
        sys_data["label"] = label
        systems_block[key] = sys_data

    if "mono" in systems_block:
        _inject_diagnosis_metrics(systems_block["mono"])

    # HEA placeholder so the front-end can render a "coming soon" page
    systems_block["hea"] = {
        "kind":     "hea",
        "label":    "High-entropy",
        "status":   "coming_soon",
        "models":   [],
        "datasets": [],
    }

    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "systems": [k for k in ("mono", "bi", "hea") if k in systems_block],
            "metrics": [
                {"key": k, "col": c, "label": l, "unit": u,
                 "lower_better": lb, "group": g, "target": t}
                for k, c, l, u, lb, g, t in METRICS
            ],
        },
        "systems": systems_block,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n✓ wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")
    for sk, sv in systems_block.items():
        if sv.get("status") == "coming_soon":
            print(f"  · {sk}: coming_soon")
        else:
            print(f"  · {sk}: {sv['n_models']} models, "
                  f"{len(sv.get('active_pairs', sv.get('active_elements', [])))} "
                  f"{'pairs' if sv['kind']=='pair' else 'elements'}")


if __name__ == "__main__":
    main()
