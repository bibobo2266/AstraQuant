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
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CAPITAL_SENSITIVITY.md"))

CAPITALS = (300_000.0, 500_000.0, 1_000_000.0, 10_000_000.0)


def metrics(nav: pd.Series, initial_cash: float) -> dict[str, float]:
    daily = nav.pct_change().dropna()
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.2425
    total_return = nav.iloc[-1] / initial_cash - 1.0
    cagr = (nav.iloc[-1] / initial_cash) ** (1.0 / elapsed_years) - 1.0
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
    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    quarantined = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    quarantined_signal_rows = int(
        signals["stock_id"].astype(str).isin(quarantined).sum()
    )
    signals = signals[
        ~signals["stock_id"].astype(str).isin(quarantined)
    ].copy()

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    eligible_end_positions = [i for i, x in enumerate(market_sessions) if x <= SIGNAL_END]
    if not eligible_end_positions:
        raise SystemExit("BLOCKED: no sessions in signal horizon")
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
            f"BLOCKED: unsupported corporate-action rows remain {unsupported_summary}"
        )

    rows = []
    for initial_cash in CAPITALS:
        portfolio = PortfolioEngine(opening_cash=initial_cash)
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
            raise SystemExit(f"FAIL: invalid NAV for capital={initial_cash}")
        m = metrics(nav, initial_cash)
        rows.append({
            "initial_cash": initial_cash,
            "final_nav": m["final_nav"],
            "total_return": m["total_return"],
            "cagr": m["cagr"],
            "max_drawdown": m["max_drawdown"],
            "sharpe": m["sharpe"],
            "entries": result.total_entries,
            "stop_exits": result.total_stop_exits,
            "max_hold_exits": result.total_max_hold_exits,
            "blocked_exits": result.total_blocked_exits,
            "ending_receivables": portfolio.cash.pending_receivables,
            "ending_payables": portfolio.cash.pending_payables,
            "ending_open_positions": len(policy.managed_positions),
        })

    frame = pd.DataFrame(rows)
    checks = {
        "all_capital_scenarios_complete": len(frame) == len(CAPITALS),
        "all_final_nav_positive": bool(frame["final_nav"].gt(0).all()),
        "all_pending_payables_nonnegative_with_float_tolerance": bool(frame["ending_payables"].ge(-1e-6).all()),
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_tickers & quarantined),
        "baseline_10m_present": bool(frame["initial_cash"].eq(10_000_000.0).any()),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Frozen Canonical Starting-Capital Sensitivity",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: rerun the exact audited canonical strategy with different starting capital while keeping all strategy, board-lot, execution, accounting, CA, PIT, and random-seed rules fixed.",
        "",
        "## Frozen rules",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation/drain horizon: {sim_sessions[0].date()} through {sim_sessions[-1].date()}",
        f"- signals supplied: {len(signals):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined):,}",
        f"- signal rows removed by PIT quarantine: {quarantined_signal_rows:,}",
        "- position target remains 10% of NAV",
        "- max positions remains 10",
        "- board lot remains 1,000 shares",
        "- stop remains 12%",
        "- re-entry gap remains 20 sessions",
        "- max hold remains 250 sessions",
        "- zero explicit fees / zero slippage for comparability with the descriptive baseline",
        "",
        "## Results",
        "",
        "| Starting capital | Final NAV | Total return | CAGR | Max DD | Sharpe | Entries | Stop exits | Max-hold exits | Blocked exits | Open positions | Ending payables |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.initial_cash:,.0f} | {row.final_nav:,.2f} | {row.total_return*100:.2f}% "
            f"| {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.entries:,} | {row.stop_exits:,} | {row.max_hold_exits:,} "
            f"| {row.blocked_exits:,} | {row.ending_open_positions:,} | {row.ending_payables:.9f} |"
        )

    lines += [
        "",
        "## Interpretation boundary",
        "",
        "This is a capital/lot-size sensitivity test. With a fixed 1,000-share board lot and a 10% NAV target, smaller accounts can be unable to buy otherwise eligible signals. Therefore percentage returns need not scale linearly with starting capital.",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        failed = [name for name, ok in checks.items() if not ok]
        print(REPORT_PATH.read_text(encoding="utf-8"))
        raise SystemExit(f"FAIL: starting-capital sensitivity gate failed: {failed}")


if __name__ == "__main__":
    main()
