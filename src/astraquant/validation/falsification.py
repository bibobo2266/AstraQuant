from __future__ import annotations

from collections.abc import Callable
import numpy as np


def permutation_test(
    observed: float,
    null_samples: list[float] | np.ndarray,
    *,
    alternative: str = "greater",
) -> dict[str, float]:
    """Compute an empirical permutation p-value from pre-generated null samples.

    The caller is responsible for generating null samples in a way that
    respects the time-series structure of the experiment.
    """
    null = np.asarray(null_samples, dtype=float)
    null = null[np.isfinite(null)]
    if null.size == 0:
        raise ValueError("null_samples must contain at least one finite value")

    if alternative == "greater":
        exceed = np.sum(null >= observed)
    elif alternative == "less":
        exceed = np.sum(null <= observed)
    elif alternative == "two-sided":
        exceed = np.sum(np.abs(null) >= abs(observed))
    else:
        raise ValueError("alternative must be greater, less, or two-sided")

    p_value = float((exceed + 1) / (null.size + 1))
    return {
        "observed": float(observed),
        "null_mean": float(np.mean(null)),
        "null_std": float(np.std(null, ddof=1)) if null.size > 1 else 0.0,
        "p_value": p_value,
        "n_null": float(null.size),
    }


def run_placebo(
    scorer: Callable[[np.ndarray], float],
    values: list[float] | np.ndarray,
    *,
    n_permutations: int,
    seed: int = 0,
) -> dict[str, object]:
    """Simple IID placebo harness for non-temporal toy checks.

    Time-series research should supply block/stationary-bootstrap or other
    structure-preserving nulls instead of using this helper blindly.
    """
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    observed = float(scorer(x))
    null = [float(scorer(rng.permutation(x))) for _ in range(n_permutations)]
    result = permutation_test(observed, null)
    result["seed"] = seed
    result["warning"] = (
        "IID permutation destroys temporal dependence; use a structure-preserving "
        "null for time-series inference."
    )
    return result
