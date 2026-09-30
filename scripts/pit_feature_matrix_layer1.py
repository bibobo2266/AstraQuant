from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from astraquant.research.feature_cache import FeatureCache, FeatureCacheKey


FORMULA_VERSION = "pit_feature_matrix_layer1_v1"
AVAILABILITY_POLICY = "AFTER_SESSION_CLOSE"
RANK_METHOD = "average"
RANK_MIN_N = 2


@dataclass(frozen=True)
class Layer1Parameters:
    ma_windows: tuple[int, ...] = (20, 60, 120, 250)
    ma_slope_lookback: int = 10
    high_low_lookback: int = 250
    atr_period: int = 21
    rv_windows: tuple[int, ...] = (20, 60)
    bollinger_window: int = 14
    bollinger_stddev: float = 2.0
    bollinger_percentile_lookback: int = 120
    volume_short_window: int = 5
    volume_mid_window: int = 20
    volume_long_window: int = 60
    amount_window: int = 20
    up_day_volume_window: int = 20
    rsi_windows: tuple[int, ...] = (13, 14, 26)
    rsi_difference_fast: int = 13
    rsi_difference_slow: int = 26
    rsi_slope_window: int = 14
    rsi_slope_lookback: int = 5
    kd_lookback: int = 9
    kd_k_smooth: int = 3
    kd_d_smooth: int = 3
    kd_high_level: float = 80.0
    kd_low_level: float = 20.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_slope_lookback: int = 5
    cci_window: int = 20
    williams_window: int = 14
    relative_strength_horizons: tuple[int, ...] = (20, 60, 120)
    beta_window: int = 60
    market_ma_window: int = 200
    market_rv_window: int = 20
    market_position_window: int = 252
    tier_count: int = 3


@dataclass(frozen=True)
class FeatureSpec:
    item_id: str
    feature_key: str
    column: str
    parameter_version: str
    table: str
    dtype: str
    unit: str
    formula: str
    lookback: str
    smoothing: str
    price_volume_semantics: str
    includes_today: str
    input_available_at: str
    output_available_at: str
    missing_policy: str
    parameter_origin: str
    cross_section_rank: bool
    status: str = "COMPLETE"


def _spec(
    item_id: str,
    key: str,
    col: str,
    version: str,
    *,
    table: str = "stock_features",
    dtype: str = "float",
    unit: str = "ratio",
    formula: str,
    lookback: str,
    smoothing: str = "none",
    semantics: str = "adjusted EOD research price; source daily volume/amount",
    includes_today: str = "yes",
    input_available_at: str = "session close",
    output_available_at: str = "after same-session close",
    missing_policy: str = "null; no zero-fill or forward-fill",
    origin: str = "research implementation",
    rank: bool = True,
    status: str = "COMPLETE",
) -> FeatureSpec:
    return FeatureSpec(
        item_id=item_id,
        feature_key=key,
        column=col,
        parameter_version=version,
        table=table,
        dtype=dtype,
        unit=unit,
        formula=formula,
        lookback=lookback,
        smoothing=smoothing,
        price_volume_semantics=semantics,
        includes_today=includes_today,
        input_available_at=input_available_at,
        output_available_at=output_available_at,
        missing_policy=missing_policy,
        parameter_origin=origin,
        cross_section_rank=rank,
        status=status,
    )


def feature_specs(p: Layer1Parameters | None = None) -> list[FeatureSpec]:
    p = p or Layer1Parameters()
    out: list[FeatureSpec] = []
    for w in p.ma_windows:
        out.append(_spec(
            "L2-T01", "ma_position", f"close_to_ma{w}", f"MA{w}",
            formula=f"adjusted_close / SMA{w}(adjusted_close) - 1",
            lookback=f"{w} valid stock sessions",
            origin="research translation; windows from owner inventory",
        ))
    out.append(_spec(
        "L2-T01", "ma_alignment", "ma_order_score", "MA20/60/120/250",
        formula="mean(MA20>MA60, MA60>MA120, MA120>MA250)",
        lookback="250 valid stock sessions",
        unit="0..1",
        origin="research translation",
    ))
    for w in p.ma_windows:
        out.append(_spec(
            "L2-T01", "ma_slope", f"ma{w}_slope10", f"MA{w}/10",
            formula=f"SMA{w}_t / SMA{w}_(t-10) - 1",
            lookback=f"{w}+10 valid stock sessions",
            origin="repo-existing slope lookback=10 reused from LONG_TERM_TREND_STRUCTURE",
        ))

    out += [
        _spec("L2-T02", "distance_250_high", "distance_250_high", "250",
              formula="adjusted_close / rolling_max250(adjusted_high) - 1",
              lookback="250 valid stock sessions"),
        _spec("L2-T02", "distance_250_low", "distance_250_low", "250",
              formula="adjusted_close / rolling_min250(adjusted_low) - 1",
              lookback="250 valid stock sessions"),
        _spec("L2-T02", "sessions_since_prior_high", "sessions_since_prior_250_high", "250",
              formula="sessions since most recent maximum adjusted_high in prior 250 sessions; today excluded",
              lookback="prior 250 valid stock sessions", unit="sessions",
              includes_today="no", origin="research translation"),
        _spec("L2-T03", "atr_pct", "atr21_pct", "ATR21",
              formula="Wilder ATR21 / adjusted_close",
              lookback="21 valid TR observations", smoothing="Wilder; SMA seed then recursive alpha=1/21",
              origin="repo-existing VCP round1 ATR21 definition"),
        _spec("L2-T03", "realized_volatility", "rv20", "20",
              formula="std(daily adjusted simple return,20)*sqrt(252)",
              lookback="20 return observations", unit="annualized volatility"),
        _spec("L2-T03", "realized_volatility", "rv60", "60",
              formula="std(daily adjusted simple return,60)*sqrt(252)",
              lookback="60 return observations", unit="annualized volatility"),
        _spec("L2-T03", "volatility_ratio", "rv20_rv60_ratio", "20/60",
              formula="rv20 / rv60", lookback="60 return observations",
              missing_policy="null when rv60 is missing or zero"),
        _spec("L2-T04", "bollinger_bandwidth", "bollinger_bandwidth_14_2", "14/2",
              formula="(upper14_2-lower14_2)/middle14",
              lookback="14 valid stock sessions", origin="repo-existing Bollinger window=14,stddev=2"),
        _spec("L2-T04", "bollinger_bandwidth_percentile", "bollinger_bandwidth_pctile120", "14/2/120",
              formula="time-series percentile rank of current bandwidth inside trailing 120 bandwidth observations",
              lookback="14+119 valid stock sessions", unit="0..1",
              origin="repo-existing Bollinger percentile_lookback=120"),
        _spec("L2-T04", "bollinger_channel_position", "bollinger_channel_position_14_2", "14/2",
              formula="(adjusted_close-lower)/(upper-lower)",
              lookback="14 valid stock sessions", unit="channel units",
              missing_policy="null when band width is missing or zero"),
        _spec("L2-T05", "volume_ratio", "volume_ratio_5_20", "5/20",
              formula="mean(volume,5)/mean(volume,20)", lookback="20 valid stock sessions",
              semantics="adjusted-series Trading_Volume; same source daily amount"),
        _spec("L2-T05", "volume_ratio", "volume_ratio_20_60", "20/60",
              formula="mean(volume,20)/mean(volume,60)", lookback="60 valid stock sessions",
              semantics="adjusted-series Trading_Volume; same source daily amount"),
        _spec("L2-T05", "average_trading_amount", "amount_mean20_twd", "20",
              formula="mean(Trading_money,20)", lookback="20 valid stock sessions",
              unit="TWD/day", semantics="source Trading_money"),
        _spec("L2-T05", "turnover_value_ratio", "turnover_value_ratio", "daily",
              formula="Trading_money / FinMind TaiwanStockMarketValue.market_value",
              lookback="same date", unit="value turnover ratio",
              semantics="source Trading_money / source market_value",
              missing_policy="null when market_value is missing or <=0",
              origin="research implementation; value-turnover proxy, not share-turnover"),
        _spec("L2-T05", "volume_dryup_ratio", "volume_dryup_prior5_20", "prior5/prior20",
              formula="mean(volume,t-5..t-1)/mean(volume,t-20..t-1)",
              lookback="prior 20 valid stock sessions", includes_today="no",
              semantics="adjusted-series Trading_Volume",
              missing_policy="null when prior20 mean is missing or zero"),
        _spec("L2-T05", "up_day_volume_share", "up_day_volume_share20", "20",
              formula="sum(volume where adjusted_close return>0,20)/sum(volume,20)",
              lookback="20 valid stock sessions", unit="0..1",
              semantics="adjusted close direction + source Trading_Volume",
              missing_policy="null when rolling total volume is missing or zero"),
    ]
    for w in p.rsi_windows:
        out.append(_spec(
            "L2-T06", "rsi_level", f"rsi{w}", f"RSI{w}",
            formula=f"Wilder RSI({w}) on adjusted_close",
            lookback=f"{w} return observations", unit="0..100",
            smoothing=f"Wilder alpha=1/{w}",
            origin="repo-registered RSI lookbacks 13/14/26",
        ))
    out += [
        _spec("L2-T06", "rsi_difference", "rsi13_minus_rsi26", "13-26",
              formula="RSI13-RSI26", lookback="26 return observations", unit="RSI points",
              origin="repo-registered RSI_RELATIVE 13/26"),
        _spec("L2-T06", "rsi_slope", "rsi14_slope5", "RSI14/5",
              formula="RSI14_t-RSI14_(t-5)", lookback="14+5 return observations", unit="RSI points",
              origin="research implementation; RSI14 registered, slope lookback=5 routine choice"),
        _spec("L2-T07", "kd_k", "kd_k_9_3_3", "9/3/3",
              formula="RSV9 smoothed with Wilder-style alpha=1/3", lookback="9 plus smoothing warmup",
              unit="0..100", smoothing="K alpha=1/3", origin="repo-registered KD 9/3/3"),
        _spec("L2-T07", "kd_d", "kd_d_9_3_3", "9/3/3",
              formula="K smoothed with Wilder-style alpha=1/3", lookback="9 plus K/D smoothing warmup",
              unit="0..100", smoothing="D alpha=1/3", origin="repo-registered KD 9/3/3"),
        _spec("L2-T07", "kd_high_saturation_days", "kd_high_saturation_days80", "80",
              formula="consecutive sessions K>=80 and D>=80 through today", lookback="stateful after KD warmup",
              unit="sessions", origin="repo-registered high_level=80"),
        _spec("L2-T07", "kd_low_saturation_days", "kd_low_saturation_days20", "20",
              formula="consecutive sessions K<=20 and D<=20 through today", lookback="stateful after KD warmup",
              unit="sessions", origin="repo-registered low-zone=20"),
        _spec("L2-T08", "macd_histogram", "macd_hist_12_26_9", "12/26/9",
              formula="EMA12-EMA26-EMA9(EMA12-EMA26)", lookback="EMA warmup through signal EMA",
              unit="adjusted price", smoothing="EMA adjust=False",
              origin="research correction: histogram, not legacy MACD-line proxy"),
        _spec("L2-T08", "macd_histogram_slope", "macd_hist_slope5", "12/26/9 slope5",
              formula="MACD_hist_t-MACD_hist_(t-5)", lookback="MACD histogram warmup +5",
              unit="adjusted price", smoothing="EMA adjust=False", origin="research implementation"),
        _spec("L2-T08", "cci", "cci20", "20",
              formula="(typical_price-SMA20(typical_price))/(0.015*mean_abs_deviation20)",
              lookback="20 valid stock sessions", unit="CCI", origin="research implementation"),
        _spec("L2-T08", "williams_r", "williams_r14", "14",
              formula="-100*(rolling_high14-close)/(rolling_high14-rolling_low14)",
              lookback="14 valid stock sessions", unit="-100..0", origin="research implementation"),
    ]

    out += [
        _spec("L3-G01", "pit_industry", "industry", "PIT interval", dtype="string", unit="category",
              formula="industry from causal industry_pit interval valid on row date", lookback="same-date PIT interval",
              semantics="PIT industry reference", input_available_at="industry valid_from",
              rank=False, origin="repo-existing official MOPS PIT source"),
        _spec("L3-G01", "market_cap", "market_cap_twd", "daily", unit="TWD",
              formula="FinMind TaiwanStockMarketValue.market_value on same date", lookback="same date",
              semantics="FinMind market_value", origin="existing source dataset"),
        _spec("L3-G01", "market_cap_tier", "market_cap_tier", "tercile", dtype="category", unit="SMALL/MID/LARGE",
              formula="same-day eligible-universe market_cap percentile tercile", lookback="same-day cross-section",
              rank=False, origin="research implementation"),
        _spec("L3-G01", "liquidity_tier", "liquidity_tier", "tercile", dtype="category", unit="LOW/MID/HIGH",
              formula="same-day eligible-universe amount_mean20 percentile tercile", lookback="same-day cross-section",
              rank=False, origin="research implementation"),
        _spec("L3-G01", "volatility_cluster", "volatility_cluster", "tercile", dtype="category", unit="LOW/MID/HIGH",
              formula="same-day eligible-universe rv60 percentile tercile", lookback="same-day cross-section",
              rank=False, origin="research implementation"),
        _spec("L3-G02", "theme_membership", "theme_membership", "dated membership", dtype="boolean", unit="flag",
              formula="dated owner theme membership", lookback="dated membership interval",
              semantics="dated theme source only", input_available_at="membership from-date",
              rank=False, status="BLOCKED_DATA",
              missing_policy="BLOCKED_DATA: no persisted dated theme membership source is available in repo",
              origin="owner observation"),
    ]
    for h in p.relative_strength_horizons:
        out.append(_spec(
            "L3-R01", "relative_strength_market", f"rs_market_{h}", f"market/{h}",
            formula=f"stock adjusted return({h}) - TAIEX total-return-index return({h})",
            lookback=f"{h} valid sessions", unit="return spread",
            semantics="stock adjusted close vs FinMind TAIEX total-return index",
            origin="research implementation; total-return benchmark is repo canonical",
        ))
        out.append(_spec(
            "L3-R01", "relative_strength_industry", f"rs_industry_{h}", f"industry/{h}",
            formula=f"stock adjusted return({h}) - same-day PIT-industry median stock return({h})",
            lookback=f"{h} valid sessions + same-day eligible cross-section", unit="return spread",
            semantics="stock adjusted close + PIT industry",
            missing_policy="null when PIT industry or industry return is unavailable",
            origin="research implementation",
        ))
    out += [
        _spec("L3-R02", "beta", "beta60_market", "60",
              formula="rolling cov(stock_ret1,market_ret1)/var(market_ret1)", lookback="60 aligned daily returns",
              unit="beta", semantics="stock adjusted simple return vs TAIEX total-return simple return",
              missing_policy="null when market variance is missing or zero", origin="research implementation"),
        _spec("L3-R02", "market_correlation", "corr60_market", "60",
              formula="rolling Pearson correlation(stock_ret1,market_ret1)", lookback="60 aligned daily returns",
              unit="-1..1", semantics="stock adjusted simple return vs TAIEX total-return simple return",
              origin="research implementation"),
        _spec("L3-R02", "residual_volatility", "resid_vol60_market", "60",
              formula="sqrt(max(var(stock)-cov(stock,market)^2/var(market),0))*sqrt(252)",
              lookback="60 aligned daily returns", unit="annualized volatility",
              semantics="single-factor rolling residual variance vs TAIEX total-return index",
              missing_policy="null when market variance is missing or zero", origin="research implementation"),
    ]
    for h in p.relative_strength_horizons:
        out.append(_spec(
            "L3-I01", "industry_relative_strength_market", f"industry_rs_market_{h}", f"{h}",
            formula=f"PIT-industry median stock return({h}) - TAIEX total-return-index return({h})",
            lookback=f"{h} valid sessions + same-day eligible industry cross-section", unit="return spread",
            semantics="PIT-industry eligible members + total-return benchmark",
            missing_policy="null when PIT industry or market return is unavailable",
            origin="research implementation",
        ))
        out.append(_spec(
            "L3-I01", "industry_strength_rank", f"industry_strength_rank_{h}", f"{h}",
            formula=f"average-tie percentile rank of industry_rs_market_{h} across industries",
            lookback="same-day valid industries", unit="0..1",
            semantics="PIT-industry eligible members + total-return benchmark",
            missing_policy="null when fewer than 2 valid industries", origin="research implementation",
            rank=False,
        ))
    out += [
        _spec("L3-M01", "market_to_ma200", "market_to_ma200", "200",
              table="market_context", formula="TAIEX total-return index / SMA200 - 1",
              lookback="200 market sessions", semantics="FinMind TaiwanStockTotalReturnIndex TAIEX",
              rank=False, origin="repo canonical total-return benchmark"),
        _spec("L3-M01", "market_volatility", "market_rv20", "20",
              table="market_context", formula="std(TAIEX total-return daily return,20)*sqrt(252)",
              lookback="20 market returns", unit="annualized volatility",
              semantics="FinMind TaiwanStockTotalReturnIndex TAIEX", rank=False,
              origin="repo canonical total-return benchmark"),
        _spec("L3-M01", "market_position", "market_position252", "252",
              table="market_context", formula="(TRI-low252)/(high252-low252)",
              lookback="252 market sessions", unit="0..1",
              semantics="FinMind TaiwanStockTotalReturnIndex TAIEX", rank=False,
              missing_policy="null when 252-session range is missing or zero", origin="research implementation"),
    ]
    return out


def dictionary_frame(p: Layer1Parameters | None = None) -> pd.DataFrame:
    rows = [s.__dict__ for s in feature_specs(p)]
    for i, seed in enumerate(range(1001, 1011), start=1):
        rows.append({
            "item_id": "RANDOM_CONTROL",
            "feature_key": "random_control",
            "column": f"random_control_{i:02d}",
            "parameter_version": f"seed={seed}",
            "table": "stock_features",
            "dtype": "float",
            "unit": "0..1",
            "formula": "stable SplitMix64 transform of date|stock_id|feature_id|seed",
            "lookback": "none",
            "smoothing": "none",
            "price_volume_semantics": "none; negative control only",
            "includes_today": "date identifier only",
            "input_available_at": "deterministic identifier",
            "output_available_at": "after same-session close",
            "missing_policy": "never missing when logical keys are valid",
            "parameter_origin": "owner-required random control; fixed research seeds",
            "cross_section_rank": True,
            "status": "CONTROL",
        })
    return pd.DataFrame(rows)


def _cache(
    cache: FeatureCache,
    *,
    source_revision: str,
    name: str,
    params: dict[str, object],
    compute: Callable[[], pd.Series],
) -> pd.Series:
    key = FeatureCacheKey.build(
        source_revision=source_revision,
        feature_name=f"{FORMULA_VERSION}:{name}",
        params={"formula_version": FORMULA_VERSION, **params},
        availability_policy=AVAILABILITY_POLICY,
    )
    return cache.get_or_compute_view(key, compute)


def _roll_by_stock(
    values: pd.Series,
    tickers: pd.Series,
    window: int,
    op: str,
) -> pd.Series:
    g = values.groupby(tickers, sort=False)
    if op == "mean":
        return g.transform(lambda s: s.rolling(window, min_periods=window).mean())
    if op == "std":
        return g.transform(lambda s: s.rolling(window, min_periods=window).std(ddof=1))
    if op == "max":
        return g.transform(lambda s: s.rolling(window, min_periods=window).max())
    if op == "min":
        return g.transform(lambda s: s.rolling(window, min_periods=window).min())
    if op == "sum":
        return g.transform(lambda s: s.rolling(window, min_periods=window).sum())
    raise ValueError(op)


def _ema_by_stock(
    values: pd.Series,
    tickers: pd.Series,
    span: int,
) -> pd.Series:
    return values.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(span=span, adjust=False, min_periods=span).mean()
    )


def _rsi(
    close: pd.Series,
    tickers: pd.Series,
    lookback: int,
) -> pd.Series:
    delta = close.groupby(tickers, sort=False).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(alpha=1 / lookback, adjust=False, min_periods=lookback).mean()
    )
    avg_loss = loss.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(alpha=1 / lookback, adjust=False, min_periods=lookback).mean()
    )
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    both_zero = avg_gain.eq(0) & avg_loss.eq(0)
    out = out.where(~avg_loss.eq(0), 100.0)
    out = out.where(~both_zero, 50.0)
    return out


def _wilder_atr_group(group: pd.DataFrame, period: int) -> pd.Series:
    high = pd.to_numeric(group["max"], errors="coerce").to_numpy(float)
    low = pd.to_numeric(group["min"], errors="coerce").to_numpy(float)
    close = pd.to_numeric(group["close"], errors="coerce").to_numpy(float)
    out = np.full(len(group), np.nan, dtype=float)
    prev_valid_close: float | None = None
    seed: list[float] = []
    state: float | None = None
    for i, (h, l, c) in enumerate(zip(high, low, close)):
        valid = (
            np.isfinite(h) and np.isfinite(l) and np.isfinite(c)
            and h > 0 and l > 0 and c > 0 and h >= max(l, c) and l <= min(h, c)
        )
        if not valid:
            continue
        tr = h - l if prev_valid_close is None else max(
            h - l, abs(h - prev_valid_close), abs(l - prev_valid_close)
        )
        if state is None:
            seed.append(float(tr))
            if len(seed) == period:
                state = float(np.mean(seed))
        else:
            state = ((period - 1) * state + float(tr)) / period
        if state is not None:
            out[i] = state
        prev_valid_close = float(c)
    return pd.Series(out, index=group.index, dtype=float)


def _sessions_since_prior_high(values: pd.Series, window: int) -> pd.Series:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(float)
    out = np.full(len(arr), np.nan, dtype=float)
    from collections import deque
    dq: deque[int] = deque()
    for i in range(len(arr)):
        j = i - 1
        if j >= 0 and np.isfinite(arr[j]):
            while dq and (not np.isfinite(arr[dq[-1]]) or arr[dq[-1]] <= arr[j]):
                dq.pop()
            dq.append(j)
        cutoff = i - window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if dq:
            out[i] = float(i - dq[0])
    return pd.Series(out, index=values.index)


def _run_length(mask: pd.Series, tickers: pd.Series) -> pd.Series:
    x = mask.fillna(False).astype(bool)
    return x.groupby(tickers, sort=False).transform(
        lambda s: s.astype(int).groupby((~s).cumsum()).cumsum()
    )


def build_market_context(
    tri: pd.Series,
    *,
    p: Layer1Parameters | None = None,
) -> pd.DataFrame:
    p = p or Layer1Parameters()
    s = pd.Series(tri, dtype=float).copy()
    s.index = pd.to_datetime(s.index, errors="coerce").normalize()
    if s.index.isna().any() or s.index.duplicated().any():
        raise ValueError("total-return index dates must be valid and unique")
    s = s.sort_index()
    ret1 = s.pct_change(fill_method=None)
    ma = s.rolling(p.market_ma_window, min_periods=p.market_ma_window).mean()
    rv = ret1.rolling(p.market_rv_window, min_periods=p.market_rv_window).std(ddof=1) * np.sqrt(252.0)
    lo = s.rolling(p.market_position_window, min_periods=p.market_position_window).min()
    hi = s.rolling(p.market_position_window, min_periods=p.market_position_window).max()
    span = hi - lo
    pos = (s - lo) / span.replace(0, np.nan)
    out = pd.DataFrame({
        "date": s.index,
        "tri_value": s.to_numpy(),
        "market_ret1": ret1.to_numpy(),
        "market_to_ma200": (s / ma - 1.0).to_numpy(),
        "market_rv20": rv.to_numpy(),
        "market_position252": pos.to_numpy(),
        "__denom_zero_market_position252": span.eq(0).to_numpy(),
    })
    for h in p.relative_strength_horizons:
        out[f"market_return_{h}"] = (s / s.shift(h) - 1.0).to_numpy()
    out["available_at_date"] = out["date"]
    out["available_at_rule"] = AVAILABILITY_POLICY
    return out


def attach_industry_pit(
    frame: pd.DataFrame,
    industry_pit: pd.DataFrame,
) -> pd.DataFrame:
    required = {"stock_id", "valid_from", "valid_to", "industry"}
    missing = required - set(industry_pit.columns)
    if missing:
        raise ValueError(f"industry PIT missing columns: {sorted(missing)}")
    pit = industry_pit[list(required)].copy()
    pit["stock_id"] = pit["stock_id"].astype(str)
    pit["valid_from"] = pd.to_datetime(pit["valid_from"], errors="coerce").dt.normalize()
    pit["valid_to"] = pd.to_datetime(pit["valid_to"], errors="coerce").dt.normalize()
    pit = pit.dropna(subset=["stock_id", "valid_from", "industry"])

    out = frame.copy()
    out["industry"] = pd.NA
    out["industry_valid_from"] = pd.NaT
    out["industry_valid_to"] = pd.NaT
    for sid, idx in out.groupby("stock_id", sort=False).groups.items():
        pg = pit[pit["stock_id"].eq(str(sid))].sort_values("valid_from")
        if pg.empty:
            continue
        left = out.loc[idx, ["date"]].copy()
        left["_row_index"] = left.index
        left = left.sort_values("date")
        joined = pd.merge_asof(
            left,
            pg[["valid_from", "valid_to", "industry"]],
            left_on="date",
            right_on="valid_from",
            direction="backward",
        )
        ok = joined["valid_from"].notna() & (
            joined["valid_to"].isna() | joined["date"].le(joined["valid_to"])
        )
        joined.loc[~ok, ["industry", "valid_from", "valid_to"]] = [pd.NA, pd.NaT, pd.NaT]
        row_index = joined["_row_index"].astype(int).to_numpy()
        out.loc[row_index, "industry"] = joined["industry"].to_numpy()
        out.loc[row_index, "industry_valid_from"] = joined["valid_from"].to_numpy()
        out.loc[row_index, "industry_valid_to"] = joined["valid_to"].to_numpy()
    return out


def build_stock_features(
    panel: pd.DataFrame,
    *,
    source_revision: str,
    market_context: pd.DataFrame,
    cache: FeatureCache | None = None,
    p: Layer1Parameters | None = None,
) -> tuple[pd.DataFrame, FeatureCache]:
    p = p or Layer1Parameters()
    cache = cache or FeatureCache()
    required = {
        "date", "stock_id", "open", "max", "min", "close",
        "Trading_Volume", "Trading_money", "observed_trade", "valid_ohlc",
        "market_value", "industry", "industry_valid_from",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"feature panel missing columns: {sorted(missing)}")
    x = panel.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    if x[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("feature panel contains null logical keys")
    if x.duplicated(["date", "stock_id"]).any():
        raise ValueError("feature panel contains duplicate logical keys")
    x = x.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    for col in ("open", "max", "min", "close", "Trading_Volume", "Trading_money", "market_value"):
        x[col] = pd.to_numeric(x[col], errors="coerce")
    m = market_context.copy()
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    x = x.merge(m, on="date", how="left", validate="many_to_one")
    tickers = x["stock_id"]
    close = x["close"]
    high = x["max"]
    low = x["min"]
    volume = x["Trading_Volume"]
    amount = x["Trading_money"]
    x["bars_seen"] = x.groupby("stock_id", sort=False).cumcount() + 1
    ret1 = _cache(
        cache, source_revision=source_revision, name="stock_ret1", params={},
        compute=lambda: close.groupby(tickers, sort=False).transform(lambda s: s.pct_change(fill_method=None)),
    )
    x["__stock_ret1"] = ret1

    ma: dict[int, pd.Series] = {}
    for w in p.ma_windows:
        ma[w] = _cache(
            cache, source_revision=source_revision, name="sma_close", params={"window": w},
            compute=lambda w=w: _roll_by_stock(close, tickers, w, "mean"),
        )
        denom = ma[w].replace(0, np.nan)
        x[f"close_to_ma{w}"] = close / denom - 1.0
        x[f"__denom_zero_close_to_ma{w}"] = ma[w].eq(0)
        prior = ma[w].groupby(tickers, sort=False).shift(p.ma_slope_lookback)
        x[f"ma{w}_slope10"] = ma[w] / prior.replace(0, np.nan) - 1.0
        x[f"__denom_zero_ma{w}_slope10"] = prior.eq(0)

    probe_window = p.ma_windows[0]
    probe = _cache(
        cache,
        source_revision=source_revision,
        name="sma_close",
        params={"window": probe_window},
        compute=lambda: _roll_by_stock(close, tickers, probe_window, "mean"),
    )
    if not probe.equals(ma[probe_window]):
        raise RuntimeError("feature cache repeat-hit returned a different SMA")
    ready_ma = pd.concat([ma[w].notna() for w in p.ma_windows], axis=1).all(axis=1)
    x["ma_order_score"] = (
        ma[20].gt(ma[60]).astype(float)
        + ma[60].gt(ma[120]).astype(float)
        + ma[120].gt(ma[250]).astype(float)
    ) / 3.0
    x.loc[~ready_ma, "ma_order_score"] = np.nan

    hi250 = _cache(
        cache, source_revision=source_revision, name="rolling_high", params={"window": p.high_low_lookback},
        compute=lambda: _roll_by_stock(high, tickers, p.high_low_lookback, "max"),
    )
    lo250 = _cache(
        cache, source_revision=source_revision, name="rolling_low", params={"window": p.high_low_lookback},
        compute=lambda: _roll_by_stock(low, tickers, p.high_low_lookback, "min"),
    )
    x["distance_250_high"] = close / hi250.replace(0, np.nan) - 1.0
    x["distance_250_low"] = close / lo250.replace(0, np.nan) - 1.0
    x["__denom_zero_distance_250_high"] = hi250.eq(0)
    x["__denom_zero_distance_250_low"] = lo250.eq(0)
    sessions_since = pd.Series(np.nan, index=x.index, dtype=float)
    atr = pd.Series(np.nan, index=x.index, dtype=float)
    for _, idx in x.groupby("stock_id", sort=False).groups.items():
        sessions_since.loc[idx] = _sessions_since_prior_high(
            high.loc[idx], p.high_low_lookback
        ).to_numpy()
        atr.loc[idx] = _wilder_atr_group(
            x.loc[idx], p.atr_period
        ).to_numpy()
    x["sessions_since_prior_250_high"] = sessions_since
    x["atr21_pct"] = atr / close.replace(0, np.nan)
    x["__denom_zero_atr21_pct"] = close.eq(0)

    rv: dict[int, pd.Series] = {}
    for w in p.rv_windows:
        rv[w] = _cache(
            cache, source_revision=source_revision, name="realized_volatility", params={"window": w},
            compute=lambda w=w: _roll_by_stock(ret1, tickers, w, "std") * np.sqrt(252.0),
        )
        x[f"rv{w}"] = rv[w]
    x["rv20_rv60_ratio"] = rv[20] / rv[60].replace(0, np.nan)
    x["__denom_zero_rv20_rv60_ratio"] = rv[60].eq(0)

    mid = _cache(
        cache, source_revision=source_revision, name="bollinger_mid", params={"window": p.bollinger_window},
        compute=lambda: _roll_by_stock(close, tickers, p.bollinger_window, "mean"),
    )
    sd = close.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(p.bollinger_window, min_periods=p.bollinger_window).std(ddof=0)
    )
    upper = mid + p.bollinger_stddev * sd
    lower = mid - p.bollinger_stddev * sd
    width = upper - lower
    bandwidth = width / mid.replace(0, np.nan)
    x["bollinger_bandwidth_14_2"] = bandwidth
    x["__denom_zero_bollinger_bandwidth_14_2"] = mid.eq(0)
    x["bollinger_bandwidth_pctile120"] = bandwidth.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(
            p.bollinger_percentile_lookback,
            min_periods=p.bollinger_percentile_lookback,
        ).rank(pct=True)
    )
    x["bollinger_channel_position_14_2"] = (close - lower) / width.replace(0, np.nan)
    x["__denom_zero_bollinger_channel_position_14_2"] = width.eq(0)

    v5 = _roll_by_stock(volume, tickers, p.volume_short_window, "mean")
    v20 = _roll_by_stock(volume, tickers, p.volume_mid_window, "mean")
    v60 = _roll_by_stock(volume, tickers, p.volume_long_window, "mean")
    x["volume_ratio_5_20"] = v5 / v20.replace(0, np.nan)
    x["volume_ratio_20_60"] = v20 / v60.replace(0, np.nan)
    x["__denom_zero_volume_ratio_5_20"] = v20.eq(0)
    x["__denom_zero_volume_ratio_20_60"] = v60.eq(0)
    x["amount_mean20_twd"] = _roll_by_stock(amount, tickers, p.amount_window, "mean")
    x["market_cap_twd"] = x["market_value"]
    x["turnover_value_ratio"] = amount / x["market_value"].where(x["market_value"].gt(0))
    x["__denom_zero_turnover_value_ratio"] = x["market_value"].eq(0)

    prior_v = volume.groupby(tickers, sort=False).shift(1)
    prior5 = _roll_by_stock(prior_v, tickers, p.volume_short_window, "mean")
    prior20 = _roll_by_stock(prior_v, tickers, p.volume_mid_window, "mean")
    x["volume_dryup_prior5_20"] = prior5 / prior20.replace(0, np.nan)
    x["__denom_zero_volume_dryup_prior5_20"] = prior20.eq(0)
    up_volume = volume.where(ret1.gt(0), 0.0).where(ret1.notna())
    up_sum = _roll_by_stock(up_volume, tickers, p.up_day_volume_window, "sum")
    total_sum = _roll_by_stock(volume, tickers, p.up_day_volume_window, "sum")
    x["up_day_volume_share20"] = up_sum / total_sum.replace(0, np.nan)
    x["__denom_zero_up_day_volume_share20"] = total_sum.eq(0)

    rsi: dict[int, pd.Series] = {}
    for w in p.rsi_windows:
        rsi[w] = _cache(
            cache, source_revision=source_revision, name="rsi", params={"lookback": w},
            compute=lambda w=w: _rsi(close, tickers, w),
        )
        x[f"rsi{w}"] = rsi[w]
    x["rsi13_minus_rsi26"] = rsi[p.rsi_difference_fast] - rsi[p.rsi_difference_slow]
    x["rsi14_slope5"] = rsi[p.rsi_slope_window] - rsi[p.rsi_slope_window].groupby(
        tickers, sort=False
    ).shift(p.rsi_slope_lookback)

    lowest = _roll_by_stock(low, tickers, p.kd_lookback, "min")
    highest = _roll_by_stock(high, tickers, p.kd_lookback, "max")
    kd_span = highest - lowest
    rsv = ((close - lowest) / kd_span.replace(0, np.nan) * 100.0).clip(0, 100)
    k = rsv.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(
            alpha=1 / p.kd_k_smooth,
            adjust=False,
            min_periods=p.kd_k_smooth,
        ).mean()
    )
    d = k.groupby(tickers, sort=False).transform(
        lambda s: s.ewm(
            alpha=1 / p.kd_d_smooth,
            adjust=False,
            min_periods=p.kd_d_smooth,
        ).mean()
    )
    x["kd_k_9_3_3"] = k
    x["kd_d_9_3_3"] = d
    x["kd_high_saturation_days80"] = _run_length(
        k.ge(p.kd_high_level) & d.ge(p.kd_high_level), tickers
    )
    x["kd_low_saturation_days20"] = _run_length(
        k.le(p.kd_low_level) & d.le(p.kd_low_level), tickers
    )
    x["__denom_zero_kd"] = kd_span.eq(0)

    ema_fast = _ema_by_stock(close, tickers, p.macd_fast)
    ema_slow = _ema_by_stock(close, tickers, p.macd_slow)
    macd = ema_fast - ema_slow
    macd_signal = _ema_by_stock(macd, tickers, p.macd_signal)
    hist = macd - macd_signal
    x["macd_hist_12_26_9"] = hist
    x["macd_hist_slope5"] = hist - hist.groupby(tickers, sort=False).shift(p.macd_slope_lookback)

    typical = (high + low + close) / 3.0
    tp_ma = _roll_by_stock(typical, tickers, p.cci_window, "mean")
    mean_dev = typical.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(p.cci_window, min_periods=p.cci_window).apply(
            lambda a: float(np.mean(np.abs(a - np.mean(a)))), raw=True
        )
    )
    cci_denom = 0.015 * mean_dev
    x["cci20"] = (typical - tp_ma) / cci_denom.replace(0, np.nan)
    x["__denom_zero_cci20"] = cci_denom.eq(0)

    wr_high = _roll_by_stock(high, tickers, p.williams_window, "max")
    wr_low = _roll_by_stock(low, tickers, p.williams_window, "min")
    wr_span = wr_high - wr_low
    x["williams_r14"] = -100.0 * (wr_high - close) / wr_span.replace(0, np.nan)
    x["__denom_zero_williams_r14"] = wr_span.eq(0)

    for h in p.relative_strength_horizons:
        stock_return = close / close.groupby(tickers, sort=False).shift(h) - 1.0
        x[f"__stock_return_{h}"] = stock_return
        x[f"rs_market_{h}"] = stock_return - x[f"market_return_{h}"]

    mr = pd.to_numeric(x["market_ret1"], errors="coerce")
    stock_var = ret1.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(p.beta_window, min_periods=p.beta_window).var(ddof=1)
    )
    market_var = mr.groupby(tickers, sort=False).transform(
        lambda s: s.rolling(p.beta_window, min_periods=p.beta_window).var(ddof=1)
    )
    cov = pd.Series(index=x.index, dtype=float)
    corr = pd.Series(index=x.index, dtype=float)
    for _, idx in x.groupby("stock_id", sort=False).groups.items():
        a = ret1.loc[idx]
        b = mr.loc[idx]
        cov.loc[idx] = a.rolling(p.beta_window, min_periods=p.beta_window).cov(b).to_numpy()
        corr.loc[idx] = a.rolling(p.beta_window, min_periods=p.beta_window).corr(b).to_numpy()
    beta = cov / market_var.replace(0, np.nan)
    residual_var = stock_var - (cov * cov / market_var.replace(0, np.nan))
    x["beta60_market"] = beta
    x["corr60_market"] = corr
    x["resid_vol60_market"] = np.sqrt(residual_var.clip(lower=0)) * np.sqrt(252.0)
    x["__denom_zero_beta60_market"] = market_var.eq(0)
    x["__denom_zero_resid_vol60_market"] = market_var.eq(0)

    x["available_at_date"] = x["date"]
    x["available_at_rule"] = AVAILABILITY_POLICY

    keep = [
        "date", "stock_id", "available_at_date", "available_at_rule",
        "observed_trade", "valid_ohlc", "close", "Trading_money",
        "bars_seen", "industry", "industry_valid_from", "market_value",
        "market_cap_twd", "__stock_ret1", "market_ret1",
    ]
    for h in p.relative_strength_horizons:
        keep += [f"__stock_return_{h}", f"market_return_{h}"]
    primary_cols = [
        s.column for s in feature_specs(p)
        if s.table == "stock_features" and s.status == "COMPLETE"
        and s.column not in {"industry", "market_cap_twd", "market_cap_tier", "liquidity_tier", "volatility_cluster"}
        and not s.column.startswith("rs_industry_")
        and not s.column.startswith("industry_rs_market_")
        and not s.column.startswith("industry_strength_rank_")
    ]
    keep += [c for c in primary_cols if c in x.columns]
    keep += [c for c in x.columns if c.startswith("__denom_zero_")]
    return x.loc[:, list(dict.fromkeys(keep))].copy(), cache


def _percentile(
    frame: pd.DataFrame,
    column: str,
    *,
    min_n: int = RANK_MIN_N,
) -> tuple[pd.Series, pd.Series]:
    value = pd.to_numeric(frame[column], errors="coerce")
    n = value.groupby(frame["date"]).transform("count")
    pct = value.groupby(frame["date"]).rank(
        pct=True,
        method=RANK_METHOD,
        ascending=True,
        na_option="keep",
    )
    pct = pct.where(n.ge(min_n))
    return pct, n


def _tier_from_pct(pct: pd.Series, labels: tuple[str, str, str]) -> pd.Series:
    out = pd.Series(pd.NA, index=pct.index, dtype="string")
    out.loc[pct.le(1 / 3)] = labels[0]
    out.loc[pct.gt(1 / 3) & pct.le(2 / 3)] = labels[1]
    out.loc[pct.gt(2 / 3)] = labels[2]
    return out


def add_industry_and_cross_section_features(
    eligible: pd.DataFrame,
    *,
    p: Layer1Parameters | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = p or Layer1Parameters()
    x = eligible.copy()
    daily_rows: list[pd.DataFrame] = []

    cap_pct, _ = _percentile(x, "market_cap_twd")
    liq_pct, _ = _percentile(x, "amount_mean20_twd")
    vol_pct, _ = _percentile(x, "rv60")
    x["market_cap_tier"] = _tier_from_pct(cap_pct, ("SMALL", "MID", "LARGE"))
    x["liquidity_tier"] = _tier_from_pct(liq_pct, ("LOW", "MID", "HIGH"))
    x["volatility_cluster"] = _tier_from_pct(vol_pct, ("LOW", "MID", "HIGH"))

    industry_key = x["industry"].astype("string")
    for h in p.relative_strength_horizons:
        stock_col = f"__stock_return_{h}"
        industry_return = x.groupby(["date", industry_key], dropna=True)[stock_col].transform("median")
        industry_return = industry_return.where(industry_key.notna())
        x[f"rs_industry_{h}"] = x[stock_col] - industry_return
        x[f"industry_rs_market_{h}"] = industry_return - x[f"market_return_{h}"]
        industry_table = (
            x.loc[industry_key.notna(), ["date", "industry", f"industry_rs_market_{h}"]]
            .dropna()
            .drop_duplicates(["date", "industry"])
        )
        if industry_table.empty:
            rank_map = pd.DataFrame(columns=["date", "industry", "rank"])
        else:
            counts = industry_table.groupby("date")[f"industry_rs_market_{h}"].transform("count")
            industry_table["rank"] = industry_table.groupby("date")[f"industry_rs_market_{h}"].rank(
                pct=True, method=RANK_METHOD, ascending=True
            ).where(counts.ge(RANK_MIN_N))
            rank_map = industry_table[["date", "industry", "rank"]]
        x = x.merge(rank_map, on=["date", "industry"], how="left", validate="many_to_one")
        x = x.rename(columns={"rank": f"industry_strength_rank_{h}"})

    numeric_rank_cols = [
        s.column for s in feature_specs(p)
        if s.table == "stock_features"
        and s.status == "COMPLETE"
        and s.dtype == "float"
        and s.cross_section_rank
        and s.column in x.columns
    ]
    for col in numeric_rank_cols:
        pct, n = _percentile(x, col)
        x[f"{col}_pct"] = pct
        daily = pd.DataFrame({
            "date": x["date"],
            "feature": col,
            "n_valid": pd.to_numeric(x[col], errors="coerce").notna().groupby(x["date"]).transform("sum"),
            "n_eligible": x.groupby("date")["stock_id"].transform("size"),
            "rank_usable": n.ge(RANK_MIN_N),
        }).drop_duplicates(["date", "feature"])
        daily_rows.append(daily)

    daily_counts = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame(
        columns=["date", "feature", "n_valid", "n_eligible", "rank_usable"]
    )
    return x, daily_counts


def stable_random_controls(
    dates: pd.Series,
    stock_ids: pd.Series,
    *,
    seeds: Iterable[int] = range(1001, 1011),
) -> pd.DataFrame:
    key_text = (
        pd.to_datetime(dates, errors="coerce").dt.strftime("%Y-%m-%d")
        + "|"
        + stock_ids.astype(str)
    )
    base = pd.util.hash_pandas_object(key_text, index=False).to_numpy(dtype=np.uint64)
    out: dict[str, np.ndarray] = {}
    mask64 = np.uint64(0xFFFFFFFFFFFFFFFF)
    for i, seed in enumerate(seeds, start=1):
        feature_id = f"random_control_{i:02d}"
        const = int.from_bytes(
            hashlib.sha256(f"{feature_id}|{int(seed)}".encode("utf-8")).digest()[:8],
            "little",
        )
        z = base ^ np.uint64(const)
        z = (z + np.uint64(0x9E3779B97F4A7C15)) & mask64
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9) & mask64
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB) & mask64
        z = z ^ (z >> np.uint64(31))
        out[feature_id] = (z.astype(np.float64) / float(2**64))
    return pd.DataFrame(out, index=dates.index)


def add_random_controls_and_ranks(
    frame: pd.DataFrame,
    *,
    seeds: Iterable[int] = range(1001, 1011),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    x = frame.copy()
    controls = stable_random_controls(x["date"], x["stock_id"], seeds=seeds)
    daily_rows: list[pd.DataFrame] = []
    for col in controls.columns:
        x[col] = controls[col]
        pct, n = _percentile(x, col)
        x[f"{col}_pct"] = pct
        daily_rows.append(pd.DataFrame({
            "date": x["date"],
            "feature": col,
            "n_valid": x.groupby("date")["stock_id"].transform("size"),
            "n_eligible": x.groupby("date")["stock_id"].transform("size"),
            "rank_usable": n.ge(RANK_MIN_N),
        }).drop_duplicates(["date", "feature"]))
    return x, pd.concat(daily_rows, ignore_index=True)


def primary_columns(p: Layer1Parameters | None = None) -> list[str]:
    p = p or Layer1Parameters()
    return [
        s.column for s in feature_specs(p)
        if s.status == "COMPLETE" and s.table == "stock_features"
    ]


def market_primary_columns(p: Layer1Parameters | None = None) -> list[str]:
    p = p or Layer1Parameters()
    return [
        s.column for s in feature_specs(p)
        if s.status == "COMPLETE" and s.table == "market_context"
    ]


def warmup_requirement(column: str, p: Layer1Parameters | None = None) -> int:
    p = p or Layer1Parameters()
    exact = {
        "ma_order_score": 250,
        "distance_250_high": 250,
        "distance_250_low": 250,
        "sessions_since_prior_250_high": 251,
        "atr21_pct": 21,
        "rv20": 21,
        "rv60": 61,
        "rv20_rv60_ratio": 61,
        "bollinger_bandwidth_14_2": 14,
        "bollinger_bandwidth_pctile120": 133,
        "bollinger_channel_position_14_2": 14,
        "volume_ratio_5_20": 20,
        "volume_ratio_20_60": 60,
        "amount_mean20_twd": 20,
        "turnover_value_ratio": 1,
        "volume_dryup_prior5_20": 21,
        "up_day_volume_share20": 21,
        "rsi13": 14,
        "rsi14": 15,
        "rsi26": 27,
        "rsi13_minus_rsi26": 27,
        "rsi14_slope5": 20,
        "kd_k_9_3_3": 11,
        "kd_d_9_3_3": 13,
        "kd_high_saturation_days80": 13,
        "kd_low_saturation_days20": 13,
        "macd_hist_12_26_9": 34,
        "macd_hist_slope5": 39,
        "cci20": 20,
        "williams_r14": 14,
        "market_cap_twd": 1,
        "market_cap_tier": 1,
        "liquidity_tier": 20,
        "volatility_cluster": 61,
        "beta60_market": 61,
        "corr60_market": 61,
        "resid_vol60_market": 61,
        "industry": 1,
    }
    for w in p.ma_windows:
        exact[f"close_to_ma{w}"] = w
        exact[f"ma{w}_slope10"] = w + p.ma_slope_lookback
    for h in p.relative_strength_horizons:
        exact[f"rs_market_{h}"] = h + 1
        exact[f"rs_industry_{h}"] = h + 1
        exact[f"industry_rs_market_{h}"] = h + 1
        exact[f"industry_strength_rank_{h}"] = h + 1
    return int(exact.get(column, 1))


def missing_reason_counts(
    frame: pd.DataFrame,
    *,
    columns: Iterable[str],
    p: Layer1Parameters | None = None,
) -> pd.DataFrame:
    p = p or Layer1Parameters()
    rows: list[dict[str, object]] = []
    for col in columns:
        if col not in frame.columns:
            continue
        value = frame[col]
        valid = value.notna()
        reason = pd.Series("VALID", index=frame.index, dtype="string")
        missing = ~valid
        req = warmup_requirement(col, p)
        reason.loc[missing & frame["bars_seen"].lt(req)] = "WARMUP_INSUFFICIENT"
        if col == "industry" or "industry" in col:
            reason.loc[missing & frame["industry"].isna()] = "SOURCE_MISSING_INDUSTRY_PIT"
        if col in {"market_cap_twd", "market_cap_tier", "turnover_value_ratio"}:
            reason.loc[missing & frame["market_value"].isna()] = "SOURCE_MISSING_MARKET_VALUE"
        if (
            col.startswith("rs_market_")
            or col.startswith("beta")
            or col.startswith("corr")
            or col.startswith("resid_vol")
        ):
            reason.loc[missing & frame["market_ret1"].isna()] = "SOURCE_MISSING_MARKET_TRI"
        denom_col = f"__denom_zero_{col}"
        if denom_col in frame.columns:
            reason.loc[missing & frame[denom_col].fillna(False).astype(bool)] = "DENOMINATOR_ZERO"
        residual = missing & reason.eq("VALID")
        reason.loc[residual] = "SOURCE_MISSING_OR_INVALID"
        temp = pd.DataFrame({
            "year": pd.to_datetime(frame["date"]).dt.year,
            "feature": col,
            "reason": reason,
        })
        grouped = temp.groupby(["year", "feature", "reason"], dropna=False).size()
        for (year, feature, why), count in grouped.items():
            rows.append({
                "year": int(year),
                "feature": str(feature),
                "reason": str(why),
                "count": int(count),
            })
    return pd.DataFrame(rows)
