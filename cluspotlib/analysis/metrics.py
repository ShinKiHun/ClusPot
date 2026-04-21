"""
ClusterBench Metrics Module

Collection of statistical metric calculation functions for E_form and forces.
"""

import numpy as np


def _as_1d_finite(a, b):
    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)
    m = np.isfinite(a) & np.isfinite(b)
    return a[m], b[m]


def _rankdata_average_ties(x):
    """
    Rankdata implementation using average-rank method for ties.
    Implemented without scipy.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    n = x.size
    if n == 0:
        return x

    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(n, dtype=float)

    i = 0
    r = 1.0
    while i < n:
        j = i
        while j + 1 < n and x[order[j + 1]] == x[order[i]]:
            j += 1
        k = j - i + 1
        avg_rank = (r + (r + k - 1.0)) / 2.0
        ranks[order[i:j + 1]] = avg_rank
        r += k
        i = j + 1

    return ranks


def mae(a, b):
    return float(np.mean(np.abs(np.array(a) - np.array(b))))


def rmse(a, b):
    return float(np.sqrt(np.mean((np.array(a) - np.array(b)) ** 2)))


def r2(a, b):
    """
    Coefficient of determination (paper-standard):
      R^2 = 1 - SSE/SST
    where:
      SSE = sum((a - b)^2)
      SST = sum((a - mean(a))^2)

    a: true (DFT), b: pred (MLIP)
    """
    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)

    m = np.isfinite(a) & np.isfinite(b)
    a = a[m]
    b = b[m]

    if a.size < 2:
        return float("nan")

    ss_res = float(np.sum((a - b) ** 2))
    ss_tot = float(np.sum((a - float(np.mean(a))) ** 2))

    if ss_tot <= 0.0:
        return float("nan")

    return float(1.0 - ss_res / ss_tot)


def pearson(a, b):
    a, b = _as_1d_finite(a, b)
    if a.size < 2:
        return float("nan")
    if float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a, b):
    a, b = _as_1d_finite(a, b)
    if a.size < 2:
        return float("nan")

    ra = _rankdata_average_ties(a)
    rb = _rankdata_average_ties(b)

    if float(np.std(ra)) == 0.0 or float(np.std(rb)) == 0.0:
        return float("nan")

    return float(np.corrcoef(ra, rb)[0, 1])


def cosine_sim(a, b):
    a, b = np.array(a).flatten(), np.array(b).flatten()
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return float("nan")
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def energy_metrics(dft, mlip):
    a, b = np.array(dft), np.array(mlip)
    return {
        "MAE": mae(a, b),
        "RMSE": rmse(a, b),
        "R2": r2(a, b),
        "Pearson": pearson(a, b),
        "Spearman": spearman(a, b),
    }


def force_metrics(dft_forces, mlip_forces):
    """
    dft_forces, mlip_forces:
      - list of forces per sample
      - each sample: (n_atoms, 3) list/ndarray

    Policy:
      - exclude samples whose shape is not (n, 3)
      - exclude samples with atom count mismatch instead of cropping (data integrity first)
      - return the number of excluded mismatch samples as n_mismatch
    """
    dft_list = []
    mlip_list = []
    n_mismatch = 0
    n_badshape = 0

    for df, mf in zip(dft_forces, mlip_forces):
        df_arr = np.asarray(df, dtype=float)
        mf_arr = np.asarray(mf, dtype=float)

        if (
            df_arr.ndim != 2 or mf_arr.ndim != 2
            or df_arr.shape[1] != 3 or mf_arr.shape[1] != 3
        ):
            n_badshape += 1
            continue

        if df_arr.shape[0] != mf_arr.shape[0]:
            n_mismatch += 1
            continue

        n = df_arr.shape[0]
        if n == 0:
            n_badshape += 1
            continue

        dft_list.append(df_arr)
        mlip_list.append(mf_arr)

    if not dft_list:
        return {
            "MAE": float("nan"),
            "RMSE": float("nan"),
            "R2": float("nan"),
            "Pearson": float("nan"),
            "Spearman": float("nan"),
            "cosine": float("nan"),
            "n_mismatch": int(n_mismatch),
            "n_badshape": int(n_badshape),
            "n_used_samples": 0,
        }

    dft_flat = np.concatenate(dft_list, axis=0).reshape(-1)
    mlip_flat = np.concatenate(mlip_list, axis=0).reshape(-1)

    m = energy_metrics(dft_flat, mlip_flat)

    cos_sims = []
    for df_arr, mf_arr in zip(dft_list, mlip_list):
        cs = cosine_sim(df_arr, mf_arr)
        if not np.isnan(cs):
            cos_sims.append(cs)

    m["cosine"] = float(np.mean(cos_sims)) if cos_sims else float("nan")
    m["AFwT"] = _afwt(dft_flat, mlip_flat)
    m["n_mismatch"] = int(n_mismatch)
    m["n_badshape"] = int(n_badshape)
    m["n_used_samples"] = int(len(dft_list))
    return m


def fwt_curve_data(dft_forces, mlip_forces,
                   t_min: float = 0.01, t_max: float = 1.0, n_steps: int = 100):
    """
    Return FwT(%) curve data for each threshold.

    Returns:
        thresholds : np.ndarray (n_steps,)
        fwt_pct   : np.ndarray (n_steps,)  — % within threshold at each threshold value
        None, None if no valid data
    """
    dft_list, mlip_list = [], []
    for df, mf in zip(dft_forces, mlip_forces):
        df_arr = np.asarray(df, dtype=float)
        mf_arr = np.asarray(mf, dtype=float)
        if (df_arr.ndim != 2 or mf_arr.ndim != 2
                or df_arr.shape[1] != 3 or mf_arr.shape[1] != 3
                or df_arr.shape[0] != mf_arr.shape[0]
                or df_arr.shape[0] == 0):
            continue
        dft_list.append(df_arr)
        mlip_list.append(mf_arr)

    if not dft_list:
        return None, None

    dft_flat  = np.concatenate(dft_list, axis=0).reshape(-1)
    mlip_flat = np.concatenate(mlip_list, axis=0).reshape(-1)
    diff = np.abs(mlip_flat - dft_flat)
    m = np.isfinite(diff)
    diff = diff[m]
    if diff.size == 0:
        return None, None

    thresholds = np.linspace(t_min, t_max, n_steps)
    fwt_pct = np.array([(diff < t).mean() * 100.0 for t in thresholds])
    return thresholds, fwt_pct


def _afwt(dft_flat: np.ndarray, mlip_flat: np.ndarray,
           t_min: float = 0.01, t_max: float = 1.0) -> float:
    """
    AFwT (Average Force within Threshold).

    Computes the mean of FwT(t) over [t_min, t_max] as a continuous integral:

        AFwT = 1/(t_max - t_min) * ∫[t_min, t_max] FwT(t) dt

    FwT(t) = P(|F_mlip - F_dft| < t) is the empirical CDF of absolute errors,
    so the integral is computed analytically (no discretization):

        ∫[a,b] F(t) dt = (b-a) * P(X < a) + (1/n) * Σ (b - xᵢ) for xᵢ ∈ [a, b]
    """
    diff = np.abs(mlip_flat - dft_flat)
    m = np.isfinite(diff)
    diff = diff[m]
    if diff.size == 0:
        return float("nan")

    diff_sorted = np.sort(diff)
    n = len(diff_sorted)

    count_below = int(np.searchsorted(diff_sorted, t_min, side="left"))
    in_range = diff_sorted[(diff_sorted >= t_min) & (diff_sorted <= t_max)]

    integral = (t_max - t_min) * count_below / n + float(np.sum(t_max - in_range)) / n
    return float(integral / (t_max - t_min) * 100.0)
