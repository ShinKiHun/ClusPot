# cluspotlib

MLIP benchmarking library. Compares DFT reference data against MLIP single-point
results to quantitatively evaluate energy and force accuracy.

Supports mono-element, bimetallic, and HEA clusters.

---

## Installation

```bash
pip install -e /path/to/ClusPot
```

---

## Overall Workflow

```
DFT OUTCAR
    │
    ▼
build_db.py ──► data/source.db          (DFT reference DB)
                    │
                    ▼
            ClusterCalculation ──► data/{mlip_name}/source.db   (MLIP result DB)
                                        │
                                        ▼
                                ClusterAnalysis ──► analysis/results.xlsx
                                                    analysis/{mlip_name}/...  (plots)
```

---

## 1. Build DB — `build_db`

Converts DFT OUTCAR files into an ASE database.

### Input Directory Structure

`build_db` runs `rglob("OUTCAR")` under each of `cluster_dir` and `bulk_dir`.
The two roots **must not overlap** — any OUTCAR reachable from `cluster_dir`
is treated as a cluster, and any OUTCAR reachable from `bulk_dir` as a bulk.

**Layout A — separate roots (recommended)**

```
data_root/
  user_cluster/
    <any_path>/<calc_folder>/OUTCAR    # cluster calculations (searched recursively)
  user_bulk/
    <any_path>/<elem_folder>/OUTCAR    # bulk calculations (one OUTCAR per element)
```

**Layout B — cluster subfolders and bulk under a common root**

```
data_root/
  Ag-Au/<size>/<isomer>/OUTCAR
  Ag-Ir/<size>/<isomer>/OUTCAR
  ...
  bulk/
    Ag/OUTCAR
    Au/OUTCAR
    ...
```

In Layout B you **cannot** pass `cluster_dir=data_root/` — the recursive search
would pick up `bulk/*/OUTCAR` as cluster entries. Iterate over the individual
cluster subfolders instead (see the wrapper example below).

### Usage

```bash
# CLI
python build_db.py \
    --cluster-dir /data/user_cluster \
    --bulk-dir    /data/user_bulk \
    --out         data/bimetallic.db

# overwrite existing entries
python build_db.py ... --overwrite
```

```python
# Python API — Layout A
from cluspotlib import build_db
from pathlib import Path

build_db(
    out_db      = Path("data/bimetallic.db"),
    cluster_dir = Path("/data/user_cluster"),
    bulk_dir    = Path("/data/user_bulk"),
    overwrite   = False,
)
```

```python
# Python API — Layout B (cluster subfolders + bulk under one root)
from cluspotlib import build_db
from pathlib import Path

root = Path("/data/data_root")
out  = Path("data/bimetallic.db")

for sub in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "bulk"):
    build_db(out_db=out, cluster_dir=sub)     # accumulates into the same DB

build_db(out_db=out, bulk_dir=root / "bulk")
```

### DB Schema

**cluster entries**

| Key | Description |
|---|---|
| `type` | `"cluster"` |
| `element` | Sorted element combination separated by `-`. e.g. `"Ag-Au"`, `"Au-Fe-Pt"` |
| `n_atoms` | Total number of atoms |
| `calc_id` | Reproducible 28-char ID derived from SHA-256 hash of `src_path` |
| `src_path` | Relative path from the parent of `cluster_dir` |
| `step` | Ionic step index (0-based) |
| `is_last` | 1 if this is the last ionic step, otherwise 0 |
| atoms | Positions, forces, cell, and energy |

**bulk entries**

| Key | Description |
|---|---|
| `type` | `"bulk"` |
| `element` | Element symbol. e.g. `"Au"` |
| `n_atoms` | Total number of atoms |
| `src_path` | Relative path from the parent of `bulk_dir` |
| atoms | Positions, cell, and energy (last ionic step) |

> **Note**: `calc_id` is determined from the `src_path` string.
> If the directory structure changes, `calc_id` changes as well — rebuild the DB with `--overwrite`.

---

## 2. MLIP Calculation — `ClusterCalculation`

Runs MLIP single-point calculations on structures from the source DB and saves
results to a separate DB.

### Directory Structure

```
work_dir/
  data/
    bimetallic.db          ← source DB (output of build_db)
    {mlip_name}/
      bimetallic.db        ← MLIP result DB (auto-created)
  log/
    {mlip_name}/
      bimetallic_bulk_YYYYMMDD_HHMMSS.log
      bimetallic_cluster_YYYYMMDD_HHMMSS.log
```

### Usage

```python
from cluspotlib import ClusterCalculation

# prepare any ASE calculator (MACE, CHGNet, SevenNet, etc.)
from mace.calculators import MACECalculator
calc = MACECalculator(model_paths="model.pt", device="cuda")

runner = ClusterCalculation(
    calculator = calc,
    mlip_name  = "MACE_MH_1",
    work_dir   = ".",        # directory containing the data/ folder
    overwrite  = False,
)

runner.run()                      # bulk + cluster
runner.run(targets=["cluster"])   # cluster only
runner.run(targets=["bulk"])      # bulk only
```

### Result DB Schema

**cluster entries** (source DB fields + the following)

| Key | Description |
|---|---|
| `calc_time` | Single-point calculation time [s] |
| atoms | MLIP energy and forces |

**bulk entries**

| Key | Description |
|---|---|
| `energy_per_atom` | MLIP energy per atom [eV] |
| `calc_time` | Calculation time [s] |

### Skip Logic

- `overwrite=False` (default): skips if `(calc_id, step)` pair already exists in the result DB
- For bulk: skips if `element` already exists

---

## 3. Analysis — `ClusterAnalysis`

Compares the source DB (DFT) and MLIP result DB to compute metrics and generate plots.

### Output Directory Structure

```
work_dir/
  data/
    bimetallic.db               ← source DB
    {mlip_name}/
      bimetallic.db             ← MLIP result DB
  analysis/
    results.xlsx                ← all metrics summary
    {mlip_name}/
      {dataset}/
        normal/
          all/
            energy/
              Eform.png                  # Eform parity plot (colored by element)
              heatmap_MAE.png            # periodic table heatmap
              heatmap_R2.png
              per_element/
                Au-Fe.png               # per-pair Eform parity (colored by atom count)
                ...
            force/
              Force.png
              heatmap_MAE.png
              per_element/
                Au-Fe.png
                ...
          tm12/                          # same structure, filtered to TM12 pairs only
            ...
        anomaly/                         # outliers with |ΔEform| >= 5 eV/atom
          all/ ...
          tm12/ ...
      total/                             # aggregated over all datasets for this model
        normal/ ...
    total/
      {dataset}/                         # cross-model comparison plots
        all/
          E_form_MAE.png
          force_MAE.png
          pareto_accuracy_efficiency.png
          pareto_robustness_efficiency.png
        tm12/ ...
        fwt_curve.png
      total/                             # cross-model comparison aggregated over all datasets
        ...
```

### Usage

```python
from cluspotlib import ClusterAnalysis
from pathlib import Path

ClusterAnalysis(work_dir=Path(".")).run()

# re-analyze already-processed entries
ClusterAnalysis(work_dir=Path("."), overwrite=True).run()
```

### Skip Logic

- `overwrite=False` (default): skips if `(model, dataset)` pair exists in the per-model sheet of `results.xlsx` and the PNG files are present
- If PNGs are missing but the xlsx entry exists, plots are regenerated without rewriting xlsx

### Anomaly Classification

```
|e_form_dft - e_form_mlip| >= 5.0 eV/atom  →  anomaly
```

Anomalies are excluded from metric computation and saved to a separate `anomaly/` folder.

### Metrics

**Energy (formation energy `e_form`)**

| Metric | Description |
|---|---|
| MAE | Mean Absolute Error [eV/atom] |
| RMSE | Root Mean Squared Error [eV/atom] |
| R² | Coefficient of determination |
| Pearson | Pearson correlation coefficient |
| Spearman | Spearman rank correlation coefficient |

**Forces**

| Metric | Description |
|---|---|
| MAE | [eV/Å] |
| RMSE | [eV/Å] |
| R², Pearson, Spearman | Same as above |
| cosine | Average cosine similarity of force vectors per sample |
| AFwT | Average Force within Threshold — integral of FwT(t) over [0.01, 1.0] eV/Å (%) |

### FwT (Force within Threshold)

The `fwt_curves` sheet in `results.xlsx` stores FwT(%) at key thresholds:

`FwT@0.05`, `FwT@0.10`, `FwT@0.15`, `FwT@0.20`, `FwT@0.30`, `FwT@0.50`, `FwT@0.70`, `FwT@1.00`

---

## Dependencies

```
numpy, pandas, matplotlib, ase, openpyxl, tqdm
```

Python >= 3.8

---

## Version

`0.1.0` — 2026-03
