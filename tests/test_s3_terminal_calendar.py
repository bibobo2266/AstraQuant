"""Official settlement tail fixes maturity without extending E1 trading."""
import json
from pathlib import Path
import pandas as pd
import pytest
import astraquant.research.trading_plan_r1_s3 as s3
from astraquant.research.e1_settlement_calendar import terminal_due,verified_tail,PROOF_SHA
from test_trading_plan_r1_s3 import bundle

PERIOD={'epoch':'E1','start':'2016-01-04','end':'2021-12-31'}


def test_official_tail_exact_maturity_and_no_unknown_fallback():
    proof=verified_tail()
    assert proof['tail_sessions']==['2022-01-03','2022-01-04']
    for day,due in [('2021-12-29','2022-01-03'),('2021-12-30','2022-01-04')]:
        date,provenance=terminal_due(['2021-12-29','2021-12-30'],day,PERIOD)
        assert date==due and provenance['proof_sha256']==PROOF_SHA
    for sessions,day in [(['2020-12-30'],'2020-12-30'),(['2021-12-30'],'2022-01-03')]:
        with pytest.raises(ValueError,match='outside authorized'):
            terminal_due(sessions,day,PERIOD)


def test_terminal_buy_pending_T2_full_vs_checkpoint_resume_all_ledgers_equal(tmp_path,monkeypatch):
    root,original=bundle(tmp_path,tail=(100.,104.,105.))
    days=pd.bdate_range(end='2021-12-30',periods=len(original))
    mapping=dict(zip(original,days))
    manifest=json.loads((root/'manifest.json').read_text())
    for item in manifest['files']:
        path=root/item['path']
        if path.suffix=='.parquet':
            frame=pd.read_parquet(path)
            indexed='date' not in frame.columns
            if indexed:frame=frame.reset_index()
            for column in ['date','available_date']:
                if column in frame:frame[column]=pd.to_datetime(frame[column]).map(mapping)
            if indexed:frame=frame.set_index(['date','stock'])
            frame.to_parquet(path)
        item['sha256']=s3._hash(path)
    (root/'manifest.json').write_text(json.dumps(manifest))
    receipt=json.loads((root/'receipt.json').read_text());receipt['input_digest']=s3._digest(manifest)
    (root/'receipt.json').write_text(json.dumps(receipt))
    inputs=s3.S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    original_due=s3.S3TradingPlanR1._settlement_due
    def strict_terminal(self,day):
        # Explicit engineering boundary: exercise the real official resolver,
        # rather than the fixture-only generic business-day fallback.
        if self.sessions.index(day)+2>=len(self.sessions):
            return terminal_due(self.sessions,day,self.inputs.manifest['period'])
        return original_due(self,day)
    monkeypatch.setattr(s3.S3TradingPlanR1,'_settlement_due',strict_terminal)
    full=s3.S3BatchTradingPlanR1(inputs=inputs,run_id='terminal-parity',entry_mode='next_open',exit_mode='sma20')
    for day in days[80:82]:
        label=str(day.date());full.prepare(label);full.reconcile_session(label,observed_at=label)
    before=tmp_path/'checkpoint.json';full.save_checkpoint(before)
    saved=before.read_bytes()
    resumed=s3.S3BatchTradingPlanR1.load_checkpoint(before,inputs=inputs)
    assert list(resumed.remaining_sessions())==['2021-12-30']
    for engine in (full,resumed):
        engine.prepare('2021-12-30');engine.reconcile_session('2021-12-30',observed_at='2021-12-30')
        engine.validate_tables();engine._check_accounts()
        assert engine.completed[-1]=='2021-12-30'
        assert engine.sessions[-1]=='2021-12-30' and not engine.remaining_sessions()
        pending=engine.canonical.portfolio.settlements.pending
        assert len(pending)==1
        assert next(iter(pending.values())).due_at.isoformat().startswith('2022-01-04')
        assert engine.canonical.portfolio.cash.pending_payables>0
        assert not any(event['kind']=='settle' for event in engine.journal)
    assert before.read_bytes()==saved
    for name,engine in [('full',full),('resumed',resumed)]:
        engine.save(tmp_path/(name+'.json'));engine.export_tables(tmp_path/name)
    assert (tmp_path/'full.json').read_bytes()==(tmp_path/'resumed.json').read_bytes()
    for path in (tmp_path/'full').glob('*.csv'):
        assert path.read_bytes()==(tmp_path/'resumed'/path.name).read_bytes()
    state=json.loads((tmp_path/'full.json').read_text())
    assert state['settlement_calendar']['proof_sha256']==PROOF_SHA
    restored=s3.S3BatchTradingPlanR1.load(tmp_path/'full.json',inputs=inputs)
    assert restored.completed==full.completed
    state['settlement_calendar']['proof_sha256']='0'*64
    state['state_digest']=s3._digest({k:v for k,v in state.items() if k!='state_digest'})
    (tmp_path/'tampered.json').write_text(json.dumps(state))
    with pytest.raises(ValueError,match='provenance mismatch'):
        s3.S3BatchTradingPlanR1.load(tmp_path/'tampered.json',inputs=inputs)
