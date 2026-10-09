"""Batch executor equivalence, immutable bytes and real restart entry contracts."""
import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astraquant.research.trading_plan_r1_s3 import (
    S3Inputs, S3TradingPlanR1, S3BatchTradingPlanR1, _FEATURE_DTYPE,
    _feature_bytes, _atomic_write,
)
from test_trading_plan_r1_s3 import bundle
from test_s3_normalized_restore import _normalized_bundle


def step(engine, day):
    engine.prepare(day); engine.reconcile_session(day, observed_at=day)


@pytest.mark.parametrize('entry', ['close', 'next_open'])
@pytest.mark.parametrize('exit', ['sma20', 'sma20_or_rsi13_lt50'])
@pytest.mark.parametrize('kind', ['cash', 'stock', 'chain'])
def test_batch_reference_full_state_and_resume_identical(tmp_path, entry, exit, kind):
    root, days = _normalized_bundle(tmp_path, kind)
    inputs = S3Inputs.open_engineering_fixture(root, 'manifest.json', 'receipt.json')
    cash = 104 * 1.002855 * 1000.1 / .07
    kwargs = dict(inputs=inputs, run_id='batch-equivalence', entry_mode=entry, exit_mode=exit, initial_cash=cash)
    old = S3TradingPlanR1(**kwargs); new = S3BatchTradingPlanR1(**kwargs)
    for day in days[80:84]:
        step(old, day); step(new, day)
    new.save(tmp_path/'checkpoint.json')
    restored = S3BatchTradingPlanR1.load(tmp_path/'checkpoint.json', inputs=inputs)
    restored.run_remaining(checkpoint=tmp_path/'resumed.json')
    for day in days[84:]:
        step(old, day); step(new, day)
    for name, engine in [('old', old), ('new', new), ('resumed', restored)]:
        engine.save(tmp_path/f'{name}.json')
    assert (tmp_path/'old.json').read_bytes() == (tmp_path/'new.json').read_bytes() == (tmp_path/'resumed.json').read_bytes()


def test_causal_cache_equals_all_prefixes_and_future_mutations():
    rng = np.random.default_rng(719)
    history = pd.DataFrame({'stock_id': '1101', 'close': rng.uniform(80, 105, 150)})
    history.loc[[0, 32, 71, 120], 'close'] = np.nan
    full = np.frombuffer(_feature_bytes(history), dtype=_FEATURE_DTYPE)
    owner = __import__('astraquant.research.trading_plan_r1', fromlist=['TradingPlanR1']).TradingPlanR1(
        run_id='features', mode='backtest', sessions=pd.bdate_range('2020-01-01', periods=150).strftime('%Y-%m-%d').tolist())
    frame = history.assign(stock='1101', date=owner.sessions)
    from astraquant.research.technical_components import _rsi_value
    for i in range(len(history)):
        expected = owner._features(frame, '1101', owner.sessions[i])
        expected['rsi13'] = float(_rsi_value(panel=history.iloc[:i+1], lookback=13).iloc[-1])
        for key in _FEATURE_DTYPE.names:
            got = full[i][key].item()
            assert got == expected[key] or (pd.isna(got) and pd.isna(expected[key])), (i, key, got, expected[key])
        changed = history.copy(); changed.loc[i+1:, 'close'] = rng.uniform(1, 10000, len(history)-i-1)
        assert _feature_bytes(changed)[:(i+1)*_FEATURE_DTYPE.itemsize] == full[:i+1].tobytes()


def test_snapshot_bytes_aliases_and_no_inner_dataset_hash(tmp_path, monkeypatch):
    root, days = _normalized_bundle(tmp_path, 'cash')
    inputs = S3Inputs.open_engineering_fixture(root, 'manifest.json', 'receipt.json')
    e = S3BatchTradingPlanR1(inputs=inputs, run_id='immutable', entry_mode='close', exit_mode='sma20')
    snap = e._runtime
    with pytest.raises(TypeError): snap.days['wrong'] = b'changed'
    with pytest.raises(TypeError): snap.features['1101'] = b'changed'
    values = np.frombuffer(snap.features['1101'], dtype=_FEATURE_DTYPE)
    with pytest.raises(ValueError): values['sma20'][80] = 1
    with pytest.raises(ValueError): values.setflags(write=True)
    import pyarrow as pa
    raw_bytes = snap.days[str(days[80].date())]
    assert memoryview(raw_bytes).readonly and not pa.py_buffer(raw_bytes).is_mutable
    raw_alias = np.frombuffer(raw_bytes, dtype=np.uint8)
    with pytest.raises(ValueError): raw_alias[0] = 0
    with pytest.raises(ValueError): raw_alias.setflags(write=True)
    with pytest.raises(TypeError): snap.stocks['1101'] = b'changed RAW'
    with pytest.raises(ValueError, match='unverified'):
        S3BatchTradingPlanR1(inputs=inputs, run_id='wrong-cache', entry_mode='close', exit_mode='sma20',
            snapshot=replace(snap, features={}))
    with pytest.raises(TypeError): e.inputs.manifest['period']['end'] = '2026-01-01'
    with pytest.raises(TypeError): e.inputs.normalized_ca.actions = ()
    with pytest.raises(Exception): e.inputs.normalized_ca.actions[0].cash_per_share = 123
    # Original frames and shared arrays are detached; external changes cannot affect runtime.
    inputs._bars.loc[:, 'close'] = 1
    inputs.normalized_ca.actions = ()
    import astraquant.research.trading_plan_r1_s3 as module
    def forbidden(*args, **kwargs): raise AssertionError('dataset hash inside trading loop')
    monkeypatch.setattr(module, '_hash', forbidden); monkeypatch.setattr(module, '_frame_digest', forbidden)
    step(e, days[80])
    assert e.positions['1101'].entry_price == 104
    with pytest.raises(ValueError, match='changed S3'):
        e._runtime = replace(snap, features={}); step(e, days[81])


def test_atomic_checkpoint_replace_failure_keeps_prior(tmp_path, monkeypatch):
    p = tmp_path/'checkpoint.json'; _atomic_write(p, b'prior')
    def interrupted(*args): raise OSError('forced before publication')
    monkeypatch.setattr(os, 'replace', interrupted)
    with pytest.raises(OSError): _atomic_write(p, b'new generation')
    assert p.read_bytes() == b'prior'
    assert list(tmp_path.iterdir()) == [p]


def test_chunk_checkpoint_restore_next_day_and_wrong_identity(tmp_path):
    root, days = _normalized_bundle(tmp_path, 'cash')
    inputs = S3Inputs.open_engineering_fixture(root, 'manifest.json', 'receipt.json')
    e = S3BatchTradingPlanR1(inputs=inputs, run_id='durable', entry_mode='close', exit_mode='sma20')
    for day in days[80:84]:
        step(e, day); e.save_checkpoint(tmp_path/'checkpoint.json')
    r = S3BatchTradingPlanR1.load_checkpoint(tmp_path/'checkpoint.json', inputs=inputs,
        run_id='durable', entry_mode='close', exit_mode='sma20')
    assert r.remaining_sessions()[0] == str(days[84].date())
    for day in days[84:]: step(e, day)
    r.run_remaining(checkpoint=tmp_path/'checkpoint.json')
    e.save(tmp_path/'full.json'); r.save(tmp_path/'resumed.json')
    assert (tmp_path/'full.json').read_bytes() == (tmp_path/'resumed.json').read_bytes()
    with pytest.raises(ValueError, match='identity mismatch'):
        S3BatchTradingPlanR1.load_checkpoint(tmp_path/'checkpoint.json', inputs=inputs, exit_mode='sma20_or_rsi13_lt50')
    state = json.loads((tmp_path/'checkpoint.json').read_text())
    chunk = tmp_path/state['checkpoint_storage']['chunks'][0]['path']; chunk.write_bytes(b'corrupted')
    with pytest.raises(Exception): S3BatchTradingPlanR1.load_checkpoint(tmp_path/'checkpoint.json', inputs=inputs)


def test_actual_killed_process_and_atomic_write_interrupt(tmp_path):
    import subprocess, sys
    root, days = _normalized_bundle(tmp_path, 'cash')
    script = '''
from pathlib import Path
from astraquant.research.trading_plan_r1_s3 import S3Inputs,S3BatchTradingPlanR1
import os,sys,signal
r=Path(sys.argv[1]); cp=Path(sys.argv[2]); inputs=S3Inputs.open_engineering_fixture(r,'manifest.json','receipt.json')
e=S3BatchTradingPlanR1(inputs=inputs,run_id='kill-proof',entry_mode='close',exit_mode='sma20')
for day in e.sessions[80:83]:
 e.prepare(day);e.reconcile_session(day,observed_at=day);e.save_checkpoint(cp)
os.kill(os.getpid(),signal.SIGKILL)
'''
    result = subprocess.run([sys.executable, '-c', script, str(root), str(tmp_path/'checkpoint.json')])
    assert result.returncode == -9
    inputs = S3Inputs.open_engineering_fixture(root, 'manifest.json', 'receipt.json')
    e = S3BatchTradingPlanR1(inputs=inputs, run_id='kill-proof', entry_mode='close', exit_mode='sma20')
    r = S3BatchTradingPlanR1.load_checkpoint(tmp_path/'checkpoint.json', inputs=inputs, run_id='kill-proof')
    assert r.remaining_sessions()[0] == str(days[83].date())
    r.run_remaining(checkpoint=tmp_path/'checkpoint.json')
    for day in days[80:]: step(e, day)
    e.save(tmp_path/'full.json');r.save(tmp_path/'resumed.json')
    assert (tmp_path/'full.json').read_bytes() == (tmp_path/'resumed.json').read_bytes()
    # Kill before fsync on a small temporary write; this is not a large-file stress test.
    before = (tmp_path/'checkpoint.json').read_bytes()
    writer = '''
from pathlib import Path
from astraquant.research.trading_plan_r1_s3 import _atomic_write
import os,signal,sys
old=os.fsync
def kill(fd): os.kill(os.getpid(),signal.SIGKILL)
os.fsync=kill
_atomic_write(sys.argv[1],b'new incomplete generation')
'''
    result = subprocess.run([sys.executable, '-c', writer, str(tmp_path/'checkpoint.json')])
    assert result.returncode == -9
    assert (tmp_path/'checkpoint.json').read_bytes() == before
    S3BatchTradingPlanR1.load_checkpoint(tmp_path/'checkpoint.json', inputs=inputs, run_id='kill-proof')
