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


def run_reviewed_reduction_probe(*, source_root, overlay, manifest_path, output):
    """Controlled real RAW accounting case; no strategy cells or unlock receipt."""
    import json
    import math
    from dataclasses import fields
    from astraquant.execution.assumptions import FixedBpsSlippage
    from astraquant.execution.fills import ExecutionFillFactory
    from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
    from astraquant.data.market_coordinates import SignalPriceSemantics
    from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
    from astraquant.portfolio.models import OrderIntent
    from astraquant.portfolio.reviewed_ca import ReviewedCA, sha
    from astraquant.research.trading_plan_r1_s3 import _OwnerCosts
    from astraquant.validation.accounting_gate import AccountingReadiness

    source_root = Path(source_root)
    if sha(manifest_path) != "e18b21dab018c04ae5f6d05979c9d601b035bde45338ed40c42544be9337a26c":
        raise ValueError("unreviewed accounting export manifest")
    manifest = json.loads(Path(manifest_path).read_text())
    evidence = []
    for item in manifest['files']:
        if item['role'] not in {'official_events', 'tradability'} and not (item['role']=='raw' and '2020' in item['source_path']):
            continue
        path=source_root/item['source_path']
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
            raise ValueError('changed frozen accounting probe input')
        evidence.append(dict(path=item['source_path'],sha256=item['sha256']))
    actions=ReviewedCA(overlay,source_root/'reference/corporate_actions_official.csv')
    portfolio=PortfolioEngine(opening_cash=1_000_000)
    service=CanonicalExecutionService(market_data=ExecutionMarketData(SourceDataAdapter(source_root)),
        fill_factory=ExecutionFillFactory(_OwnerCosts(),FixedBpsSlippage(0)),portfolio=portfolio)
    signal=SignalDeclaration(source=actions.binding,price_semantics=SignalPriceSemantics.RAW_REQUIRED)
    at=datetime(2020,10,14,13,30)
    buy=service.execute(intent=OrderIntent('ca-real-buy-intent','1315','buy',1000,at,'controlled accounting probe'),
        signal=signal,order_id='ca-real-buy-order',fill_id='ca-real-buy-fill',submitted_at=at,
        session_date='2020-10-14',use=PriceUse.ENTRY,field='close',
        settlement=SettlementInstruction('ca-real-buy-settle',datetime(2020,10,16)))
    portfolio.settlements.settle('ca-real-buy-settle',datetime(2020,10,16))
    assert buy.fill.price==52.7 and buy.fill.fees>0
    before_cash=portfolio.cash.settled_cash
    old_stop=buy.fill.price*.93
    record=actions.apply(portfolio=portfolio,ticker='1315',day='2020-10-26',stop_price=old_stop)
    assert portfolio.positions.positions['1315'].quantity==700
    assert portfolio.cash.pending_receivables==3000
    assert portfolio.cash.settled_cash==before_cash
    assert math.isclose(record['new_stop']*.7+3,old_stop)
    assert not actions.pay_due(portfolio=portfolio,day='2020-10-28')
    replay_rejected=False
    try: actions.apply(portfolio=portfolio,ticker='1315',day='2020-10-26',stop_price=old_stop)
    except ValueError as error:
        assert 'duplicate' in str(error);replay_rejected=True
    mark=service.mark(ticker='1315',session_date='2020-10-26')
    assert mark.availability is ExecutionAvailability.EXECUTABLE and mark.price==68.9
    nav=portfolio.cash.projected_cash+700*mark.price
    paid=actions.pay_due(portfolio=portfolio,day='2020-10-29')
    assert len(paid)==1 and portfolio.cash.pending_receivables==0
    assert portfolio.cash.settled_cash==before_cash+3000
    assert not actions.pay_due(portfolio=portfolio,day='2020-10-29')
    checks={f.name:dict(status='NOT_EXERCISED',scope='single real accounting case; not full E1 acceptance')
            for f in fields(AccountingReadiness)}
    for name in ['signal_source_declared','entry_raw','mark_raw','share_count_reconciles','cash_reconciles',
                 'receivables_reconcile','corporate_actions_reconcile','nav_reconciles',
                 'no_adjusted_execution_fallback','canonical_execution_path_active','ca_payment_dates_settle']:
        checks[name]['status']='EXERCISED_CASE_ONLY'
    result=dict(schema_version='reviewed_ca_real_probe_v1',source_revision=manifest['source_revision'],
        review='6061085838',overlay_sha256=sha(overlay),source_inputs=evidence,
        purpose='controlled 1000-share accounting holding; not S1/strategy-generated trade',
        entry=dict(day='2020-10-14',price=buy.fill.price,quantity=1000,cost=buy.fill.fees),
        event=record,available_cash_before_payment=before_cash,receivable_before_payment=3000,
        mark=dict(day='2020-10-26',raw_price=mark.price,quantity=700,nav_including_receivable=nav),
        payment=paid,available_cash_after_payment=portfolio.cash.available_to_commit_cash,
        duplicate_event_rejected=replay_rejected,duplicate_payment_count=0,
        checks=checks,accounting_gate_passed=False,s3_effects_executed=False,
        fractional_settlement='BLOCKED: five accepted fields do not establish fractional cash-out terms',
        remaining_gaps=manifest.get('source_limits'))
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__ == "__main__":
    main()
