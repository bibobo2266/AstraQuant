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


def run_remaining_accounting_probe(*, source_root, overlay, manifest_path, archive, output):
    """Evidence only: exercise frozen inputs without issuing an unlock receipt."""
    import json
    import math
    import zipfile
    from dataclasses import asdict
    from astraquant.data.corporate_actions import build_finmind_normalized_actions
    from astraquant.data.market_coordinates import SignalPriceSemantics
    from astraquant.execution.assumptions import FixedBpsSlippage
    from astraquant.execution.fills import ExecutionFillFactory
    from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
    from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
    from astraquant.portfolio.models import OrderIntent
    from astraquant.portfolio.reviewed_ca import ReviewedCA, sha
    from astraquant.research.trading_plan_r1_s3 import _OwnerCosts
    from astraquant.research.trading_plan_r1 import COMMISSION, SLIPPAGE
    from astraquant.research.terminal_events import load_terminal_event_records
    import hashlib
    from tempfile import TemporaryDirectory

    root = Path(source_root)
    if sha(manifest_path) != 'e18b21dab018c04ae5f6d05979c9d601b035bde45338ed40c42544be9337a26c':
        raise ValueError('unreviewed accounting export manifest')
    manifest = json.loads(Path(manifest_path).read_text())
    evidence = []
    for item in manifest['files']:
        if item['role'] not in {'raw', 'tradability', 'dividend', 'official_events'}:
            continue
        path = root / item['source_path']
        if sha(path) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('changed frozen accounting probe input')
        evidence.append(dict(path=item['source_path'], sha256=item['sha256']))
    if sha(archive) != '79a45e098fb55f9c358c2c8a67e58365d07277b5ba706e2768d1842d11902867':
        raise ValueError('changed reviewed accounting archive')
    terms = next(x for x in manifest['files'] if x['role'] == 'terminal_terms')
    with zipfile.ZipFile(archive) as zipped:
        terminal_bytes = zipped.read('research/' + terms['source_path'])
    if hashlib.sha256(terminal_bytes).hexdigest() != terms['sha256'] or len(terminal_bytes) != terms['bytes']:
        raise ValueError('changed terminal terms')
    evidence.append(dict(path=terms['source_path'], sha256=terms['sha256']))
    actions = ReviewedCA(overlay, root/'reference/corporate_actions_official.csv')
    portfolio = PortfolioEngine(opening_cash=1_000_000)
    service = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(root), ticker_scope={'1315'}),
        fill_factory=ExecutionFillFactory(_OwnerCosts(), FixedBpsSlippage(0)), portfolio=portfolio)
    signal = SignalDeclaration(source=actions.binding, price_semantics=SignalPriceSemantics.RAW_REQUIRED)
    sizing = service.sizing_price(ticker='1315', session_date='2020-10-14', side='buy', field='close', signal=signal)
    assert sizing.availability is ExecutionAvailability.EXECUTABLE
    per_share = sizing.price*(1+COMMISSION+SLIPPAGE)
    sized_quantity = math.floor(min(1_000_000*.07, 1_000_000*.25)/per_share)
    assert sized_quantity*per_share <= 70_000 < (sized_quantity+1)*per_share
    at = datetime(2020,10,14,13,30)
    buy = service.execute(intent=OrderIntent('real7-buy','1315','buy',1000,at,'controlled accounting holding, not strategy sizing'),
        signal=signal, order_id='real7-buy-order',fill_id='real7-buy-fill',submitted_at=at,
        session_date='2020-10-14', use=PriceUse.ENTRY,field='close',
        settlement=SettlementInstruction('real7-buy-settlement',datetime(2020,10,16)))
    portfolio.settlements.settle('real7-buy-settlement',datetime(2020,10,16))
    event = actions.apply(portfolio=portfolio,ticker='1315',day='2020-10-26',stop_price=buy.fill.price*.93)
    observation = service.stop_observation(ticker='1315',session_date='2020-10-26',side='sell')
    assert observation.availability is ExecutionAvailability.EXECUTABLE and observation.price == 68.2
    assert observation.price > event['new_stop']
    actions.pay_due(portfolio=portfolio,day='2020-10-29')
    at = datetime(2020,10,30,9)
    sell = service.execute(intent=OrderIntent('real7-sell','1315','sell',700,at,'controlled next-open accounting exit, not an SMA signal'),
        signal=signal,order_id='real7-sell-order',fill_id='real7-sell-fill',submitted_at=at,
        session_date='2020-10-30',use=PriceUse.EXIT,field='open',
        settlement=SettlementInstruction('real7-sell-settlement',datetime(2020,11,3)))
    portfolio.settlements.settle('real7-sell-settlement',datetime(2020,11,3))
    entry_cash = buy.fill.quantity*buy.fill.price+buy.fill.fees
    exit_cash = sell.fill.quantity*sell.fill.price-sell.fill.fees
    economic_pnl = exit_cash+3000-entry_cash
    assert math.isclose(portfolio.cash.settled_cash-1_000_000,economic_pnl,abs_tol=1e-8)
    assert portfolio.positions.positions['1315'].quantity == 0
    assert portfolio.cash.pending_receivables == portfolio.cash.pending_payables == 0
    dividend = pd.read_parquet(root/'fundamentals/dividend.parquet')
    normalized = [a for a in build_finmind_normalized_actions(dividend)
                  if datetime(2016,1,1).date() <= a.effective_date <= datetime(2021,12,31).date()]
    late = [a for a in normalized if a.known_at is None or a.known_at.date() > a.effective_date]
    with TemporaryDirectory() as temporary:
        terminal_path = Path(temporary)/'terminal_events.csv'
        terminal_path.write_bytes(terminal_bytes)
        terminal = load_terminal_event_records(terminal_path)
    e1_terminal = [asdict(a) for a in terminal if a.effective_date and a.effective_date.year <= 2021]
    result = dict(schema_version='real_accounting_remaining_v1',source_revision=manifest['source_revision'],
        source_inputs=evidence, overlay_sha256=sha(overlay),
        sizing=dict(source_key=['2020-10-14','1315'],raw_price=sizing.price,budget=70000,per_share_cost=per_share,
                    quantity=sized_quantity,executed_quantity=1000,scope='formula observation; controlled holding differs from strategy sizing'),
        stop_observation=dict(source_key=['2020-10-26','1315'],raw_low=observation.price,
                              adjusted_stop=event['new_stop'],triggered=False),
        exit=dict(source_key=['2020-10-30','1315'],raw_open=sell.fill.price,quantity=700,cost=sell.fill.fees,
                  entry_cash=entry_cash,exit_cash=exit_cash,refund=3000,pnl=economic_pnl,
                  final_cash=portfolio.cash.settled_cash,settlement='2020-11-03',
                  scope='controlled accounting exit, not a strategy-generated signal'),
        normalized=dict(count=len(normalized),unsafe=[asdict(a) for a in late],
                        scope='actual normalization and unsafe-key inventory; not production exclusion replay'),
        terminal=dict(e1_records=e1_terminal,known_at_field_present=False,
                      scope='frozen terms contain no announcement timestamp; no guessed terminal application'),
        checks={
            'stop_observation_raw':'EXERCISED_CASE_ONLY', 'exit_raw':'EXERCISED_CASE_ONLY',
            'sizing_raw':'OBSERVED_FORMULA_ONLY', 'normalized_ca_view_active':'NORMALIZATION_ONLY',
            'pit_unsafe_ca_excluded':'INVENTORY_ONLY_NOT_REPLAYED',
            'terminal_security_lifecycle_active':'NOT_EXERCISED_MISSING_KNOWN_AT',
            'long_horizon_canonical_probe_passed':'NOT_EXERCISED_UNRESOLVED_EVENT_EVIDENCE'},
        accounting_gate_passed=False,s3_effects_executed=False,
        blockers=['Terminal terms lack known_at; no new timestamp/source inferred.',
                  'Full E1 canonical integration not executed: terminal announcement times and other nine event evidence gaps remain unresolved.'])
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,indent=2,default=str)+'\n')
    return result


if __name__ == "__main__":
    main()
