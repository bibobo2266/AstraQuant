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
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_TEMPORAL_REPLICATION.md"))
INITIAL_CASH = 10_000_000.0


@dataclass(frozen=True)
class Segment:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


SEGMENTS = (
    Segment("era_2016_2019", pd.Timestamp("2016-01-04"), pd.Timestamp("2019-12-31")),
    Segment("era_2020_2022", pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-31")),
    Segment("era_2023_2026H1", pd.Timestamp("2023-01-01"), pd.Timestamp("2026-06-30")),
)


def metrics(nav: pd.Series) -> dict[str, float]:
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
        "positive_session_rate": float((daily > 0).mean()) if len(daily) else float("nan"),
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )

    all_market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if SIGNAL_START <= pd.Timestamp(x)
    ]

    rows: list[dict[str, object]] = []
    operational_checks: list[bool] = []

    for segment in SEGMENTS:
        signals = all_signals[
            all_signals["signal_date"].between(segment.start, segment.end)
        ].copy()

        quarantined = pit_unsafe_ca_tickers(start=segment.start, end=segment.end)
        quarantined_signal_rows = int(
            signals["stock_id"].astype(str).isin(quarantined).sum()
        )
        signals = signals[
            ~signals["stock_id"].astype(str).isin(quarantined)
        ].copy()

        segment_sessions = [
            x for x in all_market_sessions
            if segment.start <= x <= segment.end
        ]
        if not segment_sessions:
            raise SystemExit(f"FAIL: no market sessions for {segment.name}")

        last_idx = max(i for i, x in enumerate(all_market_sessions) if x <= segment.end)
        first_idx = min(i for i, x in enumerate(all_market_sessions) if x >= segment.start)
        drain_end = min(len(all_market_sessions), last_idx + 1 + DRAIN_SESSIONS)
        sim_sessions = all_market_sessions[first_idx:drain_end]

        candidate_tickers = set(signals["stock_id"].astype(str))
        ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
            candidate_tickers=candidate_tickers,
            sessions=set(sim_sessions),
        )
        if unsupported_count:
            raise SystemExit(
                f"BLOCKED {segment.name}: unsupported CA rows {unsupported_summary}"
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
        m = metrics(nav)

        checks = {
            "signals_present": len(signals) > 0,
            "entries_present": result.total_entries > 0,
            "nav_complete": len(nav) == len(sim_sessions),
            "positive_nav": bool((nav > 0).all()),
            "no_unsupported_ca": unsupported_count == 0,
            "pit_unsafe_excluded": not bool(candidate_tickers & quarantined),
        }
        operational_checks.append(all(checks.values()))

        rows.append({
            "segment": segment.name,
            "start": dates[0].date(),
            "end": dates[-1].date(),
            "signal_count": len(signals),
            "quarantined_tickers": len(quarantined),
            "quarantined_signal_rows": quarantined_signal_rows,
            "entries": result.total_entries,
            "stop_exits": result.total_stop_exits,
            "max_hold_exits": result.total_max_hold_exits,
            "blocked_exits": result.total_blocked_exits,
            "ca_applied": result.total_corporate_actions,
            "ca_payments": result.total_corporate_cash_payments,
            **m,
        })

    frame = pd.DataFrame(rows)
    status = "PASS" if all(operational_checks) else "FAIL"

    lines = [
        "# Frozen Canonical Temporal Replication",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: rerun the exact audited strategy configuration from fresh capital in non-overlapping historical eras. No strategy parameter is re-estimated or tuned between eras. This is temporal replication evidence, not locked future OOS.",
        "",
        "## Frozen configuration",
        "",
        f"- parent signal horizon: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        "- each era starts from TWD 10,000,000 fresh capital",
        "- policy unchanged: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0",
        "- execution assumptions unchanged: zero explicit fees and zero slippage",
        "- normalized CA, PIT quarantine, payment settlement, terminal-security rules unchanged",
        "",
        "## Era results",
        "",
        "| Era | Simulation dates | Signals | Entries | Stop exits | Max-hold exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Positive sessions |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.segment} | {row.start}→{row.end} | {row.signal_count:,} | {row.entries:,} "
            f"| {row.stop_exits:,} | {row.max_hold_exits:,} | {row.final_nav:,.2f} "
            f"| {row.total_return*100:.2f}% | {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% "
            f"| {row.sharpe:.3f} | {row.positive_session_rate*100:.2f}% |"
        )

    lines += [
        "",
        "## Source-quality/activity counts",
        "",
        "| Era | PIT-unsafe tickers quarantined | Signal rows removed | Blocked exits | CA applied | CA payments settled |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.segment} | {row.quarantined_tickers:,} | {row.quarantined_signal_rows:,} "
            f"| {row.blocked_exits:,} | {row.ca_applied:,} | {row.ca_payments:,} |"
        )

    lines += [
        "",
        "## Operational gate",
        "",
        f"- all non-overlapping era runs completed under the frozen canonical path: {'PASS' if status == 'PASS' else 'FAIL'}",
        "",
        "## Interpretation boundary",
        "",
        "The era statistics are reported without choosing a winning period or changing parameters. Temporal differences are evidence to investigate, not a basis for retrospective tuning. Formal OOS remains locked until a future period is reserved and not iterated on.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: temporal replication operational gate failed")


if __name__ == "__main__":
    main()
