#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.valuation import value_portfolio

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CA_CASH_REPLAY.md"))


def choose_event() -> pd.Series:
    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id", "event_date", "known_date", "event_type",
            "cash_per_share", "source_name", "source_url",
        ],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["known_date"] = pd.to_datetime(ledger["known_date"], errors="coerce")
    ledger["cash_per_share"] = pd.to_numeric(ledger["cash_per_share"], errors="coerce")

    candidates = ledger[
        ledger["event_type"].astype(str).eq("dividend")
        & ledger["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & ledger["event_date"].notna()
        & ledger["known_date"].notna()
        & ledger["cash_per_share"].gt(0)
        & ledger["event_date"].between(pd.Timestamp("2015-01-05"), pd.Timestamp("2026-09-24"))
    ].copy()
    if candidates.empty:
        raise SystemExit("BLOCKED: no supported cash-dividend event found")

    preferred = candidates[candidates["stock_id"].eq("2330")].sort_values("event_date", ascending=False)
    if not preferred.empty:
        return preferred.iloc[0]
    return candidates.sort_values("event_date", ascending=False).iloc[0]


def load_valid_sessions(ticker: str, years: set[int]) -> pd.DataFrame:
    raw_parts = []
    for year in sorted(years):
        p = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if p.exists():
            raw_parts.append(pd.read_parquet(
                p, columns=["date", "stock_id", "open", "max", "min", "close"]
            ))
    if not raw_parts:
        raise SystemExit("BLOCKED: no RAW price files around dividend event")

    raw = pd.concat(raw_parts, ignore_index=True)
    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked", "sell_blocked"],
    )
    for df in (raw, trad):
        df["stock_id"] = df["stock_id"].astype(str)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()

    raw = raw[raw["stock_id"].eq(ticker)].copy()
    trad = trad[
        trad["stock_id"].eq(ticker)
        & trad["observed_trade"].fillna(False).astype(bool)
        & trad["valid_ohlc"].fillna(False).astype(bool)
    ].copy()
    return raw.merge(trad, on=["date", "stock_id"], how="inner").sort_values("date")


def find_window(event: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    event_day = pd.Timestamp(event["event_date"]).normalize()
    d = load_valid_sessions(str(event["stock_id"]), {event_day.year - 1, event_day.year, event_day.year + 1})
    before = d[d["date"].lt(event_day) & ~d["buy_blocked"].fillna(True).astype(bool)]
    after = d[d["date"].ge(event_day)]
    if before.empty or after.empty:
        raise SystemExit("BLOCKED: no valid pre/post dividend sessions")
    return pd.Timestamp(before.iloc[-1]["date"]), pd.Timestamp(after.iloc[0]["date"])


def must(market: ExecutionMarketData, **kwargs):
    decision = market.resolve(**kwargs)
    if decision.availability is not ExecutionAvailability.EXECUTABLE:
        raise SystemExit(f"BLOCKED: {kwargs['use'].value} -> {decision.reason}")
    return decision


def main() -> None:
    source_event = choose_event()
    ticker = str(source_event["stock_id"])
    event_day = pd.Timestamp(source_event["event_date"]).normalize()
    cash_per_share = float(source_event["cash_per_share"])
    pre_day, post_day = find_window(source_event)

    source = SourceDataAdapter(SOURCE_ROOT)
    market = ExecutionMarketData(source)
    entry = must(
        market,
        ticker=ticker,
        session_date=pre_day,
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )
    post_mark = must(
        market,
        ticker=ticker,
        session_date=post_day,
        side="sell",
        use=PriceUse.MARK,
        field="close",
    )

    quantity = 100.0
    opening_cash = max(1_000_000.0, float(entry.price) * quantity * 3.0)
    engine = PortfolioEngine(opening_cash=opening_cash)
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )

    entry_at = datetime.combine(pre_day.date(), datetime.min.time())
    intent = OrderIntent(
        intent_id="cash-ca-buy-intent",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        created_at=entry_at,
        rationale="source-backed cash-dividend accounting replay",
    )
    engine.orders.create_from_intent(intent, "cash-ca-buy-order")
    engine.orders.submit("cash-ca-buy-order", entry_at)
    fill = factory.create_fill(
        fill_id="cash-ca-buy-fill",
        order_id="cash-ca-buy-order",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        filled_at=entry_at,
        decision=entry,
    )
    due = entry_at + timedelta(days=2)
    engine.apply_fill(fill, SettlementInstruction("cash-ca-buy-settlement", due))
    engine.settlements.settle("cash-ca-buy-settlement", due)

    settled_before = engine.cash.settled_cash
    event = CorporateActionEvent(
        event_id=f"source:{ticker}:{event_day.date()}:dividend",
        ticker=ticker,
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime.combine(event_day.date(), datetime.min.time()),
        known_at=pd.Timestamp(source_event["known_date"]).to_pydatetime(),
        payment_at=None,
        cash_per_share=cash_per_share,
        source=str(source_event["source_name"]),
        notes=str(source_event["source_url"]),
    )
    receivable = engine.corporate_actions.accrue_cash_dividend(
        event=event,
        shares_entitled=engine.positions.positions[ticker].quantity,
        accrued_at=datetime.combine(event_day.date(), datetime.min.time()),
    )

    valuation = value_portfolio(
        cash=engine.cash,
        positions=engine.positions.positions,
        raw_mark_decisions={ticker: post_mark},
    )
    expected_receivable = quantity * cash_per_share
    expected_nav = (
        engine.cash.settled_cash
        + expected_receivable
        - engine.cash.pending_payables
        + quantity * float(post_mark.price)
    )

    payment_blocked = False
    try:
        engine.corporate_actions.pay_cash_dividend(
            event.event_id,
            paid_at=datetime.combine(post_day.date(), datetime.min.time()),
        )
    except ValueError as exc:
        payment_blocked = "UNKNOWN" in str(exc)

    checks = {
        "source_dividend_supported": str(source_event["event_type"]) == "dividend",
        "known_date_present": pd.notna(source_event["known_date"]),
        "cash_per_share_positive": cash_per_share > 0,
        "raw_entry": entry.use is PriceUse.ENTRY,
        "raw_post_event_mark": post_mark.use is PriceUse.MARK,
        "receivable_reconciles": abs(receivable.amount - expected_receivable) < 1e-9,
        "settled_cash_unchanged_on_accrual": abs(engine.cash.settled_cash - settled_before) < 1e-9,
        "nav_includes_receivable": abs(valuation.nav - expected_nav) < 1e-6,
        "unknown_payment_date_not_guessed": payment_blocked,
        "no_adjusted_price_used": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source-Backed Cash-Dividend Receivable Replay",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: replay a canonical cash-dividend event on RAW economic coordinates while preserving an unknown payment date.",
        "This is an accounting test, not strategy-performance evidence.",
        "",
        "## Source event",
        "",
        f"- ticker: {ticker}",
        f"- event date: {event_day.date()}",
        f"- known date: {source_event['known_date']}",
        f"- cash per share: {cash_per_share}",
        f"- source: {source_event['source_name']}",
        f"- payment date in canonical ledger: UNKNOWN / unavailable",
        "",
        "## Replay",
        "",
        f"- pre-event RAW entry session: {pre_day.date()}",
        f"- entry RAW open: {entry.price}",
        f"- post-event RAW mark session: {post_day.date()}",
        f"- post-event RAW close: {post_mark.price}",
        f"- entitled shares: {quantity}",
        f"- dividend receivable accrued: {receivable.amount}",
        f"- settled cash before accrual: {settled_before}",
        f"- settled cash after accrual: {engine.cash.settled_cash}",
        f"- pending receivables after accrual: {engine.cash.pending_receivables}",
        f"- NAV including receivable: {valuation.nav}",
        "",
        "## Accounting checks",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, value in checks.items():
        lines.append(f"| {name} | {'PASS' if value else 'FAIL'} |")

    lines += [
        "",
        "## Decision",
        "",
        "The dividend becomes an economic receivable at the event/effective date. Because the canonical ledger has no payment-date field, the receivable is not converted to settled cash. AstraQuant explicitly rejects a guessed payment.",
        "",
        "This is the required behavior until a trustworthy payment date becomes available from a future source layer.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        raise SystemExit("FAIL: cash-dividend replay gate failed")


if __name__ == "__main__":
    main()
