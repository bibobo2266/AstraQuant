#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.portfolio.replay import run_accounting_only_replay

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md"))
YEAR = int(os.environ.get("REPLAY_YEAR", "2026"))


def choose_window() -> tuple[str, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    raw_path = SOURCE_ROOT / "raw" / f"prices_raw_{YEAR}.parquet"
    trad_path = SOURCE_ROOT / "reference" / "tradability.parquet"
    raw = pd.read_parquet(raw_path, columns=["date", "stock_id", "open", "max", "min", "close"])
    trad = pd.read_parquet(
        trad_path,
        columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked", "sell_blocked"],
    )
    for df in (raw, trad):
        df["stock_id"] = df["stock_id"].astype(str)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()

    raw = raw[raw["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)].copy()
    trad = trad[
        trad["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & trad["observed_trade"].fillna(False).astype(bool)
        & trad["valid_ohlc"].fillna(False).astype(bool)
        & ~trad["buy_blocked"].fillna(True).astype(bool)
        & ~trad["sell_blocked"].fillna(True).astype(bool)
    ].copy()

    merged = raw.merge(trad[["date", "stock_id"]], on=["date", "stock_id"], how="inner")
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geom = (
        (merged["max"] >= merged[["open", "close", "min"]].max(axis=1))
        & (merged["min"] <= merged[["open", "close", "max"]].min(axis=1))
    )
    merged = merged[positive & geom].sort_values(["stock_id", "date"])

    preferred = ["2330", "2317", "2454"]
    ids = preferred + [x for x in merged["stock_id"].drop_duplicates().tolist() if x not in preferred]
    for sid in ids:
        dates = merged.loc[merged["stock_id"].eq(sid), "date"].drop_duplicates().tolist()
        if len(dates) >= 3:
            return sid, pd.Timestamp(dates[-3]), pd.Timestamp(dates[-2]), pd.Timestamp(dates[-1])
    raise SystemExit("BLOCKED: no 3-session tradable replay window found")


def must_resolve(market: ExecutionMarketData, **kwargs):
    d = market.resolve(**kwargs)
    if d.availability is not ExecutionAvailability.EXECUTABLE:
        raise SystemExit(f"BLOCKED: {kwargs['use'].value} -> {d.reason}")
    return d


def main() -> None:
    ticker, entry_day, mark_day, exit_day = choose_window()
    source = SourceDataAdapter(SOURCE_ROOT)
    market = ExecutionMarketData(source)

    sizing = must_resolve(
        market,
        ticker=ticker,
        session_date=entry_day,
        side="buy",
        use=PriceUse.SIZING,
        field="open",
    )
    entry = must_resolve(
        market,
        ticker=ticker,
        session_date=entry_day,
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )
    stop_obs = must_resolve(
        market,
        ticker=ticker,
        session_date=mark_day,
        side="sell",
        use=PriceUse.STOP_OBSERVATION,
        field="low",
    )
    mark = must_resolve(
        market,
        ticker=ticker,
        session_date=mark_day,
        side="sell",
        use=PriceUse.MARK,
        field="close",
    )
    exit_decision = must_resolve(
        market,
        ticker=ticker,
        session_date=exit_day,
        side="sell",
        use=PriceUse.EXIT,
        field="close",
    )

    quantity = 100.0
    opening_cash = max(1_000_000.0, float(entry.price) * quantity * 2.0)
    result = run_accounting_only_replay(
        ticker=ticker,
        quantity=quantity,
        opening_cash=opening_cash,
        signal_source="SOURCE_SMOKE_DECLARED_RESEARCH_SIGNAL_PLACEHOLDER",
        sizing_decision=sizing,
        entry_decision=entry,
        stop_observation_decision=stop_obs,
        mark_decision=mark,
        exit_decision=exit_decision,
        entry_at=datetime.combine(entry_day.date(), datetime.min.time()),
        entry_settlement_due=datetime.combine((entry_day + timedelta(days=2)).date(), datetime.min.time()),
        exit_at=datetime.combine(exit_day.date(), datetime.min.time()),
        exit_settlement_due=datetime.combine((exit_day + timedelta(days=2)).date(), datetime.min.time()),
    )

    checks = result.checks.__dict__
    status = "PASS" if result.checks.passed else "FAIL"
    lines = [
        "# Source-Backed Accounting Smoke Replay",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: exercise the accounting-only replay against real frozen RAW/tradability source data.",
        "This is not a strategy backtest and no performance metric is used as an acceptance criterion.",
        "",
        "## Selected source window",
        "",
        f"- ticker: {ticker}",
        f"- entry session: {entry_day.date()}",
        f"- mark/stop-observation session: {mark_day.date()}",
        f"- exit session: {exit_day.date()}",
        f"- quantity: {quantity:g}",
        "",
        "## RAW decisions",
        "",
        f"- sizing RAW open: {sizing.price}",
        f"- entry RAW open: {entry.price}",
        f"- stop observation RAW low: {stop_obs.price}",
        f"- mark RAW close: {mark.price}",
        f"- exit RAW close: {exit_decision.price}",
        "",
        "## Accounting gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, value in checks.items():
        lines.append(f"| {name} | {'PASS' if value else 'FAIL'} |")

    lines += [
        "",
        "## Accounting state",
        "",
        f"- opening cash: {opening_cash}",
        f"- pre-exit RAW market value: {result.pre_exit_valuation.market_value}",
        f"- pre-exit NAV: {result.pre_exit_valuation.nav}",
        f"- final settled cash after exit settlement: {result.final_cash}",
        "",
        "These values are retained only to prove accounting identity. They are not strategy-performance evidence.",
        "",
        "## Scope limitation",
        "",
        "This source smoke window intentionally tests a plain trade lifecycle. Corporate-action replay remains a separate gate.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not result.checks.passed:
        raise SystemExit("FAIL: one or more accounting gates failed")


if __name__ == "__main__":
    main()
