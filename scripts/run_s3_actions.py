#!/usr/bin/env python3
"""Authorized single-worker S3 continuation on the existing Actions workflow.

Source artifacts and execution IDs are immutable. Real SIGKILL pilot, bounded
segments, pinned checkpoint readback, and fail-closed same-workflow dispatch.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

from run_s3_ab_saved import GitHubCheckpointPublisher, BRANCH, git_blob, sha
from source_accounting_smoke_replay import restore_s3_evidence_transport, run_s3_diagnostic_a

REPO = Path(__file__).resolve().parents[1]
REMOTE = 'results/trading_plan_r1/s3_live_20261011'
ROOT = REPO / REMOTE
CONTROL = ROOT / 'actions_chain.json'
WORKFLOW = 'source_pit_feature_matrix_layer1.yml'
IDS = {'A': 's3-A-20261011T045203Z', 'B': 's3-B-20261011T045202Z'}
FAILURES = {'ERROR', 'INCOMPLETE', 'STOP_THRESHOLD_LEDGER_REVIEW'}
MAX_SEGMENTS = 72
INTERMEDIATE_ARTIFACT_CAP = 512 * 1024**2
FINAL_ARTIFACT_CAP = 2 * 1024**3


def write_json(path, value):
    from astraquant.research.trading_plan_r1_s3 import _atomic_write
    _atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def token_path():
    # Job-scoped token stays in RUNNER_TEMP, outside all artifact/upload paths.
    path = Path(os.environ['RUNNER_TEMP']) / 's3-job-token'
    path.write_text(os.environ['GH_TOKEN'])
    path.chmod(0o600)
    return path


def client():
    return GitHubCheckpointPublisher(token_file=token_path(), local_root=ROOT, remote_root=REMOTE)


def persist(api, paths, message):
    files = {str(p.relative_to(REPO)): p.read_bytes() for p in paths}
    revision = api.publish_files(files, message + ' [skip ci]')
    for name, value in files.items():
        if api.read_file(revision, name) != value:
            raise ValueError('pinned evidence readback differs: ' + name)
    return revision


def issue(api, message):
    api.api('POST', 'issues/6/comments', {'body': 'Sol-E｜' + message})


def locate(directory, name):
    matches = list(directory.rglob(name))
    if len(matches) != 1:
        raise ValueError(f'fixed artifact requires exactly one {name}: {len(matches)}')
    return matches[0]


def bootstrap(workspace):
    """Reproduce canonical paths from existing artifacts, without new data reads."""
    fixed = workspace / 'fixed-inputs'
    archive = locate(fixed / 'accounting', 'accounting_source_inputs.zip')
    expected = '79a45e098fb55f9c358c2c8a67e58365d07277b5ba706e2768d1842d11902867'
    if sha(archive.read_bytes()) != expected:
        raise ValueError('frozen accounting ZIP SHA mismatch')
    export = workspace / 'accounting-export-37769333701'
    export.mkdir(exist_ok=True)
    shutil.copyfile(archive, export / archive.name)
    with zipfile.ZipFile(archive) as zipped:
        manifest = zipped.read('input_manifest.json')
        if sha(manifest) != 'e18b21dab018c04ae5f6d05979c9d601b035bde45338ed40c42544be9337a26c':
            raise ValueError('frozen accounting manifest SHA mismatch')
        (export / 'input_manifest.json').write_bytes(manifest)
        for row in json.loads(manifest)['files']:
            data = zipped.read(row['archive_path'])
            if len(data) != row['bytes'] or sha(data) != row['sha256']:
                raise ValueError('frozen archive member mismatch: ' + row['archive_path'])
            if row['owner'] != 'source':
                continue
            target = workspace / 'accounting-canonical-source' / row['source_path']
            target.resolve().relative_to((workspace / 'accounting-canonical-source').resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    panel = locate(fixed / 's1', 'eligibility_panel.parquet')
    target = workspace / 's1-37708776526/data/panel/eligibility_panel.parquet'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(panel, target)
    alias = workspace / 'AstraQuant-full'
    if not alias.exists():
        alias.symlink_to(REPO, target_is_directory=True)
    if alias.resolve() != REPO:
        raise ValueError('canonical research path points to another checkout')
    restore_s3_evidence_transport(REPO / 'results/trading_plan_r1/limit_supplement_2016_2018')
    expected_files = json.loads((ROOT.parent / 's3_saved_20261011/stage1/stage1_environment_receipt.json').read_text())['files']
    verified = []
    for row in expected_files:
        path = workspace / row['path']
        if path.stat().st_size != row['bytes'] or sha(path.read_bytes()) != row['expected_sha256']:
            raise ValueError('canonical frozen source mismatch: ' + row['path'])
        verified.append({'path': row['path'], 'sha256': row['expected_sha256']})
    for rnd in IDS:
        progress = json.loads((ROOT / rnd / 'progress.json').read_text())
        if progress['execution_id'] != IDS[rnd]:
            raise ValueError('saved execution ID changed')
        for directory in sorted((ROOT / rnd).glob(rnd + '[1-4]')):
            if (directory / 'transport.json').exists():
                restore_s3_evidence_transport(directory)
    write_json(ROOT / 'actions_sources_verified.json', {'files': verified, 'source_refresh': False})


def inventory():
    result = {}
    for rnd in IDS:
        for index in range(1, 5):
            cell = rnd + str(index)
            path = ROOT / rnd / cell / 'checkpoint.json'
            if not path.exists():
                result[cell] = {'completed': 0, 'last_day': None, 'fills': 0, 'holdings': 0}
                continue
            state = json.loads(path.read_bytes())
            from astraquant.research.trading_plan_r1_s3 import _digest
            if state['state_digest'] != _digest({k: v for k, v in state.items() if k != 'state_digest'}):
                raise ValueError('local head digest differs: ' + cell)
            result[cell] = {'completed': len(state['completed']), 'last_day': state['completed'][-1],
                            'fills': sum(r['fill'] is True for r in state['tables']['fills']),
                            'holdings': len(state['positions']), 'frozen': state['frozen'],
                            'checkpoint_sha256': sha(path.read_bytes())}
    return result


def publisher(rnd):
    class ReportingPublisher(GitHubCheckpointPublisher):
        def __call__(self, path, *, force=False):
            previous = self.receipts.get(Path(path).parent.name, {}).get('commit')
            receipt = super().__call__(path, force=force)
            if receipt['commit'] != previous:
                issue(self, '新保存日固定讀回head SHA通過；run ' + os.environ['GITHUB_RUN_ID']
                      + '；' + json.dumps(receipt, ensure_ascii=False)
                      + '；實讀各格 ' + json.dumps(inventory(), ensure_ascii=False))
            return receipt
    pub = ReportingPublisher(token_file=token_path(), local_root=ROOT / rnd, remote_root=REMOTE + '/' + rnd)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    for directory in sorted((ROOT / rnd).glob(rnd + '[1-4]')):
        path = directory / 'transport.json'
        if not path.exists():
            continue
        state = json.loads((directory / 'checkpoint.json').read_bytes())
        pub.receipts[directory.name] = dict(commit=revision, repo='bibobo2266/AstraQuant',
            path=str(path.relative_to(REPO)), transport_sha256=sha(path.read_bytes()),
            checkpoint_sha256=sha((directory / 'checkpoint.json').read_bytes()),
            saved_completed_day=state['completed'][-1], saved_completed_sessions=len(state['completed']),
            local_completed_sessions=len(state['completed']), readback_verified=True)
        for item in json.loads(path.read_bytes())['files']:
            for part in item['parts']:
                value = (directory / part['file']).read_bytes()
                pub.known[str((directory / part['file']).relative_to(REPO))] = git_blob(value)
        pub.known[str(path.relative_to(REPO))] = git_blob(path.read_bytes())
    return pub


def copy_checkpoint(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    state = json.loads((source / 'checkpoint.json').read_bytes())
    shutil.copyfile(source / 'checkpoint.json', destination / 'checkpoint.json')
    for row in state.get('checkpoint_storage', {}).get('chunks', []):
        target = destination / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != (source / row['path']).read_bytes():
                raise ValueError('checkpoint chunk collision')
        else:
            shutil.copyfile(source / row['path'], target)


def pilot_child(workspace, action, path):
    from astraquant.research.trading_plan_r1_s3 import S3Inputs, S3BatchTradingPlanR1
    started = time.monotonic()
    inputs = S3Inputs.open_accounting_probe(workspace, ROOT / 'A/manifest.json', ROOT / 'A/receipt.json')
    engine = S3BatchTradingPlanR1.load_checkpoint(path / 'checkpoint.json', inputs=inputs,
                run_id=IDS['A'] + '-A1', entry_mode='close', exit_mode='sma20')
    initial = len(engine.completed)
    for day in engine.remaining_sessions()[:2 if action == 'baseline' else 1]:
        engine.prepare(day)
        engine.reconcile_session(day, observed_at=day)
        engine.save_checkpoint(path / 'checkpoint.json')
        if engine.frozen:
            raise RuntimeError(engine.freeze_reason)
        if action == 'interrupt':
            # A real process death after durable head, not a mocked exception.
            os.kill(os.getpid(), signal.SIGKILL)
    engine.save(path / 'expanded.json')
    engine.export_tables(path / 'tables')
    duplicates = {}
    for name in engine.ledger.rows:
        rows = list(engine.ledger.rows[name])
        keys = [r['row_id'] for r in rows]
        duplicates[name] = len(keys) - len(set(keys))
    if any(duplicates.values()) or len(engine.completed) != len(set(engine.completed)):
        raise ValueError('pilot duplicate accounting rows/dates')
    write_json(path / 'timing.json', dict(initial=initial, completed=engine.completed,
        elapsed_seconds=time.monotonic() - started, duplicates=duplicates,
        fills=sum(r['fill'] for r in engine.ledger.rows['fills']), holdings=len(engine.positions)))


def pilot(workspace):
    started = time.monotonic()
    deadline = float(os.environ.get('S3_JOB_EPOCH', time.time())) + 3600
    lab = Path(os.environ['RUNNER_TEMP']) / 's3-pilot'
    baseline, interrupted = lab / 'baseline', lab / 'interrupted'
    for path in [baseline, interrupted]:
        copy_checkpoint(ROOT / 'A/A1', path)
    commands = [('baseline', baseline, 0), ('interrupt', interrupted, -signal.SIGKILL), ('resume', interrupted, 0)]
    exits = []
    for action, path, expected in commands:
        args = [sys.executable, str(Path(__file__).resolve()), '--phase', 'child', '--action', action,
                '--workspace', str(workspace), '--path', str(path)]
        remaining = deadline - time.time()
        if remaining <= 0:raise TimeoutError('pilot soft budget exhausted before next child')
        result = subprocess.run(args, cwd=REPO, timeout=min(1800, remaining))
        exits.append({'action': action, 'actual_exit': result.returncode, 'expected_exit': expected})
        if result.returncode != expected:
            raise RuntimeError('pilot child failed: ' + json.dumps(exits[-1]))
    first = (baseline / 'expanded.json').read_bytes()
    if first != (interrupted / 'expanded.json').read_bytes():
        raise ValueError('uninterrupted/resumed full state bytes differ')
    tables = {}
    for path in sorted((baseline / 'tables').glob('*.csv')):
        other = interrupted / 'tables' / path.name
        if path.read_bytes() != other.read_bytes():
            raise ValueError('uninterrupted/resumed table differs: ' + path.name)
        tables[path.name] = sha(path.read_bytes())
    # Seed known remote files BEFORE advancing the live head.
    pub = publisher('A')
    copy_checkpoint(interrupted, ROOT / 'A/A1')
    receipt = pub(ROOT / 'A/A1/checkpoint.json', force=True)
    a = json.loads((baseline / 'timing.json').read_text())
    b = json.loads((interrupted / 'timing.json').read_text())
    result = dict(full_state_equal=True, all_tables_equal=True, state_sha256=sha(first),
        table_sha256=tables, real_sigkill=exits, start_completed=a['initial'],
        saved_after_interrupt=b['initial'], completed=len(b['completed']),
        next_completed_days=b['completed'][a['initial']:], remote_checkpoint=receipt,
        duplicates=b['duplicates'], fills=b['fills'], holdings=b['holdings'],
        baseline_seconds=a['elapsed_seconds'], resume_seconds=b['elapsed_seconds'],
        total_seconds=time.monotonic() - started,
        scope='same fixed real A1 data and original run ID; empty holdings if reported; not a claim of new holding/event coverage')
    write_json(ROOT / 'actions_pilot_evidence.json', result)
    return result


def segment(workspace, seconds):
    deadline = time.monotonic() + seconds
    states = {}
    for rnd in IDS:
        if time.monotonic() >= deadline:
            break
        status = run_s3_diagnostic_a(workspace=workspace, output_dir=ROOT / rnd, round_name=rnd,
            checkpoint_publisher=publisher(rnd), stop_requested=lambda: time.monotonic() >= deadline,
            stop_on_failure=True)
        states[rnd] = status
        if any(s['status'] in FAILURES for s in status['cells'].values()):
            raise RuntimeError('runner stop: ' + json.dumps(status, ensure_ascii=False))
    return states


def stage_artifact(before, complete):
    """Only small receipts/new transport pieces; durable Git holds full restores."""
    target = REPO / 's3-action-artifact'
    target.mkdir(exist_ok=True)
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        relative = str(path.relative_to(REPO))
        allowed = (path.name in {'actions_chain.json', 'actions_pilot_evidence.json', 'actions_segment_receipt.json',
                    'actions_sources_verified.json', 'progress.json', 'error.json', 'transport.json',
                    'diagnostic_metrics.json', 'open_positions.csv'} or 'transport/' in relative)
        if complete and path.name in {'A_B_eight_columns.csv', 'A_B_final_manifest.json'}:
            allowed = True
        if not allowed or before.get(relative) == sha(path.read_bytes()):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    if complete:
        # Cost cap measures stored payload. Compress large final ledgers before
        # upload instead of rejecting highly compressible CSV on raw byte size.
        with tarfile.open(target / 'A_B_final_ledgers.tar.gz', 'w:gz') as archive:
            for rnd in IDS:
                for directory in sorted((ROOT/rnd).glob(rnd+'[1-4]')):
                    for path in [directory/'state.json', *sorted((directory/'tables').glob('*.csv'))]:
                        archive.add(path, arcname=str(path.relative_to(ROOT)))
    cap = FINAL_ARTIFACT_CAP if complete else INTERMEDIATE_ARTIFACT_CAP
    size = sum(p.stat().st_size for p in target.rglob('*') if p.is_file())
    if size > cap:
        raise ValueError(f'artifact size budget exceeded: {size}>{cap}')
    return size


def final_metrics():
    import pandas as pd
    columns = ['net_win_rate', 'avg_win', 'avg_loss', 'payoff_ratio', 'expectancy',
               'median_holding_sessions', 'capital_occupied_position_days', 'closed_count']
    rows, ledgers = [], {}
    for rnd in IDS:
        for index in range(1,5):
            cell = rnd + str(index)
            directory = ROOT/rnd/cell
            row = json.loads((directory/'diagnostic_metrics.json').read_text())[0]
            rows.append(dict(round=rnd, cell=cell, **{key:row[key] for key in columns}))
            for path in [directory/'state.json', *sorted((directory/'tables').glob('*.csv'))]:
                ledgers[str(path.relative_to(ROOT))] = {'bytes':path.stat().st_size, 'sha256':sha(path.read_bytes())}
    pd.DataFrame(rows).to_csv(ROOT/'A_B_eight_columns.csv', index=False)
    write_json(ROOT/'A_B_final_manifest.json', {'cells':inventory(), 'files':ledgers,
            'metric_columns':columns, 'scope':'fixed authorized A/B E1 diagnostics, pending independent review'})


def execute(workspace, chain_id, index):
    os.chdir(REPO)
    started = time.monotonic()
    api = client()
    prior = json.loads(CONTROL.read_text()) if CONTROL.exists() else {}
    if prior and (prior['chain_id'] != chain_id or prior['next_segment'] != index or prior['status'] != 'READY'):
        raise ValueError('chain identity/segment/state mismatch; duplicate/stale start refused')
    if index >= MAX_SEGMENTS or prior.get('jobs_started',0) >= MAX_SEGMENTS:
        raise ValueError('72-segment budget exhausted')
    run_id = os.environ['GITHUB_RUN_ID']
    control = dict(chain_id=chain_id, segment=index, next_segment=index, status='ACTIVE',
                   owner_run_id=run_id, code_commit=os.environ['GITHUB_SHA'], jobs_started=prior.get('jobs_started',0)+1)
    write_json(CONTROL, control)
    persist(api, [CONTROL], f'Claim S3 hosted segment {index} run {run_id}')
    before = {str(p.relative_to(REPO)): sha(p.read_bytes()) for p in ROOT.rglob('*') if p.is_file()}
    bootstrap(workspace)
    initial = inventory()
    with ExitStack() as stack:
        for rnd in IDS:
            lock = stack.enter_context((ROOT / rnd / 'execution.lock').open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if index == 0:
            evidence = pilot(workspace)
            persist(api, [ROOT / 'actions_pilot_evidence.json'], 'Save real SIGKILL S3 pilot comparison')
            states = {'pilot': evidence}
        else:
            # A new hosted process reads the previous job's pinned checkpoint.
            # Independently visible completed-day advance is reported below.
            seconds = float(os.environ.get('S3_JOB_EPOCH', time.time())) + 3600 - time.time()
            if seconds <= 0:raise TimeoutError('setup exhausted60-minute soft budget')
            states = segment(workspace, seconds)
    final = inventory()
    advanced = sum(v['completed'] for v in final.values()) - sum(v['completed'] for v in initial.values())
    if advanced <= 0:
        raise ValueError('zero completed-day progress; no automatic retry')
    complete = all(v['completed'] == 1468 for v in final.values())
    if any(v.get('frozen') for v in final.values()):
        raise RuntimeError('frozen cell; continuation refused')
    if complete:final_metrics()
    control.update(status='SAVED', next_segment=index + 1, complete=complete, advanced=advanced,
                   requires_artifact_success=True)
    receipt = dict(chain_id=chain_id, segment=index, actions_run_id=run_id,
        initial_cells=initial, cells=final, advanced=advanced, complete=complete,
        elapsed_seconds=time.monotonic() - started, states=states,
        persistence='hosted Actions; no chat-side service dependency',
        post_chat_observation='requires later independent observation; run ID alone is not evidence')
    write_json(CONTROL, control)
    write_json(ROOT / 'actions_segment_receipt.json', receipt)
    evidence_paths=[CONTROL, ROOT / 'actions_segment_receipt.json', ROOT / 'actions_sources_verified.json']
    if complete:evidence_paths += [ROOT/'A_B_eight_columns.csv', ROOT/'A_B_final_manifest.json']
    revision = persist(api, evidence_paths,
                       f'Save S3 hosted segment {index} actual progress')
    size = stage_artifact(before, complete)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as out:
        out.write(f'complete={str(complete).lower()}\nartifact_bytes={size}\n')
    issue(api, f'Actions段{index}／run {run_id} 已保存並固定讀回；commit {revision}；實際{advanced}新日，耗時{receipt["elapsed_seconds"]:.2f}秒。'
               + json.dumps(final, ensure_ascii=False) + ('；真SIGKILL→恢復完整state/全部CSV逐位元相同。' if index == 0 else '')
               + '；artifact成功才接下一段，RUNNING/啟動ID不作跨聊天證據。')


def continue_chain(chain_id, index, artifact_id):
    api = client()
    control = json.loads(CONTROL.read_text())
    if control['chain_id'] != chain_id or control['segment'] != index or control['status'] != 'SAVED':
        raise ValueError('duplicate/stale continuation refused')
    artifact = api.api('GET', 'actions/artifacts/' + str(artifact_id))
    expected = f's3-{chain_id}-{index}-{os.environ["GITHUB_RUN_ID"]}'
    if artifact['name'] != expected or artifact['expired'] or artifact['workflow_run']['id'] != int(os.environ['GITHUB_RUN_ID']):
        raise ValueError('uploaded artifact identity mismatch')
    control['artifact_id'] = artifact_id
    control['status'] = 'COMPLETE' if control['complete'] else ('BUDGET_EXHAUSTED' if index + 1 >= MAX_SEGMENTS or control['jobs_started'] >= MAX_SEGMENTS else 'READY')
    write_json(CONTROL, control)
    persist(api, [CONTROL], f'Confirm S3 segment {index} artifact and continuation boundary')
    if control['status'] != 'READY':
        issue(api, control['status'] + '；' + json.dumps(inventory(), ensure_ascii=False))
        return
    # Permission documented for workflow_dispatch; token triggers only this file.
    api.api('POST', 'actions/workflows/' + WORKFLOW + '/dispatches', dict(ref=BRANCH,
        inputs={'stage': 's3_resume', 's3_chain': chain_id, 's3_segment': str(index + 1)}))
    issue(api, f'段{index} artifact {artifact_id}核存在，已排同workflow段{index + 1}；單worker接最新已存日，不等核准。')


def record_failure(api, error):
    failure = {'type': type(error).__name__, 'error': str(error),
               'actions_run_id': os.environ['GITHUB_RUN_ID']}
    error_path = ROOT / 'actions_error.json'
    write_json(error_path, failure)
    if not CONTROL.exists():
        return
    control = json.loads(CONTROL.read_text())
    if str(control.get('owner_run_id')) != os.environ['GITHUB_RUN_ID']:
        return  # A stale job must never replace another worker's control state.
    control.update(status='BLOCKED', failure=failure, automatic_retry=False)
    write_json(CONTROL, control)
    persist(api, [CONTROL, error_path], 'Save blocked S3 worker and original failure')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--phase', choices=['execute', 'continue', 'child', 'failure'], required=True)
    p.add_argument('--workspace', type=Path, default=REPO.parent)
    p.add_argument('--chain', default='s3-actions-20261011')
    p.add_argument('--segment', type=int, default=0)
    p.add_argument('--artifact-id', type=int)
    p.add_argument('--action', choices=['baseline', 'interrupt', 'resume'])
    p.add_argument('--path', type=Path)
    args = p.parse_args()
    if args.phase == 'child':
        pilot_child(args.workspace.resolve(), args.action, args.path)
    elif args.phase == 'continue':
        continue_chain(args.chain, args.segment, args.artifact_id)
    elif args.phase == 'failure':
        api = client()
        issue(api, 'Actions失敗停止，無自動重啟；run ' + os.environ['GITHUB_RUN_ID'] + '；請讀該run原始log。')
    else:
        try:
            execute(args.workspace.resolve(), args.chain, args.segment)
        except Exception as error:
            try:
                record_failure(client(), error)
            except Exception as save_error:
                write_json(ROOT / 'actions_failure_save_error.json',
                           {'type': type(save_error).__name__, 'error': str(save_error),
                            'original_error': str(error)})
            issue(client(), 'Actions具體錯誤：' + type(error).__name__ + ': ' + str(error)[:3500]
                  + '；run ' + os.environ['GITHUB_RUN_ID'] + '；停止，未自動重啟。')
            raise


if __name__ == '__main__':
    main()
