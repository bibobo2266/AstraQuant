"""Run the real diagnostic orchestration against a canonical engineering fixture.

Only the external approved-source loader/population boundary and Git metadata
are replaced. Trading, checkpoints, accounting, exports and metrics are real.
This does not attest the availability or correctness of real A/B source files.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import astraquant.research.trading_plan_r1_s3 as s3
from test_trading_plan_r1_s3 import bundle


METRICS = {
    'net_win_rate', 'avg_win', 'avg_loss', 'payoff_ratio', 'expectancy',
    'median_holding_sessions', 'capital_occupied_position_days', 'closed_count',
}


def runner_fixture(tmp_path, monkeypatch, tail, round_name):
    if isinstance(tail, str):
        from test_s3_normalized_restore import _normalized_bundle, _refresh
        root, days = _normalized_bundle(tmp_path, 'cash')
        if tail=='small_loss':
            dividend=root/'source/fundamentals/dividend.parquet'
            frame=pd.read_parquet(dividend);frame['CashEarningsDistribution']=5.
            frame.to_parquet(dividend,index=False);_refresh(root, [])
    else:
        root, days = bundle(tmp_path, tail=tail)
    inputs = s3.S3Inputs.open_engineering_fixture(root, 'manifest.json', 'receipt.json')
    scope = [str(d.date()) for d in days[80:]]
    # The loader returns genuine independently verified engineering inputs to
    # the real batch engine. The runner's fixed production count assertions
    # receive only a boundary stand-in; no synthetic production gate is issued.
    population = SimpleNamespace(
        _panel_keys=[('', str(i)) for i in range(1916)],
        _bars=pd.DataFrame({'stock': [str(i) for i in range(1814 if round_name == 'A' else 1835)]}),
        binding_id=inputs.binding_id,
    )
    old = tmp_path/'AstraQuant-full/results/trading_plan_r1/accounting_export_37769333701/s3_wiring_v5'
    old.mkdir(parents=True)
    calendar = tmp_path/'calendar.parquet'
    pd.DataFrame({'date': scope}).to_parquet(calendar, index=False)
    manifest=json.loads((root/'manifest.json').read_text())
    manifest['files']=[{'role':'raw', 'path':str(calendar.relative_to(tmp_path))}]
    (old/'manifest.json').write_text(json.dumps(manifest))
    (old/'receipt.json').write_text((root/'receipt.json').read_text())
    pd.DataFrame({'stock':['excluded-'+str(i) for i in range(102)]}).to_csv(old/'missing_limit_keys.csv', index=False)
    supplement=tmp_path/'AstraQuant-full/results/trading_plan_r1/limit_supplement_2016_2018/price_limit_supplement_2016_2018.parquet'
    supplement.parent.mkdir(parents=True)
    supplement.write_bytes(b'engineering-boundary-only')
    monkeypatch.setattr(s3, 'DIAGNOSTIC_B_LIMIT_SHA', s3._hash(supplement))
    monkeypatch.setattr(s3.S3Inputs, 'open_accounting_probe', lambda *a: population)
    original = s3.S3BatchTradingPlanR1
    class FixtureBatch(original):
        def __init__(self, **kwargs):
            if kwargs['inputs'] is population:
                kwargs['inputs']=inputs
            super().__init__(**kwargs)
        def remaining_sessions(self):
            return [d for d in super().remaining_sessions() if d in scope]
    monkeypatch.setattr(s3, 'S3BatchTradingPlanR1', FixtureBatch)
    import subprocess
    monkeypatch.setattr(subprocess, 'check_output', lambda args, **kw: '' if 'diff' in args else 'fixture-program-sha')
    path=Path(__file__).resolve().parents[1]/'scripts/source_accounting_smoke_replay.py'
    spec=importlib.util.spec_from_file_location('diagnostic_runner_fixture', path)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    return runner, tmp_path/'output', scope, FixtureBatch


@pytest.mark.parametrize('round_name', ['A','B'])
def test_runner_final_day_four_cells_eight_metrics_and_resume(tmp_path, monkeypatch, round_name):
    runner, output, scope, engine = runner_fixture(tmp_path, monkeypatch, (104.,101.,99.), round_name)
    status=runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output, round_name=round_name)
    assert len(status['cells'])==4
    for cell, state in status['cells'].items():
        assert state['status']=='COMPLETE_DIAGNOSTIC_PENDING_REVIEW', state
        assert state['current_date']==scope[-1] and state['completed']==len(scope)
        rows=json.loads((output/cell/'diagnostic_metrics.json').read_text())
        assert len(rows)==1 and METRICS <= rows[0].keys()
        assert rows[0]['closed_count']==1 and rows[0]['open_count']==0
        assert rows[0]['net_win_rate']==0 and rows[0]['avg_loss']>.01
        assert (output/cell/'tables/s3_fills.csv').exists()
        assert not (output/cell/'error.json').exists()
    before={c:(output/c/'checkpoint.json').read_bytes() for c in status['cells']}
    def no_repeat(*a, **kw):
        raise AssertionError('completed trading day was replayed')
    monkeypatch.setattr(engine, 'prepare', no_repeat)
    monkeypatch.setattr(engine, 'reconcile_session', no_repeat)
    # Simulate lost final exports after a successfully saved final-day checkpoint.
    for c in status['cells']:
        (output/c/'diagnostic_metrics.json').unlink()
    resumed=runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output, round_name=round_name)
    assert resumed['execution_id']==status['execution_id']
    for c, state in resumed['cells'].items():
        assert state['resumed'] and state['status']=='COMPLETE_DIAGNOSTIC_PENDING_REVIEW', state
        assert (output/c/'checkpoint.json').read_bytes()==before[c]
        assert (output/c/'diagnostic_metrics.json').exists()


@pytest.mark.parametrize('tail,flag', [('small_loss', True), ('winner', True), ((104.,105.,106.), False)])
def test_runner_threshold_and_open_positions(tmp_path, monkeypatch, tail, flag):
    runner, output, scope, _=runner_fixture(tmp_path, monkeypatch, tail, 'A')
    status=runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output)
    first=status['cells']['A1']
    row=json.loads((output/'A1/diagnostic_metrics.json').read_text())[0]
    assert METRICS <= row.keys()
    if flag:
        assert first['status']=='STOP_THRESHOLD_LEDGER_REVIEW', first
        assert row['net_win_rate']>.7 or row['avg_loss']<.01
        assert all(s['status']=='QUEUED' for c,s in status['cells'].items() if c!='A1')
    else:
        assert first['status']=='COMPLETE_DIAGNOSTIC_PENDING_REVIEW', first
        assert row['open_count']==1 and row['closed_count']==0
        assert row['net_win_rate'] is None and row['avg_loss'] is None
        assert len(pd.read_csv(output/'A1/open_positions.csv'))==1
