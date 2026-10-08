import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from astraquant.portfolio.reviewed_ca import ReviewedCA
from astraquant.research.trading_plan_r1_s3 import S3Inputs, S3TradingPlanR1, _hash, _digest
from test_trading_plan_r1_s3 import bundle

PROBE = Path(__file__).resolve().parents[1] / 'results/trading_plan_r1/accounting_export_37769333701/official_probe_v1'


def setup(tmp_path, *, fractional=False):
    root, _ = bundle(tmp_path, tail=(104., 140., 140.))
    days = list(pd.bdate_range(end='2020-10-14', periods=81)) + [pd.Timestamp('2020-10-26'), pd.Timestamp('2020-10-29')]
    for path in root.rglob('*.parquet'):
        frame = pd.read_parquet(path).reset_index()
        frame['date'] = days
        for col in ['stock', 'stock_id']:
            if col in frame: frame[col] = '1315'
        if 'open' in frame:
            for col in ['open', 'close', 'max', 'min']: frame[col] *= 52.7 / 104
        if path.name == 'panel.parquet': frame = frame.set_index(['date', 'stock'])
        frame.to_parquet(path, index=path.name == 'panel.parquet')
    events = root/'source/reference/corporate_actions_official.csv'
    pd.DataFrame([dict(stock_id='1315', event_date='2020-10-26',event_type='capital_reduction')]).to_csv(events,index=False)
    shutil.copytree(PROBE, root/'overlay')
    manifest = json.loads((root/'manifest.json').read_text())
    for entry in manifest['files']: entry['sha256'] = _hash(root/entry['path'])
    manifest['files'].append(dict(path='overlay/event_overlay_v1.json',role='reviewed_ca_overlay',sha256=_hash(root/'overlay/event_overlay_v1.json')))
    (root/'manifest.json').write_text(json.dumps(manifest))
    receipt=json.loads((root/'receipt.json').read_text());receipt['input_digest']=_digest(manifest)
    (root/'receipt.json').write_text(json.dumps(receipt))
    inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    qty=1001 if fractional else 1000
    e=S3TradingPlanR1(inputs=inputs,run_id='ca-engineering',entry_mode='close',exit_mode='sma20',initial_cash=52.7*1.002855*(qty+.1)/.07)
    e.prepare(days[80]);e.reconcile_session(days[80],observed_at=days[80])
    assert e.positions['1315'].quantity==qty
    return root,days,e


def test_actual_s3_ca_receivable_payment_stop_and_restore(tmp_path):
    root,days,e=setup(tmp_path)
    stop=e.positions['1315'].stop_price
    e.prepare(days[81]);e.reconcile_session(days[81],observed_at=days[81])
    assert not e.frozen
    assert e.positions['1315'].quantity == 700
    assert e.canonical.portfolio.cash.pending_receivables == 3000
    assert e.positions['1315'].stop_price == pytest.approx((stop-3)/.7)
    available=e._available_cash()
    state=tmp_path/'ca-state.json';e.save(state)
    restored=S3TradingPlanR1.load(state,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))
    for run in [e,restored]:
        run.prepare(days[81]);run.reconcile_session(days[81],observed_at=days[81])
        assert run.positions['1315'].quantity == 700
        assert run.canonical.portfolio.cash.pending_receivables == 3000
        run.prepare(days[82]);run.reconcile_session(days[82],observed_at=days[82])
        assert run._available_cash() == pytest.approx(available+3000)
        assert run.canonical.portfolio.cash.pending_receivables == 0
        run.prepare(days[82]);run.reconcile_session(days[82],observed_at=days[82])
        assert run._available_cash() == pytest.approx(available+3000)
    assert restored.journal == e.journal


def test_fractional_path_stops_before_any_ca_mutation(tmp_path):
    _,days,e=setup(tmp_path,fractional=True)
    e.prepare(days[81]);e.reconcile_session(days[81],observed_at=days[81])
    assert e.frozen
    assert not e.canonical.portfolio.corporate_actions.share_mutations
    assert not e.canonical.portfolio.corporate_actions.cash_entitlement_receivables
    assert e.canonical.portfolio.positions.positions['1315'].quantity == 1001


@pytest.mark.parametrize('ticker,day',[('1316','2017-01-24'),('4550','2016-09-12'),('1315','2020-10-27')])
def test_incomplete_or_wrong_key_rejected(tmp_path,ticker,day):
    _,_,e=setup(tmp_path)
    with pytest.raises(ValueError,match='complete reviewed'):
        e.inputs.reviewed_ca.apply(portfolio=e.canonical.portfolio,ticker=ticker,day=day,stop_price=49.)
    assert not e.canonical.portfolio.corporate_actions.share_mutations


def test_changed_original_rejected_before_account_mutation(tmp_path):
    root,_,e=setup(tmp_path)
    path=root/'overlay/originals/tahhsin_board20200915.pdf'
    path.write_bytes(path.read_bytes()+b'x')
    with pytest.raises(ValueError,match='physical evidence'):
        e.inputs.verify()
    assert not e.canonical.portfolio.corporate_actions.share_mutations


def test_bound_accounting_implementation_cannot_be_removed(tmp_path):
    _,_,e=setup(tmp_path)
    e.inputs.reviewed_ca=None
    with pytest.raises(ValueError,match='bound corporate-action'):
        e.inputs.verify()


def test_position_replay_marker_rejects_before_cash_accrual(tmp_path):
    _,_,e=setup(tmp_path)
    action=e.inputs.reviewed_ca.resolve('1315','2020-10-26')
    e.canonical.portfolio.positions.applied_share_mutation_ids.add(action.event.event_id)
    with pytest.raises(ValueError,match='duplicate'):
        e.inputs.reviewed_ca.apply(portfolio=e.canonical.portfolio,ticker='1315',day='2020-10-26',stop_price=49.)
    assert not e.canonical.portfolio.corporate_actions.cash_entitlement_receivables
    assert e.canonical.portfolio.cash.pending_receivables==0


@pytest.mark.parametrize('case',['stop','payment'])
def test_restore_rejects_changed_stop_or_early_payment(tmp_path,case):
    root,days,e=setup(tmp_path)
    for day in days[81:]:
        e.prepare(day);e.reconcile_session(day,observed_at=day)
    path=tmp_path/'state.json';e.save(path);state=json.loads(path.read_text())
    if case=='stop':
        next(r for r in state['journal'] if r['kind']=='reviewed_ca')['old_stop']+=1
    else:
        next(r for r in state['journal'] if r['kind']=='reviewed_ca_payment')['day']='2020-10-28'
    state.pop('state_digest');state['state_digest']=_digest(state);path.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='corporate-action'):
        S3TradingPlanR1.load(path,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))
