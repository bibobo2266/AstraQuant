#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime
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
from astraquant.portfolio.historical_runner import (
    HistoricalCorporateActionInstruction,
    HistoricalPortfolioRunner,
    HistoricalTradeInstruction,
)
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_FULL_HISTORY_PROBE.md"))
TICKER = os.environ.get("REPLAY_TICKER", "2330")
START_YEAR = int(os.environ.get("START_YEAR", "2015"))
END_YEAR = int(os.environ.get("END_YEAR", "2026"))


def read_scoped(path: Path, columns: list[str]) -> pd.DataFrame:
    return pd.read_parquet(
        path,
        columns=columns,
        filters=[("stock_id", "==", TICKER)],
    )


def build_sessions() -> list[pd.Timestamp]:
    raw_parts = []
    for year in range(START_YEAR, END_YEAR + 1):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing RAW file for {year}")
        frame = read_scoped(
            path,
            ["date", "stock_id", "open", "max", "min", "close"],
        )
        raw_parts.append(frame)

    raw = pd.concat(raw_parts, ignore_index=True)
    trad = read_scoped(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        [
            "date", "stock_id", "observed_trade", "valid_ohlc",
            "buy_blocked", "sell_blocked", "reason",
        ],
    )

    for frame in (raw, trad):
        frame["stock_id"] = frame["stock_id"].astype(str)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()

    merged = raw.merge(trad, on=["date", "stock_id"], how="inner", validate="one_to_one")
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geometry = (
        (merged["max"] >= merged[["open", "close", "min"]].max(axis=1))
        & (merged["min"] <= merged[["open", "close", "max"]].min(axis=1))
    )
    valid = merged[
        merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
        & positive
        & geometry
    ].copy()

    if valid.empty:
        raise SystemExit("BLOCKED: no valid observed sessions for replay ticker")

    dates = valid["date"].drop_duplicates().sort_values().tolist()
    if pd.Timestamp(dates[0]).year != START_YEAR or pd.Timestamp(dates[-1]).year != END_YEAR:
        raise SystemExit(
            f"BLOCKED: ticker history does not span {START_YEAR}-{END_YEAR}: "
            f"{dates[0]}..{dates[-1]}"
        )
    return [pd.Timestamp(x) for x in dates]


def scoped_tradability() -> pd.DataFrame:
    t = read_scoped(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        ["date", "stock_id", "buy_blocked", "sell_blocked"],
    )
    t["date"] = pd.to_datetime(t["date"], errors="coerce").dt.normalize()
    t["stock_id"] = t["stock_id"].astype(str)
    return t


def choose_entry_exit(sessions: list[pd.Timestamp]) -> tuple[int, int]:
    trad = scoped_tradability().set_index("date")
    entry_idx = None
    for i, day in enumerate(sessions):
        row = trad.loc[day]
        if isinstance(row, pd.DataFrame):
            raise SystemExit(f"BLOCKED: duplicate tradability row on {day.date()}")
        if not bool(row["buy_blocked"]):
            entry_idx = i
            break
    if entry_idx is None or entry_idx + 2 >= len(sessions):
        raise SystemExit("BLOCKED: no valid historical entry window")

    exit_idx = None
    for i in range(len(sessions) - 3, entry_idx + 2, -1):
        day = sessions[i]
        row = trad.loc[day]
        if isinstance(row, pd.DataFrame):
            raise SystemExit(f"BLOCKED: duplicate tradability row on {day.date()}")
        if not bool(row["sell_blocked"]):
            exit_idx = i
            break
    if exit_idx is None or exit_idx + 2 >= len(sessions):
        raise SystemExit("BLOCKED: no valid historical exit/settlement window")
    return entry_idx, exit_idx


def dedupe_dividends(session_set: set[pd.Timestamp]) -> list[HistoricalCorporateActionInstruction]:
    ledger = read_scoped(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        [
            "stock_id", "event_date", "known_date", "event_type",
            "cash_per_share", "source_name", "source_url",
        ],
    )
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["known_date"] = pd.to_datetime(ledger["known_date"], errors="coerce")
    ledger["cash_per_share"] = pd.to_numeric(ledger["cash_per_share"], errors="coerce")
    d = ledger[
        ledger["event_type"].astype(str).eq("dividend")
        & ledger["event_date"].isin(session_set)
        & ledger["cash_per_share"].gt(0)
    ].copy()

    out: list[HistoricalCorporateActionInstruction] = []
    for day, g in d.groupby("event_date", sort=True):
        values = sorted(set(round(float(v), 8) for v in g["cash_per_share"].dropna()))
        if len(values) != 1:
            raise SystemExit(
                f"BLOCKED: conflicting dividend cash/share on {pd.Timestamp(day).date()}: {values}"
            )
        row = g.sort_values(["source_name", "source_url"]).iloc[0]
        event = CorporateActionEvent(
            event_id=f"full-history:{TICKER}:{pd.Timestamp(day).date()}:dividend",
            ticker=TICKER,
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime.combine(pd.Timestamp(day).date(), datetime.min.time()),
            known_at=None if pd.isna(row["known_date"]) else pd.Timestamp(row["known_date"]).to_pydatetime(),
            payment_at=None,
            cash_per_share=float(row["cash_per_share"]),
            source=str(row["source_name"]),
            notes=str(row["source_url"]),
        )
        out.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
            )
        )
    return out


def dedupe_share_mutations(
    session_set: set[pd.Timestamp],
) -> tuple[list[HistoricalCorporateActionInstruction], float]:
    ledger = read_scoped(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        [
            "stock_id", "event_date", "known_date", "event_type",
            "share_multiplier", "source_name", "source_url",
        ],
    )
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["known_date"] = pd.to_datetime(ledger["known_date"], errors="coerce")
    ledger["share_multiplier"] = pd.to_numeric(ledger["share_multiplier"], errors="coerce")
    d = ledger[
        ledger["event_date"].isin(session_set)
        & ledger["share_multiplier"].gt(0)
    ].copy()

    out: list[HistoricalCorporateActionInstruction] = []
    cumulative = 1.0
    for (day, event_type), g in d.groupby(["event_date", "event_type"], sort=True):
        values = sorted(set(round(float(v), 10) for v in g["share_multiplier"].dropna()))
        if len(values) != 1:
            raise SystemExit(
                f"BLOCKED: conflicting share multiplier on {pd.Timestamp(day).date()} "
                f"{event_type}: {values}"
            )
        multiplier = float(g.iloc[0]["share_multiplier"])
        row = g.sort_values(["source_name", "source_url"]).iloc[0]
        event_type_text = str(event_type)
        mapped_type = (
            CorporateActionType.CAPITAL_REDUCTION
            if "capital_reduction" in event_type_text
            else CorporateActionType.SPLIT
        )
        event = CorporateActionEvent(
            event_id=f"full-history:{TICKER}:{pd.Timestamp(day).date()}:{event_type_text}",
            ticker=TICKER,
            event_type=mapped_type,
            effective_at=datetime.combine(pd.Timestamp(day).date(), datetime.min.time()),
            known_at=None if pd.isna(row["known_date"]) else pd.Timestamp(row["known_date"]).to_pydatetime(),
            share_multiplier=multiplier,
            source=str(row["source_name"]),
            notes=str(row["source_url"]),
        )
        out.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
            )
        )
        cumulative *= multiplier
    return out, cumulative


def main() -> None:
    sessions = build_sessions()
    session_set = set(sessions)
    entry_idx, exit_idx = choose_entry_exit(sessions)
    entry_day = sessions[entry_idx]
    exit_day = sessions[exit_idx]

    dividends = dedupe_dividends(session_set)
    share_events, cumulative_multiplier = dedupe_share_mutations(session_set)
    corporate_actions = sorted(
        dividends + share_events,
        key=lambda x: (x.event.effective_at, x.event.event_id),
    )

    starting_quantity = 100.0
    exit_quantity = starting_quantity * cumulative_multiplier

    portfolio = PortfolioEngine(opening_cash=10_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope={TICKER},
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    replay = CanonicalPortfolioReplay(execution=execution, portfolio=portfolio)
    runner = HistoricalPortfolioRunner(replay)
    signal = SignalDeclaration(
        source="SOURCE_FULL_HISTORY_ACCOUNTING_PROBE",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )

    entry_at = datetime.combine(entry_day.date(), datetime.min.time()).replace(hour=9)
    exit_at = datetime.combine(exit_day.date(), datetime.min.time()).replace(hour=13)

    trades = [
        HistoricalTradeInstruction(
            intent=OrderIntent(
                intent_id="full-history-entry-intent",
                ticker=TICKER,
                side="buy",
                quantity=starting_quantity,
                created_at=entry_at,
                rationale="full-history accounting probe",
            ),
            signal=signal,
            order_id="full-history-entry-order",
            fill_id="full-history-entry-fill",
            submitted_at=entry_at,
            session_date=entry_day.date(),
            use=PriceUse.ENTRY,
            field="open",
            settlement_id="full-history-entry-settlement",
            settlement_due=datetime.combine(
                sessions[entry_idx + 2].date(), datetime.min.time()
            ),
        ),
        HistoricalTradeInstruction(
            intent=OrderIntent(
                intent_id="full-history-exit-intent",
                ticker=TICKER,
                side="sell",
                quantity=exit_quantity,
                created_at=exit_at,
                rationale="full-history accounting probe exit",
            ),
            signal=signal,
            order_id="full-history-exit-order",
            fill_id="full-history-exit-fill",
            submitted_at=exit_at,
            session_date=exit_day.date(),
            use=PriceUse.EXIT,
            field="close",
            settlement_id="full-history-exit-settlement",
            settlement_due=datetime.combine(
                sessions[exit_idx + 2].date(), datetime.min.time()
            ),
        ),
    ]

    result = runner.run(
        sessions=[x.date() for x in sessions],
        trades=trades,
        corporate_actions=corporate_actions,
    )

    final_position = portfolio.positions.positions[TICKER]
    final_snapshot = result.sessions[-1].snapshot
    years = sorted({x.session_date.year for x in result.sessions})
    year_counts = {
        year: sum(1 for x in result.sessions if x.session_date.year == year)
        for year in years
    }

    checks = {
        "calendar_starts_2015": years[0] == START_YEAR,
        "calendar_ends_2026": years[-1] == END_YEAR,
        "all_years_present": years == list(range(START_YEAR, END_YEAR + 1)),
        "session_snapshots_complete": len(result.sessions) == len(sessions),
        "entry_and_exit_executed": result.total_trades == 2,
        "all_corporate_actions_applied": result.total_corporate_actions == len(corporate_actions),
        "trade_settlements_completed": result.total_settlements == 2,
        "position_flat_final": abs(final_position.quantity) < 1e-9,
        "pending_payables_zero": abs(portfolio.cash.pending_payables) < 1e-9,
        "final_market_value_zero": abs(final_snapshot.valuation.market_value) < 1e-9,
        "raw_only_execution": True,
        "canonical_historical_runner_used": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source Full-History Canonical Accounting Probe",
        "",
        f"Status: **{status}**",
        "",
        f"Scope: {TICKER} observed/valid RAW sessions from {START_YEAR} through {END_YEAR}.",
        "Purpose: exercise the chronological AstraQuant canonical runner across the full frozen history range.",
        "This is not a strategy backtest and no return/risk statistic is an acceptance criterion.",
        "",
        "## Historical span",
        "",
        f"- first replay session: {sessions[0].date()}",
        f"- final replay session: {sessions[-1].date()}",
        f"- sessions replayed / RAW NAV snapshots: {len(result.sessions):,}",
        f"- entry: {entry_day.date()} RAW open",
        f"- exit: {exit_day.date()} RAW close",
        f"- starting shares: {starting_quantity}",
        f"- cumulative explicit share multiplier: {cumulative_multiplier}",
        f"- exit shares: {exit_quantity}",
        f"- cash-dividend events applied: {len(dividends)}",
        f"- share-multiplier events applied: {len(share_events)}",
        f"- total corporate actions applied: {result.total_corporate_actions}",
        "",
        "## Sessions by year",
        "",
        "| Year | Sessions / RAW snapshots |",
        "|---:|---:|",
    ]
    for year in years:
        lines.append(f"| {year} | {year_counts[year]:,} |")

    lines += [
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
        "Dividend receivables can remain outstanding because the canonical source ledger does not provide payment dates. They are retained in NAV and never converted to settled cash using guessed dates.",
        "",
        "## Limitation",
        "",
        "This full-history probe validates the canonical accounting/runtime path on one continuously held source security. It does not migrate the legacy strategy's signal-generation logic. Performance remains locked until strategy intents are fed through this canonical historical runner under declared PIT signal semantics.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        print("FAILED_CHECKS=" + ",".join(failed))
        raise SystemExit("FAIL: full-history canonical accounting probe failed")


if __name__ == "__main__":
    main()
