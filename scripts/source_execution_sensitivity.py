#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import (
    FixedBpsFeeModel,
    FixedBpsSlippage,
    ZeroFeeModel,
)
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

REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_EXECUTION_SENSITIVITY.md"))
SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
INITIAL_CASH = 10_000_000.0


@dataclass(frozen=True)
class Scenario:
    name: str
    fee_bps: float
    slippage_bps: float


SCENARIOS = (
    Scenario("baseline_0_0", 0.0, 0.0),
    Scenario("stress_10_10", 10.0, 10.0),
    Scenario("stress_25_25", 25.0, 25.0),
    Scenario("stress_50_50", 50.0, 50.0),
)


def build_inputs():
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
    candidate_tickers = set(signals["stock_id"].astype(str))
    ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=set(sim_sessions),
    )
    if unsupported_count:
        raise SystemExit(
            "BLOCKED: unsupported corporate-action rows remain "
            f"{unsupported_summary}"
        )
    return signals, sim_sessions, candidate_tickers, ca_instructions, quarantined_tickers


def run_scenario(
    scenario: Scenario,
    *,
    signals: pd.DataFrame,
    sim_sessions: list[pd.Timestamp],
    candidate_tickers: set[str],
    ca_instructions,
):
    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    fee_model = (
        ZeroFeeModel()
        if scenario.fee_bps == 0
        else FixedBpsFeeModel(bps=scenario.fee_bps)
    )
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope=candidate_tickers,
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=fee_model,
            slippage_model=FixedBpsSlippage(bps=scenario.slippage_bps),
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
    daily = nav.pct_change().dropna()
    elapsed_years = (dates[-1] - dates[0]).days / 365.2425
    total_return = nav.iloc[-1] / INITIAL_CASH - 1.0
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    drawdown = nav / nav.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    vol = float(daily.std(ddof=1) * math.sqrt(252))
    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * math.sqrt(252))
        if daily.std(ddof=1) > 0
        else float("nan")
    )
    return {
        "scenario": scenario.name,
        "fee_bps_per_fill": scenario.fee_bps,
        "slippage_bps_per_fill": scenario.slippage_bps,
        "final_nav": float(nav.iloc[-1]),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "max_drawdown": max_drawdown,
        "ann_vol": vol,
        "sharpe": sharpe,
        "entries": result.total_entries,
        "stop_exits": result.total_stop_exits,
        "max_hold_exits": result.total_max_hold_exits,
        "blocked_exits": result.total_blocked_exits,
        "ca_payments": result.total_corporate_cash_payments,
        "positive_nav_all_sessions": bool((nav > 0).all()),
        "nav_sessions": len(nav),
    }


def main() -> None:
    signals, sim_sessions, candidate_tickers, ca_instructions, quarantined = build_inputs()
    rows = [
        run_scenario(
            s,
            signals=signals,
            sim_sessions=sim_sessions,
            candidate_tickers=candidate_tickers,
            ca_instructions=ca_instructions,
        )
        for s in SCENARIOS
    ]
    frame = pd.DataFrame(rows)
    baseline = frame.iloc[0]
    frame["final_nav_vs_baseline"] = frame["final_nav"] / baseline["final_nav"] - 1.0
    frame["cagr_delta_pp"] = (frame["cagr"] - baseline["cagr"]) * 100.0
    frame["max_dd_delta_pp"] = (frame["max_drawdown"] - baseline["max_drawdown"]) * 100.0

    checks = {
        "all_scenarios_complete": len(frame) == len(SCENARIOS),
        "same_nav_session_count": frame["nav_sessions"].nunique() == 1,
        "positive_nav_all_sessions": bool(frame["positive_nav_all_sessions"].all()),
        "baseline_matches_zero_friction": (
            float(baseline["fee_bps_per_fill"]) == 0
            and float(baseline["slippage_bps_per_fill"]) == 0
        ),
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_tickers & quarantined),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Frozen Canonical Execution-Sensitivity Report",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: hold the audited strategy configuration fixed while varying only explicit per-fill fee and slippage assumptions. These scenarios are stress tests, not calibrated Taiwan transaction-cost estimates and not parameter tuning.",
        "",
        "## Frozen strategy configuration",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation/drain horizon: {sim_sessions[0].date()} through {sim_sessions[-1].date()}",
        f"- canonical signals supplied: {len(signals):,}",
        f"- candidate tickers: {len(candidate_tickers):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined):,}",
        "- policy unchanged: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0",
        "",
        "## Scenarios",
        "",
        "| Scenario | Fee bps/fill | Slippage bps/fill | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.fee_bps_per_fill:.0f} | {row.slippage_bps_per_fill:.0f} "
            f"| {row.final_nav:,.2f} | {row.total_return*100:.2f}% | {row.cagr*100:.2f}% "
            f"| {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.final_nav_vs_baseline*100:.2f}% | {row.cagr_delta_pp:.2f} |"
        )

    lines += [
        "",
        "## Activity counts",
        "",
        "| Scenario | Entries | RAW stop exits | Max-hold exits | Blocked exits | CA cash payments |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.entries:,} | {row.stop_exits:,} | {row.max_hold_exits:,} "
            f"| {row.blocked_exits:,} | {row.ca_payments:,} |"
        )

    lines += [
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
        "This report measures sensitivity to mechanically worse execution assumptions while keeping the strategy fixed. It does not establish robustness by itself, does not select a preferred cost assumption, and is not OOS evidence.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: execution-sensitivity reproducibility gate failed")


if __name__ == "__main__":
    main()
