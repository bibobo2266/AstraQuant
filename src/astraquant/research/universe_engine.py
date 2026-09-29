from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

import pandas as pd

from astraquant.research.component_registry import ComponentRegistry
from astraquant.research.strategy_config import (
    AllPoolConfig,
    LogicalOp,
    UniverseConfig,
)


@dataclass(frozen=True)
class UniverseContext:
    p2_060_excluded_tickers: frozenset[str]
    p2_060_exclusion_sha256: str


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


class UniversePoolEvaluator(Protocol):
    def __call__(
        self,
        *,
        panel: pd.DataFrame,
        base_pass: pd.Series,
        config: object,
        context: UniverseContext,
    ) -> pd.Series: ...


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
    return base_pass & pct.le(float(config.turnover_top_fraction)).fillna(False)


def default_universe_registry() -> ComponentRegistry[UniversePoolEvaluator]:
    registry: ComponentRegistry[UniversePoolEvaluator] = ComponentRegistry("universe")
    registry.register("ALL", _all_pool)
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
        for i, pool in enumerate(config.pools):
            handler = self.registry.get(pool.type)
            value = handler(
                panel=work,
                base_pass=base_pass,
                config=pool,
                context=context,
            )
            if len(value) != len(work):
                raise ValueError(f"universe pool {pool.type} changed row count")
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
        for name, value in zip(pool_names, pool_values):
            result[name] = value.to_numpy(bool)
        result["counts"] = counts.to_numpy(bool)
        return UniverseMask(frame=result, config_name=config.name)
