"""
ClusPot site — size-dependence precompute.

The size-dependence view (formation-energy error vs cluster atom count) is NOT
in results.xlsx — it lives in the per-model processed caches
(analysis/{model}/{dataset}/cache/normal_df.parquet, ~1.5M rows each). This is
the slow pass: it reads every model's parquet once and reduces it to a tiny
per-(n_atoms) summary (median / Q1 / Q3 / count) written to size_dependence.json.

build_data.py folds this JSON into data.json. Re-run only when the parquet
caches change (new model, re-analysis) — not on every xlsx rebuild.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python build_size_dependence.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path("/home/khshin/ClusPot_analysis")
OUT = ROOT / "site" / "size_dependence.json"

# (system_key, analysis dir, dataset folder name under each model)
SYSTEMS = [
    ("mono", ROOT / "clusterbench" / "analysis", "qcd_cluster"),
    # bimetallic can be added later once its size story is wanted:
    # ("bi", Path("/DATA/user_scratch/khshin/ClusPot_bimetallic/clusterbench/analysis"), "bimetallic_cluster"),
]

MIN_COUNT = 30  # drop atom-counts with too few samples to trust a quartile


def summarize(parquet: Path):
    """Return {n: (median, q1, q3, count)} in meV/atom for one model cache."""
    t = pq.read_table(str(parquet), columns=["n_atoms", "e_form_dft", "e_form_mlip"])
    n = np.asarray(t.column("n_atoms"), dtype=float)
    ae = np.abs(np.asarray(t.column("e_form_mlip"), dtype=float)
                - np.asarray(t.column("e_form_dft"), dtype=float)) * 1000.0  # meV/atom
    ok = np.isfinite(n) & np.isfinite(ae)
    n, ae = n[ok], ae[ok]
    out = {}
    for k in np.unique(n.astype(int)):
        v = ae[n == k]
        if len(v) < MIN_COUNT:
            continue
        out[int(k)] = (float(np.median(v)), float(np.percentile(v, 25)),
                       float(np.percentile(v, 75)), int(len(v)))
    return out


def build_system(analysis_dir: Path, dataset: str) -> dict | None:
    paths = sorted(glob.glob(str(analysis_dir / "*" / dataset / "cache" / "normal_df.parquet")))
    if not paths:
        return None
    per_model = {}
    all_sizes = set()
    for p in paths:
        model = Path(p).parts[-4]
        try:
            s = summarize(Path(p))
        except Exception as e:  # noqa: BLE001
            print(f"  skip {model}: {e}")
            continue
        if not s:
            continue
        per_model[model] = s
        all_sizes.update(s.keys())
        print(f"  {model:30s} {len(s)} sizes")

    if not per_model:
        return None
    sizes = sorted(all_sizes)
    idx = {n: i for i, n in enumerate(sizes)}
    models = {}
    for model, s in per_model.items():
        med = [None] * len(sizes)
        q1 = [None] * len(sizes)
        q3 = [None] * len(sizes)
        cnt = [0] * len(sizes)
        for n, (m, a, b, c) in s.items():
            med[idx[n]], q1[idx[n]], q3[idx[n]], cnt[idx[n]] = round(m, 2), round(a, 2), round(b, 2), c
        models[model] = {"median": med, "q1": q1, "q3": q3, "count": cnt}
    return {"sizes": sizes, "models": models}


def main() -> None:
    out = {}
    for key, adir, dataset in SYSTEMS:
        print(f"[{key}] {adir}")
        block = build_system(adir, dataset)
        if block:
            out[key] = block
            print(f"  → {len(block['models'])} models, sizes {block['sizes'][0]}–{block['sizes'][-1]}")
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"\n✓ wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
