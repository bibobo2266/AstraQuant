from __future__ import annotations

import math

import pandas as pd


ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
BREAK_LOW_WINDOW = 20


class Baseline60DMathError(ValueError):
    pass


def atr14_sma_from_true_range(true_range: pd.Series) -> pd.Series:
    """Return the frozen baseline ATR14 simple moving average.

    The input must already be the approved sequence of true-range observations
    on one consistent price coordinate. This helper deliberately does not choose
    a corporate-action transform, a valid-bar sequence, or simulator timing.
    """

    tr = pd.to_numeric(true_range, errors="coerce")
    return tr.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()


def atr_from_entry_stop_level(entry_anchor: float, atr_value: float) -> float:
    """Compute entry_anchor - 3 * ATR for one already-normalized observation."""

    entry = float(entry_anchor)
    atr = float(atr_value)
    if not math.isfinite(entry) or entry <= 0:
        raise Baseline60DMathError("entry_anchor must be finite and positive")
    if not math.isfinite(atr) or atr < 0:
        raise Baseline60DMathError("atr_value must be finite and non-negative")
    return entry - ATR_MULTIPLIER * atr


def atr_from_entry_stop_trigger(
    *,
    close: float | None,
    entry_anchor: float | None,
    atr_value: float | None,
) -> bool | pd._libs.missing.NAType:
    """Frozen close-confirmed comparator; missing inputs stay unknown."""

    values = (close, entry_anchor, atr_value)
    if any(value is None or pd.isna(value) for value in values):
        return pd.NA
    level = atr_from_entry_stop_level(float(entry_anchor), float(atr_value))
    return bool(float(close) <= level)


def break_n_day_low_trigger(
    *,
    close: float | None,
    prior_low_reference: float | None,
) -> bool | pd._libs.missing.NAType:
    """Apply only the frozen strict comparator close < prior-low reference.

    Construction of the 20-observation reference remains outside this helper
    until the baseline's valid-observed-bar / CA-coordinate contract is frozen.
    """

    if close is None or prior_low_reference is None:
        return pd.NA
    if pd.isna(close) or pd.isna(prior_low_reference):
        return pd.NA
    return bool(float(close) < float(prior_low_reference))
