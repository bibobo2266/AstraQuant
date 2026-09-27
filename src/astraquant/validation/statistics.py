from __future__ import annotations

import numpy as np
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.sandwich_covariance import cov_hac
import statsmodels.api as sm


def bh_fdr(p_values: list[float], alpha: float = 0.05) -> dict[str, np.ndarray]:
    reject, q_values, _, _ = multipletests(p_values, alpha=alpha, method="fdr_bh")
    return {"reject": reject, "q_values": q_values}


def newey_west_mean_test(values: list[float] | np.ndarray, maxlags: int = 5) -> dict[str, float]:
    y = np.asarray(values, dtype=float)
    if y.ndim != 1 or len(y) < 3:
        raise ValueError("values must be one-dimensional with at least 3 observations")
    x = np.ones((len(y), 1))
    model = sm.OLS(y, x).fit()
    cov = cov_hac(model, nlags=maxlags)
    se = float(np.sqrt(cov[0, 0]))
    mean = float(model.params[0])
    t_stat = mean / se if se > 0 else float("nan")
    return {"mean": mean, "se_newey_west": se, "t_stat": t_stat}


def parameter_plateau(values: list[float], scores: list[float], tolerance: float = 0.05) -> dict[str, object]:
    if len(values) != len(scores) or not values:
        raise ValueError("values and scores must have equal non-zero length")
    arr = np.asarray(scores, dtype=float)
    best = float(np.nanmax(arr))
    threshold = best * (1 - tolerance) if best >= 0 else best * (1 + tolerance)
    mask = arr >= threshold
    admitted = [float(v) for v, keep in zip(values, mask) if keep]
    return {"best_score": best, "tolerance": tolerance, "plateau_values": admitted, "plateau_width": len(admitted)}
