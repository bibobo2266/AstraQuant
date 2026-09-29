from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from astraquant.research.component_registry import ComponentRegistry
from astraquant.research.feature_cache import FeatureCache, FeatureCacheKey
from astraquant.research.strategy_config import ComponentSpec, LogicalOp, SignalConfig
from astraquant.research.technical_components import (
    bollinger_upper_break,
    column_threshold,
    column_value,
    consecutive_up_days,
    gap_up,
    kd_low_zone_golden_cross,
    long_term_trend_structure,
    ma_golden_cross,
    macd_cross_above_zero,
    n_session_high,
    pullback_reclaim,
    rsi_cross,
    rsi_filter,
    rsi_rank,
    volume_spike,
)
from astraquant.research.universe_engine import UniverseMask


@dataclass(frozen=True)
class SignalContext:
    source_revision: str
    availability_policy: str = "adjusted-research-close"


class SignalComponentEvaluator(Protocol):
    def __call__(
        self,
        *,
        panel: pd.DataFrame,
        spec: ComponentSpec,
        cache: FeatureCache,
        context: SignalContext,
    ) -> pd.Series: ...


@dataclass(frozen=True)
class SignalPlan:
    config: SignalConfig
    trigger: SignalComponentEvaluator
    filters: tuple[SignalComponentEvaluator, ...]
    rankings: tuple[SignalComponentEvaluator, ...]


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "stock_id", "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"signal panel missing columns: {sorted(missing)}")
    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    if out.duplicated(["date", "stock_id"]).any():
        raise ValueError("signal panel contains duplicate logical keys")
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)


def _n_session_high(
    *,
    panel: pd.DataFrame,
    spec: ComponentSpec,
    cache: FeatureCache,
    context: SignalContext,
) -> pd.Series:
    lookback = int(spec.params.get("lookback", 250))
    if lookback <= 1:
        raise ValueError("N_SESSION_HIGH lookback must be > 1")

    key = FeatureCacheKey.build(
        source_revision=context.source_revision,
        feature_name="prior_high",
        params={"lookback": lookback},
        availability_policy=context.availability_policy,
    )

    def compute() -> pd.Series:
        prior = (
            panel.groupby("stock_id", sort=False)["close"]
            .transform(lambda s: s.shift(1).rolling(lookback, min_periods=lookback).max())
        )
        return prior

    prior_high = cache.get_or_compute(key, compute)
    previous_close = panel.groupby("stock_id", sort=False)["close"].shift(1)
    previous_prior = prior_high.groupby(panel["stock_id"], sort=False).shift(1)
    return (
        panel["close"].gt(prior_high)
        & previous_close.le(previous_prior)
        & prior_high.notna()
    ).fillna(False)


def default_trigger_registry() -> ComponentRegistry[SignalComponentEvaluator]:
    registry: ComponentRegistry[SignalComponentEvaluator] = ComponentRegistry("signal trigger")
    registry.register("N_SESSION_HIGH", n_session_high)
    registry.register("GAP_UP", gap_up)
    registry.register("VOLUME_SPIKE", volume_spike)
    registry.register("MA_GOLDEN_CROSS", ma_golden_cross)
    registry.register("MACD_CROSS_ABOVE_ZERO", macd_cross_above_zero)
    registry.register("KD_LOW_ZONE_GOLDEN_CROSS", kd_low_zone_golden_cross)
    registry.register("RSI_CROSS", rsi_cross)
    registry.register("BOLLINGER_UPPER_BREAK", bollinger_upper_break)
    registry.register("PULLBACK_RECLAIM", pullback_reclaim)
    registry.register("CONSECUTIVE_UP_DAYS", consecutive_up_days)
    return registry


def default_filter_registry() -> ComponentRegistry[SignalComponentEvaluator]:
    registry: ComponentRegistry[SignalComponentEvaluator] = ComponentRegistry("signal filter")
    registry.register("RSI", rsi_filter)
    registry.register("LONG_TERM_TREND_STRUCTURE", long_term_trend_structure)
    registry.register("COLUMN_THRESHOLD", column_threshold)
    return registry


def default_ranking_registry() -> ComponentRegistry[SignalComponentEvaluator]:
    registry: ComponentRegistry[SignalComponentEvaluator] = ComponentRegistry("signal ranking")
    registry.register("RSI", rsi_rank)
    registry.register("COLUMN_VALUE", column_value)
    return registry


class SignalCompiler:
    def __init__(
        self,
        *,
        triggers: ComponentRegistry[SignalComponentEvaluator] | None = None,
        filters: ComponentRegistry[SignalComponentEvaluator] | None = None,
        rankings: ComponentRegistry[SignalComponentEvaluator] | None = None,
    ) -> None:
        self.triggers = triggers or default_trigger_registry()
        self.filters = filters or default_filter_registry()
        self.rankings = rankings or default_ranking_registry()

    def compile(self, config: SignalConfig) -> SignalPlan:
        trigger = self.triggers.get(config.trigger.type)
        filter_handlers = tuple(self.filters.get(x.type) for x in config.filters)
        ranking_handlers = tuple(self.rankings.get(x.type) for x in config.ranking)
        return SignalPlan(
            config=config,
            trigger=trigger,
            filters=filter_handlers,
            rankings=ranking_handlers,
        )


class SignalEvaluator:
    def __init__(self, cache: FeatureCache | None = None) -> None:
        self.cache = cache or FeatureCache()

    def evaluate(
        self,
        plan: SignalPlan,
        panel: pd.DataFrame,
        universe_mask: UniverseMask,
        context: SignalContext,
    ) -> pd.DataFrame:
        work = _normalize_panel(panel)
        mask = universe_mask.frame[["date", "stock_id", "counts"]].copy()
        merged = work.merge(mask, on=["date", "stock_id"], how="left", validate="one_to_one")
        if len(merged) != len(work):
            raise ValueError("universe mask changed signal-panel row count")
        merged["counts"] = merged["counts"].fillna(False).astype(bool)

        triggered = plan.trigger(
            panel=merged,
            spec=plan.config.trigger,
            cache=self.cache,
            context=context,
        ).fillna(False).astype(bool)

        if plan.filters:
            if plan.config.filter_combine is LogicalOp.AND:
                filter_pass = pd.Series(True, index=merged.index)
                for spec, handler in zip(plan.config.filters, plan.filters):
                    filter_pass &= handler(
                        panel=merged,
                        spec=spec,
                        cache=self.cache,
                        context=context,
                    ).fillna(False).astype(bool)
            else:
                filter_pass = pd.Series(False, index=merged.index)
                for spec, handler in zip(plan.config.filters, plan.filters):
                    filter_pass |= handler(
                        panel=merged,
                        spec=spec,
                        cache=self.cache,
                        context=context,
                    ).fillna(False).astype(bool)
        else:
            filter_pass = pd.Series(True, index=merged.index)

        result = merged[["date", "stock_id"]].copy()
        result = result.rename(columns={"date": "signal_date"})
        result["triggered"] = triggered.to_numpy(bool)
        result["filter_pass"] = filter_pass.to_numpy(bool)
        result["universe_counts"] = merged["counts"].to_numpy(bool)
        result["counts_as_candidate"] = (
            triggered & filter_pass & merged["counts"]
        ).to_numpy(bool)

        for spec, handler in zip(plan.config.ranking, plan.rankings):
            name = str(spec.params.get("name", spec.type)).lower()
            result[f"rank_{name}"] = handler(
                panel=merged,
                spec=spec,
                cache=self.cache,
                context=context,
            ).to_numpy()

        return result
