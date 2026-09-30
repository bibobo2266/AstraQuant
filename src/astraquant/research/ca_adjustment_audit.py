from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AuditTolerance:
    ma_ratio_abs: float = 1e-6
    reconstruction_price_abs: float = 1e-4
    near_ma_threshold_abs: float = 1e-4
    near_breakout_margin_abs: float = 1e-4
    near_close_threshold_twd: float = 0.05


def valid_adjustment_events(
    frame: pd.DataFrame,
    *,
    ratio_min: float = 0.5,
    ratio_max: float = 1.2,
) -> pd.DataFrame:
    required = {"date", "stock_id", "before_price", "after_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"adjustment event columns missing: {sorted(missing)}")
    x = frame.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    before = pd.to_numeric(x["before_price"], errors="coerce")
    after = pd.to_numeric(x["after_price"], errors="coerce")
    x["ratio"] = after / before
    x = x[
        x["date"].notna()
        & before.gt(0)
        & after.gt(0)
        & x["ratio"].between(float(ratio_min), float(ratio_max), inclusive="both")
    ].copy()
    x = (
        x.groupby(["stock_id", "date"], as_index=False)["ratio"]
        .prod()
        .sort_values(["stock_id", "date"], kind="stable")
        .reset_index(drop=True)
    )
    if (x["ratio"] <= 0).any():
        raise ValueError("adjustment ratios must remain positive")
    return x


def future_factor(
    dates: pd.Series,
    event_dates: np.ndarray,
    event_ratios: np.ndarray,
) -> np.ndarray:
    d = pd.to_datetime(dates, errors="coerce").to_numpy(dtype="datetime64[ns]")
    if len(event_dates) == 0:
        return np.ones(len(d), dtype=float)
    e = np.asarray(event_dates, dtype="datetime64[ns]")
    r = np.asarray(event_ratios, dtype=float)
    order = np.argsort(e, kind="stable")
    e = e[order]
    r = r[order]
    suffix = np.ones(len(r) + 1, dtype=float)
    for i in range(len(r) - 1, -1, -1):
        suffix[i] = suffix[i + 1] * r[i]
    pos = np.searchsorted(e, d, side="right")
    return suffix[pos]


def close_to_ma(close: pd.Series, window: int) -> pd.Series:
    c = pd.to_numeric(close, errors="coerce")
    ma = c.rolling(window, min_periods=window).mean()
    return c / ma - 1.0


def n_session_high_details(close: pd.Series, lookback: int) -> pd.DataFrame:
    c = pd.to_numeric(close, errors="coerce")
    prior = c.shift(1).rolling(lookback, min_periods=lookback).max()
    previous_close = c.shift(1)
    previous_prior = prior.shift(1)
    signal = (
        c.gt(prior)
        & previous_close.le(previous_prior)
        & prior.notna()
    ).fillna(False)
    margin = c / prior - 1.0
    previous_margin = previous_close / previous_prior - 1.0
    return pd.DataFrame(
        {
            "prior_high": prior,
            "previous_prior_high": previous_prior,
            "breakout_margin": margin,
            "previous_margin": previous_margin,
            "signal": signal.astype(bool),
        }
    )


def metrics_for_close(close: pd.Series, *, ma_window: int, breakout_lookback: int) -> pd.DataFrame:
    ma = close_to_ma(close, ma_window)
    breakout = n_session_high_details(close, breakout_lookback)
    return pd.DataFrame(
        {
            "close_to_ma": ma,
            "ma_pass": ma.ge(0) & ma.notna(),
            "prior_high": breakout["prior_high"],
            "breakout_margin": breakout["breakout_margin"],
            "previous_margin": breakout["previous_margin"],
            "breakout_signal": breakout["signal"],
        }
    )


def asof_metrics_from_raw_and_events(
    *,
    dates: pd.Series,
    raw_close: pd.Series,
    full_factor: np.ndarray,
    ma_window: int,
    breakout_lookback: int,
    round_decimals: int,
    target_mask: np.ndarray,
) -> pd.DataFrame:
    raw = pd.to_numeric(raw_close, errors="coerce").to_numpy(dtype=float)
    full_unrounded = raw * np.asarray(full_factor, dtype=float)
    factors = np.asarray(full_factor, dtype=float)
    out = pd.DataFrame(
        {
            "close_to_ma": np.nan,
            "ma_pass": False,
            "prior_high": np.nan,
            "breakout_margin": np.nan,
            "previous_margin": np.nan,
            "breakout_signal": False,
        },
        index=np.arange(len(raw)),
    )
    wanted = np.asarray(target_mask, dtype=bool)
    for k in np.unique(factors[wanted & np.isfinite(factors)]):
        transformed = np.round(full_unrounded / float(k), round_decimals)
        m = metrics_for_close(
            pd.Series(transformed),
            ma_window=ma_window,
            breakout_lookback=breakout_lookback,
        )
        take = wanted & np.isclose(factors, k, rtol=1e-13, atol=1e-15)
        out.loc[take, :] = m.loc[take, :].to_numpy()
    out["ma_pass"] = out["ma_pass"].fillna(False).astype(bool)
    out["breakout_signal"] = out["breakout_signal"].fillna(False).astype(bool)
    return out


def classify_feature_rows(dictionary: pd.DataFrame) -> pd.DataFrame:
    x = dictionary.copy()
    rows: list[dict[str, object]] = []
    price_scale_invariant = {
        "close_to_ma20", "close_to_ma60", "close_to_ma120", "close_to_ma250",
        "ma_order_score",
        "ma20_slope10", "ma60_slope10", "ma120_slope10", "ma250_slope10",
        "distance_250_high", "distance_250_low", "sessions_since_prior_250_high",
        "atr21_pct", "rv20", "rv60", "rv20_rv60_ratio",
        "bollinger_bandwidth_14_2", "bollinger_bandwidth_pctile120",
        "bollinger_channel_position_14_2",
        "up_day_volume_share20",
        "rsi13", "rsi14", "rsi26", "rsi13_minus_rsi26", "rsi14_slope5",
        "kd_k_9_3_3", "kd_d_9_3_3", "kd_high_saturation_days80",
        "kd_low_saturation_days20", "cci20", "williams_r14",
        "rs_market_20", "rs_market_60", "rs_market_120",
        "beta60_market", "corr60_market", "resid_vol60_market",
    }
    direct_independent = {
        "volume_ratio_5_20", "volume_ratio_20_60", "amount_mean20_twd",
        "turnover_value_ratio", "volume_dryup_prior5_20",
        "market_cap_twd", "industry",
    }
    cross_section_membership = {
        "market_cap_tier", "liquidity_tier", "volatility_cluster",
        "rs_industry_20", "rs_industry_60", "rs_industry_120",
        "industry_rs_market_20", "industry_rs_market_60", "industry_rs_market_120",
        "industry_strength_rank_20", "industry_strength_rank_60",
        "industry_strength_rank_120",
    }
    market_only = {"market_to_ma200", "market_rv20", "market_position252"}
    magnitude_affected = {"macd_hist_12_26_9", "macd_hist_slope5"}

    for r in x.itertuples(index=False):
        col = str(r.column)
        table = str(r.table)
        status = str(r.status)
        if status == "CONTROL":
            klass = "VALUE_INDEPENDENT_OF_PRICE_FACTOR"
            proof = "deterministic key/seed transform"
        elif status == "BLOCKED_DATA":
            klass = "INSUFFICIENT_DATA"
            proof = "source absent"
        elif table == "market_context" or col in market_only:
            klass = "NOT_DEPENDENT_ON_STOCK_PRICE_FACTOR"
            proof = "TAIEX market context only"
        elif col in magnitude_affected:
            klass = "PROVEN_NUMERICALLY_AFFECTED_BY_SCALE"
            proof = "EMA differences are homogeneous of degree 1; sign can remain invariant but raw magnitude scales"
        elif col in price_scale_invariant:
            klass = "PROVEN_INVARIANT_FIXED_KEYS_UNIFORM_POSITIVE_FACTOR"
            proof = "dimensionless ratio/order/return formula; common positive factor cancels"
        elif col in direct_independent:
            klass = "VALUE_INDEPENDENT_OF_OHLC_FACTOR"
            proof = "formula uses volume/amount/market-value/industry rather than adjusted OHLC"
        elif col in cross_section_membership:
            klass = "INDIRECTLY_AFFECTED_BY_ELIGIBLE_SET"
            proof = "formula uses same-day eligible cross-section or PIT-industry eligible members"
        else:
            klass = "INSUFFICIENT_EVIDENCE"
            proof = "not classified by the documented factor proof"
        rows.append(
            {
                "item_id": r.item_id,
                "feature_key": r.feature_key,
                "column": col,
                "parameter_version": r.parameter_version,
                "table": table,
                "status": status,
                "formula": r.formula,
                "adjustment_effect_class": klass,
                "proof_scope": (
                    "future-effective dividend factor defined as a common positive multiplier "
                    "over all OHLC inputs used at decision T; fixed stock-day keys; source-revision "
                    "or announcement-timing effects are separate"
                ),
                "proof_basis": proof,
                "persisted_stock_artifact_membership": (
                    "MAY_DIFFER_IF_UNIVERSE_DIFF"
                    if table == "stock_features"
                    else "NOT_APPLICABLE"
                ),
                "cross_section_rank_dependency": bool(
                    getattr(r, "cross_section_rank", False)
                ),
            }
        )
    rows.append(
        {
            "item_id": "BASELINE_SIGNAL",
            "feature_key": "n_session_high",
            "column": "N_SESSION_HIGH_60",
            "parameter_version": "lookback=60",
            "table": "signal",
            "status": "AUDIT_TARGET",
            "formula": "close_t>prior_high60_t AND close_t-1<=prior_high60_t-1",
            "adjustment_effect_class": "PROVEN_INVARIANT_FIXED_KEYS_UNIFORM_POSITIVE_FACTOR",
            "proof_scope": "same as above; strict booleans empirically audited without tolerance",
            "proof_basis": "positive common scaling preserves ordering and strict/equality relations absent rounding",
            "persisted_stock_artifact_membership": "NOT_APPLICABLE",
            "cross_section_rank_dependency": False,
        }
    )
    return pd.DataFrame(rows)
