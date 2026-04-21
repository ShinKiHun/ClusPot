"""
PerElementAnalysis Module

Generates per-element parity plots (Eform, Force) for user-specified element
combinations, reading from existing analysis cache (no DB re-read).

Directory structure:
  analysis/
    per_element/
      {element}/
        {mlip}/
          {dataset}/
            normal/
              Eform.png
              Force.png
            anomaly/
              Eform.png
              Force.png
"""

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from ..analysis.plots import plot_parity_elem


def _elem_set(label: str) -> frozenset:
    """'Fe-Co' → frozenset({'Fe', 'Co'})"""
    return frozenset(label.split("-"))


def _match_element(label: str, targets: List[frozenset]) -> bool:
    s = _elem_set(label)
    return s in targets


class PerElementAnalysis:
    """
    Generate per-element parity plots for specified element combinations.

    Args:
        work_dir : working directory (must contain analysis/ subfolder)
        dpi      : plot resolution (default 300)
    """

    def __init__(self, work_dir=None, dpi: int = 300):
        self.work_dir      = Path(work_dir).resolve() if work_dir else Path.cwd()
        self.analysis_root = self.work_dir / "analysis"
        self.output_root   = self.work_dir / "per_element"
        self.dpi           = dpi

    def run(self, elements: List[str]):
        """
        Generate per-element plots for specified element combinations.

        Args:
            elements : list of element labels, e.g. ["Fe", "Fe-Co", "Pt"]
                       Order-insensitive: "Fe-Co" matches "Co-Fe" in the cache.
        """
        if not elements:
            print("[PerElement] No elements specified.")
            return

        targets = [_elem_set(e) for e in elements]
        # canonical label: sorted join (for directory naming)
        canonical = {frozenset(e.split("-")): "-".join(sorted(e.split("-"))) for e in elements}

        # find all (mlip, dataset) pairs that have a cache
        mlip_dirs = [
            d for d in sorted(self.analysis_root.iterdir())
            if d.is_dir() and d.name not in ("cache", "total", "per_element")
        ]

        if not mlip_dirs:
            print("[PerElement] No MLIP directories found under analysis/.")
            return

        for mlip_dir in mlip_dirs:
            mlip_name = mlip_dir.name
            dataset_dirs = [d for d in sorted(mlip_dir.iterdir()) if d.is_dir() and d.name != "total"]

            for dataset_dir in dataset_dirs:
                dataset_name = dataset_dir.name
                cache_dir    = dataset_dir / "cache"

                normal_pq  = cache_dir / "normal_df.parquet"
                anomaly_pq = cache_dir / "anomaly_df.parquet"

                if not normal_pq.exists():
                    print(f"  [SKIP] {mlip_name}/{dataset_name}: no cache found")
                    continue

                normal_df  = pd.read_parquet(normal_pq)
                anomaly_df = pd.read_parquet(anomaly_pq) if anomaly_pq.exists() else pd.DataFrame()

                for target_set in targets:
                    elem_label = canonical[target_set]

                    self._plot_subset(mlip_name, dataset_name, elem_label, target_set,
                                      normal_df, split="normal")
                    if not anomaly_df.empty:
                        self._plot_subset(mlip_name, dataset_name, elem_label, target_set,
                                          anomaly_df, split="anomaly")

    def _plot_subset(self, mlip_name, dataset_name, elem_label, target_set,
                     df, split: str):
        out_dir = self.output_root / elem_label / mlip_name / dataset_name / split

        if (out_dir / "Eform.png").exists():
            print(f"  [SKIP] {elem_label} / {mlip_name} / {dataset_name} / {split} already exists")
            return

        mask = df["element"].apply(lambda x: _elem_set(x) == target_set)
        sub  = df[mask].reset_index(drop=True)

        if sub.empty:
            return

        out_dir.mkdir(parents=True, exist_ok=True)

        # Eform parity
        plot_parity_elem(
            sub["e_form_dft"].values,
            sub["e_form_mlip"].values,
            sub["element"].values,
            title=f"{mlip_name} — {elem_label} $\\mathbf{{E_{{form}}}}$",
            xlabel="DFT $\\mathbf{E_{form}}$ (eV/atom)",
            ylabel="MLIP $\\mathbf{E_{form}}$ (eV/atom)",
            save_path=out_dir / "Eform.png",
            dpi=self.dpi,
            mlip_name=mlip_name,
        )

        # Force parity
        f_dft_rows, f_mlip_rows, f_elem_rows = [], [], []
        for _, row in sub.iterrows():
            fd = np.asarray(list(row["dft_forces"]), dtype=float)
            fm = np.asarray(list(row["mlip_forces"]), dtype=float)
            if fd.shape != fm.shape or fd.ndim != 2:
                continue
            n_at = fd.shape[0]
            f_dft_rows.append(fd.reshape(-1))
            f_mlip_rows.append(fm.reshape(-1))
            f_elem_rows.extend([row["element"]] * (n_at * 3))

        if f_dft_rows:
            plot_parity_elem(
                np.concatenate(f_dft_rows),
                np.concatenate(f_mlip_rows),
                np.array(f_elem_rows, dtype=str),
                title=f"{mlip_name} — {elem_label} $\\mathbf{{Force}}$",
                xlabel="DFT $\\mathbf{Force}$ (eV/Å)",
                ylabel="MLIP $\\mathbf{Force}$ (eV/Å)",
                save_path=out_dir / "Force.png",
                dpi=self.dpi,
                iqr_filter=False,
                mlip_name=mlip_name,
                unit="eV/Å",
            )

        print(f"  [PerElement] {elem_label} / {mlip_name} / {dataset_name} / {split} → {out_dir}")
