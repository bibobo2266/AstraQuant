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


@pytest.mark.parametrize('status', ['ACTIVE', 'READY', 'COMPLETE', 'ERROR'])
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
