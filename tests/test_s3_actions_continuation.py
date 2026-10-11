"""Real runner/checkpoint boundaries; synthetic source fixture is explicit."""
import importlib.util
import json
from pathlib import Path

import pytest

from test_s3_diagnostic_runner_finish import runner_fixture


def actions_module():
    import sys
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location('s3_actions_test', scripts / 'run_s3_actions.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deadline_forces_off_interval_save_and_whole_worker_stops(tmp_path, monkeypatch):
    runner, output, scope, _ = runner_fixture(tmp_path, monkeypatch, (104.,101.,99.), 'A')
    calls = []
    def published(path, *, force=False):
        state = json.loads(Path(path).read_text())
        calls.append((len(state['completed']), force))
        return {'saved_completed_day': state['completed'][-1]}
    def stop():
        path = output / 'A1/checkpoint.json'
        return path.exists() and len(json.loads(path.read_text())['completed']) == 1
    result = runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output,
                    checkpoint_publisher=published, stop_requested=stop, stop_on_failure=True)
    assert calls == [(1, False), (1, True)]
    assert result['cells']['A1']['status'] == 'PAUSED_SAVED'
    assert all(v['status'] == 'QUEUED' for k,v in result['cells'].items() if k != 'A1')
    assert json.loads((output/'A1/checkpoint.json').read_text())['completed'] == scope[:1]
    # The exact persisted day is never prepared again after a new runner starts.
    original = runner.__dict__['run_s3_diagnostic_a']
    result = original(workspace=tmp_path, output_dir=output, cell_names={'A1'}, max_sessions=1)
    state = json.loads((output/'A1/checkpoint.json').read_text())
    assert state['completed'] == scope[:2]
    keys = [r['row_id'] for r in state['tables']['fills']]
    assert len(keys) == len(set(keys))


def test_accounting_stop_blocks_other_cells(tmp_path, monkeypatch):
    runner, output, _, engine = runner_fixture(tmp_path, monkeypatch, (104.,101.,99.), 'A')
    def reject(self, day):
        raise ValueError('original accounting failure')
    monkeypatch.setattr(engine, 'prepare', reject)
    result = runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output, stop_on_failure=True)
    assert result['cells']['A1']['status'] == 'ERROR'
    assert result['stop_reason'] == 'original accounting failure'
    assert all(v['status'] == 'QUEUED' for k,v in result['cells'].items() if k != 'A1')


def test_error_force_saves_last_valid_prefix_and_other_cells_continue(tmp_path, monkeypatch):
    runner,output,scope,engine=runner_fixture(tmp_path,monkeypatch,(104.,101.,99.),'A')
    original=engine.prepare
    def fail_second(self,day):
        if len(self.completed)==1:raise ValueError('S3 source calendar lacks T+2 settlement sessions')
        return original(self,day)
    monkeypatch.setattr(engine,'prepare',fail_second)
    saved=[]
    def pub(path,force=False):
        h=json.loads(Path(path).read_text())
        saved.append((Path(path).parent.name,h['completed'],force))
        return {'saved_completed_sessions':len(h['completed']),'readback_verified':True}
    result=runner.run_s3_diagnostic_a(workspace=tmp_path,output_dir=output,
        cell_names={'A1','A2'},checkpoint_publisher=pub,stop_on_failure=False)
    for cell in ['A1','A2']:
        assert (cell,scope[:1],True) in saved
        assert result['cells'][cell]['status']=='ERROR'
        assert result['cells'][cell]['external_checkpoint']['saved_completed_sessions']==1
        assert result['cells'][cell]['error']=='S3 source calendar lacks T+2 settlement sessions'


def test_artifact_budget_stops_before_upload(tmp_path, monkeypatch):
    module = actions_module()
    monkeypatch.setattr(module, 'REPO', tmp_path)
    monkeypatch.setattr(module, 'ROOT', tmp_path/'results')
    module.ROOT.mkdir()
    p = module.ROOT/'actions_segment_receipt.json'
    p.write_text('{}')
    assert module.stage_artifact({}, False) == 2
    assert (tmp_path/'s3-action-artifact/results'/p.name).read_bytes() == b'{}'
    monkeypatch.setattr(module,'INTERMEDIATE_ARTIFACT_CAP',1)
    with pytest.raises(ValueError,match='budget exceeded'):
        module.stage_artifact({},False)


@pytest.mark.parametrize('status', ['ACTIVE', 'READY', 'COMPLETE', 'ERROR', 'BLOCKED'])
def test_duplicate_or_unverified_continuation_never_dispatches(tmp_path, monkeypatch, status):
    module = actions_module()
    control = tmp_path/'chain.json'
    control.write_text(json.dumps({'chain_id':'chain', 'segment':0, 'status':status}))
    monkeypatch.setattr(module, 'CONTROL', control)
    class NoAPI:
        def api(self, *a, **k):raise AssertionError('must not touch remote API')
    monkeypatch.setattr(module, 'client', lambda: NoAPI())
    with pytest.raises(ValueError, match='duplicate/stale'):
        module.continue_chain('chain',0,123)


def test_wrong_uploaded_artifact_never_dispatches(tmp_path, monkeypatch):
    module = actions_module()
    control = tmp_path/'chain.json'
    control.write_text(json.dumps({'chain_id':'chain','segment':0,'status':'SAVED'}))
    monkeypatch.setattr(module, 'CONTROL', control)
    monkeypatch.setenv('GITHUB_RUN_ID','42')
    class API:
        def api(self, method, path, *args):
            assert method == 'GET'
            return {'name':'unrelated','expired':False,'workflow_run':{'id':42}}
    monkeypatch.setattr(module,'client',lambda:API())
    with pytest.raises(ValueError, match='identity mismatch'):
        module.continue_chain('chain',0,123)


@pytest.mark.parametrize('owner', ['42', 'newer-worker'])
def test_failure_preserves_original_error_and_respects_worker_ownership(tmp_path, monkeypatch, owner):
    module = actions_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'CONTROL', tmp_path/'actions_chain.json')
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    original = {'owner_run_id': owner, 'status': 'ACTIVE', 'next_segment': 1}
    module.CONTROL.write_text(json.dumps(original))
    saved = []
    monkeypatch.setattr(module, 'persist', lambda api, paths, message: saved.append(paths))
    module.record_failure(object(), RuntimeError('8436:unresolved_ca'))
    error = json.loads((tmp_path/'actions_error.json').read_text())
    assert error['error'] == '8436:unresolved_ca'
    control = json.loads(module.CONTROL.read_text())
    if owner == '42':
        assert control['status'] == 'BLOCKED'
        assert control['automatic_retry'] is False
        assert control['failure'] == error
        assert control['next_segment'] == 1
        assert saved == [[module.CONTROL, tmp_path/'actions_error.json']]
    else:
        assert control == original
        assert saved == []


def test_segment_skips_blocked_cell_and_continues_other_round(tmp_path, monkeypatch):
    module = actions_module()
    control = tmp_path/'chain.json'
    control.write_text(json.dumps({'blocked_cells': ['A1', 'A2']}))
    monkeypatch.setattr(module, 'CONTROL', control)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    cells = {r+str(i): {'completed': 0, 'frozen': False} for r in 'AB' for i in range(1,5)}
    cells['A1'].update(completed=634, frozen=True)
    cells['A4']['completed'] = 1468
    delivered = tmp_path/'A'/'A4'/'cell_delivery.json'
    delivered.parent.mkdir(parents=True)
    delivered.write_text('{}')
    monkeypatch.setattr(module, 'inventory', lambda: cells)
    monkeypatch.setattr(module, 'publisher', lambda rnd: None)
    calls = []
    def runner(**kwargs):
        calls.append(kwargs)
        return {'cells': {c: {'status': 'INCOMPLETE'} for c in kwargs['cell_names']}}
    monkeypatch.setattr(module, 'run_s3_diagnostic_a', runner)
    states = module.segment(tmp_path, 60)
    assert list(states) == ['A', 'B']
    assert calls[0]['cell_names'] == {'A3'}
    assert calls[1]['cell_names'] == {'B1', 'B2', 'B3', 'B4'}
    assert all(c['stop_on_failure'] is False for c in calls)


def test_measurement_preserves_real_checkpoint_and_all_ledger_bytes(tmp_path, monkeypatch):
    actions_module()  # Make sibling instrumentation importable.
    runner, output, scope, _ = runner_fixture(tmp_path, monkeypatch, (104.,101.,99.), 'A')
    measured = tmp_path/'measured'
    for directory in (output, measured):
        directory.mkdir()
        (directory/'progress.json').write_text(json.dumps({'execution_id':'parity-fixed-id'}))
    runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=output, cell_names={'A1'})
    rows, completed = [], []
    runner.run_s3_diagnostic_a(workspace=tmp_path, output_dir=measured, cell_names={'A1'},
        day_observer=lambda cell,row:rows.append(row),
        cell_finished=lambda cell,directory,state:completed.append(cell))
    assert completed == ['A1']
    assert [r['day'] for r in rows] == scope
    assert all(r['wall_seconds'] >= sum(r[p] for p in ['calculation','validation','local_save','remote_save']) for r in rows)
    for name in ['checkpoint.json', 'state.json', 'diagnostic_metrics.json']:
        assert (output/'A1'/name).read_bytes() == (measured/'A1'/name).read_bytes()
    tables = list((output/'A1/tables').glob('*.csv'))
    assert len(tables) == 4
    for path in tables:
        assert path.read_bytes() == (measured/'A1/tables'/path.name).read_bytes()


def test_timing_estimates_only_same_cell_after_contiguous100_days(tmp_path, monkeypatch):
    module = actions_module()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    path = tmp_path/'A/A2/day_timing.json'
    path.parent.mkdir(parents=True)
    rows = [dict(day=str(i), completed=i, wall_seconds=4, calculation=2,
                 validation=.5, local_save=.5, remote_save=1, other_seconds=0) for i in range(1,101)]
    path.write_text(json.dumps({'records':rows}))
    result = module.timing_summary({'A2':{'completed':100}, 'A3':{'completed':0}})
    assert result['A2']['remaining_seconds'] == (1468-100)*4
    assert result['A2']['seconds']['wall_seconds'] == 400
    assert result['A3']['remaining_seconds'] is None
    rows[-1]['completed'] = 102
    path.write_text(json.dumps({'records':rows}))
    assert module.timing_summary({'A2':{'completed':102}})['A2']['remaining_seconds'] is None


def test_cell_delivery_pins_eight_columns_four_ledgers_and_is_idempotent(tmp_path, monkeypatch):
    module = actions_module()
    monkeypatch.setattr(module, 'REPO', tmp_path)
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    directory = tmp_path/'A2'
    (directory/'tables').mkdir(parents=True)
    columns = ['closed_count','net_win_rate','avg_win','avg_loss','payoff_ratio','expectancy',
               'median_holding_sessions','capital_occupied_position_days']
    metric = {key:1 for key in columns}
    metric.update(closed_count=10, open_count=2, net_win_rate=.8, avg_loss=.02)
    (directory/'diagnostic_metrics.json').write_text(json.dumps([metric]))
    (directory/'checkpoint.json').write_text(json.dumps({'frozen':False,'completed':list(range(1468))}))
    for name in ['fills','decisions','equity','eligibility']:
        (directory/'tables'/('s3_'+name+'.csv')).write_text('canonical '+name)
    saves, messages = [], []
    monkeypatch.setattr(module, 'persist', lambda api,paths,message:saves.append(paths) or 'fixed-result')
    monkeypatch.setattr(module, 'issue', lambda api,message:messages.append(message))
    pub = lambda path,force: {'commit':'fixed-checkpoint','readback_verified':True}
    module.deliver_cell(pub, 'A2', directory, {'status':'STOP_THRESHOLD_LEDGER_REVIEW',
                                             'threshold_ledger_check':'revalidated'})
    report = json.loads((directory/'cell_delivery.json').read_text())
    assert list(report['metrics']) == columns
    assert report['metrics']['closed_count'] == 10 and report['open_count'] == 2
    assert report['threshold_review'] and report['threshold_ledger_check'] == 'revalidated'
    assert len(report['tables']) == 4
    assert len(saves) == len(messages) == 1
    assert (tmp_path/'s3-action-artifact/A2_ledgers.tar.gz').exists()
    module.deliver_cell(pub, 'A2', directory, {})
    assert len(saves) == len(messages) == 1


def test_restore_timing_keeps_unpersisted_days_as_history(tmp_path):
    module=actions_module()
    (tmp_path/'checkpoint.json').write_text(json.dumps({'completed':['saved-day']*1460}))
    rows=[{'completed':n,'day':str(n)} for n in range(1368,1468)]
    (tmp_path/'day_timing.json').write_text(json.dumps({'records':rows}))
    module.align_timing_to_checkpoint(tmp_path)
    data=json.loads((tmp_path/'day_timing.json').read_text())
    assert data['records']==rows[:93]
    assert data['superseded_records']==rows[93:]
    assert data['restored_checkpoint_completed']==1460
    saved=(tmp_path/'day_timing.json').read_bytes()
    module.align_timing_to_checkpoint(tmp_path)
    assert (tmp_path/'day_timing.json').read_bytes()==saved
