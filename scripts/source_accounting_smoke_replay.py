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


def _verify_frozen_probe_inputs(*, source_root, manifest_path, archive):
    import json
    import zipfile
    import hashlib
    from astraquant.portfolio.reviewed_ca import sha
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
    return root, manifest, evidence, terminal_bytes


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

    root, manifest, evidence, terminal_bytes = _verify_frozen_probe_inputs(
        source_root=source_root, manifest_path=manifest_path, archive=archive)
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


def run_real_flow_probe(*, source_root, manifest_path, archive, panel, output):
    """Bounded RAW/canonical process cases, never an S3 unlock or four-cell run."""
    import json
    import math
    from dataclasses import asdict
    from types import SimpleNamespace
    from astraquant.portfolio.reviewed_ca import sha
    from astraquant.data.corporate_actions import build_finmind_normalized_actions
    from astraquant.data.market_coordinates import SignalPriceSemantics
    from astraquant.execution.assumptions import FixedBpsSlippage
    from astraquant.execution.fills import ExecutionFillFactory
    from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
    from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
    from astraquant.portfolio.models import OrderIntent
    from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay
    from astraquant.research.trading_plan_r1 import TradingPlanR1, COMMISSION, SLIPPAGE
    from astraquant.research.trading_plan_r1_s3 import _OwnerCosts

    root, manifest, evidence, _ = _verify_frozen_probe_inputs(
        source_root=source_root, manifest_path=manifest_path, archive=archive)
    panel_sha = '2fc9680a3cbb74b15d690edbeb02ed03457b26c74dd682a877b1c6e93f8dc38e'
    if sha(panel) != panel_sha:
        raise ValueError('changed frozen S1 panel')
    panel_frame = pd.read_parquet(panel).reset_index()
    raw = pd.concat([pd.read_parquet(root/f'raw/prices_raw_{y}.parquet',
                                   columns=['date','stock_id','open','max','min','close'])
                     for y in range(2015, 2022)], ignore_index=True)
    raw = raw.rename(columns={'stock_id':'stock','max':'high','min':'low'})
    raw['date'] = raw.date.dt.strftime('%Y-%m-%d')
    sessions = sorted(raw.date.unique())
    features_owner = SimpleNamespace(sessions=sessions)
    dividend = pd.read_parquet(root/'fundamentals/dividend.parquet')
    normalized = build_finmind_normalized_actions(dividend)
    official = pd.read_csv(root/'reference/corporate_actions_official.csv')

    def context(ticker):
        portfolio = PortfolioEngine(opening_cash=1_000_000)
        service = CanonicalExecutionService(
            market_data=ExecutionMarketData(SourceDataAdapter(root), ticker_scope={ticker}),
            fill_factory=ExecutionFillFactory(_OwnerCosts(), FixedBpsSlippage(0)),
            portfolio=portfolio)
        replay = CanonicalPortfolioReplay(execution=service, portfolio=portfolio)
        return portfolio, service, replay

    signal = SignalDeclaration(source=f'frozen RAW process probe:{panel_sha}',
                               price_semantics=SignalPriceSemantics.RAW_REQUIRED)

    def trade(service, *, ticker, day, side, quantity, case, field='open', stop=None):
        at = datetime.fromisoformat(day + ('T13:30:00' if field == 'close' or stop is not None else 'T09:00:00'))
        key = f'{case}:{side}'
        due = datetime.fromisoformat(sessions[sessions.index(day)+2])
        args = dict(intent=OrderIntent(key,ticker,side,quantity,at,'bounded true-data accounting probe'),
                    signal=signal,order_id=key+':order',fill_id=key+':fill',submitted_at=at,
                    session_date=day,settlement=SettlementInstruction(key+':settlement',due))
        if stop is not None:
            executed = service.execute_stop(**args,stop_price=stop)
        else:
            executed = service.execute(**args,use=PriceUse.ENTRY if side=='buy' else PriceUse.EXIT,field=field)
        return executed, key+':settlement', due

    cases = []
    for name, entry_day, signal_day, exit_day in [
            ('raw_stop','2019-09-18',None,'2019-09-23'),
            ('sma20_next_open','2019-08-07','2019-09-23','2019-09-24')]:
        ticker = '2345'
        prices = raw[raw.stock.eq(ticker)].sort_values('date')
        rows = prices.set_index('date').to_dict('index')
        eligibility = panel_frame[panel_frame.stock.eq(ticker) & panel_frame.date.eq(pd.Timestamp(entry_day))]
        if len(eligibility) != 1 or not bool(eligibility.iloc[0].eligibility):
            raise ValueError('probe entry is not in frozen S1 eligible panel')
        assert eligibility.iloc[0].available_date <= pd.Timestamp(entry_day)
        feature = TradingPlanR1._features(features_owner,prices,ticker,entry_day)
        assert feature['trigger'] and feature['base_valid'] and feature['base_sessions'] >= 10
        assert rows[entry_day]['close'] <= feature['pivot']*1.05
        assert rows[entry_day]['open'] <= feature['prev_close']*1.05
        stop = max(rows[entry_day]['close']*.93,feature['structure_stop'])
        event_days = {str(a.effective_date) for a in normalized if a.ticker==ticker}
        event_days |= set(official.loc[official.stock_id.astype(str).eq(ticker),'event_date'].astype(str))
        if any(entry_day < d <= exit_day for d in event_days):
            raise ValueError('probe window contains an unaccounted corporate action')
        path = []
        for day in sessions[sessions.index(entry_day)+1:sessions.index(exit_day)+1]:
            bar = rows[day]
            f = TradingPlanR1._features(features_owner,prices,ticker,day)
            reason = TradingPlanR1._close_exit_reason(features_owner,bar,f)
            path.append(dict(day=day,raw_open=bar['open'],raw_low=bar['low'],raw_close=bar['close'],
                             sma20=f['sma20'],stop=stop,stop_triggered=bar['low']<=stop,close_exit=reason))
            if day < exit_day:
                assert bar['low'] > stop
                assert not reason or (name=='sma20_next_open' and day==signal_day)
        portfolio, service, replay = context(ticker)
        sizing = service.sizing_price(ticker=ticker,session_date=entry_day,side='buy',field='close',signal=signal)
        assert sizing.availability is ExecutionAvailability.EXECUTABLE
        unit_cost = sizing.price*(1+COMMISSION+SLIPPAGE)
        quantity = math.floor(min(1_000_000*.07,1_000_000*.25)/unit_cost)
        assert quantity*unit_cost <= 70000 < (quantity+1)*unit_cost
        buy, buy_settle, buy_due = trade(service,ticker=ticker,day=entry_day,side='buy',
                                       quantity=quantity,case=name,field='close')
        replay.settle(buy_settle,buy_due)
        assert portfolio.positions.positions[ticker].quantity == quantity
        if name=='raw_stop':
            observation = service.stop_observation(ticker=ticker,session_date=exit_day,side='sell')
            assert observation.price <= stop
            sell, sell_settle, sell_due = trade(service,ticker=ticker,day=exit_day,side='sell',
                                                quantity=quantity,case=name,stop=stop)
            assert sell.fill.price == min(rows[exit_day]['open'],stop)
        else:
            assert signal_day == sessions[sessions.index(exit_day)-1]
            assert path[-2]['close_exit']=='sma20_next_open'
            assert rows[exit_day]['low'] > stop
            sell, sell_settle, sell_due = trade(service,ticker=ticker,day=exit_day,side='sell',
                                                quantity=quantity,case=name)
            assert sell.fill.price == rows[exit_day]['open']
        entry_cash = buy.fill.price*quantity+buy.fill.fees
        exit_cash = sell.fill.price*quantity-sell.fill.fees
        before_settle = portfolio.cash.settled_cash
        assert math.isclose(before_settle,1_000_000-entry_cash,abs_tol=1e-8)
        assert math.isclose(portfolio.cash.pending_receivables,exit_cash,abs_tol=1e-8)
        replay.settle(sell_settle,sell_due)
        assert portfolio.positions.positions[ticker].quantity == 0
        assert portfolio.cash.pending_receivables == portfolio.cash.pending_payables == 0
        assert math.isclose(portfolio.cash.settled_cash-1_000_000,exit_cash-entry_cash,abs_tol=1e-8)
        cases.append(dict(case=name,stock=ticker,entry_day=entry_day,signal_day=signal_day,exit_day=exit_day,
            s1_eligibility=True,entry_feature=feature,stop=stop,budget=70000,quantity=quantity,
            buy=asdict(buy.fill),sell=asdict(sell.fill),entry_cash=entry_cash,exit_cash=exit_cash,
            sell_settlement=sell_due,pre_settlement_cash=before_settle,final_cash=portfolio.cash.settled_cash,
            pnl=exit_cash-entry_cash,path=path,
            fill_scope='RAW OHLC stop-level simulation recorded at EOD observation; no intraday execution print' if name=='raw_stop'
                       else 'first SMA20 close breach, following source-session RAW open'))

    # Source-normalized cash entitlement over a controlled, actually bought holding.
    action = next(a for a in normalized if a.ticker=='2330' and str(a.effective_date)=='2016-06-27')
    portfolio, service, replay = context('2330')
    buy, settle_id, due = trade(service,ticker='2330',day='2016-06-23',side='buy',quantity=1000,case='normalized_cash')
    assert due <= datetime(2016,6,27,9)
    replay.settle(settle_id,due)
    cash_before = portfolio.cash.settled_cash
    entitlement = replay.apply_normalized_action(action,applied_at=datetime(2016,6,27,9))
    assert entitlement.amount==6000 and portfolio.cash.pending_receivables==6000
    assert portfolio.cash.settled_cash == cash_before
    failed = []
    for label, operation in [
            ('duplicate_accrual',lambda:replay.apply_normalized_action(action,applied_at=datetime(2016,6,27,9))),
            ('early_payment',lambda:replay.pay_cash_dividend(entitlement.event_id,datetime(2016,7,20)))]:
        try: operation()
        except ValueError: failed.append(label)
        else: raise AssertionError('normalized event accepted invalid replay/payment')
        assert portfolio.cash.settled_cash==cash_before and portfolio.cash.pending_receivables==6000
    replay.pay_cash_dividend(entitlement.event_id,action.payment_at)
    assert portfolio.cash.settled_cash==cash_before+6000 and portfolio.cash.pending_receivables==0
    try: replay.pay_cash_dividend(entitlement.event_id,action.payment_at)
    except KeyError: failed.append('duplicate_payment')
    else: raise AssertionError('duplicate normalized payment accepted')
    source_row = {key:None if pd.isna(value) else value
                  for key,value in dividend.iloc[action.source_row].to_dict().items()}
    normalized_case = dict(action=asdict(action),source_row=source_row,
        controlled_quantity=1000,buy=asdict(buy.fill),cash_before=cash_before,
        entitlement=asdict(entitlement),cash_after_payment=portfolio.cash.settled_cash,rejected=failed,
        scope='common canonical replay boundary; not a complete S3/E1 wiring acceptance')

    # Attempt all three actual late announcements against held RAW positions.
    unsafe_cases = []
    for action in sorted([a for a in normalized if a.known_at and a.known_at.date()>a.effective_date
                          and 2016<=a.effective_date.year<=2021],key=lambda a:a.ticker):
        day = str(action.effective_date)
        entry = sessions[sessions.index(day)-1]
        portfolio, service, replay = context(action.ticker)
        buy, settle_id, due = trade(service,ticker=action.ticker,day=entry,side='buy',quantity=100,
                                   case='pit:'+action.ticker,field='close')
        before = (portfolio.cash.settled_cash,portfolio.cash.pending_receivables,
                  portfolio.cash.pending_payables,portfolio.positions.positions[action.ticker].quantity)
        try: replay.apply_normalized_action(action,applied_at=datetime.fromisoformat(day+'T09:00:00'))
        except ValueError as error:
            assert 'point-in-time' in str(error)
        else: raise AssertionError('late source action accepted against actual holding')
        after = (portfolio.cash.settled_cash,portfolio.cash.pending_receivables,
                 portfolio.cash.pending_payables,portfolio.positions.positions[action.ticker].quantity)
        assert before == after
        assert not portfolio.corporate_actions.dividend_receivables
        assert not portfolio.corporate_actions.share_mutations
        unsafe_cases.append(dict(action=asdict(action),entry_day=entry,buy=asdict(buy.fill),
                                 account_before=before,account_after=after,rejected_before_ca_mutation=True))
    assert len(unsafe_cases)==3
    result = dict(schema_version='real_process_cases_v1',base_sha='19e1b909c6dcacba69ffe7409708f62595a70f48',
        source_inputs=evidence,s1_panel_sha256=panel_sha,cases=cases,normalized_cash=normalized_case,
        pit_rejections=unsafe_cases,
        scope='bounded true-data canonical process cases; not four cells or full E1',
        checks={name:'EXERCISED_CASE_ONLY' for name in ['sizing_raw','stop_observation_raw','exit_raw',
                    'normalized_ca_view_active','pit_unsafe_ca_excluded']},
        remaining=['Full S3 production wiring/restore/replay acceptance remains pending.',
                   'Terminal lifecycle/final rights, other nine official events and fractions unresolved.',
                   'Long-horizon E1 canonical run not executed.'],
        accounting_gate_passed=False,four_cells_executed=False,workflow_dispatch_count=0)
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n')
    return result


if __name__ == "__main__":
    main()
