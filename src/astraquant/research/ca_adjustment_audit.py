from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


# Frozen before the E1 audit in configs/quality/ca_adjustment_invariance_audit_v1.yaml.
# Boolean comparisons remain exact; these tolerances classify value differences
# and near-boundary cases only.
VALUE_RTOL = 0.0
VALUE_ATOL = 1e-6
BOUNDARY_BAND = 1e-4
PRICE_REBUILD_ATOL = 1e-4
RATIO_LO = 0.5
RATIO_HI = 1.2


def normalize_dividend_events(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "stock_id", "before_price", "after_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dividend events missing columns: {sorted(missing)}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    out["before_price"] = pd.to_numeric(out["before_price"], errors="coerce")
    out["after_price"] = pd.to_numeric(out["after_price"], errors="coerce")
    out = out[
        out["date"].notna()
        & out["before_price"].gt(0)
        & out["after_price"].gt(0)
    ].copy()
    out["ratio"] = out["after_price"] / out["before_price"]
    out = out[out["ratio"].between(RATIO_LO, RATIO_HI, inclusive="both")].copy()
    # daily_update_adj aggregates same-day events by product before one rounding step.
    out = (
        out.groupby(["stock_id", "date"], as_index=False)["ratio"]
        .prod()
        .sort_values(["stock_id", "date"], kind="stable")
        .reset_index(drop=True)
    )
    if (out["ratio"] <= 0).any():
        raise ValueError("corporate-action ratios must be positive")
    return out


def future_factor_for_rows(
    rows: pd.DataFrame,
    events: pd.DataFrame,
) -> np.ndarray:
    required = {"date", "stock_id"}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError(f"rows missing columns: {sorted(missing)}")
    work = rows[["date", "stock_id"]].copy().reset_index(drop=True)
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work["stock_id"] = work["stock_id"].astype(str)
    out = np.ones(len(work), dtype=float)
    event_groups = {
        sid: g for sid, g in events.groupby("stock_id", sort=False)
    }
    for sid, positions in work.groupby("stock_id", sort=False).indices.items():
        ev = event_groups.get(str(sid))
        if ev is None or ev.empty:
            continue
        ev_dates = ev["date"].to_numpy(dtype="datetime64[ns]")
        ratios = ev["ratio"].to_numpy(dtype=float)
        suffix = np.ones(len(ratios) + 1, dtype=float)
        if len(ratios):
            suffix[:-1] = np.cumprod(ratios[::-1])[::-1]
        row_dates = work.iloc[positions]["date"].to_numpy(dtype="datetime64[ns]")
        # build_adj applies an event only to dates strictly before event.date.
        loc = np.searchsorted(ev_dates, row_dates, side="right")
        out[np.asarray(positions, dtype=int)] = suffix[loc]
    return out


def current_price_feature_frame(
    rows: pd.DataFrame,
    *,
    future_factor: np.ndarray,
) -> pd.DataFrame:
    work = rows[["date", "stock_id", "close"]].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work["stock_id"] = work["stock_id"].astype(str)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    if len(work) != len(future_factor):
        raise ValueError("future_factor length mismatch")
    # Attach before sorting so a caller's row order cannot detach a factor
    # from its logical (date, stock_id) observation.
    work["future_factor"] = np.asarray(future_factor, dtype=float)
    work = work.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

    by = work.groupby("stock_id", sort=False)["close"]
    ma120 = by.transform(lambda s: s.rolling(120, min_periods=120).mean())
    prior_high60 = by.transform(
        lambda s: s.shift(1).rolling(60, min_periods=60).max()
    )
    previous_close = by.shift(1)
    previous_prior = prior_high60.groupby(work["stock_id"], sort=False).shift(1)

    ratio = work["close"] / ma120 - 1.0
    factor = work["future_factor"].where(work["future_factor"].gt(0))
    cf_close = work["close"] / factor
    cf_ma120 = ma120 / factor
    cf_ratio = cf_close / cf_ma120 - 1.0

    current_gate = ratio.ge(0) & ratio.notna()
    cf_gate = cf_ratio.ge(0) & cf_ratio.notna()

    current_breakout = (
        work["close"].gt(prior_high60)
        & previous_close.le(previous_prior)
        & prior_high60.notna()
    ).fillna(False)
    cf_breakout = (
        (work["close"] / factor).gt(prior_high60 / factor)
        & (previous_close / factor).le(previous_prior / factor)
        & prior_high60.notna()
    ).fillna(False)

    result = work.copy()
    result["close_to_ma120_current"] = ratio
    result["close_to_ma120_remove_future"] = cf_ratio
    result["ma120_gate_current"] = current_gate.astype(bool)
    result["ma120_gate_remove_future"] = cf_gate.astype(bool)
    result["prior_high60_current"] = prior_high60
    result["n60_current"] = current_breakout.astype(bool)
    result["n60_remove_future"] = cf_breakout.astype(bool)
    result["ma120_value_diff"] = ~np.isclose(
        result["close_to_ma120_current"],
        result["close_to_ma120_remove_future"],
        rtol=VALUE_RTOL,
        atol=VALUE_ATOL,
        equal_nan=True,
    )
    result["ma120_gate_flip"] = (
        result["ma120_gate_current"] != result["ma120_gate_remove_future"]
    )
    result["n60_flip"] = result["n60_current"] != result["n60_remove_future"]
    result["ma120_near_boundary"] = ratio.abs().le(BOUNDARY_BAND).fillna(False)
    gap_now = work["close"] / prior_high60 - 1.0
    gap_prev = previous_close / previous_prior - 1.0
    result["n60_near_boundary"] = (
        gap_now.abs().le(BOUNDARY_BAND)
        | gap_prev.abs().le(BOUNDARY_BAND)
    ).fillna(False)
    result["ma120_comparable"] = ratio.notna() & cf_ratio.notna()
    result["n60_comparable"] = (
        prior_high60.notna()
        & previous_close.notna()
        & previous_prior.notna()
        & factor.notna()
    )
    return result


def online_asof_price_features(
    rows: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    required = {"date", "stock_id", "raw_close"}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError(f"online rows missing columns: {sorted(missing)}")
    work = rows[list(required)].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work["stock_id"] = work["stock_id"].astype(str)
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    work = work.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

    ratio_by_stock_date = {
        (str(row.stock_id), pd.Timestamp(row.date)): float(row.ratio)
        for row in events.itertuples(index=False)
    }

    ma_out = np.full(len(work), np.nan, dtype=float)
    gate_out = np.zeros(len(work), dtype=bool)
    n60_out = np.zeros(len(work), dtype=bool)
    raw_missing = np.zeros(len(work), dtype=bool)

    for sid, positions in work.groupby("stock_id", sort=False).indices.items():
        hist: deque[float] = deque(maxlen=120)
        for pos in positions:
            day = pd.Timestamp(work.at[pos, "date"])
            event_ratio = ratio_by_stock_date.get((str(sid), day))
            if event_ratio is not None:
                hist = deque(
                    [
                        np.nan
                        if not np.isfinite(v)
                        else round(float(v) * float(event_ratio), 4)
                        for v in hist
                    ],
                    maxlen=120,
                )

            arr = np.asarray(hist, dtype=float)
            prior_high = (
                float(np.max(arr[-60:]))
                if len(arr) >= 60 and np.isfinite(arr[-60:]).all()
                else np.nan
            )
            prev_close = (
                float(arr[-1])
                if len(arr) >= 1 and np.isfinite(arr[-1])
                else np.nan
            )
            prev_prior = (
                float(np.max(arr[-61:-1]))
                if len(arr) >= 61 and np.isfinite(arr[-61:-1]).all()
                else np.nan
            )

            current = float(work.at[pos, "raw_close"]) if pd.notna(work.at[pos, "raw_close"]) else np.nan
            if not np.isfinite(current):
                raw_missing[pos] = True

            if (
                np.isfinite(current)
                and np.isfinite(prior_high)
                and np.isfinite(prev_close)
                and np.isfinite(prev_prior)
            ):
                n60_out[pos] = bool(
                    current > prior_high and prev_close <= prev_prior
                )

            hist.append(current)
            arr2 = np.asarray(hist, dtype=float)
            if len(arr2) >= 120 and np.isfinite(arr2[-120:]).all():
                ma = float(np.mean(arr2[-120:]))
                if ma != 0 and np.isfinite(current):
                    ma_out[pos] = current / ma - 1.0
                    gate_out[pos] = bool(ma_out[pos] >= 0.0)

    out = work[["date", "stock_id"]].copy()
    out["close_to_ma120_online_asof"] = ma_out
    out["ma120_gate_online_asof"] = gate_out
    out["n60_online_asof"] = n60_out
    out["raw_close_missing"] = raw_missing
    return out


def rebuild_final_adjusted_close(
    rows: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    required = {"date", "stock_id", "raw_close"}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError(f"rebuild rows missing columns: {sorted(missing)}")
    work = rows[list(required)].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work["stock_id"] = work["stock_id"].astype(str)
    work["raw_close"] = pd.to_numeric(work["raw_close"], errors="coerce")
    work = work.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

    full_factor = future_factor_for_rows(work, events)
    once = np.round(work["raw_close"].to_numpy(float) * full_factor, 4)
    sequential = work["raw_close"].to_numpy(float).copy()

    event_groups = {
        sid: g for sid, g in events.groupby("stock_id", sort=False)
    }
    for sid, positions in work.groupby("stock_id", sort=False).indices.items():
        ev = event_groups.get(str(sid))
        if ev is None or ev.empty:
            continue
        pos = np.asarray(positions, dtype=int)
        dates = work.iloc[pos]["date"].to_numpy(dtype="datetime64[ns]")
        values = sequential[pos].copy()
        for row in ev.itertuples(index=False):
            mask = dates < np.datetime64(pd.Timestamp(row.date))
            finite = mask & np.isfinite(values)
            values[finite] = np.round(values[finite] * float(row.ratio), 4)
        sequential[pos] = values

    out = work[["date", "stock_id"]].copy()
    out["future_factor"] = full_factor
    out["rebuild_round_once"] = once
    out["rebuild_sequential_round4"] = sequential
    return out


def universe_masks(
    frame: pd.DataFrame,
    *,
    excluded: set[str],
    min_close: float = 10.0,
    turnover_top_fraction: float = 0.25,
) -> pd.DataFrame:
    required = {
        "date", "stock_id", "adjusted_close", "raw_close",
        "Trading_money", "observed_trade", "valid_ohlc",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"universe frame missing columns: {sorted(missing)}")
    x = frame.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    x["adjusted_close"] = pd.to_numeric(x["adjusted_close"], errors="coerce")
    x["raw_close"] = pd.to_numeric(x["raw_close"], errors="coerce")
    x["Trading_money"] = pd.to_numeric(x["Trading_money"], errors="coerce")
    ids = x["stock_id"].str.fullmatch(r"^[1-9]\d{3}$", na=False)
    observed = x["observed_trade"].fillna(False).astype(bool)
    valid = x["valid_ohlc"].fillna(False).astype(bool)
    not_excluded = ~x["stock_id"].isin(excluded)
    fixed = ids & observed & valid & not_excluded

    adj_gate = x["adjusted_close"].ge(min_close).fillna(False)
    raw_gate = x["raw_close"].ge(min_close).fillna(False)
    adj_base = fixed & adj_gate
    raw_base = fixed & raw_gate

    adj_pct = x["Trading_money"].where(adj_base).groupby(x["date"]).rank(
        pct=True, ascending=False, method="average"
    )
    raw_pct = x["Trading_money"].where(raw_base).groupby(x["date"]).rank(
        pct=True, ascending=False, method="average"
    )
    adj_counts = adj_base & adj_pct.le(turnover_top_fraction).fillna(False)
    raw_counts = raw_base & raw_pct.le(turnover_top_fraction).fillna(False)

    out = x[["date", "stock_id", "adjusted_close", "raw_close", "Trading_money"]].copy()
    out["fixed_other_qualifiers"] = fixed
    out["adjusted_close_gate"] = adj_gate
    out["raw_close_gate"] = raw_gate
    out["adjusted_base_pass"] = adj_base
    out["raw_base_pass"] = raw_base
    out["adjusted_turnover_pct"] = adj_pct
    out["raw_turnover_pct"] = raw_pct
    out["adjusted_counts"] = adj_counts
    out["raw_counts"] = raw_counts
    out["raw_close_missing"] = x["raw_close"].isna()
    return out


def synthetic_uniform_scale_case() -> dict[str, object]:
    dates = pd.bdate_range("2020-01-01", periods=140)
    close = np.linspace(20.0, 30.0, len(dates))
    close[-2] = 31.0
    close[-1] = 32.0
    base = pd.DataFrame(
        {"date": dates, "stock_id": "2330", "close": close}
    )
    event = pd.DataFrame(
        {
            "date": [dates[-1] + pd.Timedelta(days=20)],
            "stock_id": ["2330"],
            "before_price": [100.0],
            "after_price": [80.0],
        }
    )
    ev = normalize_dividend_events(event)
    scaled = base.copy()
    scaled["close"] = scaled["close"] * 0.8
    ff = future_factor_for_rows(scaled, ev)
    feature = current_price_feature_frame(scaled, future_factor=ff)
    raw_threshold_before = 11.0
    adjusted_threshold_after = raw_threshold_before * 0.8
    return {
        "max_ma120_abs_diff": float(
            (
                feature["close_to_ma120_current"]
                - feature["close_to_ma120_remove_future"]
            ).abs().max(skipna=True)
        ),
        "ma120_gate_flips": int(feature["ma120_gate_flip"].sum()),
        "n60_flips": int(feature["n60_flip"].sum()),
        "absolute_close_threshold_flips": bool(
            raw_threshold_before >= 10.0
            and adjusted_threshold_after < 10.0
        ),
    }
