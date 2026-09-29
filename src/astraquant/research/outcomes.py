from __future__ import annotations

import pandas as pd


def build_forward_outcomes_with_cross_sectional_demean(
    panel: pd.DataFrame,
    *,
    excluded_tickers: set[str] | frozenset[str],
    forward_sessions: int,
    min_cross_section: int = 200,
) -> pd.DataFrame:
    """Build absolute and same-day cross-sectionally demeaned forward returns.

    The demean universe is the PIT-common-support daily panel restricted to:
    - four-digit numeric ordinary-share IDs;
    - not in the frozen exclusion set;
    - observed_trade and valid_ohlc on the signal date.

    Demeaned outcome is undefined for dates with fewer than min_cross_section
    valid forward-return observations.
    """
    required = {
        "date",
        "stock_id",
        "close",
        "observed_trade",
        "valid_ohlc",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"outcome panel missing columns: {sorted(missing)}")
    if forward_sessions <= 0:
        raise ValueError("forward_sessions must be positive")
    if min_cross_section <= 0:
        raise ValueError("min_cross_section must be positive")

    x = panel[list(required)].copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    x["close"] = pd.to_numeric(x["close"], errors="coerce")
    if x[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("outcome panel contains null logical keys")
    if x.duplicated(["date", "stock_id"]).any():
        raise ValueError("outcome panel contains duplicate logical keys")

    x = x.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    grouped = x.groupby("stock_id", sort=False)
    future = grouped["close"].shift(-forward_sessions)
    x["forward_date"] = grouped["date"].shift(-forward_sessions)
    x["forward_return"] = future / x["close"] - 1.0

    common_support = (
        x["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & ~x["stock_id"].isin(excluded_tickers)
        & x["observed_trade"].fillna(False).astype(bool)
        & x["valid_ohlc"].fillna(False).astype(bool)
        & x["forward_return"].notna()
    )
    eligible_return = x["forward_return"].where(common_support)
    x["demean_cross_section_count"] = (
        common_support.astype(int).groupby(x["date"], sort=False).transform("sum")
    )
    x["demean_cross_section_mean"] = (
        eligible_return.groupby(x["date"], sort=False).transform("mean")
    )
    valid_date = x["demean_cross_section_count"].ge(min_cross_section)
    x.loc[~valid_date, "demean_cross_section_mean"] = pd.NA
    x["demeaned_forward_return"] = (
        x["forward_return"] - x["demean_cross_section_mean"]
    )
    return x[
        [
            "date",
            "stock_id",
            "forward_date",
            "forward_return",
            "demean_cross_section_count",
            "demean_cross_section_mean",
            "demeaned_forward_return",
        ]
    ]
