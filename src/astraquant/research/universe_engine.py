from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from astraquant.research.component_registry import ComponentRegistry, UnsupportedComponentError
from astraquant.research.config_io import load_theme_file
from astraquant.research.strategy_config import (
    AllPoolConfig,
    IndustryThemePoolConfig,
    LogicalOp,
    ThemeGroupingConfig,
    UniverseConfig,
)


@dataclass(frozen=True)
class UniverseContext:
    p2_060_excluded_tickers: frozenset[str]
    p2_060_exclusion_sha256: str
    theme_root: Path | None = None


@dataclass(frozen=True)
class UniverseMask:
    frame: pd.DataFrame
    config_name: str

    def __post_init__(self) -> None:
        required = {"date", "stock_id", "base_pass", "counts"}
        missing = required - set(self.frame.columns)
        if missing:
            raise ValueError(f"universe mask missing columns: {sorted(missing)}")
        if self.frame.duplicated(["date", "stock_id"]).any():
            raise ValueError("universe mask contains duplicate logical keys")

    def theme_member_counts_over_time(self) -> pd.DataFrame:
        theme_cols = [c for c in self.frame.columns if c.startswith("theme_")]
        rows: list[pd.DataFrame] = []
        for col in theme_cols:
            counts = (
                self.frame.groupby("date", as_index=False)[col]
                .sum()
                .rename(columns={col: "member_count"})
            )
            counts["theme"] = col.removeprefix("theme_")
            rows.append(counts[["date", "theme", "member_count"]])
        if not rows:
            return pd.DataFrame(columns=["date", "theme", "member_count"])
        return pd.concat(rows, ignore_index=True).sort_values(
            ["theme", "date"], kind="stable"
        ).reset_index(drop=True)


@dataclass(frozen=True)
class PoolEvaluation:
    mask: pd.Series
    details: dict[str, pd.Series]


class UniversePoolEvaluator(Protocol):
    def __call__(
        self,
        *,
        panel: pd.DataFrame,
        base_pass: pd.Series,
        config: object,
        context: UniverseContext,
    ) -> PoolEvaluation: ...


def _normalized_panel(panel: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "stock_id",
        "close",
        "Trading_money",
        "observed_trade",
        "valid_ohlc",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"universe panel missing columns: {sorted(missing)}")
    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    if out[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("universe panel contains null logical keys")
    if out.duplicated(["date", "stock_id"]).any():
        raise ValueError("universe panel contains duplicate logical keys")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["Trading_money"] = pd.to_numeric(out["Trading_money"], errors="coerce")
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)


def _all_pool(
    *,
    panel: pd.DataFrame,
    base_pass: pd.Series,
    config: AllPoolConfig,
    context: UniverseContext,
) -> pd.Series:
    turnover = panel["Trading_money"].where(base_pass)
    pct = turnover.groupby(panel["date"]).rank(
        pct=True,
        ascending=False,
        method="average",
    )
    mask = base_pass & pct.le(float(config.turnover_top_fraction)).fillna(False)
    return PoolEvaluation(mask=mask, details={"turnover_percentile": pct})



def _theme_group_mask(
    *,
    panel: pd.DataFrame,
    config: ThemeGroupingConfig,
    context: UniverseContext,
) -> PoolEvaluation:
    if context.theme_root is None:
        raise ValueError("THEME grouping requires UniverseContext.theme_root")

    theme_masks: list[pd.Series] = []
    details: dict[str, pd.Series] = {}
    for theme_name in config.themes:
        path = context.theme_root / f"{theme_name}.yaml"
        theme = load_theme_file(path)
        if theme.theme != theme_name:
            raise ValueError(
                f"theme file name/content mismatch: requested={theme_name} file={theme.theme}"
            )
        mask = pd.Series(False, index=panel.index)
        for member in theme.members:
            active = panel["stock_id"].eq(str(member.ticker)) & panel["date"].ge(
                pd.Timestamp(member.from_date)
            )
            if member.to is not None:
                active &= panel["date"].le(pd.Timestamp(member.to))
            mask |= active
        theme_masks.append(mask)
        details[f"theme_{theme_name}"] = mask

    if not theme_masks:
        raise ValueError("THEME grouping requires at least one theme")
    if config.combine is LogicalOp.AND:
        combined = pd.Series(True, index=panel.index)
        for mask in theme_masks:
            combined &= mask
    else:
        combined = pd.Series(False, index=panel.index)
        for mask in theme_masks:
            combined |= mask
    return PoolEvaluation(mask=combined, details=details)


def _industry_theme_pool(
    *,
    panel: pd.DataFrame,
    base_pass: pd.Series,
    config: IndustryThemePoolConfig,
    context: UniverseContext,
) -> PoolEvaluation:
    group_results: list[PoolEvaluation] = []
    for group in config.groups:
        if isinstance(group, ThemeGroupingConfig):
            group_results.append(
                _theme_group_mask(panel=panel, config=group, context=context)
            )
        else:
            raise UnsupportedComponentError(
                f"grouping mode {group.mode} is declared by schema but has no evaluator yet"
            )

    if not group_results:
        raise ValueError("INDUSTRY_THEME requires at least one grouping mode")

    if config.combine is LogicalOp.AND:
        combined = pd.Series(True, index=panel.index)
        for result in group_results:
            combined &= result.mask
    else:
        combined = pd.Series(False, index=panel.index)
        for result in group_results:
            combined |= result.mask

    details: dict[str, pd.Series] = {}
    for result in group_results:
        details.update(result.details)
    return PoolEvaluation(mask=base_pass & combined, details=details)


def default_universe_registry() -> ComponentRegistry[UniversePoolEvaluator]:
    registry: ComponentRegistry[UniversePoolEvaluator] = ComponentRegistry("universe")
    registry.register("ALL", _all_pool)
    registry.register("INDUSTRY_THEME", _industry_theme_pool)
    return registry


class UniverseCompiler:
    def __init__(
        self,
        registry: ComponentRegistry[UniversePoolEvaluator] | None = None,
    ) -> None:
        self.registry = registry or default_universe_registry()

    def compile(
        self,
        config: UniverseConfig,
        panel: pd.DataFrame,
        context: UniverseContext,
    ) -> UniverseMask:
        if config.base.p2_060_exclusion_sha256 != context.p2_060_exclusion_sha256:
            raise ValueError(
                "P2-060 exclusion SHA mismatch: "
                f"config={config.base.p2_060_exclusion_sha256} "
                f"context={context.p2_060_exclusion_sha256}"
            )

        work = _normalized_panel(panel)
        ids = work["stock_id"].str.fullmatch(config.base.ticker_pattern, na=False)
        close_ok = work["close"].ge(float(config.base.min_close_twd)).fillna(False)
        observed = (
            work["observed_trade"].fillna(False).astype(bool)
            if config.base.require_observed_trade
            else pd.Series(True, index=work.index)
        )
        valid = (
            work["valid_ohlc"].fillna(False).astype(bool)
            if config.base.require_valid_ohlc
            else pd.Series(True, index=work.index)
        )
        not_excluded = ~work["stock_id"].isin(context.p2_060_excluded_tickers)
        base_pass = ids & close_ok & observed & valid & not_excluded

        pool_values: list[pd.Series] = []
        pool_names: list[str] = []
        pool_evaluations: list[PoolEvaluation] = []
        for i, pool in enumerate(config.pools):
            handler = self.registry.get(pool.type)
            evaluation = handler(
                panel=work,
                base_pass=base_pass,
                config=pool,
                context=context,
            )
            value = evaluation.mask
            if len(value) != len(work):
                raise ValueError(f"universe pool {pool.type} changed row count")
            pool_evaluations.append(evaluation)
            pool_values.append(value.fillna(False).astype(bool))
            pool_names.append(f"pool_{i}_{pool.type.lower()}")

        if config.combine is LogicalOp.AND:
            counts = base_pass.copy()
            for value in pool_values:
                counts &= value
        else:
            combined = pd.Series(False, index=work.index)
            for value in pool_values:
                combined |= value
            counts = base_pass & combined

        result = work[["date", "stock_id"]].copy()
        result["base_pass"] = base_pass.to_numpy(bool)
        detail_columns: dict[str, pd.Series] = {}
        for evaluation in pool_evaluations:
            overlap = set(detail_columns) & set(evaluation.details)
            if overlap:
                raise ValueError(f"duplicate universe detail columns: {sorted(overlap)}")
            detail_columns.update(evaluation.details)

        for name, value in zip(pool_names, pool_values):
            result[name] = value.to_numpy(bool)
        for name, value in detail_columns.items():
            result[name] = value.to_numpy()
        result["counts"] = counts.to_numpy(bool)
        return UniverseMask(frame=result, config_name=config.name)
