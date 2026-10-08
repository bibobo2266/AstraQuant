"""Offline engineering fixtures exercise the supported canonical S3 path."""
import json
from dataclasses import fields

import numpy as np
import pandas as pd
import pytest

from astraquant.research.trading_plan_r1 import TradingPlanR1, metrics as legacy_metrics
from astraquant.research.trading_plan_r1_s3 import (
    COMMISSION, LIMIT_REVISION, SOURCE_REVISION, SLIPPAGE, TAX, VERSION,
    S3Inputs, S3TradingPlanR1, _digest, _hash,
)
from astraquant.validation.accounting_gate import AccountingReadiness, PerformanceLockedError


def bundle(tmp_path, *, tail=(104., 101., 99.), buy_blocked=False, rsi_seed=False):
    root = tmp_path / "bundle"
    (root / "source/raw").mkdir(parents=True)
    (root / "source/reference").mkdir()
    days = pd.bdate_range("2020-01-02", periods=80+len(tail))
    closes = [100.] * 80 + list(tail)
    opens = [100.] * 80 + [103.] + list(tail[1:])
    if rsi_seed:
        closes[:59] = [120.] * 59
        opens[:59] = [120.] * 59
    raw = pd.DataFrame(dict(date=days, stock_id="1101", open=opens, close=closes,
                           max=np.maximum(opens, closes)+1, min=np.minimum(opens, closes)-(.01 if rsi_seed else 1),
                           Trading_Volume=100000, market="TWSE"))
    raw_path = root / "source/raw/prices_raw_2020.parquet"
    raw.to_parquet(raw_path,index=False)
    tape = pd.DataFrame(dict(date=days,stock_id="1101",observed_trade=True,valid_ohlc=True,
                            buy_blocked=buy_blocked,sell_blocked=False,reason="BLOCKED_TEST" if buy_blocked else "OBSERVED"))
    tape_path = root / "source/reference/tradability.parquet"
    tape.to_parquet(tape_path,index=False)
    events_path = root / "source/reference/corporate_actions_official.csv"
    pd.DataFrame(columns=["stock_id","event_date","event_type"]).to_csv(events_path,index=False)
    panel_path = root / "panel.parquet"
    panel = pd.DataFrame(dict(date=days,stock="1101",eligibility=True,rs=80.,available_date=days)).set_index(["date","stock"])
    panel.to_parquet(panel_path)
    limits_path = root / "supplement.parquet"
    pd.DataFrame(dict(date=days,stock_id="1101",limit_up=120.,limit_down=80.)).to_parquet(limits_path,index=False)
    paths = [(raw_path,"raw"),(tape_path,"tradability"),(events_path,"events"),(panel_path,"panel"),(limits_path,"supplement")]
    manifest = dict(schema_version=VERSION,purpose="s3_engineering_fixture",source_root="source",
        source_revision=SOURCE_REVISION,limit_revision=LIMIT_REVISION,
        period=dict(epoch="E1",start="2016-01-04",end="2021-12-31"),entry_modes=["close","next_open"],
        exit_modes=["sma20","sma20_or_rsi13_lt50"],
        files=[dict(path=str(p.relative_to(root)),role=role,sha256=_hash(p)) for p,role in paths])
    (root / "manifest.json").write_text(json.dumps(manifest))
    # A fixture audit receipt is input to the real existing validator, not a
    # mocked gate or a production approval. Every check has a failure test.
    receipt=dict(schema_version="s3-accounting-receipt-v1",input_digest=_digest(manifest),
        checks={f.name:True for f in fields(AccountingReadiness)},
        evidence=[dict(kind="offline_fixture",scope="engineering-only canonical lifecycle regression")])
    (root / "receipt.json").write_text(json.dumps(receipt))
    return root, days


def inputs(root):
    return S3Inputs.open_engineering_fixture(root,"manifest.json","receipt.json")


def engine(root, *, mode="close", exit="sma20"):
    return S3TradingPlanR1(inputs=inputs(root),run_id="engineering",entry_mode=mode,exit_mode=exit)


def execute(e, days):
    for day in days[80:]:
        e.prepare(day)
        e.reconcile_session(day,observed_at=day)
    return e


def filled(e,side):
    t=e.ledger.table("fills")
    return t[t.side.eq(side)&t.fill.fillna(False)]


@pytest.mark.parametrize("mode",["close","next_open"])
@pytest.mark.parametrize("exit",["sma20","sma20_or_rsi13_lt50"])
def test_supported_entry_canonical_cost_ledger_and_restore(tmp_path,mode,exit):
    root,days=bundle(tmp_path)
    e=engine(root,mode=mode,exit=exit)
    e.prepare(days[80]); e.reconcile_session(days[80],observed_at=days[80])
    path=tmp_path / "state.json";e.save(path)
    restored=S3TradingPlanR1.load(path,inputs=inputs(root))
    assert restored.ledger.identity==e.ledger.identity
    assert restored.ledger.identity['source_kind']=='s3_engineering_fixture'
    for day in days[81:]:
        e.prepare(day);e.reconcile_session(day,observed_at=day)
        restored.prepare(day);restored.reconcile_session(day,observed_at=day)
    for name,table in e.ledger.tables().items():
        pd.testing.assert_frame_equal(table,restored.ledger.table(name))
        assert table.input_binding.eq(e.inputs.binding_id).all()
        assert table.source_kind.eq('s3_engineering_fixture').all()
    buys=filled(e,'buy');assert len(buys)==1
    buy=buys.iloc[0];expected=104 if mode=='close' else 101
    assert buy.fill_price==expected
    gross=float(buy.fill_price*buy.quantity)
    assert buy.commission==pytest.approx(gross*COMMISSION)
    assert buy.slippage==pytest.approx(gross*SLIPPAGE)
    assert buy.tax==0
    assert buy.quantity==int(70000//(expected*(1+COMMISSION+SLIPPAGE)))
    assert float(buy.cost)==pytest.approx(gross*(COMMISSION+SLIPPAGE))
    assert e.cash==pytest.approx(e.canonical.portfolio.cash.projected_cash)
    assert len(e.positions)<=5
    for sell in filled(e,'sell').itertuples():
        assert sell.tax==pytest.approx(sell.fill_price*sell.quantity*TAX)
    e.export_tables(tmp_path / "csv")
    for name,table in e.read_tables(tmp_path / "csv").items():
        pd.testing.assert_frame_equal(table,e.ledger.table(name))
    with pytest.raises(ValueError,match='engineering fixtures'):
        e.metrics()
    with pytest.raises(ValueError,match='schema mismatch'):
        legacy_metrics(e.ledger.tables())
    from astraquant.research.trading_plan_r1 import SCHEMAS
    old_schema={name:t[list(SCHEMAS[name])] for name,t in e.ledger.tables().items()}
    with pytest.raises(ValueError,match='synthetic R1'):
        legacy_metrics(old_schema)


@pytest.mark.parametrize('check',[f.name for f in fields(AccountingReadiness)])
def test_each_existing_accounting_gate_fails_before_engine_or_fill(tmp_path,check):
    root,_=bundle(tmp_path)
    p=root / 'receipt.json';j=json.loads(p.read_text());j['checks'][check]=False;p.write_text(json.dumps(j))
    with pytest.raises(PerformanceLockedError,match=check):
        engine(root)


@pytest.mark.parametrize('case',['missing_receipt','wrong_receipt_inputs','incomplete_checks','non_boolean_checks',
    'wrong_period','wrong_version','wrong_four_cells','wrong_hash','wrong_source_revision','wrong_limit_revision'])
def test_input_gate_failures(tmp_path,case):
    root,_=bundle(tmp_path);m=root/'manifest.json';r=root/'receipt.json';manifest=json.loads(m.read_text());receipt=json.loads(r.read_text())
    if case=='missing_receipt':r.unlink()
    elif case=='wrong_receipt_inputs':receipt['input_digest']='0'*64
    elif case=='incomplete_checks':receipt['checks'].pop('entry_raw')
    elif case=='non_boolean_checks':receipt['checks']['entry_raw']='True'
    elif case=='wrong_period':manifest['period']['end']='2021-12-30'
    elif case=='wrong_version':manifest['schema_version']='other'
    elif case=='wrong_four_cells':manifest['entry_modes']=['close']
    elif case=='wrong_hash':manifest['files'][0]['sha256']='0'*64
    elif case=='wrong_source_revision':manifest['source_revision']='unaccepted'
    elif case=='wrong_limit_revision':manifest['limit_revision']='unaccepted'
    m.write_text(json.dumps(manifest))
    if case!='missing_receipt':r.write_text(json.dumps(receipt))
    with pytest.raises((ValueError,FileNotFoundError)):
        engine(root)


def test_canonical_raw_gate_rejects_before_fill_and_position(tmp_path):
    root,days=bundle(tmp_path,buy_blocked=True)
    e=execute(engine(root),days)
    assert filled(e,'buy').empty
    assert not e.positions
    assert e.cash==1_000_000
    assert not e.canonical.portfolio.orders.orders
    assert e.ledger.table('decisions').reject_reason.dropna().str.contains('canonical_raw:BLOCKED_TEST').any()


def test_legacy_and_external_input_entries_stay_restricted(tmp_path):
    root,days=bundle(tmp_path);e=engine(root)
    with pytest.raises(ValueError,match='synthetic bars only'):
        TradingPlanR1._prices(e._bound_bars)
    with pytest.raises(ValueError,match='external bars'):
        e.prepare_session(e._bound_bars.copy(),days[80])
    with pytest.raises(ValueError,match='purpose'):
        S3Inputs.open_source(root,'manifest.json','receipt.json')
    assert not e.positions
    assert not e.canonical.portfolio.orders.orders


@pytest.mark.parametrize('field',['version','input_binding','source_kind'])
def test_saved_identity_version_and_binding_reject(tmp_path,field):
    root,days=bundle(tmp_path);e=execute(engine(root),days);p=tmp_path/'state.json';e.save(p);state=json.loads(p.read_text())
    if field=='source_kind':state['identity'][field]='synthetic'
    else:state[field]='wrong'
    state.pop('state_digest');state['state_digest']=_digest(state);p.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='mismatch'):
        S3TradingPlanR1.load(p,inputs=inputs(root))


def test_changed_bound_raw_or_gate_rejects_without_economic_mutation(tmp_path):
    root,days=bundle(tmp_path);e=engine(root);before=e.cash
    (root/'source/raw/prices_raw_2020.parquet').write_bytes(b'changed')
    with pytest.raises(ValueError,match='input hash'):
        e.prepare(days[80])
    assert e.cash==before and not e.positions and not e.canonical.portfolio.orders.orders


def test_rsi_exit_uses_existing_calculation_and_next_session_open(tmp_path):
    root,days=bundle(tmp_path,tail=(104.,103.,102.),rsi_seed=True)
    e=execute(engine(root,exit='sma20_or_rsi13_lt50'),days)
    sales=filled(e,'sell')
    assert len(sales)==1
    sale=sales.iloc[0]
    assert sale.reason=='rsi13_lt50_next_open'
    assert sale.fill_date==str(days[82].date())
    assert sale.fill_price==102
    only_sma=execute(engine(root,exit='sma20'),days)
    assert filled(only_sma,'sell').empty
    assert len(only_sma.positions)==1
    feature=e._features(e._prices(e._bound_bars),'1101',str(days[81].date()))
    assert feature['rsi13']<50 and feature['sma20']<103
    assert e._close_exit_reason({'close':105},{'sma20':100,'rsi13':50})==''


def test_saved_unreconciled_next_open_plan_restores_same_execution(tmp_path):
    root,days=bundle(tmp_path)
    e=engine(root,mode='next_open')
    e.prepare(days[80]);e.reconcile_session(days[80],observed_at=days[80])
    e.prepare(days[81]);p=tmp_path/'pending.json';e.save(p)
    restored=S3TradingPlanR1.load(p,inputs=inputs(root))
    for instance in [e,restored]:
        instance.reconcile_session(days[81],observed_at=days[81])
        instance.prepare(days[82]);instance.reconcile_session(days[82],observed_at=days[82])
    for name,frame in e.ledger.tables().items():
        pd.testing.assert_frame_equal(frame,restored.ledger.table(name))


def test_production_factory_rejects_wrong_accepted_s1_bytes(tmp_path):
    root,_=bundle(tmp_path);m=root/'manifest.json';j=json.loads(m.read_text());j['purpose']='s3_source';m.write_text(json.dumps(j))
    receipt=root/'receipt.json';r=json.loads(receipt.read_text());r['input_digest']=_digest(j);receipt.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='wrong accepted S1/limit bytes'):
        S3Inputs.open_source(root,'manifest.json','receipt.json')


def test_in_memory_prices_or_eligibility_change_cannot_enter(tmp_path):
    root,days=bundle(tmp_path);e=engine(root)
    e._bound_bars.loc[80,'eligible']=False
    with pytest.raises(ValueError,match='changed verified S3'):
        e.prepare(days[80])
    assert not e.positions and not e.canonical.portfolio.orders.orders


def test_receipt_changed_after_binding_is_rejected_before_fill(tmp_path):
    root,days=bundle(tmp_path);e=engine(root)
    receipt=root/'receipt.json';r=json.loads(receipt.read_text());r['checks']['entry_raw']=False;receipt.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='changed input manifest/accounting receipt'):
        e.prepare(days[80])
    assert not e.positions and e.cash==1_000_000


def test_csv_identity_or_missing_table_cannot_be_reported(tmp_path):
    root,days=bundle(tmp_path);e=execute(engine(root),days);tables=e.ledger.tables()
    tables['fills'].loc[0,'source_kind']='synthetic'
    with pytest.raises(ValueError,match='identity/input binding'):
        e.validate_tables(tables)
    with pytest.raises(ValueError,match='exactly four'):
        e.validate_tables({'fills':e.ledger.table('fills')})


def test_source_event_during_hold_is_preserved_as_censored_not_fake_exit(tmp_path):
    root,days=bundle(tmp_path,tail=(104.,104.,104.))
    events=root/'source/reference/corporate_actions_official.csv'
    pd.DataFrame([dict(stock_id='1101',event_date=str(days[81].date()),event_type='cash_dividend')]).to_csv(events,index=False)
    m=root/'manifest.json';j=json.loads(m.read_text());next(x for x in j['files'] if x['role']=='events')['sha256']=_hash(events);m.write_text(json.dumps(j))
    receipt=root/'receipt.json';r=json.loads(receipt.read_text());r['input_digest']=_digest(j);receipt.write_text(json.dumps(r))
    e=execute(engine(root),days)
    assert e.frozen and len(e.positions)==1 and filled(e,'sell').empty
    assert e.ledger.table('fills').truncated.fillna(False).any()
    with pytest.raises(ValueError,match='engineering fixtures'):
        e.metrics()


@pytest.mark.parametrize("missing", ["source/raw/prices_raw_2020.parquet", "source/reference/tradability.parquet"])
def test_missing_actual_raw_or_tradability_stops_before_engine(tmp_path, missing):
    root, _ = bundle(tmp_path)
    (root / missing).unlink()
    with pytest.raises(FileNotFoundError):
        engine(root)


def test_delayed_rsi_exit_retains_trigger_after_save_load(tmp_path):
    root, days = bundle(tmp_path, tail=(104.,103.,102.,101.), rsi_seed=True)
    raw_path = root / "source/raw/prices_raw_2020.parquet"
    raw = pd.read_parquet(raw_path)
    raw.loc[82, ["open", "close", "max", "min"]] = 102.
    raw.to_parquet(raw_path, index=False)
    limits_path = root / "supplement.parquet"
    limits = pd.read_parquet(limits_path)
    limits.loc[82, "limit_down"] = 102.
    limits.to_parquet(limits_path, index=False)
    manifest = json.loads((root / "manifest.json").read_text())
    for entry in manifest["files"]:
        entry["sha256"] = _hash(root / entry["path"])
    (root / "manifest.json").write_text(json.dumps(manifest))
    receipt = json.loads((root / "receipt.json").read_text())
    receipt["input_digest"] = _digest(manifest)
    (root / "receipt.json").write_text(json.dumps(receipt))
    e = engine(root, exit="sma20_or_rsi13_lt50")
    for day in days[80:83]:
        e.prepare(day); e.reconcile_session(day, observed_at=day)
    assert filled(e, "sell").empty and len(e.positions) == 1
    path = tmp_path / "blocked-exit.json"
    e.save(path)
    e = S3TradingPlanR1.load(path, inputs=inputs(root))
    e.prepare(days[83]); e.reconcile_session(days[83], observed_at=days[83])
    sale = filled(e, "sell").iloc[0]
    assert sale.reason == "rsi13_lt50_next_open" and sale.fill_price == 101
    assert sale.fill_date == str(days[83].date())
