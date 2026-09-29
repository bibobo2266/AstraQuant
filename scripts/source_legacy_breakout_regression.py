#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig
from astraquant.research.candidates import legacy_signals_to_candidates
from astraquant.research.epoch_governance import assert_legacy_breakout_nav_regression

from source_config_sweep import _research_panel
from source_strategy_integration_smoke import build_supported_ca, pit_unsafe_ca_tickers

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REGRESSION_START = pd.Timestamp("2016-01-04")
REGRESSION_SIGNAL_END = pd.Timestamp("2026-06-30")
REGRESSION_END = pd.Timestamp("2026-07-07")
INITIAL_CASH = 10_000_000.0


def main() -> None:
    _, adjusted, tradability = _research_panel()
    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(REGRESSION_START, REGRESSION_SIGNAL_END)
    ].copy()
    quarantined = pit_unsafe_ca_tickers(
        start=REGRESSION_START,
        end=REGRESSION_SIGNAL_END,
    )
    signals = signals[~signals["stock_id"].astype(str).isin(quarantined)].copy()
    declaration = SignalDeclaration(
        source="CANONICAL_SIMPLE_BREAKOUT_V1",
        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
    )
    candidates = legacy_signals_to_candidates(signals, declaration=declaration)

    sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if REGRESSION_START <= pd.Timestamp(x) <= REGRESSION_END
    ]
    session_set = set(sessions)
    valuation_tickers = set(candidates["stock_id"].astype(str))
    ca_instructions, unsupported_ca_cash, _ = build_supported_ca(
        candidate_tickers=valuation_tickers,
        sessions=session_set,
    )
    if unsupported_ca_cash:
        raise SystemExit("回歸失敗；差異金額：無法計算")

    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope=valuation_tickers,
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
            reentry_gap_sessions=20,
            max_hold_sessions=250,
            lot_size=1000,
            random_seed=0,
        )
    )
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=declaration,
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )
    result = simulator.run(
        sessions=[x.date() for x in sessions],
        candidates=candidates,
        corporate_actions=ca_instructions,
    )
    final_nav = float(result.sessions[-1].snapshot.valuation.nav)
    assert_legacy_breakout_nav_regression(final_nav)
    print("legacy_breakout_final_nav_match=true")


if __name__ == "__main__":
    main()
