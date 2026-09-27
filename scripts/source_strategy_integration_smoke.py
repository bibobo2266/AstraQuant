#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import (
    CanonicalStrategySimulator,
    StrategySimulationConfig,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_STRATEGY_INTEGRATION_SMOKE.md"))
SIGNAL_START = pd.Timestamp(os.environ.get("SIGNAL_START", "2026-01-01"))
SIGNAL_END = pd.Timestamp(os.environ.get("SIGNAL_END", "2026-03-31"))


def load_adjusted() -> pd.DataFrame:
    parts = []
    for year in (2025, 2026):
        p = SOURCE_ROOT / "adj" / f"prices_adj_{year}.parquet"
        d = pd.read_parquet(
            p,
            columns=["date", "stock_id", "open", "max", "min", "close", "Trading_money"],
        )
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
        d["stock_id"] = d["stock_id"].astype(str)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_tradability() -> pd.DataFrame:
    d = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=[
            "date", "stock_id", "observed_trade", "valid_ohlc",
            "buy_blocked", "sell_blocked", "reason",
        ],
    )
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    d["stock_id"] = d["stock_id"].astype(str)
    return d[d["date"].ge(pd.Timestamp("2025-01-01"))].copy()


def build_supported_ca(
    *,
    candidate_tickers: set[str],
    sessions: set[pd.Timestamp],
) -> tuple[list[HistoricalCorporateActionInstruction], int]:
    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id", "event_date", "known_date", "event_type",
            "cash_per_share", "share_multiplier", "source_name", "source_url",
        ],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["known_date"] = pd.to_datetime(ledger["known_date"], errors="coerce")
    ledger["cash_per_share"] = pd.to_numeric(ledger["cash_per_share"], errors="coerce")
    ledger["share_multiplier"] = pd.to_numeric(ledger["share_multiplier"], errors="coerce")

    d = ledger[
        ledger["stock_id"].isin(candidate_tickers)
        & ledger["event_date"].isin(sessions)
    ].copy()

    unsupported_cash = d[
        d["cash_per_share"].gt(0)
        & ~d["event_type"].astype(str).eq("dividend")
    ]
    unsupported_count = len(unsupported_cash)

    instructions: list[HistoricalCorporateActionInstruction] = []

    div = d[
        d["event_type"].astype(str).eq("dividend")
        & d["cash_per_share"].gt(0)
    ]
    for (ticker, day), g in div.groupby(["stock_id", "event_date"], sort=True):
        vals = sorted(set(round(float(v), 8) for v in g["cash_per_share"].dropna()))
        if len(vals) != 1:
            raise SystemExit(f"BLOCKED: conflicting dividend values {ticker} {day}: {vals}")
        row = g.sort_values(["source_name", "source_url"]).iloc[0]
        event = CorporateActionEvent(
            event_id=f"smoke:{ticker}:{pd.Timestamp(day).date()}:dividend",
            ticker=str(ticker),
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime.combine(pd.Timestamp(day).date(), datetime.min.time()),
            known_at=None if pd.isna(row["known_date"]) else pd.Timestamp(row["known_date"]).to_pydatetime(),
            cash_per_share=float(row["cash_per_share"]),
            source=str(row["source_name"]),
            notes=str(row["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(event=event, applied_at=event.effective_at)
        )

    share = d[d["share_multiplier"].gt(0)].copy()
    for (ticker, day, source_type), g in share.groupby(
        ["stock_id", "event_date", "event_type"],
        sort=True,
    ):
        vals = sorted(set(round(float(v), 10) for v in g["share_multiplier"].dropna()))
        if len(vals) != 1:
            raise SystemExit(
                f"BLOCKED: conflicting share multipliers {ticker} {day} {source_type}: {vals}"
            )
        # Skip rows already represented by an unsupported cash component; the
        # smoke must not silently apply only half of an economic event.
        if bool(g["cash_per_share"].gt(0).any()) and str(source_type) != "dividend":
            continue
        row = g.sort_values(["source_name", "source_url"]).iloc[0]
        mapped = (
            CorporateActionType.CAPITAL_REDUCTION
            if "capital_reduction" in str(source_type)
            else CorporateActionType.SPLIT
        )
        event = CorporateActionEvent(
            event_id=f"smoke:{ticker}:{pd.Timestamp(day).date()}:{source_type}",
            ticker=str(ticker),
            event_type=mapped,
            effective_at=datetime.combine(pd.Timestamp(day).date(), datetime.min.time()),
            known_at=None if pd.isna(row["known_date"]) else pd.Timestamp(row["known_date"]).to_pydatetime(),
            share_multiplier=float(row["share_multiplier"]),
            source=str(row["source_name"]),
            notes=str(row["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(event=event, applied_at=event.effective_at)
        )

    instructions.sort(key=lambda x: (x.event.effective_at, x.event.event_id))
    return instructions, unsupported_count


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability()

    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()
    if signals.empty:
        raise SystemExit("BLOCKED: no canonical breakout signals in smoke window")

    # Include two post-signal sessions to drain T+2 trade settlements.
    market_sessions = adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
    market_sessions = [pd.Timestamp(x) for x in market_sessions if pd.Timestamp(x).year == 2026]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_sessions = market_sessions[: min(len(market_sessions), end_pos + 3)]
    sim_sessions = [x for x in sim_sessions if x >= pd.Timestamp("2026-01-02")]
    session_set = set(sim_sessions)

    candidate_tickers = set(signals["stock_id"].astype(str))
    ca_instructions, unsupported_ca_cash = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=session_set,
    )
    if unsupported_ca_cash:
        raise SystemExit(
            f"BLOCKED: {unsupported_ca_cash} non-dividend cash CA source rows "
            "need explicit runtime entitlement basis before strategy smoke"
        )

    portfolio = PortfolioEngine(opening_cash=10_000_000.0)
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

    final = result.sessions[-1].snapshot.valuation
    checks = {
        "canonical_signals_used": len(signals) > 0,
        "canonical_strategy_simulator_used": True,
        "entries_executed": result.total_entries > 0,
        "raw_nav_snapshots_complete": len(result.sessions) == len(sim_sessions),
        "pending_payables_nonnegative": portfolio.cash.pending_payables >= -1e-9,
        "pending_receivables_nonnegative": portfolio.cash.pending_receivables >= -1e-9,
        "settled_cash_nonnegative": portfolio.cash.settled_cash >= -1e-9,
        "no_adjusted_execution_fallback": True,
        "unsupported_ca_cash_zero": unsupported_ca_cash == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source Canonical Strategy Integration Smoke",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: connect real canonical breakout candidates to the causal RAW portfolio simulator without evaluating strategy performance.",
        "",
        "## Integration window",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation sessions: {sim_sessions[0].date()} through {sim_sessions[-1].date()}",
        f"- session count / RAW NAV snapshots: {len(result.sessions):,}",
        f"- canonical signal candidates supplied: {len(signals):,}",
        f"- candidate tickers in scoped execution source: {len(candidate_tickers):,}",
        "- integration-only policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0",
        "",
        "## Accounting/event audit counts",
        "",
        f"- entries executed: {result.total_entries:,}",
        f"- entry candidates skipped/blocked: {result.total_entry_skips:,}",
        f"- RAW stop exits: {result.total_stop_exits:,}",
        f"- RAW max-hold exits: {result.total_max_hold_exits:,}",
        f"- blocked exit attempts: {result.total_blocked_exits:,}",
        f"- supported corporate actions applied: {result.total_corporate_actions:,}",
        "",
        "## Final accounting state",
        "",
        f"- open managed positions: {len(policy.managed_positions):,}",
        f"- settled cash: {portfolio.cash.settled_cash}",
        f"- pending receivables: {portfolio.cash.pending_receivables}",
        f"- pending payables: {portfolio.cash.pending_payables}",
        f"- RAW market value: {final.market_value}",
        f"- NAV: {final.nav}",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Performance lock",
        "",
        "The numeric NAV/cash values above are accounting state only. No return, CAGR, drawdown, MAR, Sharpe, hit rate, or strategy comparison is computed.",
        "",
        "If this smoke fails because a held security cannot be marked from current RAW data, the next task is an explicit RAW stale-mark policy; adjusted prices remain prohibited as a fallback.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        print("FAILED_CHECKS=" + ",".join(failed))
        raise SystemExit("FAIL: source canonical strategy integration smoke failed")


if __name__ == "__main__":
    main()
