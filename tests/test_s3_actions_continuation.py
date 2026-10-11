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
