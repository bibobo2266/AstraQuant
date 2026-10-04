from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from astraquant.research.component_registry import ComponentRegistry
from astraquant.research.feature_cache import FeatureCache, FeatureCacheKey
from astraquant.research.rsi_computability import (
    SignalComputabilityContext,
    TriState,
    combine_tristate,
    strict_condition_for_component,
    strict_ranking_for_component,
)
from astraquant.research.strategy_config import ComponentSpec, LogicalOp, SignalConfig
from astraquant.research.technical_components import (
    kd_saturation_release,
    kd_saturation_state,
    rsi_pullback_reclaim,
    vcp_breakout,
    vcp_three_segment,
    rsi_relative,
    overnight_market_context,
    bollinger_compression_breakout,
    bollinger_compression,
    anchor_reversal,
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
    registry.register("RSI_PULLBACK_RECLAIM", rsi_pullback_reclaim)
    registry.register("KD_SATURATION_RELEASE", kd_saturation_release)
    registry.register("BOLLINGER_UPPER_BREAK", bollinger_upper_break)
    registry.register("BOLLINGER_COMPRESSION_BREAKOUT", bollinger_compression_breakout)
    registry.register("VCP_BREAKOUT", vcp_breakout)
    registry.register("VCP_THREE_SEGMENT", vcp_three_segment)
    registry.register("ANCHOR_REVERSAL", anchor_reversal)
    registry.register("PULLBACK_RECLAIM", pullback_reclaim)
    registry.register("CONSECUTIVE_UP_DAYS", consecutive_up_days)
    return registry


def default_filter_registry() -> ComponentRegistry[SignalComponentEvaluator]:
    registry: ComponentRegistry[SignalComponentEvaluator] = ComponentRegistry("signal filter")
    registry.register("RSI", rsi_filter)
    registry.register("LONG_TERM_TREND_STRUCTURE", long_term_trend_structure)
    registry.register("BOLLINGER_COMPRESSION", bollinger_compression)
    registry.register("RSI_RELATIVE", rsi_relative)
    registry.register("KD_SATURATION_STATE", kd_saturation_state)
    registry.register("OVERNIGHT_MARKET_CONTEXT", overnight_market_context)
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

    def prepare_panel(
        self,
        panel: pd.DataFrame,
        universe_mask: UniverseMask,
    ) -> pd.DataFrame:
        work = _normalize_panel(panel)
        mask = universe_mask.frame[["date", "stock_id", "counts"]].copy()
        merged = work.merge(
            mask,
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
        if len(merged) != len(work):
            raise ValueError("universe mask changed signal-panel row count")
        merged["counts"] = merged["counts"].fillna(False).astype(bool)
        return merged

    def _apply_strict_rsi_contract(
        self,
        *,
        plan: SignalPlan,
        prepared_panel: pd.DataFrame,
        result: pd.DataFrame,
        context: SignalContext,
        computability_context: SignalComputabilityContext,
        triggered: pd.Series,
        filter_values: tuple[pd.Series, ...],
        ranking_values: tuple[pd.Series, ...],
    ) -> pd.DataFrame:
        trigger_state, trigger_reason = strict_condition_for_component(
            panel=prepared_panel,
            spec=plan.config.trigger,
            legacy_bool=triggered,
            cache=self.cache,
            signal_context=context,
            computability_context=computability_context,
        )
        result["strict_trigger_state"] = trigger_state.to_numpy()
        result["strict_trigger_reason"] = trigger_reason.to_numpy()

        filter_states: list[pd.Series] = []
        for index, (spec, legacy_bool) in enumerate(
            zip(plan.config.filters, filter_values)
        ):
            state, reason = strict_condition_for_component(
                panel=prepared_panel,
                spec=spec,
                legacy_bool=legacy_bool,
                cache=self.cache,
                signal_context=context,
                computability_context=computability_context,
            )
            filter_states.append(state)
            result[f"strict_filter_{index}_state"] = state.to_numpy()
            result[f"strict_filter_{index}_reason"] = reason.to_numpy()

        combined_states: list[str] = []
        all_filter_components_computable: list[bool] = []
        for row_index in range(len(result)):
            states = [
                TriState(state.iloc[row_index]) for state in filter_states
            ]
            combined = combine_tristate(
                states,
                plan.config.filter_combine.value,
            )
            combined_states.append(combined.value)
            all_filter_components_computable.append(
                all(state is not TriState.UNKNOWN for state in states)
            )
        result["strict_filter_condition_state"] = combined_states
        result["strict_all_filter_components_computable"] = (
            all_filter_components_computable
        )

        strict_candidate_states: list[str] = []
        strict_candidates: list[bool] = []
        for row_index in range(len(result)):
            universe_state = (
                TriState.TRUE
                if bool(result.iloc[row_index]["universe_counts"])
                else TriState.FALSE
            )
            candidate_state = combine_tristate(
                (
                    universe_state,
                    TriState(trigger_state.iloc[row_index]),
                    TriState(combined_states[row_index]),
                ),
                "AND",
            )
            strict_candidate_states.append(candidate_state.value)
            strict_candidates.append(candidate_state is TriState.TRUE)
        result["strict_candidate_state"] = strict_candidate_states
        result["strict_counts_as_candidate"] = strict_candidates
        result["strict_contract_version"] = (
            computability_context.contract_version
        )
        result["strict_expected_sessions_source"] = (
            computability_context.expected_sessions_source
        )

        for spec, legacy_values in zip(
            plan.config.ranking,
            ranking_values,
        ):
            name = str(spec.params.get("name", spec.type)).lower()
            strict_values, reason = strict_ranking_for_component(
                panel=prepared_panel,
                spec=spec,
                legacy_values=legacy_values,
                cache=self.cache,
                signal_context=context,
                computability_context=computability_context,
            )
            result[f"strict_rank_{name}"] = strict_values.to_numpy()
            result[f"strict_rank_{name}_reason"] = reason.to_numpy()

        return result

    def evaluate_prepared(
        self,
        plan: SignalPlan,
        prepared_panel: pd.DataFrame,
        context: SignalContext,
        *,
        computability_context: SignalComputabilityContext | None = None,
    ) -> pd.DataFrame:
        merged = prepared_panel

        triggered = plan.trigger(
            panel=merged,
            spec=plan.config.trigger,
            cache=self.cache,
            context=context,
        ).fillna(False).astype(bool)

        filter_values = tuple(
            handler(
                panel=merged,
                spec=spec,
                cache=self.cache,
                context=context,
            ).fillna(False).astype(bool)
            for spec, handler in zip(plan.config.filters, plan.filters)
        )
        if filter_values:
            if plan.config.filter_combine is LogicalOp.AND:
                filter_pass = pd.Series(True, index=merged.index)
                for value in filter_values:
                    filter_pass &= value
            else:
                filter_pass = pd.Series(False, index=merged.index)
                for value in filter_values:
                    filter_pass |= value
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

        ranking_values: list[pd.Series] = []
        for spec, handler in zip(plan.config.ranking, plan.rankings):
            name = str(spec.params.get("name", spec.type)).lower()
            values = handler(
                panel=merged,
                spec=spec,
                cache=self.cache,
                context=context,
            )
            ranking_values.append(values)
            result[f"rank_{name}"] = values.to_numpy()

        if computability_context is not None:
            return self._apply_strict_rsi_contract(
                plan=plan,
                prepared_panel=merged,
                result=result,
                context=context,
                computability_context=computability_context,
                triggered=triggered,
                filter_values=filter_values,
                ranking_values=tuple(ranking_values),
            )
        return result

    def evaluate(
        self,
        plan: SignalPlan,
        panel: pd.DataFrame,
        universe_mask: UniverseMask,
        context: SignalContext,
        *,
        computability_context: SignalComputabilityContext | None = None,
    ) -> pd.DataFrame:
        prepared = self.prepare_panel(panel, universe_mask)
        return self.evaluate_prepared(
            plan,
            prepared,
            context,
            computability_context=computability_context,
        )
