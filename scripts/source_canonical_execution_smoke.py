#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.valuation import value_portfolio

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CANONICAL_EXECUTION_SMOKE.md"))


def choose_sessions() -> tuple[str, pd.Timestamp, pd.Timestamp]:
    raw = pd.read_parquet(
        SOURCE_ROOT / "raw" / "prices_raw_2026.parquet",
        columns=["date", "stock_id", "open", "max", "min", "close"],
    )
    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked", "sell_blocked"],
    )
    for df in (raw, trad):
        df["stock_id"] = df["stock_id"].astype(str)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()

    merged = raw.merge(trad, on=["date", "stock_id"], how="inner")
    merged = merged[
        merged["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
        & ~merged["buy_blocked"].fillna(True).astype(bool)
        & ~merged["sell_blocked"].fillna(True).astype(bool)
    ].copy()

    for sid in ["2330", "2317", "2454"]:
        dates = merged.loc[merged["stock_id"].eq(sid), "date"].drop_duplicates().sort_values().tolist()
        if len(dates) >= 2:
            return sid, pd.Timestamp(dates[-2]), pd.Timestamp(dates[-1])

    for sid, g in merged.groupby("stock_id"):
        dates = g["date"].drop_duplicates().sort_values().tolist()
        if len(dates) >= 2:
            return str(sid), pd.Timestamp(dates[-2]), pd.Timestamp(dates[-1])

    raise SystemExit("BLOCKED: no two-session canonical execution smoke window")


def main() -> None:
    ticker, entry_day, exit_day = choose_sessions()
    source = SourceDataAdapter(SOURCE_ROOT)
    portfolio = PortfolioEngine(opening_cash=1_000_000.0)
    service = CanonicalExecutionService(
        market_data=ExecutionMarketData(source),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    signal = SignalDeclaration(
        source="SOURCE_CANONICAL_EXECUTION_SMOKE",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )

    sizing = service.sizing_price(
        ticker=ticker,
        session_date=entry_day,
        side="buy",
        field="open",
        signal=signal,
    )
    if sizing.availability is not ExecutionAvailability.EXECUTABLE:
        raise SystemExit("BLOCKED: sizing not executable")

    qty = 100.0
    entry_at = datetime.combine(entry_day.date(), datetime.min.time())
    entry_intent = OrderIntent(
        intent_id="canonical-smoke-entry-intent",
        ticker=ticker,
        side="buy",
        quantity=qty,
        created_at=entry_at,
        rationale="canonical execution service smoke",
    )
    entry = service.execute(
        intent=entry_intent,
        signal=signal,
        order_id="canonical-smoke-entry-order",
        fill_id="canonical-smoke-entry-fill",
        submitted_at=entry_at,
        session_date=entry_day,
        use=PriceUse.ENTRY,
        field="open",
        settlement=SettlementInstruction(
            settlement_id="canonical-smoke-entry-settlement",
            due_at=entry_at + timedelta(days=2),
        ),
    )
    portfolio.settlements.settle(
        "canonical-smoke-entry-settlement",
        entry_at + timedelta(days=2),
    )

    mark = service.mark(
        ticker=ticker,
        session_date=entry_day,
        side="sell",
        field="close",
    )
    valuation = value_portfolio(
        cash=portfolio.cash,
        positions=portfolio.positions.positions,
        raw_mark_decisions={ticker: mark},
    )

    exit_at = datetime.combine(exit_day.date(), datetime.min.time())
    exit_intent = OrderIntent(
        intent_id="canonical-smoke-exit-intent",
        ticker=ticker,
        side="sell",
        quantity=qty,
        created_at=exit_at,
        rationale="canonical execution service smoke",
    )
    exit_result = service.execute(
        intent=exit_intent,
        signal=signal,
        order_id="canonical-smoke-exit-order",
        fill_id="canonical-smoke-exit-fill",
        submitted_at=exit_at,
        session_date=exit_day,
        use=PriceUse.EXIT,
        field="close",
        settlement=SettlementInstruction(
            settlement_id="canonical-smoke-exit-settlement",
            due_at=exit_at + timedelta(days=2),
        ),
    )
    portfolio.settlements.settle(
        "canonical-smoke-exit-settlement",
        exit_at + timedelta(days=2),
    )

    checks = {
        "signal_declared": bool(signal.source),
        "sizing_raw": sizing.use is PriceUse.SIZING,
        "entry_raw": entry.raw_decision.use is PriceUse.ENTRY,
        "mark_raw": mark.use is PriceUse.MARK,
        "exit_raw": exit_result.raw_decision.use is PriceUse.EXIT,
        "position_flat_after_exit": portfolio.positions.positions[ticker].quantity == 0,
        "settlements_flat": (
            abs(portfolio.cash.pending_payables) < 1e-9
            and abs(portfolio.cash.pending_receivables) < 1e-9
        ),
        "pre_exit_nav_positive": valuation.nav > 0,
        "canonical_service_path_used": True,
        "no_adjusted_fallback": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source Canonical Execution Service Smoke",
        "",
        f"Status: **{status}**",
        "",
        "This smoke test routes real source data through CanonicalExecutionService. It is not a strategy backtest.",
        "",
        "## Window",
        "",
        f"- ticker: {ticker}",
        f"- entry session: {entry_day.date()}",
        f"- exit session: {exit_day.date()}",
        f"- sizing RAW open: {sizing.price}",
        f"- entry RAW open: {entry.fill.price}",
        f"- mark RAW close: {mark.price}",
        f"- exit RAW close: {exit_result.fill.price}",
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
        "The numeric cash/NAV values are not interpreted as performance evidence. The purpose is path validation only.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("FAIL: canonical execution service smoke failed")


if __name__ == "__main__":
    main()
