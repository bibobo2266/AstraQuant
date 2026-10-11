"""Checkpoint encoding/transport changes retain bytes, integrity and resume."""
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import astraquant.research.trading_plan_r1 as r1
import astraquant.research.trading_plan_r1_s3 as s3
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from source_accounting_smoke_replay import package_checkpoint_transport, restore_s3_evidence_transport
from test_trading_plan_r1_s3 import bundle


def old_plain():
    source=inspect.getsource(r1._plain)
    source=source.replace('    # Most persisted ledger leaves are already plain scalar values.\n'
                          '    if type(value) in (str, int, bool, type(None)):\n'
                          '        return value\n', '')
    namespace=dict(r1.__dict__)
    exec(source,namespace)
    return namespace['_plain']


def test_plain_encoding_matches_previous_for_all_supported_scalar_kinds():
    value={'plain':['str',1,True,None,1.5,float('nan'),float('inf')],
           'numpy':(np.int64(2),np.bool_(True),np.float64(3.5),np.str_('x')),
           'timestamp':pd.Timestamp('2021-12-30')}
    assert json.dumps(r1._plain(value),allow_nan=False)==json.dumps(old_plain()(value),allow_nan=False)


def test_old_new_checkpoint_next_unfinished_day_and_all_csv_equal(tmp_path,monkeypatch):
    root,days=bundle(tmp_path)
    inputs=s3.S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    e=s3.S3BatchTradingPlanR1(inputs=inputs,run_id='encoding-parity',entry_mode='close',exit_mode='sma20')
    day=str(days[80].date());e.prepare(day);e.reconcile_session(day,observed_at=day)
    before=tmp_path/'before/checkpoint.json';after=tmp_path/'after/checkpoint.json'
    previous=old_plain()
    with monkeypatch.context() as patch:
        patch.setattr(s3,'_plain',previous)
        e.save_checkpoint(before)
    e.save_checkpoint(after)
    assert before.read_bytes()==after.read_bytes()
    # Copy the already saved chunks, then reload without repeating the first day.
    import shutil
    shutil.copytree(before.parent/'checkpoint_chunks',after.parent/'checkpoint_chunks',dirs_exist_ok=True)
    restored=s3.S3BatchTradingPlanR1.load_checkpoint(after,inputs=inputs)
    assert restored.remaining_sessions()[0]==str(days[81].date())
    for engine in (e,restored):
        for day in engine.remaining_sessions():
            engine.prepare(day);engine.reconcile_session(day,observed_at=day)
    e.save(tmp_path/'full.json');restored.save(tmp_path/'resumed.json')
    assert (tmp_path/'full.json').read_bytes()==(tmp_path/'resumed.json').read_bytes()
    for name,engine in [('full',e),('resumed',restored)]:engine.export_tables(tmp_path/name)
    for path in (tmp_path/'full').glob('*.csv'):
        assert path.read_bytes()==(tmp_path/'resumed'/path.name).read_bytes()
    fills=restored.ledger.rows['fills']
    assert len({row['row_id'] for row in fills})==len(fills)


def test_transport_reuses_only_verified_bytes_and_repairs_corrupt_parts(tmp_path,monkeypatch):
    root,days=bundle(tmp_path)
    inputs=s3.S3Inputs.open_engineering_fixture(root,'manifest.json','receipt.json')
    e=s3.S3BatchTradingPlanR1(inputs=inputs,run_id='transport-parity',entry_mode='close',exit_mode='sma20')
    day=str(days[80].date());e.prepare(day);e.reconcile_session(day,observed_at=day)
    directory=tmp_path/'checkpoint'
    e.save_checkpoint(directory/'checkpoint.json')
    initial=package_checkpoint_transport(directory)
    first=(directory/'transport.json').read_bytes()
    import gzip
    calls=[];original=gzip.compress
    def measured(*args,**kwargs):
        calls.append(len(args[0]));return original(*args,**kwargs)
    monkeypatch.setattr(gzip,'compress',measured)
    package_checkpoint_transport(directory)
    assert calls==[] and (directory/'transport.json').read_bytes()==first
    corrupt=directory/initial[-1]['parts'][0]['file'];corrupt.write_bytes(b'bad')
    package_checkpoint_transport(directory)
    assert len(calls)==1 and (directory/'transport.json').read_bytes()==first
    # The complete verified transport still reproduces every source file exactly.
    import shutil
    target=tmp_path/'restored'
    shutil.copytree(directory/'transport',target/'transport')
    (target/'transport.json').write_bytes(first)
    restore_s3_evidence_transport(target)
    for item in initial:
        assert (target/item['decoded_file']).read_bytes()==(directory/item['decoded_file']).read_bytes()
    # Metadata tampering cannot cause a wrong compressed generation to be reused.
    altered=json.loads(first);altered['files'][0]['compressed_sha256']='0'*64
    (directory/'transport.json').write_text(json.dumps(altered))
    calls.clear();package_checkpoint_transport(directory)
    assert len(calls)==1 and (directory/'transport.json').read_bytes()==first
