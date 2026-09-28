#!/usr/bin/env python3
from __future__ import annotations

import math
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
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CAPACITY_SEED_SENSITIVITY.md"))
INITIAL_CASH = 10_000_000.0
COMMON_SUPPORT_EXCLUDED_TICKERS = {"2823"}
SEEDS = (0, 1, 7, 42, 101, 999)


def _metrics(nav: pd.Series) -> dict[str, float]:
    daily = nav.pct_change().dropna()
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.2425
    total_return = nav.iloc[-1] / INITIAL_CASH - 1.0
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    dd = nav / nav.cummax() - 1.0
    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * math.sqrt(252))
        if len(daily) > 1 and daily.std(ddof=1) > 0
        else float("nan")
    )
    return {
        "final_nav": float(nav.iloc[-1]),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "max_drawdown": float(dd.min()),
        "sharpe": sharpe,
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = signals[
        signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    quarantined = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    excluded = set(quarantined) | COMMON_SUPPORT_EXCLUDED_TICKERS
    signals = signals[
        ~signals["stock_id"].astype(str).isin(excluded)
    ][["signal_date", "stock_id"]].copy()
    signals = signals.sort_values(["signal_date", "stock_id"]).reset_index(drop=True)

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]

    candidate_tickers = set(signals["stock_id"].astype(str))
    ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=set(sim_sessions),
    )
    if unsupported_count:
        raise SystemExit(f"BLOCKED: unsupported CA rows {unsupported_summary}")

    rows = []
    for seed in SEEDS:
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
                stop_fraction=0.12,
                reentry_gap_sessions=20,
                max_hold_sessions=250,
                lot_size=1000,
                random_seed=seed,
            )
        )
        simulator = CanonicalStrategySimulator(
            execution=execution,
            portfolio=portfolio,
            policy=policy,
            signal=SignalDeclaration(
                source=f"CANONICAL_SIMPLE_BREAKOUT_V1_SEED_{seed}",
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
            raise SystemExit(f"FAIL seed {seed}: invalid NAV")
        rows.append({
            "seed": seed,
            "entries": result.total_entries,
            "stop_exits": result.total_stop_exits,
            "max_hold_exits": result.total_max_hold_exits,
            "blocked_exits": result.total_blocked_exits,
            **_metrics(nav),
        })

    frame = pd.DataFrame(rows)
    baseline = frame[frame["seed"].eq(0)].iloc[0]
    frame["cagr_delta_pp_vs_seed0"] = (frame["cagr"] - baseline["cagr"]) * 100.0
    frame["final_nav_vs_seed0"] = frame["final_nav"] / baseline["final_nav"] - 1.0

    checks = {
        "all_prespecified_seeds_complete": len(frame) == len(SEEDS),
        "seed0_present": int(frame["seed"].eq(0).sum()) == 1,
        "all_nav_positive": bool(frame["final_nav"].gt(0).all()),
        "common_support_exclusion_active": not bool(candidate_tickers & excluded),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Capacity-Selection Seed Sensitivity",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: isolate how much the deterministic random tie-breaking used when eligible candidates exceed available portfolio slots changes the path of the frozen common-support breakout strategy.",
        "",
        "## Design",
        "",
        "- signal set is identical across runs: canonical 250-session breakout on common support.",
        "- only PortfolioIntentPolicy.random_seed changes.",
        "- prespecified seeds: 0, 1, 7, 42, 101, 999.",
        "- all accounting, RAW execution, CA handling, sizing, stop, max-hold, re-entry, board-lot, and zero-friction assumptions remain fixed.",
        "",
        "## Results",
        "",
        "| Seed | Entries | Stop exits | Max-hold exits | Blocked exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs seed0 | CAGR delta pp |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.seed} | {row.entries:,} | {row.stop_exits:,} | {row.max_hold_exits:,} "
            f"| {row.blocked_exits:,} | {row.final_nav:,.2f} | {row.total_return*100:.2f}% "
            f"| {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.final_nav_vs_seed0*100:.2f}% | {row.cagr_delta_pp_vs_seed0:.2f} |"
        )

    lines += [
        "",
        "## Dispersion summary",
        "",
        f"- CAGR range across seeds: {frame['cagr'].min()*100:.2f}% to {frame['cagr'].max()*100:.2f}%",
        f"- CAGR spread: {(frame['cagr'].max()-frame['cagr'].min())*100:.2f} percentage points",
        f"- final NAV range: {frame['final_nav'].min():,.2f} to {frame['final_nav'].max():,.2f}",
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
        "This is a path-dependence diagnostic. No seed is selected or promoted. Large dispersion means capacity tie-breaking is a material source of portfolio outcomes and must be separated from signal-specific evidence before any candidate freeze or OOS claim.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: seed-sensitivity operational gate failed")


if __name__ == "__main__":
    main()
