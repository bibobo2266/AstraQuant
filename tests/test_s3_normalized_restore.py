"""Engineering S3 E2E; no real-source receipt or performance approval."""
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd
import pytest

from astraquant.research.trading_plan_r1_s3 import S3Inputs, S3TradingPlanR1, _digest, _hash
from test_trading_plan_r1_s3 import bundle, filled


def _refresh(root, additions):
    m=json.loads((root/'manifest.json').read_text())
    for path,role in additions:
        m['files'].append(dict(path=str(path.relative_to(root)),role=role,sha256=_hash(path)))
    for entry in m['files']: entry['sha256']=_hash(root/entry['path'])
    (root/'manifest.json').write_text(json.dumps(m))
    receipt=json.loads((root/'receipt.json').read_text());receipt['input_digest']=_digest(m)
    (root/'receipt.json').write_text(json.dumps(receipt))


def _normalized_bundle(tmp_path,kind='cash',*,late=False,unknown_payment=False,fraction=False):
    root,days=bundle(tmp_path,tail=(104.,105.,106.,100.,99.,99.,99.,99.))
    rows=[]
    def row(index,cash,stock):
        return dict(stock_id='1101',CashEarningsDistribution=cash,CashStatutorySurplus=0.,
            StockEarningsDistribution=stock,StockStatutorySurplus=0.,
            CashExDividendTradingDate=str(days[index].date()) if cash else '',
            StockExDividendTradingDate=str(days[index].date()) if stock else '',
            CashDividendPaymentDate='' if unknown_payment else str(days[85].date()),
            AnnouncementDate=str(days[index+1 if late else 79].date()),AnnouncementTime='15:00:00')
    if kind=='cash': rows=[row(81,6.,0.)]
    elif kind=='stock':rows=[row(81,0.,.003 if fraction else 1.)]
    elif kind=='combined':rows=[row(81,6.,.003 if fraction else 1.)]
    elif kind=='chain':rows=[row(81,6.,0.),row(82,0.,1.),row(83,2.,0.)]
    (root/'source/fundamentals').mkdir()
    path=root/'source/fundamentals/dividend.parquet';pd.DataFrame(rows).to_parquet(path,index=False)
    _refresh(root,[(path,'dividend')])
    return root,days


def _engine(root):
    inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    # Make the 7% execution exactly 1000 shares, to isolate integral CA accounting.
    initial_cash=104*1.002855*1000.1/.07
    return S3TradingPlanR1(inputs=inputs,run_id='normalized-engineering',entry_mode='close',
                         exit_mode='sma20',initial_cash=initial_cash)


def _step(e,day):
    e.prepare(day);e.reconcile_session(day,observed_at=day)


def _restore(e,root,path):
    e.save(path)
    return S3TradingPlanR1.load(path,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))


@pytest.mark.parametrize('kind',['cash','stock','combined','chain'])
def test_s3_normalized_source_accounting_restore_and_csv(tmp_path,kind):
    root,days=_normalized_bundle(tmp_path,kind)
    e=_engine(root);_step(e,days[80]);assert e.positions['1101'].quantity==1000
    _step(e,days[81]);restored=_restore(e,root,tmp_path/'pending.json')
    # Same-day prepare/reconcile after loading must not duplicate an event.
    _step(restored,days[81]);assert restored.journal==e.journal
    for day in days[82:85]:
        _step(e,day);_step(restored,day)
    assert len(filled(e,'sell'))==1
    sell=filled(e,'sell').iloc[0];buy=filled(e,'buy').iloc[0]
    rights={'cash':6000,'stock':0,'combined':6000,'chain':8200}[kind]
    assert sell.pnl==pytest.approx(sell.cash_flow+buy.cash_flow+rights)
    # Closed economics include vested rights even before the payment date.
    before_payment=_restore(e,root,tmp_path/'closed-before-payment.json')
    cash=before_payment._available_cash()
    _step(e,days[85]);_step(restored,days[85]);_step(before_payment,days[85])
    assert before_payment._available_cash()==pytest.approx(cash+rights)
    after_payment=_restore(e,root,tmp_path/'closed-after-payment.json')
    _step(after_payment,days[85])
    assert not after_payment.canonical.portfolio.corporate_actions.dividend_receivables
    for day in days[86:]:
        for run in [e,restored,before_payment,after_payment]: _step(run,day)
    assert after_payment.journal==e.journal==restored.journal==before_payment.journal
    assert after_payment.canonical.portfolio.cash.pending_receivables==0
    for name,table in e.ledger.tables().items():
        pd.testing.assert_frame_equal(table,after_payment.ledger.table(name))
    e.export_tables(tmp_path/'csv');e.read_tables(tmp_path/'csv')
    with pytest.raises(ValueError,match='engineering fixtures'):
        e.metrics()
    assert e.cell_status()['status']=='PARTIAL'


@pytest.mark.parametrize('failure',['late','payment','fraction'])
def test_s3_unknown_normalized_terms_freeze_before_bundle_mutation(tmp_path,failure):
    root,days=_normalized_bundle(tmp_path,'combined',late=failure=='late',
        unknown_payment=failure=='payment',fraction=failure=='fraction')
    e=_engine(root);_step(e,days[80]);before=e.cash
    _step(e,days[81]);assert e.frozen
    assert e.positions['1101'].quantity==1000
    assert e.cash==before
    assert not e.canonical.portfolio.corporate_actions.dividend_receivables
    assert not e.canonical.portfolio.corporate_actions.share_mutations
    restored=_restore(e,root,tmp_path/'frozen.json')
    assert restored.frozen and restored.cell_status()['status']=='INCOMPLETE'


@pytest.mark.parametrize('field',['cash_receivable','new_stop','new_quantity','source_row','binding','pnl','net_return','payment','amount'])
def test_s3_normalized_tampering_rehashed_state_is_rejected(tmp_path,field):
    root,days=_normalized_bundle(tmp_path,'chain');e=_engine(root)
    for day in days[80:]:_step(e,day)
    path=tmp_path/'state.json';e.save(path);s=json.loads(path.read_text())
    if field in {'pnl','net_return'}:
        next(r for r in s['tables']['fills'] if r['fill'] and r['side']=='sell')[field]+=1
    elif field=='payment':
        next(r for r in s['journal'] if r['kind']=='normalized_ca_payment')['day']=str(days[84].date())
    elif field=='amount':
        next(r for r in s['journal'] if r['kind']=='normalized_ca_payment')['amount']+=1
    else:
        record=next(r for r in s['journal'] if r['kind']=='normalized_ca')
        record[field]=record[field]+1 if field!='binding' else 'wrong'
    s.pop('state_digest');s['state_digest']=_digest(s);path.write_text(json.dumps(s))
    with pytest.raises((ValueError,KeyError)):
        S3TradingPlanR1.load(path,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))


def test_normalized_metadata_replacement_rejected_before_prepare(tmp_path):
    root,days=_normalized_bundle(tmp_path);e=_engine(root)
    action=e.inputs.normalized_ca.actions[0]
    e.inputs.normalized_ca.actions=(replace(action,cash_per_share=1234),)
    with pytest.raises(ValueError,match='changed bound normalized'):_step(e,days[80])
    assert not e.journal


def _terminal_bundle(tmp_path,*,held):
    root,days=bundle(tmp_path,tail=(104.,105.,106.,100.))
    for p in list((root/'source/raw').glob('*.parquet'))+[root/'source/reference/tradability.parquet',root/'supplement.parquet',root/'panel.parquet']:
        f=pd.read_parquet(p).reset_index();col='stock' if 'stock' in f else 'stock_id'
        f[col]='6286'
        clone=f.copy();clone[col]='5305'
        if 'eligibility' in f:
            f['eligibility']=held;clone['eligibility']=False
        f=pd.concat([f,clone],ignore_index=True)
        if p.name=='panel.parquet': f=f.set_index(['date','stock'])
        f.to_parquet(p,index=p.name=='panel.parquet')
    terminal=root/'terminal.csv'
    source=Path(__file__).resolve().parents[1]/'data/research/terminal_events.csv'
    terms=pd.read_csv(source,dtype={'ticker':str});terms=terms[terms.ticker.isin(['6286','5305'])].copy()
    # Synthetic lifecycle coordinates only; the unresolved terms are never applied.
    terms['last_trading_date']=str(days[80].date());terms['suspension_from']=str(days[81].date())
    terms['effective_date']=str(days[82].date());terms['payment_date']=str(days[83].date())
    terms.to_csv(terminal,index=False);_refresh(root,[(terminal,'terminal')])
    return root,days


@pytest.mark.parametrize('held',[False,True])
def test_s3_retains_both_terminal_stocks_tracks_exposure_and_restores(tmp_path,held):
    root,days=_terminal_bundle(tmp_path,held=held);e=_engine(root)
    assert set(e.inputs._bars.stock)=={'6286','5305'}
    _step(e,days[80]);_step(e,days[81])
    status=e.cell_status()
    assert status['unresolved_terminal_tickers']==['5305','6286']
    assert not status['full_e1_sessions_covered']
    assert status['status']==('INCOMPLETE' if held else 'PARTIAL')
    assert bool(status['held_crossings'])==held
    assert not e.canonical.portfolio.corporate_actions.cash_entitlement_receivables
    assert not len(filled(e,'sell'))
    restored=_restore(e,root,tmp_path/'terminal.json')
    assert restored.cell_status()==status
    _step(restored,days[81]);assert restored.journal==e.journal
    if held:
        path=tmp_path/'terminal.json';s=json.loads(path.read_text())
        observation=next(r for r in s['journal'] if r['kind']=='terminal_observation' and r['held_quantity']>0)
        observation['held_quantity']=0;s.pop('state_digest');s['state_digest']=_digest(s);path.write_text(json.dumps(s))
        with pytest.raises(ValueError,match='terminal exposure'):
            S3TradingPlanR1.load(path,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))


def test_completed_fixture_without_terminal_holding_has_explicit_full_coverage(tmp_path):
    root,days=_terminal_bundle(tmp_path,held=False);e=_engine(root)
    for day in days:_step(e,day)
    status=e.cell_status()
    assert status['status']=='COMPLETE_UNAFFECTED'
    assert status['full_e1_sessions_covered'] and not status['held_crossings']
    assert set(e.inputs._bars.stock)=={'6286','5305'}
    # Engineering completeness never unlocks formal performance.
    with pytest.raises(ValueError,match='engineering fixtures'):e.metrics()


@pytest.mark.parametrize('metadata',['normalized','terminal','official'])
def test_s3_accounting_metadata_stays_bound_before_mutation(tmp_path,metadata):
    if metadata=='terminal': root,days=_terminal_bundle(tmp_path,held=False)
    else:root,days=_normalized_bundle(tmp_path)
    e=_engine(root)
    if metadata=='normalized':e.inputs.normalized_ca=None
    elif metadata=='terminal':
        first,*rest=e.inputs.terminal_records
        e.inputs.terminal_records=(replace(first,suspension_from=pd.Timestamp('2021-12-31').date()),*rest)
    else:e.inputs.official_event_types[('2020-01-02','1101')]=frozenset({'other'})
    with pytest.raises(ValueError):e.prepare(days[80])
    assert not e.journal and not e.positions


@pytest.mark.parametrize('removed',['payment','terminal_observation'])
def test_missing_replay_journal_entries_are_not_accepted(tmp_path,removed):
    if removed=='payment':
        root,days=_normalized_bundle(tmp_path,'chain');e=_engine(root)
        for day in days[80:]:_step(e,day)
    else:
        root,days=_terminal_bundle(tmp_path,held=True);e=_engine(root)
        for day in days[80:82]:_step(e,day)
    path=tmp_path/'state.json';e.save(path);s=json.loads(path.read_text())
    kind='normalized_ca_payment' if removed=='payment' else 'terminal_observation'
    target=next(r for r in s['journal'] if r['kind']==kind)
    s['journal'].remove(target);s.pop('state_digest');s['state_digest']=_digest(s);path.write_text(json.dumps(s))
    with pytest.raises(ValueError):
        S3TradingPlanR1.load(path,inputs=S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json'))
