from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.features.registry import CAWindowRequirement, FeatureDefinition


@dataclass(frozen=True)
class BreakoutSignalConfig:
    lookback: int = 250
    universe_fraction: float = 0.25
    feature_name: str = "simple_breakout"
    feature_version: str = "v1"

    def __post_init__(self) -> None:
        if self.lookback <= 1:
            raise ValueError("lookback must be greater than 1")
        if not 0 < self.universe_fraction <= 1:
            raise ValueError("universe_fraction must be in (0, 1]")


def simple_breakout_feature_definition(
    config: BreakoutSignalConfig | None = None,
) -> FeatureDefinition:
    cfg = config or BreakoutSignalConfig()
    return FeatureDefinition(
        name=cfg.feature_name,
        version=cfg.feature_version,
        family="technical",
        description=(
            f"{cfg.lookback}-session adjusted-price breakout inside the "
            f"top {cfg.universe_fraction:.0%} turnover universe"
        ),
        dependencies=("adjusted_ohlc", "turnover_value", "tradability"),
        point_in_time_safe=True,
        availability_rule="signal available after signal-session close",
        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ca_window_requirement=CAWindowRequirement.CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK,
    )


def _normalize_adjusted(adjusted: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "stock_id",
        "open",
        "max",
        "min",
        "close",
        "Trading_money",
    }
    missing = sorted(required - set(adjusted.columns))
    if missing:
        raise ValueError(f"adjusted input missing columns: {missing}")

    df = adjusted[list(required)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["stock_id"] = df["stock_id"].astype(str)

    if df[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("adjusted input contains null logical keys")
    if df.duplicated(["date", "stock_id"]).any():
        raise ValueError("adjusted input contains duplicate (date, stock_id) rows")

    for col in ("open", "max", "min", "close", "Trading_money"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _normalize_tradability(tradability: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "stock_id", "observed_trade", "valid_ohlc"}
    missing = sorted(required - set(tradability.columns))
    if missing:
        raise ValueError(f"tradability input missing columns: {missing}")

    df = tradability[list(required)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["stock_id"] = df["stock_id"].astype(str)

    if df[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("tradability input contains null logical keys")
    if df.duplicated(["date", "stock_id"]).any():
        raise ValueError("tradability input contains duplicate (date, stock_id) rows")
    return df


def build_simple_breakout_signals(
    adjusted: pd.DataFrame,
    tradability: pd.DataFrame,
    *,
    config: BreakoutSignalConfig | None = None,
) -> pd.DataFrame:
    """Build the canonical simple breakout research signal.

    Research uses the adjusted price coordinate only. Invalid/non-observed
    stock-days are removed before turnover ranking and breakout formation.

    The output contains signal candidates only. It does not create orders,
    size positions, or supply execution prices.
    """

    cfg = config or BreakoutSignalConfig()
    adj = _normalize_adjusted(adjusted)
    trad = _normalize_tradability(tradability)

    merged = adj.merge(
        trad,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    numeric_id = merged["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geometry = (
        merged["max"] >= merged[["open", "close", "min"]].max(axis=1)
    ) & (
        merged["min"] <= merged[["open", "close", "max"]].min(axis=1)
    )
    valid_turnover = merged["Trading_money"].notna() & merged["Trading_money"].gt(0)
    tradable_observation = (
        merged["_merge"].eq("both")
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
    )

    eligible = merged[
        numeric_id
        & positive
        & geometry
        & valid_turnover
        & tradable_observation
    ].copy()

    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "signal_date",
                "available_date",
                "stock_id",
                "adjusted_close",
                "breakout_prior_high",
                "breakout_excess",
                "turnover_value",
                "turnover_percentile",
                "lookback",
                "feature_name",
                "feature_version",
                "price_semantics",
                "ca_window_requirement",
            ]
        )

    eligible["turnover_percentile"] = eligible.groupby("date")["Trading_money"].rank(
        pct=True,
        ascending=False,
        method="average",
    )
    eligible["in_turnover_universe"] = (
        eligible["turnover_percentile"] <= cfg.universe_fraction
    )

    close = eligible.pivot(index="date", columns="stock_id", values="close").sort_index()
    universe = (
        eligible.pivot(
            index="date",
            columns="stock_id",
            values="in_turnover_universe",
        )
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
        .astype(bool)
    )

    prior_high = close.shift(1).rolling(
        cfg.lookback,
        min_periods=cfg.lookback,
    ).max()
    breakout = (
        (close > prior_high)
        & (close.shift(1) <= prior_high.shift(1))
        & universe
    )

    hits = (
        breakout.stack(future_stack=True)
        .rename("is_signal")
        .reset_index()
    )
    hits = hits[hits["is_signal"]].drop(columns="is_signal")
    if hits.empty:
        return pd.DataFrame(
            columns=[
                "signal_date",
                "available_date",
                "stock_id",
                "adjusted_close",
                "breakout_prior_high",
                "breakout_excess",
                "turnover_value",
                "turnover_percentile",
                "lookback",
                "feature_name",
                "feature_version",
                "price_semantics",
                "ca_window_requirement",
            ]
        )

    prior_high_long = (
        prior_high.stack(future_stack=True)
        .rename("breakout_prior_high")
        .reset_index()
    )
    meta = eligible[
        ["date", "stock_id", "close", "Trading_money", "turnover_percentile"]
    ].merge(
        prior_high_long,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
    ).rename(
        columns={
            "date": "signal_date",
            "close": "adjusted_close",
            "Trading_money": "turnover_value",
        }
    )
    hits = hits.rename(columns={"date": "signal_date"})
    out = hits.merge(
        meta,
        on=["signal_date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    out["available_date"] = out["signal_date"]
    out["breakout_excess"] = (
        out["adjusted_close"] / out["breakout_prior_high"] - 1.0
    )
    out["lookback"] = cfg.lookback
    out["feature_name"] = cfg.feature_name
    out["feature_version"] = cfg.feature_version
    out["price_semantics"] = SignalPriceSemantics.SCALE_SENSITIVE.value
    out["ca_window_requirement"] = (
        CAWindowRequirement.CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK.value
    )

    return out[
        [
            "signal_date",
            "available_date",
            "stock_id",
            "adjusted_close",
            "breakout_prior_high",
            "breakout_excess",
            "turnover_value",
            "turnover_percentile",
            "lookback",
            "feature_name",
            "feature_version",
            "price_semantics",
            "ca_window_requirement",
        ]
    ].sort_values(["signal_date", "stock_id"]).reset_index(drop=True)
