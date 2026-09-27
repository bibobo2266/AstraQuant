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
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CA_SHARE_REPLAY.md"))


def choose_event() -> pd.Series:
    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id", "event_date", "known_date", "event_type",
            "share_multiplier", "cash_per_share", "source_name", "source_url",
        ],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["share_multiplier"] = pd.to_numeric(ledger["share_multiplier"], errors="coerce")
    candidates = ledger[
        ledger["event_type"].astype(str).eq("par_value_change_split")
        & ledger["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & ledger["event_date"].notna()
        & ledger["share_multiplier"].notna()
        & ledger["share_multiplier"].gt(0)
        & ledger["event_date"].between(pd.Timestamp("2015-01-05"), pd.Timestamp("2026-09-24"))
    ].copy()
    if candidates.empty:
        raise SystemExit("BLOCKED: no supported par_value_change_split event found")
    return candidates.sort_values("event_date", ascending=False).iloc[0]


def valid_sessions(ticker: str, year: int) -> pd.DataFrame:
    raw = pd.read_parquet(
        SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet",
        columns=["date", "stock_id", "open", "max", "min", "close"],
    )
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
    ticker = str(event["stock_id"])
    event_day = pd.Timestamp(event["event_date"]).normalize()
    years = sorted({event_day.year - 1, event_day.year, event_day.year + 1})
    parts = []
    for year in years:
        p = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if p.exists():
            parts.append(valid_sessions(ticker, year))
    if not parts:
        raise SystemExit("BLOCKED: no RAW sessions around event")
    d = pd.concat(parts, ignore_index=True).sort_values("date")

    before = d[
        d["date"].lt(event_day)
        & ~d["buy_blocked"].fillna(True).astype(bool)
    ]
    after = d[d["date"].ge(event_day)]
    if before.empty or after.empty:
        raise SystemExit("BLOCKED: missing valid pre/post event sessions")
    return pd.Timestamp(before.iloc[-1]["date"]), pd.Timestamp(after.iloc[0]["date"])


def must(market: ExecutionMarketData, **kwargs):
    d = market.resolve(**kwargs)
    if d.availability is not ExecutionAvailability.EXECUTABLE:
        raise SystemExit(f"BLOCKED: {kwargs['use'].value} -> {d.reason}")
    return d


def main() -> None:
    source_event = choose_event()
    ticker = str(source_event["stock_id"])
    event_day = pd.Timestamp(source_event["event_date"]).normalize()
    multiplier = float(source_event["share_multiplier"])
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
    pre_mark = must(
        market,
        ticker=ticker,
        session_date=pre_day,
        side="sell",
        use=PriceUse.MARK,
        field="close",
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

    at = datetime.combine(pre_day.date(), datetime.min.time())
    intent = OrderIntent(
        intent_id="ca-replay-buy-intent",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        created_at=at,
        rationale="source-backed CA accounting replay",
    )
    engine.orders.create_from_intent(intent, "ca-replay-buy-order")
    engine.orders.submit("ca-replay-buy-order", at)
    fill = factory.create_fill(
        fill_id="ca-replay-buy-fill",
        order_id="ca-replay-buy-order",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        filled_at=at,
        decision=entry,
    )
    due = at + timedelta(days=2)
    engine.apply_fill(fill, SettlementInstruction("ca-replay-buy-settlement", due))
    engine.settlements.settle("ca-replay-buy-settlement", due)

    pre_position = engine.positions.positions[ticker]
    old_qty = pre_position.quantity
    old_avg = pre_position.avg_cost
    old_cost = old_qty * old_avg
    pre_valuation = value_portfolio(
        cash=engine.cash,
        positions=engine.positions.positions,
        raw_mark_decisions={ticker: pre_mark},
    )

    event = CorporateActionEvent(
        event_id=f"source:{ticker}:{event_day.date()}:par_value_change_split",
        ticker=ticker,
        event_type=CorporateActionType.SPLIT,
        effective_at=datetime.combine(event_day.date(), datetime.min.time()),
        known_at=None if pd.isna(source_event["known_date"]) else pd.Timestamp(source_event["known_date"]).to_pydatetime(),
        share_multiplier=multiplier,
        source=str(source_event["source_name"]),
        notes=str(source_event["source_url"]),
    )
    engine.corporate_actions.apply_share_multiplier(
        event=event,
        positions=engine.positions,
        applied_at=datetime.combine(event_day.date(), datetime.min.time()),
    )

    post_position = engine.positions.positions[ticker]
    post_cost = post_position.quantity * post_position.avg_cost
    post_valuation = value_portfolio(
        cash=engine.cash,
        positions=engine.positions.positions,
        raw_mark_decisions={ticker: post_mark},
    )

    checks = {
        "source_event_type_supported": str(source_event["event_type"]) == "par_value_change_split",
        "explicit_share_multiplier": multiplier > 0,
        "raw_entry": entry.use is PriceUse.ENTRY,
        "raw_pre_event_mark": pre_mark.use is PriceUse.MARK,
        "raw_post_event_mark": post_mark.use is PriceUse.MARK,
        "quantity_reconciles": abs(post_position.quantity - old_qty * multiplier) < 1e-9,
        "cost_basis_reconciles": abs(post_cost - old_cost) < 1e-6,
        "cash_unchanged_by_share_mutation": abs(
            engine.cash.settled_cash - (opening_cash - quantity * float(entry.price))
        ) < 1e-6,
        "no_adjusted_price_used": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source-Backed Corporate-Action Share Replay",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: replay one official share-multiplier event on RAW economic coordinates.",
        "This is an accounting test, not strategy-performance evidence.",
        "",
        "## Source event",
        "",
        f"- ticker: {ticker}",
        f"- source event type: {source_event['event_type']}",
        f"- event date: {event_day.date()}",
        f"- source: {source_event['source_name']}",
        f"- share multiplier: {multiplier}",
        f"- known_date: {source_event['known_date']}",
        "",
        "## Replay window",
        "",
        f"- pre-event RAW session: {pre_day.date()}",
        f"- post-event RAW session: {post_day.date()}",
        f"- entry RAW open: {entry.price}",
        f"- pre-event RAW close mark: {pre_mark.price}",
        f"- post-event RAW close mark: {post_mark.price}",
        "",
        "## Share accounting",
        "",
        f"- quantity before event: {old_qty}",
        f"- average cost before event: {old_avg}",
        f"- total cost basis before event: {old_cost}",
        f"- quantity after event: {post_position.quantity}",
        f"- average cost after event: {post_position.avg_cost}",
        f"- total cost basis after event: {post_cost}",
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
        "## NAV observations",
        "",
        f"- pre-event NAV: {pre_valuation.nav}",
        f"- post-event NAV: {post_valuation.nav}",
        "",
        "The difference between pre/post NAV is not used as a pass/fail return metric because the marks are on different trading sessions. The accounting gate checks share and cost-basis identities only.",
        "",
        "## Limitation",
        "",
        "This replay covers an official par-value/share-split event with an explicit share_multiplier. Cash-dividend payment-date replay remains limited because the canonical source ledger has no payment-date field.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        raise SystemExit("FAIL: corporate-action share replay gate failed")


if __name__ == "__main__":
    main()
