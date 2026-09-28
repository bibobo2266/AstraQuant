#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from dataclasses import dataclass
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

from source_strategy_integration_smoke import (
    DRAIN_SESSIONS,
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
    pit_unsafe_ca_tickers,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_PARAMETER_NEIGHBORHOOD.md"))
INITIAL_CASH = 10_000_000.0

# 2823 (China Life) converted on 2021-12-30 into 0.8 shares of 2883,
# 0.73 shares of 2883B, plus TWD 11.5 cash per old share. AstraQuant does
# not yet model cross-security multi-asset conversions, so all neighborhood
# rows use a common-support exclusion rather than guessing or forcing a cashout.
COMMON_SUPPORT_EXCLUDED_TICKERS = {"2823"}


@dataclass(frozen=True)
class Scenario:
    name: str
    lookback: int = 250
    stop_fraction: float = 0.12
    max_hold_sessions: int = 250


SCENARIOS = (
    Scenario("baseline", 250, 0.12, 250),
    Scenario("lookback_200", 200, 0.12, 250),
    Scenario("lookback_300", 300, 0.12, 250),
    Scenario("stop_10pct", 250, 0.10, 250),
    Scenario("stop_14pct", 250, 0.14, 250),
    Scenario("hold_200", 250, 0.12, 200),
    Scenario("hold_300", 250, 0.12, 300),
)


def metrics(nav: pd.Series) -> dict[str, float]:
    daily = nav.pct_change().dropna()
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.2425
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    dd = nav / nav.cummax() - 1.0
    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * math.sqrt(252))
        if len(daily) > 1 and daily.std(ddof=1) > 0
        else float("nan")
    )
    return {
        "final_nav": float(nav.iloc[-1]),
        "cagr": float(cagr),
        "max_drawdown": float(dd.min()),
        "sharpe": sharpe,
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    quarantined = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    eligible_end_positions = [i for i, x in enumerate(market_sessions) if x <= SIGNAL_END]
    if not eligible_end_positions:
        raise SystemExit("FAIL: no sessions in parent horizon")
    end_pos = max(eligible_end_positions)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]

    rows = []
    common_support_checks: list[bool] = []
    for scenario in SCENARIOS:
        all_signals = build_simple_breakout_signals(
            adjusted,
            tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
            config=BreakoutSignalConfig(
                lookback=scenario.lookback,
                universe_fraction=0.25,
            ),
        )
        signals = all_signals[
            all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
        ].copy()
        signals = signals[
            ~signals["stock_id"].astype(str).isin(quarantined)
        ].copy()
        common_support_removed = int(
            signals["stock_id"].astype(str).isin(COMMON_SUPPORT_EXCLUDED_TICKERS).sum()
        )
        signals = signals[
            ~signals["stock_id"].astype(str).isin(COMMON_SUPPORT_EXCLUDED_TICKERS)
        ].copy()
        candidate_tickers = set(signals["stock_id"].astype(str))
        common_support_checks.append(
            not bool(candidate_tickers & COMMON_SUPPORT_EXCLUDED_TICKERS)
        )

        ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
            candidate_tickers=candidate_tickers,
            sessions=set(sim_sessions),
        )
        if unsupported_count:
            raise SystemExit(
                f"BLOCKED {scenario.name}: unsupported CA rows {unsupported_summary}"
            )

        portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
        execution = CanonicalExecutionService(
            market_data=ExecutionMarketData(
                SourceDataAdapter(SOURCE_ROOT),
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
                stop_fraction=scenario.stop_fraction,
                reentry_gap_sessions=20,
                max_hold_sessions=scenario.max_hold_sessions,
                lot_size=1000,
                random_seed=0,
            )
        )
        simulator = CanonicalStrategySimulator(
            execution=execution,
            portfolio=portfolio,
            policy=policy,
            signal=SignalDeclaration(
                source=f"CANONICAL_SIMPLE_BREAKOUT_LB{scenario.lookback}",
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
            raise SystemExit(f"FAIL {scenario.name}: invalid NAV series")
        m = metrics(nav)
        rows.append({
            "scenario": scenario.name,
            "lookback": scenario.lookback,
            "stop_fraction": scenario.stop_fraction,
            "max_hold_sessions": scenario.max_hold_sessions,
            "signals": len(signals),
            "entries": result.total_entries,
            "stop_exits": result.total_stop_exits,
            "max_hold_exits": result.total_max_hold_exits,
            "blocked_exits": result.total_blocked_exits,
            "common_support_removed": common_support_removed,
            **m,
        })

    frame = pd.DataFrame(rows)
    baseline = frame[frame["scenario"].eq("baseline")].iloc[0]
    frame["cagr_delta_pp"] = (frame["cagr"] - baseline["cagr"]) * 100.0
    frame["final_nav_vs_baseline"] = frame["final_nav"] / baseline["final_nav"] - 1.0

    checks = {
        "all_prespecified_scenarios_complete": len(frame) == len(SCENARIOS),
        "baseline_present": int(frame["scenario"].eq("baseline").sum()) == 1,
        "all_nav_positive": bool(frame["final_nav"].gt(0).all()),
        "pit_unsafe_ca_tickers_quarantined": len(quarantined) > 0,
        "unsupported_multi_security_terminal_excluded": bool(all(common_support_checks)),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Frozen Canonical Local Parameter Neighborhood",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: perturb a small prespecified neighborhood around the frozen canonical configuration without selecting a winner, retuning after results, or changing the accounting path. This is a local parameter-stability diagnostic, not OOS validation.",
        "",
        "## Prespecified neighborhood",
        "",
        "- baseline: lookback 250, stop 12%, max hold 250 sessions",
        "- lookback perturbations: 200 and 300",
        "- stop perturbations: 10% and 14%",
        "- max-hold perturbations: 200 and 300 sessions",
        "- all other settings fixed: top-turnover universe fraction 25%, 10% NAV target, max 10 positions, 20-session re-entry gap, 1000-share lot, seed 0",
        "- execution assumptions: zero explicit fees and zero slippage",
        "- common-support exclusion: ticker 2823 is excluded from every row because its 2021-12-30 merger consideration is a multi-security conversion (2883 + 2883B + cash) not yet modeled by the canonical CA engine",
        "",
        "## Results in prespecified order",
        "",
        "| Scenario | Lookback | Stop | Max hold | Signals | 2823 signal rows removed | Entries | Stop exits | Max-hold exits | Final NAV | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.lookback} | {row.stop_fraction*100:.0f}% | {row.max_hold_sessions} "
            f"| {row.signals:,} | {row.common_support_removed:,} | {row.entries:,} | {row.stop_exits:,} | {row.max_hold_exits:,} "
            f"| {row.final_nav:,.2f} | {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% "
            f"| {row.sharpe:.3f} | {row.final_nav_vs_baseline*100:.2f}% | {row.cagr_delta_pp:.2f} |"
        )

    lines += [
        "",
        "## Operational gates",
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
        "No scenario is promoted or selected from this table. The purpose is to expose whether nearby settings create materially different behavior. Any later plateau claim must use a declared criterion and must not retrospectively choose the best row.",
        "",
        "Ticker 2823 is a declared common-support exclusion for this diagnostic, not a performance-based filter. Source evidence shows last trading 2021-12-17, suspension from 2021-12-20, conversion/delisting 2021-12-30, and consideration of 0.8 shares 2883 + 0.73 shares 2883B + TWD 11.5 cash per old share. Cross-security conversion remains a separate accounting feature to implement.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: parameter-neighborhood operational gate failed")


if __name__ == "__main__":
    main()
