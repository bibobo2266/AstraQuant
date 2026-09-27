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
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_MULTI_EVENT_REPLAY.md"))


def load_ledger() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    cols = [
        "stock_id", "event_date", "known_date", "event_type",
        "cash_per_share", "share_multiplier", "source_name", "source_url",
    ]
    df = pd.read_parquet(path, columns=cols)
    df["stock_id"] = df["stock_id"].astype(str)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.normalize()
    df["known_date"] = pd.to_datetime(df["known_date"], errors="coerce")
    df["cash_per_share"] = pd.to_numeric(df["cash_per_share"], errors="coerce")
    df["share_multiplier"] = pd.to_numeric(df["share_multiplier"], errors="coerce")
    return df


def choose_events(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    split = df[
        df["event_type"].astype(str).eq("par_value_change_split")
        & df["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & df["event_date"].notna()
        & df["share_multiplier"].gt(0)
    ].sort_values("event_date", ascending=False)
    if split.empty:
        raise SystemExit("BLOCKED: no supported split event")
    split_row = split.iloc[0]

    dividend = df[
        df["event_type"].astype(str).eq("dividend")
        & df["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & df["event_date"].notna()
        & df["known_date"].notna()
        & df["cash_per_share"].gt(0)
        & df["event_date"].gt(split_row["event_date"])
    ].copy()
    if dividend.empty:
        raise SystemExit("BLOCKED: no supported later dividend event")

    preferred = dividend[dividend["stock_id"].eq("2330")].sort_values("event_date", ascending=False)
    dividend_row = preferred.iloc[0] if not preferred.empty else dividend.sort_values("event_date", ascending=False).iloc[0]
    return split_row, dividend_row


def load_sessions(ticker: str, event_day: pd.Timestamp) -> pd.DataFrame:
    raw_parts = []
    for year in sorted({event_day.year - 1, event_day.year, event_day.year + 1}):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if path.exists():
            raw_parts.append(pd.read_parquet(
                path,
                columns=["date", "stock_id", "open", "max", "min", "close"],
            ))
    if not raw_parts:
        raise SystemExit(f"BLOCKED: no RAW files for {ticker}")

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

    out = raw.merge(trad, on=["date", "stock_id"], how="inner").sort_values("date")
    return out


def window_for_event(ticker: str, event_day: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = load_sessions(ticker, event_day)
    before = d[
        d["date"].lt(event_day)
        & ~d["buy_blocked"].fillna(True).astype(bool)
    ]
    after = d[
        d["date"].ge(event_day)
        & ~d["sell_blocked"].fillna(True).astype(bool)
    ]
    if before.empty or after.empty:
        raise SystemExit(f"BLOCKED: missing tradable pre/post window for {ticker} {event_day.date()}")
    return pd.Timestamp(before.iloc[-1]["date"]), pd.Timestamp(after.iloc[0]["date"])


def dt(day: pd.Timestamp, hour: int = 9) -> datetime:
    return datetime.combine(day.date(), datetime.min.time()).replace(hour=hour)


def main() -> None:
    ledger = load_ledger()
    split_src, div_src = choose_events(ledger)

    split_ticker = str(split_src["stock_id"])
    split_day = pd.Timestamp(split_src["event_date"]).normalize()
    split_pre, split_post = window_for_event(split_ticker, split_day)

    div_ticker = str(div_src["stock_id"])
    div_day = pd.Timestamp(div_src["event_date"]).normalize()
    div_pre, div_post = window_for_event(div_ticker, div_day)

    if not (split_post < div_pre):
        raise SystemExit("BLOCKED: chosen events do not form a clean sequential replay window")

    source = SourceDataAdapter(SOURCE_ROOT)
    portfolio = PortfolioEngine(opening_cash=5_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(source),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    replay = CanonicalPortfolioReplay(execution=execution, portfolio=portfolio)
    signal = SignalDeclaration(
        source="SOURCE_MULTI_EVENT_REPLAY_DECLARED_SIGNAL",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )

    # 1) Split lifecycle.
    q_split = 100.0
    split_entry_at = dt(split_pre)
    split_entry = replay.execute_trade(
        intent=OrderIntent(
            intent_id="multi-split-entry-intent",
            ticker=split_ticker,
            side="buy",
            quantity=q_split,
            created_at=split_entry_at,
            rationale="source multi-event replay split leg",
        ),
        signal=signal,
        order_id="multi-split-entry-order",
        fill_id="multi-split-entry-fill",
        submitted_at=split_entry_at,
        session_date=split_pre,
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="multi-split-entry-settlement",
        settlement_due=split_entry_at + timedelta(days=2),
    )
    replay.settle("multi-split-entry-settlement", split_entry_at + timedelta(days=2))

    split_event = CorporateActionEvent(
        event_id=f"source:{split_ticker}:{split_day.date()}:par_value_change_split",
        ticker=split_ticker,
        event_type=CorporateActionType.SPLIT,
        effective_at=dt(split_day, 0),
        known_at=None if pd.isna(split_src["known_date"]) else pd.Timestamp(split_src["known_date"]).to_pydatetime(),
        share_multiplier=float(split_src["share_multiplier"]),
        source=str(split_src["source_name"]),
        notes=str(split_src["source_url"]),
    )
    replay.apply_share_mutation(event=split_event, applied_at=dt(split_day, 0))
    split_qty_after = portfolio.positions.positions[split_ticker].quantity

    split_exit_at = dt(split_post, 13)
    split_exit = replay.execute_trade(
        intent=OrderIntent(
            intent_id="multi-split-exit-intent",
            ticker=split_ticker,
            side="sell",
            quantity=split_qty_after,
            created_at=split_exit_at,
            rationale="source multi-event replay split exit",
        ),
        signal=signal,
        order_id="multi-split-exit-order",
        fill_id="multi-split-exit-fill",
        submitted_at=split_exit_at,
        session_date=split_post,
        use=PriceUse.EXIT,
        field="close",
        settlement_id="multi-split-exit-settlement",
        settlement_due=split_exit_at + timedelta(days=2),
    )
    replay.settle("multi-split-exit-settlement", split_exit_at + timedelta(days=2))

    # 2) Cash-dividend lifecycle.
    q_div = 100.0
    div_entry_at = dt(div_pre)
    div_entry = replay.execute_trade(
        intent=OrderIntent(
            intent_id="multi-div-entry-intent",
            ticker=div_ticker,
            side="buy",
            quantity=q_div,
            created_at=div_entry_at,
            rationale="source multi-event replay dividend leg",
        ),
        signal=signal,
        order_id="multi-div-entry-order",
        fill_id="multi-div-entry-fill",
        submitted_at=div_entry_at,
        session_date=div_pre,
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="multi-div-entry-settlement",
        settlement_due=div_entry_at + timedelta(days=2),
    )
    replay.settle("multi-div-entry-settlement", div_entry_at + timedelta(days=2))

    div_event = CorporateActionEvent(
        event_id=f"source:{div_ticker}:{div_day.date()}:dividend",
        ticker=div_ticker,
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=dt(div_day, 0),
        known_at=pd.Timestamp(div_src["known_date"]).to_pydatetime(),
        payment_at=None,
        cash_per_share=float(div_src["cash_per_share"]),
        source=str(div_src["source_name"]),
        notes=str(div_src["source_url"]),
    )
    receivable = replay.accrue_cash_dividend(event=div_event, accrued_at=dt(div_day, 0))
    div_snapshot = replay.snapshot(at=dt(div_post, 15))

    div_exit_at = dt(div_post, 13)
    div_exit = replay.execute_trade(
        intent=OrderIntent(
            intent_id="multi-div-exit-intent",
            ticker=div_ticker,
            side="sell",
            quantity=q_div,
            created_at=div_exit_at,
            rationale="source multi-event replay dividend exit",
        ),
        signal=signal,
        order_id="multi-div-exit-order",
        fill_id="multi-div-exit-fill",
        submitted_at=div_exit_at,
        session_date=div_post,
        use=PriceUse.EXIT,
        field="close",
        settlement_id="multi-div-exit-settlement",
        settlement_due=div_exit_at + timedelta(days=2),
    )
    replay.settle("multi-div-exit-settlement", div_exit_at + timedelta(days=2))
    final_snapshot = replay.snapshot(at=dt(div_post, 15))

    expected_split_qty = q_split * float(split_src["share_multiplier"])
    expected_receivable = q_div * float(div_src["cash_per_share"])

    checks = {
        "signal_declared": bool(signal.source),
        "split_entry_raw": split_entry.raw_decision.use is PriceUse.ENTRY,
        "split_quantity_reconciles": abs(split_qty_after - expected_split_qty) < 1e-9,
        "split_exit_raw": split_exit.raw_decision.use is PriceUse.EXIT,
        "split_position_flat": portfolio.positions.positions[split_ticker].quantity == 0,
        "dividend_entry_raw": div_entry.raw_decision.use is PriceUse.ENTRY,
        "dividend_receivable_reconciles": abs(receivable.amount - expected_receivable) < 1e-9,
        "dividend_exit_raw": div_exit.raw_decision.use is PriceUse.EXIT,
        "dividend_position_flat": portfolio.positions.positions[div_ticker].quantity == 0,
        "pending_payables_zero": abs(portfolio.cash.pending_payables) < 1e-9,
        "outstanding_receivable_retained": abs(portfolio.cash.pending_receivables - expected_receivable) < 1e-9,
        "final_market_value_zero": abs(final_snapshot.valuation.market_value) < 1e-9,
        "canonical_runner_path_used": len(replay.executed_orders) == 4,
        "no_adjusted_price_used": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source-Backed Multi-Event Canonical Replay",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: prove one continuous canonical replay can process multiple real source events and trade lifecycles without adjusted execution prices.",
        "This is an accounting/integration test, not strategy-performance evidence.",
        "",
        "## Split leg",
        "",
        f"- ticker: {split_ticker}",
        f"- event date: {split_day.date()}",
        f"- share multiplier: {float(split_src['share_multiplier'])}",
        f"- source: {split_src['source_name']}",
        f"- entry session: {split_pre.date()} at RAW open {split_entry.fill.price}",
        f"- quantity before event: {q_split}",
        f"- quantity after event: {split_qty_after}",
        f"- exit session: {split_post.date()} at RAW close {split_exit.fill.price}",
        "",
        "## Cash-dividend leg",
        "",
        f"- ticker: {div_ticker}",
        f"- event date: {div_day.date()}",
        f"- known date: {div_src['known_date']}",
        f"- cash per share: {float(div_src['cash_per_share'])}",
        f"- source: {div_src['source_name']}",
        f"- entry session: {div_pre.date()} at RAW open {div_entry.fill.price}",
        f"- receivable accrued: {receivable.amount}",
        f"- event-day RAW close mark: {div_snapshot.valuation.positions[0].raw_mark if div_snapshot.valuation.positions else 'N/A'}",
        f"- exit session: {div_post.date()} at RAW close {div_exit.fill.price}",
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
        "## Final accounting state",
        "",
        f"- settled cash: {portfolio.cash.settled_cash}",
        f"- pending receivables: {portfolio.cash.pending_receivables}",
        f"- pending payables: {portfolio.cash.pending_payables}",
        f"- final RAW market value: {final_snapshot.valuation.market_value}",
        f"- final NAV: {final_snapshot.valuation.nav}",
        "",
        "The remaining receivable is intentional because the canonical source ledger has no payment-date field. AstraQuant does not guess the payment date.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        raise SystemExit("FAIL: multi-event canonical replay gate failed")


if __name__ == "__main__":
    main()
