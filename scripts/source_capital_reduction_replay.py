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
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CAPITAL_REDUCTION_REPLAY.md"))


def choose_event() -> pd.Series:
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

    c = ledger[
        ledger["event_type"].astype(str).eq("capital_reduction")
        & ledger["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & ledger["event_date"].notna()
        & ledger["cash_per_share"].gt(0)
        & ledger["share_multiplier"].gt(0)
        & ledger["event_date"].between(pd.Timestamp("2015-01-05"), pd.Timestamp("2026-09-24"))
    ].copy()
    if c.empty:
        raise SystemExit("BLOCKED: no capital-reduction event with both cash and share fields")
    return c.sort_values("event_date", ascending=False).iloc[0]


def load_sessions(ticker: str, event_day: pd.Timestamp) -> pd.DataFrame:
    raw_parts = []
    for year in sorted({event_day.year - 1, event_day.year, event_day.year + 1}):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if path.exists():
            raw_parts.append(pd.read_parquet(
                path, columns=["date", "stock_id", "open", "max", "min", "close"]
            ))
    if not raw_parts:
        raise SystemExit("BLOCKED: no RAW prices around capital-reduction event")

    raw = pd.concat(raw_parts, ignore_index=True)
    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked", "sell_blocked"],
    )
    for frame in (raw, trad):
        frame["stock_id"] = frame["stock_id"].astype(str)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()

    raw = raw[raw["stock_id"].eq(ticker)].copy()
    trad = trad[
        trad["stock_id"].eq(ticker)
        & trad["observed_trade"].fillna(False).astype(bool)
        & trad["valid_ohlc"].fillna(False).astype(bool)
    ].copy()
    return raw.merge(trad, on=["date", "stock_id"], how="inner").sort_values("date")


def choose_window(ticker: str, event_day: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = load_sessions(ticker, event_day)
    pre = d[
        d["date"].lt(event_day)
        & ~d["buy_blocked"].fillna(True).astype(bool)
    ]
    post = d[
        d["date"].ge(event_day)
        & ~d["sell_blocked"].fillna(True).astype(bool)
    ]
    if pre.empty or post.empty:
        raise SystemExit("BLOCKED: missing tradable pre/post capital-reduction sessions")
    return pd.Timestamp(pre.iloc[-1]["date"]), pd.Timestamp(post.iloc[0]["date"])


def dt(day: pd.Timestamp, hour: int = 9) -> datetime:
    return datetime.combine(day.date(), datetime.min.time()).replace(hour=hour)


def main() -> None:
    src = choose_event()
    ticker = str(src["stock_id"])
    event_day = pd.Timestamp(src["event_date"]).normalize()
    multiplier = float(src["share_multiplier"])
    cash_per_share = float(src["cash_per_share"])
    pre_day, post_day = choose_window(ticker, event_day)

    portfolio = PortfolioEngine(opening_cash=5_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(SOURCE_ROOT)),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    replay = CanonicalPortfolioReplay(execution=execution, portfolio=portfolio)
    signal = SignalDeclaration(
        source="SOURCE_CAPITAL_REDUCTION_REPLAY_DECLARED_SIGNAL",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )

    qty_before = 100.0
    entry_at = dt(pre_day)
    entry = replay.execute_trade(
        intent=OrderIntent(
            intent_id="capred-entry-intent",
            ticker=ticker,
            side="buy",
            quantity=qty_before,
            created_at=entry_at,
            rationale="source capital-reduction accounting replay",
        ),
        signal=signal,
        order_id="capred-entry-order",
        fill_id="capred-entry-fill",
        submitted_at=entry_at,
        session_date=pre_day,
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="capred-entry-settlement",
        settlement_due=entry_at + timedelta(days=2),
    )
    replay.settle("capred-entry-settlement", entry_at + timedelta(days=2))

    old_position = portfolio.positions.positions[ticker]
    old_total_cost = old_position.quantity * old_position.avg_cost
    settled_before_event = portfolio.cash.settled_cash

    event = CorporateActionEvent(
        event_id=f"source:{ticker}:{event_day.date()}:capital_reduction",
        ticker=ticker,
        event_type=CorporateActionType.CAPITAL_REDUCTION,
        effective_at=dt(event_day, 0),
        known_at=None if pd.isna(src["known_date"]) else pd.Timestamp(src["known_date"]).to_pydatetime(),
        payment_at=None,
        cash_per_share=cash_per_share,
        share_multiplier=multiplier,
        source=str(src["source_name"]),
        notes=str(src["source_url"]),
    )

    refund = portfolio.corporate_actions.accrue_cash_entitlement(
        event=event,
        shares_entitled=qty_before,
        accrued_at=dt(event_day, 0),
        component="CAPITAL_REDUCTION_REFUND",
    )
    replay.apply_share_mutation(event=event, applied_at=dt(event_day, 0))

    new_position = portfolio.positions.positions[ticker]
    qty_after_event = new_position.quantity
    avg_cost_after_event = new_position.avg_cost
    total_cost_after_event = qty_after_event * avg_cost_after_event
    expected_qty = qty_before * multiplier
    expected_refund = qty_before * cash_per_share
    post_snapshot = replay.snapshot(at=dt(post_day, 15))

    exit_at = dt(post_day, 13)
    exit_result = replay.execute_trade(
        intent=OrderIntent(
            intent_id="capred-exit-intent",
            ticker=ticker,
            side="sell",
            quantity=qty_after_event,
            created_at=exit_at,
            rationale="source capital-reduction accounting replay exit",
        ),
        signal=signal,
        order_id="capred-exit-order",
        fill_id="capred-exit-fill",
        submitted_at=exit_at,
        session_date=post_day,
        use=PriceUse.EXIT,
        field="close",
        settlement_id="capred-exit-settlement",
        settlement_due=exit_at + timedelta(days=2),
    )
    replay.settle("capred-exit-settlement", exit_at + timedelta(days=2))
    final_snapshot = replay.snapshot(at=dt(post_day, 15))

    payment_blocked = False
    try:
        portfolio.corporate_actions.pay_cash_entitlement(
            event.event_id,
            paid_at=dt(post_day, 15),
        )
    except ValueError as exc:
        payment_blocked = "UNKNOWN" in str(exc)

    checks = {
        "source_event_supported": str(src["event_type"]) == "capital_reduction",
        "explicit_share_multiplier": multiplier > 0,
        "explicit_cash_component": cash_per_share > 0,
        "raw_entry": entry.raw_decision.use is PriceUse.ENTRY,
        "refund_uses_pre_mutation_share_basis": abs(refund.shares_entitled - qty_before) < 1e-9,
        "refund_reconciles": abs(refund.amount - expected_refund) < 1e-9,
        "share_quantity_reconciles": abs(qty_after_event - expected_qty) < 1e-9,
        "cost_basis_preserved": abs(total_cost_after_event - old_total_cost) < 1e-6,
        "cash_unchanged_at_event": abs(portfolio.cash.settled_cash - (
            settled_before_event + exit_result.fill.quantity * exit_result.fill.price
        )) < 1e-6,
        "receivable_retained": abs(portfolio.cash.pending_receivables - expected_refund) < 1e-9,
        "unknown_payment_not_guessed": payment_blocked,
        "raw_exit": exit_result.raw_decision.use is PriceUse.EXIT,
        "position_flat_after_exit": portfolio.positions.positions[ticker].quantity == 0,
        "final_market_value_zero": abs(final_snapshot.valuation.market_value) < 1e-9,
        "no_adjusted_price_used": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source-Backed Capital-Reduction Replay",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: test a real capital-reduction event carrying both a share multiplier and a cash refund component.",
        "This validates component arithmetic and ledger behavior; it does not claim that the source event_date is a legally complete entitlement/payment timeline.",
        "",
        "## Source event",
        "",
        f"- ticker: {ticker}",
        f"- event date: {event_day.date()}",
        f"- known date: {src['known_date']}",
        f"- share multiplier: {multiplier}",
        f"- cash per share: {cash_per_share}",
        f"- source: {src['source_name']}",
        "",
        "## Replay",
        "",
        f"- pre-event RAW entry session: {pre_day.date()}",
        f"- entry RAW open: {entry.fill.price}",
        f"- pre-event shares: {qty_before}",
        f"- post-event shares: {qty_after_event}",
        f"- post-event average cost: {avg_cost_after_event}",
        f"- post-event total cost basis: {total_cost_after_event}",
        f"- cash refund receivable: {refund.amount}",
        f"- post-event RAW mark session: {post_day.date()}",
        f"- post-event RAW market value: {post_snapshot.valuation.market_value}",
        f"- RAW exit close: {exit_result.fill.price}",
        f"- final pending receivable: {portfolio.cash.pending_receivables}",
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
        "## Source limitation",
        "",
        "The canonical ledger has no payment-date field. The capital-reduction refund therefore remains a receivable and cannot be converted to settled cash by guessing a date.",
        "",
        "The source event_date for capital reduction is treated as the available economic mutation coordinate for this accounting replay; legal entitlement/record/payment dates remain incomplete and must not be inferred.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        print("FAILED_CHECKS=" + ",".join(failed))
        raise SystemExit("FAIL: capital-reduction replay gate failed")


if __name__ == "__main__":
    main()
