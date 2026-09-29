from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.feature_cache import FeatureCache, FeatureCacheKey
from astraquant.research.strategy_config import ComponentSpec


def _require(panel: pd.DataFrame, *columns: str) -> None:
    missing = set(columns) - set(panel.columns)
    if missing:
        raise ValueError(f"signal component missing panel columns: {sorted(missing)}")


def _numeric(panel: pd.DataFrame, column: str) -> pd.Series:
    _require(panel, column)
    return pd.to_numeric(panel[column], errors="coerce")


def _cached(
    *,
    panel: pd.DataFrame,
    cache: FeatureCache,
    context,
    name: str,
    params: dict[str, Any],
    compute,
) -> pd.Series:
    key = FeatureCacheKey.build(
        source_revision=context.source_revision,
        feature_name=name,
        params=params,
        availability_policy=context.availability_policy,
    )
    return cache.get_or_compute_view(key, compute)


def _ema_by_ticker(values: pd.Series, tickers: pd.Series, span: int) -> pd.Series:
    return values.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(span=span, adjust=False, min_periods=span).mean()
    )


def _sma_by_ticker(values: pd.Series, tickers: pd.Series, window: int) -> pd.Series:
    return values.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(window, min_periods=window).mean()
    )


def n_session_high(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    lookback = int(spec.params.get("lookback", 250))
    if lookback <= 1:
        raise ValueError("N_SESSION_HIGH lookback must be > 1")
    close = _numeric(panel, "close")
    prior_high = _cached(
        panel=panel,
        cache=cache,
        context=context,
        name="prior_high",
        params={"lookback": lookback},
        compute=lambda: close.groupby(panel["stock_id"], sort=False).transform(
            lambda s: s.shift(1).rolling(lookback, min_periods=lookback).max()
        ),
    )
    previous_close = close.groupby(panel["stock_id"], sort=False).shift(1)
    previous_prior = prior_high.groupby(panel["stock_id"], sort=False).shift(1)
    return (
        close.gt(prior_high)
        & previous_close.le(previous_prior)
        & prior_high.notna()
    ).fillna(False)


def gap_up(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    threshold = float(spec.params.get("threshold", 0.01))
    unfilled = int(spec.params.get("unfilled_sessions", 0))
    if unfilled:
        raise UnsupportedComponentError(
            "GAP_UP with unfilled_sessions requires an explicit delayed-confirmation "
            "availability rule; it is intentionally not implemented yet"
        )
    open_ = _numeric(panel, "open")
    close = _numeric(panel, "close")
    prior_close = close.groupby(panel["stock_id"], sort=False).shift(1)
    return (open_ / prior_close - 1.0).gt(threshold).fillna(False)


def volume_spike(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    multiplier = float(spec.params.get("multiplier", 1.5))
    lookback = int(spec.params.get("lookback", 20))
    volume = _numeric(panel, "Trading_Volume")
    avg = _cached(
        panel=panel,
        cache=cache,
        context=context,
        name="prior_avg_volume",
        params={"lookback": lookback},
        compute=lambda: volume.groupby(panel["stock_id"], sort=False).transform(
            lambda s: s.shift(1).rolling(lookback, min_periods=lookback).mean()
        ),
    )
    return (volume / avg).gt(multiplier).fillna(False)


def ma_golden_cross(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    fast = int(spec.params["fast"])
    slow = int(spec.params["slow"])
    if not 1 <= fast < slow:
        raise ValueError("MA_GOLDEN_CROSS requires 1 <= fast < slow")
    close = _numeric(panel, "close")
    fast_ma = _cached(
        panel=panel, cache=cache, context=context,
        name="sma", params={"window": fast},
        compute=lambda: _sma_by_ticker(close, panel["stock_id"], fast),
    )
    slow_ma = _cached(
        panel=panel, cache=cache, context=context,
        name="sma", params={"window": slow},
        compute=lambda: _sma_by_ticker(close, panel["stock_id"], slow),
    )
    prev_fast = fast_ma.groupby(panel["stock_id"], sort=False).shift(1)
    prev_slow = slow_ma.groupby(panel["stock_id"], sort=False).shift(1)
    return (fast_ma.gt(slow_ma) & prev_fast.le(prev_slow)).fillna(False)


def macd_cross_above_zero(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    fast = int(spec.params.get("fast", 12))
    slow = int(spec.params.get("slow", 26))
    signal = int(spec.params.get("signal", 9))
    if not 1 <= fast < slow or signal <= 0:
        raise ValueError("invalid MACD parameters")
    close = _numeric(panel, "close")
    ema_fast = _cached(
        panel=panel, cache=cache, context=context,
        name="ema", params={"span": fast},
        compute=lambda: _ema_by_ticker(close, panel["stock_id"], fast),
    )
    ema_slow = _cached(
        panel=panel, cache=cache, context=context,
        name="ema", params={"span": slow},
        compute=lambda: _ema_by_ticker(close, panel["stock_id"], slow),
    )
    macd = ema_fast - ema_slow
    prev = macd.groupby(panel["stock_id"], sort=False).shift(1)
    return (macd.gt(0) & prev.le(0)).fillna(False)


def _stochastic_kd(*, panel, lookback: int, k_smooth: int, d_smooth: int):
    high = _numeric(panel, "max")
    low = _numeric(panel, "min")
    close = _numeric(panel, "close")
    lowest = low.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.rolling(lookback, min_periods=lookback).min()
    )
    highest = high.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.rolling(lookback, min_periods=lookback).max()
    )
    denom = highest - lowest
    rsv = ((close - lowest) / denom.replace(0, np.nan) * 100.0).clip(0, 100)
    k = rsv.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.ewm(alpha=1 / k_smooth, adjust=False, min_periods=k_smooth).mean()
    )
    d = k.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.ewm(alpha=1 / d_smooth, adjust=False, min_periods=d_smooth).mean()
    )
    return k, d


def kd_low_zone_golden_cross(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    lookback = int(spec.params.get("lookback", 9))
    k_smooth = int(spec.params.get("k_smooth", 3))
    d_smooth = int(spec.params.get("d_smooth", 3))
    low_zone = float(spec.params.get("low_zone", 20))
    k, d = _stochastic_kd(
        panel=panel,
        lookback=lookback,
        k_smooth=k_smooth,
        d_smooth=d_smooth,
    )
    pk = k.groupby(panel["stock_id"], sort=False).shift(1)
    pd_ = d.groupby(panel["stock_id"], sort=False).shift(1)
    return (k.gt(d) & pk.le(pd_) & pk.le(low_zone) & pd_.le(low_zone)).fillna(False)


def _rsi_value(*, panel, lookback: int) -> pd.Series:
    close = _numeric(panel, "close")
    delta = close.groupby(panel["stock_id"], sort=False).diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.ewm(alpha=1 / lookback, adjust=False, min_periods=lookback).mean()
    )
    avg_loss = loss.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.ewm(alpha=1 / lookback, adjust=False, min_periods=lookback).mean()
    )
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.where(avg_loss.ne(0), 100.0)


def rsi_cross(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    lookback = int(spec.params.get("lookback", 14))
    level = float(spec.params.get("level", 50))
    rsi = _cached(
        panel=panel, cache=cache, context=context,
        name="rsi", params={"lookback": lookback},
        compute=lambda: _rsi_value(panel=panel, lookback=lookback),
    )
    prev = rsi.groupby(panel["stock_id"], sort=False).shift(1)
    return (rsi.gt(level) & prev.le(level)).fillna(False)


def rsi_filter(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    lookback = int(spec.params.get("lookback", 14))
    rsi = _cached(
        panel=panel, cache=cache, context=context,
        name="rsi", params={"lookback": lookback},
        compute=lambda: _rsi_value(panel=panel, lookback=lookback),
    )
    result = pd.Series(True, index=panel.index)
    if "min" in spec.params:
        result &= rsi.ge(float(spec.params["min"]))
    if "max" in spec.params:
        result &= rsi.le(float(spec.params["max"]))
    return result.fillna(False)


def rsi_rank(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    lookback = int(spec.params.get("lookback", 14))
    return _cached(
        panel=panel, cache=cache, context=context,
        name="rsi", params={"lookback": lookback},
        compute=lambda: _rsi_value(panel=panel, lookback=lookback),
    )


def bollinger_upper_break(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    window = int(spec.params.get("window", 20))
    stddev = float(spec.params.get("stddev", 2.0))
    close = _numeric(panel, "close")
    mid = _sma_by_ticker(close, panel["stock_id"], window)
    std = close.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.rolling(window, min_periods=window).std(ddof=0)
    )
    upper = mid + stddev * std
    prev_close = close.groupby(panel["stock_id"], sort=False).shift(1)
    prev_upper = upper.groupby(panel["stock_id"], sort=False).shift(1)
    return (close.gt(upper) & prev_close.le(prev_upper)).fillna(False)


def pullback_reclaim(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    window = int(spec.params.get("ma_window", 20))
    tolerance = float(spec.params.get("touch_tolerance", 0.01))
    close = _numeric(panel, "close")
    low = _numeric(panel, "min")
    ma = _sma_by_ticker(close, panel["stock_id"], window)
    prev_close = close.groupby(panel["stock_id"], sort=False).shift(1)
    prev_low = low.groupby(panel["stock_id"], sort=False).shift(1)
    prev_ma = ma.groupby(panel["stock_id"], sort=False).shift(1)
    touched = prev_low.le(prev_ma * (1 + tolerance))
    return (close.gt(ma) & prev_close.le(prev_ma) & touched).fillna(False)


def consecutive_up_days(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    sessions = int(spec.params.get("sessions", 3))
    if sessions <= 0:
        raise ValueError("CONSECUTIVE_UP_DAYS sessions must be positive")
    close = _numeric(panel, "close")
    up = close.gt(close.groupby(panel["stock_id"], sort=False).shift(1)).astype(float)
    count = up.groupby(panel["stock_id"], sort=False).transform(
        lambda s: s.rolling(sessions, min_periods=sessions).sum()
    )
    return count.eq(float(sessions)).fillna(False)


def column_threshold(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    column = str(spec.params["column"])
    values = _numeric(panel, column)
    result = pd.Series(True, index=panel.index)
    if "min" in spec.params:
        result &= values.ge(float(spec.params["min"]))
    if "max" in spec.params:
        result &= values.le(float(spec.params["max"]))
    return result.fillna(False)


def column_value(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    return _numeric(panel, str(spec.params["column"]))


def long_term_trend_structure(*, panel, spec: ComponentSpec, cache, context) -> pd.Series:
    """O'Neil-style long-term trend structure using daily equivalents.

    Defaults use 50 sessions (~W10) and 200 sessions (=W40), with both moving
    averages required to slope upward. The fast/slow spread band is configurable
    and is evaluated as fast_ma / slow_ma - 1.
    """

    fast = int(spec.params.get("fast_sessions", 50))
    slow = int(spec.params.get("slow_sessions", 200))
    slope_lookback = int(spec.params.get("slope_lookback_sessions", 10))
    min_spread = float(spec.params.get("min_fast_slow_spread", 0.0))
    max_spread_raw = spec.params.get("max_fast_slow_spread")
    max_spread = None if max_spread_raw is None else float(max_spread_raw)

    if not 1 <= fast < slow:
        raise ValueError("LONG_TERM_TREND_STRUCTURE requires 1 <= fast < slow")
    if slope_lookback <= 0:
        raise ValueError("slope_lookback_sessions must be positive")
    if min_spread < 0:
        raise ValueError("min_fast_slow_spread must be non-negative")
    if max_spread is not None and max_spread < min_spread:
        raise ValueError("max_fast_slow_spread must be >= min_fast_slow_spread")

    close = _numeric(panel, "close")
    fast_ma = _cached(
        panel=panel,
        cache=cache,
        context=context,
        name="sma",
        params={"window": fast},
        compute=lambda: _sma_by_ticker(close, panel["stock_id"], fast),
    )
    slow_ma = _cached(
        panel=panel,
        cache=cache,
        context=context,
        name="sma",
        params={"window": slow},
        compute=lambda: _sma_by_ticker(close, panel["stock_id"], slow),
    )
    fast_prev = fast_ma.groupby(panel["stock_id"], sort=False).shift(slope_lookback)
    slow_prev = slow_ma.groupby(panel["stock_id"], sort=False).shift(slope_lookback)
    spread = fast_ma / slow_ma - 1.0

    result = (
        close.gt(fast_ma)
        & fast_ma.gt(slow_ma)
        & fast_ma.gt(fast_prev)
        & slow_ma.gt(slow_prev)
        & spread.ge(min_spread)
    )
    if max_spread is not None:
        result &= spread.le(max_spread)
    return result.fillna(False)
