#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
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

from source_strategy_integration_smoke import (
    SIGNAL_START,
    SIGNAL_END,
    DRAIN_SESSIONS,
    build_supported_ca,
    load_adjusted,
    load_tradability,
    pit_unsafe_ca_tickers,
)

REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_STRATEGY_PERFORMANCE_REPORT.md"))
INITIAL_CASH = 10_000_000.0


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)

    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    quarantined_tickers = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    quarantined_signal_rows = int(
        signals["stock_id"].astype(str).isin(quarantined_tickers).sum()
    )
    signals = signals[
        ~signals["stock_id"].astype(str).isin(quarantined_tickers)
    ].copy()

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    eligible_end_positions = [i for i, x in enumerate(market_sessions) if x <= SIGNAL_END]
    if not eligible_end_positions:
        raise SystemExit("BLOCKED: signal end precedes first source session")
    end_pos = max(eligible_end_positions)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]
    session_set = set(sim_sessions)

    candidate_tickers = set(signals["stock_id"].astype(str))
    ca_instructions, unsupported_ca_cash, unsupported_ca_summary = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=session_set,
    )
    if unsupported_ca_cash:
        raise SystemExit(
            "BLOCKED: unsupported corporate-action rows remain "
            f"{unsupported_ca_summary}"
        )

    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(
                Path(os.environ.get(
                    "SOURCE_ROOT",
                    "source_runtime/minervini_picks/data",
                )).resolve()
            ),
            ticker_scope=candidate_tickers,
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
        signal=SignalDeclaration(
            source="CANONICAL_SIMPLE_BREAKOUT_V1",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )

    result = simulator.run(
        sessions=[x.date() for x in sim_sessions],
        signals=signals,
        corporate_actions=ca_instructions,
    )

    dates = pd.DatetimeIndex([pd.Timestamp(x.session_date) for x in result.sessions])
    nav = pd.Series(
        [float(x.snapshot.valuation.nav) for x in result.sessions],
        index=dates,
        dtype=float,
    )
    if nav.empty or (nav <= 0).any():
        raise SystemExit("FAIL: NAV series is empty or nonpositive")

    daily_returns = nav.pct_change().dropna()
    total_return = nav.iloc[-1] / INITIAL_CASH - 1.0
    elapsed_years = (dates[-1] - dates[0]).days / 365.2425
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    running_peak = nav.cummax()
    drawdown = nav / running_peak - 1.0
    max_drawdown = float(drawdown.min())
    max_dd_date = pd.Timestamp(drawdown.idxmin()).date()

    ann_vol = float(daily_returns.std(ddof=1) * math.sqrt(252)) if len(daily_returns) > 1 else float("nan")
    sharpe = (
        float(daily_returns.mean() / daily_returns.std(ddof=1) * math.sqrt(252))
        if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0
        else float("nan")
    )
    positive_day_rate = float((daily_returns > 0).mean()) if len(daily_returns) else float("nan")
    best_day = float(daily_returns.max()) if len(daily_returns) else float("nan")
    worst_day = float(daily_returns.min()) if len(daily_returns) else float("nan")

    checks = {
        "same_signal_window_as_long_horizon_probe": SIGNAL_START == pd.Timestamp("2016-01-04") and SIGNAL_END == pd.Timestamp("2026-06-30"),
        "same_policy_configuration": True,
        "raw_nav_series_complete": len(nav) == len(sim_sessions),
        "no_unsupported_ca_cash": unsupported_ca_cash == 0,
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_tickers & quarantined_tickers),
        "positive_nav_all_sessions": bool((nav > 0).all()),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Frozen Canonical Strategy Descriptive Performance Report",
        "",
        f"Status: **{status}**",
        "",
        "This report computes descriptive statistics for the exact audited canonical long-horizon configuration. It is not OOS validation, robustness validation, parameter promotion, or an investment recommendation.",
        "",
        "## Frozen configuration",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation/drain horizon: {dates[0].date()} through {dates[-1].date()}",
        f"- RAW NAV sessions: {len(nav):,}",
        f"- starting capital: {INITIAL_CASH:,.2f}",
        f"- canonical signals supplied: {len(signals):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined_tickers):,}",
        f"- signal rows removed by PIT CA quarantine: {quarantined_signal_rows:,}",
        "- policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0",
        "- execution assumptions: zero explicit fees, zero slippage in this frozen descriptive run",
        "",
        "## Descriptive statistics",
        "",
        f"- final NAV: {nav.iloc[-1]:,.2f}",
        f"- total return: {_pct(total_return)}",
        f"- CAGR: {_pct(cagr)}",
        f"- maximum drawdown: {_pct(max_drawdown)}",
        f"- maximum drawdown date: {max_dd_date}",
        f"- annualized daily volatility (sqrt(252)): {_pct(ann_vol)}",
        f"- daily Sharpe ratio (rf=0, sqrt(252)): {sharpe:.3f}",
        f"- positive-session return rate: {_pct(positive_day_rate)}",
        f"- best session return: {_pct(best_day)}",
        f"- worst session return: {_pct(worst_day)}",
        "",
        "## Activity/accounting counts",
        "",
        f"- entries executed: {result.total_entries:,}",
        f"- RAW stop exits: {result.total_stop_exits:,}",
        f"- RAW max-hold exits: {result.total_max_hold_exits:,}",
        f"- blocked exit attempts: {result.total_blocked_exits:,}",
        f"- corporate actions applied: {result.total_corporate_actions:,}",
        f"- corporate-action cash payments settled: {result.total_corporate_cash_payments:,}",
        f"- ending pending receivables: {portfolio.cash.pending_receivables:,.6f}",
        f"- ending pending payables: {portfolio.cash.pending_payables:,.6f}",
        "",
        "## Reproducibility gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Interpretation boundary",
        "",
        "These are in-sample/descriptive statistics for one frozen canonical configuration. They do not establish expected future returns. The next research steps are temporal replication, execution sensitivity, parameter-plateau testing, falsification/placebo work, and then truly locked future OOS evaluation.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: descriptive performance reproducibility gate failed")


if __name__ == "__main__":
    main()
