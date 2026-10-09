"""Missing event markers and real-event negative controls across pandas modes."""
import json
import pandas as pd
import pytest

from astraquant.execution.fills import NotExecutableError
from astraquant.research.trading_plan_r1 import TradingPlanR1, _has_corporate_event
from astraquant.research.trading_plan_r1_s3 import S3Inputs, S3TradingPlanR1, _digest, _hash
from test_trading_plan_r1_s3 import bundle, engine, filled


@pytest.mark.parametrize('value',[None,float('nan'),pd.NA,pd.NaT,'','  ',False,{}])
def test_missing_event_marker_is_not_an_event(value):
    assert _has_corporate_event(value) is False
    assert TradingPlanR1._bar_problem(dict(open=100,high=101,low=99,close=100,volume=100,
                                          corporate_action=value)) == ''


@pytest.mark.parametrize('value',['source_event_requires_accounting','terminal_terms_unverified',{'event':'cash'}])
def test_real_event_marker_remains_rejected(value):
    assert _has_corporate_event(value) is True
    assert TradingPlanR1._bar_problem(dict(open=100,high=101,low=99,close=100,volume=100,
                                          corporate_action=value)) == 'unsupported_corporate_action'


@pytest.mark.parametrize('infer_string',[False,True])
@pytest.mark.parametrize('mode',['close','next_open'])
def test_missing_source_event_executes_and_replays(tmp_path,infer_string,mode):
    with pd.option_context('future.infer_string',infer_string):
        root,days=bundle(tmp_path,tail=(104.,104.,104.,103.,103.))
        e=engine(root,mode=mode)
        for day in days[80:83]:e.prepare(day);e.reconcile_session(day,observed_at=day)
        assert len(filled(e,'buy'))==1 and not e.frozen
        e.save(tmp_path/'state.json')
        r=S3TradingPlanR1.load(tmp_path/'state.json',inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))
        for run in [e,r]:run.prepare(days[83]);run.reconcile_session(days[83],observed_at=days[83])
        assert r.journal==e.journal and not r.frozen


@pytest.mark.parametrize('infer_string',[False,True])
def test_true_source_event_blocks_fill_under_string_inference(tmp_path,infer_string):
    with pd.option_context('future.infer_string',infer_string):
        root,days=bundle(tmp_path)
        p=root/'source/reference/corporate_actions_official.csv'
        pd.DataFrame([dict(stock_id='1101',event_date=str(days[80].date()),event_type='unresolved_capital_reduction')]).to_csv(p,index=False)
        m=json.loads((root/'manifest.json').read_text())
        next(e for e in m['files'] if e['role']=='events')['sha256']=_hash(p)
        (root/'manifest.json').write_text(json.dumps(m))
        receipt=json.loads((root/'receipt.json').read_text());receipt['input_digest']=_digest(m)
        (root/'receipt.json').write_text(json.dumps(receipt))
        e=engine(root);e.prepare(days[80]);e.reconcile_session(days[80],observed_at=days[80])
        assert len(filled(e,'buy'))==0
        with pytest.raises(NotExecutableError,match='source event requires resolved accounting'):
            e._execute(dict(day=str(days[80].date()),side='buy',stock='1101',id='negative',
                quantity=1,price=104.,cost=.29692,field='close',use='ENTRY',stop_price=None))
        assert not e.canonical.portfolio.positions.positions
        assert e._bound_bars.loc[e._bound_bars.date.eq(days[80]),'corporate_action'].iloc[0]=='source_event_requires_accounting'


def test_probe_route_cannot_be_switched_in_memory(tmp_path):
    root,_=bundle(tmp_path);i=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    i.probe=True
    with pytest.raises(ValueError,match='binding identity'):i.verify()


def test_fixture_bytes_cannot_enter_real_accounting_probe(tmp_path):
    root,_=bundle(tmp_path);m=json.loads((root/'manifest.json').read_text());m['purpose']='s3_accounting_probe'
    (root/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='wrong accepted S1/limit bytes'):
        S3Inputs.open_accounting_probe(root,'manifest.json','receipt.json')


def test_indexed_features_keep_owner_formula_and_all_market_rows(tmp_path):
    root,days=bundle(tmp_path,tail=(104.,101.,99.,99.,99.));e=engine(root)
    prices=e._prices(e._bound_bars)
    assert len(prices)==len(e._bound_bars)
    assert set(prices.stock)==set(e._bound_bars.stock)
    # Add another stock to the comparison frame; its prices must never leak in.
    unindexed=prices.reset_index(drop=True)
    second=unindexed.copy();second['stock']='9999';second['close']=9999.
    combined=pd.concat([unindexed,second],ignore_index=True)
    indexed=combined.set_index(['stock','date'],drop=False)
    indexed.index.names=['_stock_feature_key','_date_feature_key']
    for day in days[79:]:
        day=str(day.date());expected=TradingPlanR1._features(e,combined,'1101',day)
        actual=e._features(indexed,'1101',day)
        for key,value in expected.items():
            if isinstance(value,float):assert actual[key]==pytest.approx(value,nan_ok=True)
            else:assert actual[key]==value
        assert actual['rsi13']==pytest.approx(e._features(combined,'1101',day)['rsi13'],nan_ok=True)
