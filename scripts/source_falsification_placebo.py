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
    DRAIN_SESSIONS,
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
    pit_unsafe_ca_tickers,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_FALSIFICATION_PLACEBO.md"))
INITIAL_CASH = 10_000_000.0
COMMON_SUPPORT_EXCLUDED_TICKERS = {"2823"}


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


def _run(
    name: str,
    signals: pd.DataFrame,
    sim_sessions: list[pd.Timestamp],
    candidate_tickers: set[str],
    ca_instructions,
) -> dict[str, object]:
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
            random_seed=0,
        )
    )
    sim = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source=f"FALSIFICATION:{name}",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )
    result = sim.run(
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
        raise SystemExit(f"FAIL {name}: invalid NAV")
    return {
        "scenario": name,
        "signals": len(signals),
        "entries": result.total_entries,
        "stop_exits": result.total_stop_exits,
        "max_hold_exits": result.total_max_hold_exits,
        **_metrics(nav),
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    base = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    base = base[base["signal_date"].between(SIGNAL_START, SIGNAL_END)].copy()

    quarantined = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    excluded = set(quarantined) | COMMON_SUPPORT_EXCLUDED_TICKERS
    base = base[~base["stock_id"].astype(str).isin(excluded)].copy()
    base = base[["signal_date", "stock_id"]].sort_values(
        ["signal_date", "stock_id"]
    ).reset_index(drop=True)

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]

    candidate_tickers = set(base["stock_id"].astype(str))
    ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=set(sim_sessions),
    )
    if unsupported_count:
        raise SystemExit(f"BLOCKED: unsupported CA rows {unsupported_summary}")

    rng_ticker = np.random.default_rng(1729)
    placebo_ticker = base.copy()
    placebo_ticker["stock_id"] = rng_ticker.permutation(
        placebo_ticker["stock_id"].to_numpy()
    )
    placebo_ticker = placebo_ticker.drop_duplicates(
        ["signal_date", "stock_id"]
    ).reset_index(drop=True)

    rng_date = np.random.default_rng(31415)
    placebo_date = base.copy()
    placebo_date["signal_date"] = rng_date.permutation(
        placebo_date["signal_date"].to_numpy()
    )
    placebo_date = placebo_date.drop_duplicates(
        ["signal_date", "stock_id"]
    ).reset_index(drop=True)

    rows = [
        _run("baseline_common_support", base, sim_sessions, candidate_tickers, ca_instructions),
        _run("placebo_permute_tickers_seed1729", placebo_ticker, sim_sessions, candidate_tickers, ca_instructions),
        _run("placebo_permute_dates_seed31415", placebo_date, sim_sessions, candidate_tickers, ca_instructions),
    ]
    frame = pd.DataFrame(rows)
    baseline = frame.iloc[0]
    frame["cagr_delta_pp_vs_baseline"] = (frame["cagr"] - baseline["cagr"]) * 100.0
    frame["final_nav_vs_baseline"] = frame["final_nav"] / baseline["final_nav"] - 1.0

    checks = {
        "all_prespecified_runs_complete": len(frame) == 3,
        "base_signals_nonempty": len(base) > 0,
        "placebos_nonempty": len(placebo_ticker) > 0 and len(placebo_date) > 0,
        "common_support_exclusion_active": not bool(candidate_tickers & excluded),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Frozen Canonical Falsification / Placebo Diagnostic",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: keep the canonical execution/accounting/policy fixed while deliberately breaking the stock-date relationship in the breakout signals. This is a falsification diagnostic, not an OOS test and not a strategy-selection exercise.",
        "",
        "## Prespecified runs",
        "",
        "- baseline_common_support: canonical 250-session breakout signals, with PIT exclusions plus 2823 common-support exclusion.",
        "- placebo_permute_tickers_seed1729: preserve signal dates and ticker marginal counts but deterministically permute ticker assignments.",
        "- placebo_permute_dates_seed31415: preserve ticker identities and date marginal counts but deterministically permute signal dates.",
        "- policy remains 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0.",
        "- execution remains zero explicit fees / zero slippage to isolate signal falsification.",
        "",
        "## Results",
        "",
        "| Scenario | Signals | Entries | Stop exits | Max-hold exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.signals:,} | {row.entries:,} | {row.stop_exits:,} "
            f"| {row.max_hold_exits:,} | {row.final_nav:,.2f} | {row.total_return*100:.2f}% "
            f"| {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.final_nav_vs_baseline*100:.2f}% | {row.cagr_delta_pp_vs_baseline:.2f} |"
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
        "A placebo result is informative only as a falsification diagnostic. No pass/fail threshold for economic superiority was preregistered before observing these results, so this report does not claim that the strategy has formally survived falsification. It records whether breaking the stock-date mapping materially changes the descriptive path.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: falsification operational gate failed")


if __name__ == "__main__":
    main()
