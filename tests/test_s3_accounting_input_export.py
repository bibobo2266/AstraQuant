"""Real Git, byte-copy and ZIP paths on small, explicit engineering fixtures."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pandas as pd
import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/source_pit_feature_matrix_layer1.py'


def load_export():
    tree = ast.parse(SCRIPT.read_text())
    names = {'_sha256', '_s3_export_accounting_inputs', '_s3_accounting_inputs'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = {'Path': Path, 'pd': pd, 'os': os, 'hashlib': hashlib, 'json': json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), 'exec'), scope)
    return scope


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def fixture(tmp_path):
    source_repo, research = tmp_path / 'source', tmp_path / 'research'
    source, output = source_repo / 'data', tmp_path / 'export'
    for root in [source_repo, research]:
        root.mkdir()
        git(root, 'init', '-q')
        git(root, 'config', 'user.email', 'engineering@example.invalid')
        git(root, 'config', 'user.name', 'Engineering fixture')
    for year in range(2015, 2022):
        p = source / 'raw' / f'prices_raw_{year}.parquet'
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({'date': [pd.Timestamp(f'{year}-06-01')], 'stock_id': ['1101'],
                      'open': [100.], 'close': [100.]}).to_parquet(p, index=False)
    paths = [f'reference/price_limit_{year}.parquet' for year in range(2015, 2019)]
    paths += ['reference/tradability.parquet', 'fundamentals/dividend.parquet',
              'reference/corporate_actions_ledger.parquet', 'reference/finmind_suspended.parquet', 'universe.parquet']
    for relative in paths:
        p = source / relative; p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({'fixture': [True]}).to_parquet(p, index=False)
    for relative in ['reference/corporate_actions_official.csv', 'reference/corporate_actions_reconciliation.csv']:
        (source / relative).write_text('fixture\nTrue\n')
    for relative in ['data/research/terminal_events.csv', 'scripts/source_strategy_integration_smoke.py',
                     'src/astraquant/research/terminal_events.py', 'src/astraquant/data/corporate_actions.py',
                     'src/astraquant/portfolio/strategy_simulator.py', 'src/astraquant/portfolio/policy.py',
                     'scripts/source_pit_feature_matrix_layer1.py']:
        p = research / relative; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('engineering fixture\n')
    for root in [source_repo, research]:
        git(root, 'add', '.'); git(root, 'commit', '-qm', 'Immutable fixture inputs')
    return source, research, output, git(source_repo, 'rev-parse', 'HEAD'), git(research, 'rev-parse', 'HEAD')


def run(args):
    return load_export()['_s3_export_accounting_inputs'](*args)


def test_complete_export_actual_git_copy_archive_and_manifest(tmp_path):
    args = fixture(tmp_path)
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for root in args[:2] for p in root.rglob('*')
                 if p.is_file() and '.git' not in p.parts}
    manifest = run(args)
    assert manifest['status'] == 'SOURCE_EXPORT_COMPLETE_FOR_REVIEW'
    assert len(manifest['files']) == 25 and not manifest['missing_inputs']
    assert not manifest['s1_rebuilt'] and not manifest['s3_run'] and not manifest['accounting_gate_passed']
    assert manifest['official_event_probe_cap'] == 10 and manifest['official_events_verified'] == 0
    assert manifest['period_end'] == '2021-12-31'
    with zipfile.ZipFile(args[2] / 'accounting_source_inputs.zip') as z:
        assert set(z.namelist()) == {'input_manifest.json'} | {r['archive_path'] for r in manifest['files']}
        assert json.loads(z.read('input_manifest.json')) == manifest
        for row in manifest['files']:
            assert hashlib.sha256(z.read(row['archive_path'])).hexdigest() == row['sha256']
            assert len(z.read(row['archive_path'])) == row['bytes']
            assert row['revision'] == (args[3] if row['owner'] == 'source' else args[4])
            assert row['git_blob'] == hashlib.sha1(b'blob ' + str(row['bytes']).encode() + b'\0' + z.read(row['archive_path'])).hexdigest()
    for path, sha in originals.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    receipt = json.loads((args[2] / 'archive_receipt.json').read_text())
    assert receipt['archived_input_files'] == 25
    assert receipt['sha256'] == hashlib.sha256((args[2] / receipt['path']).read_bytes()).hexdigest()
    assert receipt['input_manifest_sha256'] == hashlib.sha256((args[2] / 'input_manifest.json').read_bytes()).hexdigest()
    assert {r['date_start'][:4] for r in manifest['files'] if r['role'] == 'raw'} == {str(y) for y in range(2015, 2022)}


@pytest.mark.parametrize('owner', ['source', 'research'])
def test_wrong_git_revision_rejects_without_archive(tmp_path, owner):
    args = list(fixture(tmp_path)); args[3 if owner == 'source' else 4] = '0' * 40
    with pytest.raises(SystemExit, match='revision mismatch'):
        run(args)
    assert not args[2].exists()


@pytest.mark.parametrize('relative', ['raw/prices_raw_2015.parquet', 'reference/tradability.parquet',
                                     'fundamentals/dividend.parquet'])
def test_missing_required_input_retains_exact_gap_not_complete_zip(tmp_path, relative):
    args = fixture(tmp_path); (args[0] / relative).unlink()
    with pytest.raises(SystemExit, match='required accounting inputs absent'):
        run(args)
    manifest = json.loads((args[2] / 'input_manifest.json').read_text())
    assert manifest['status'] == 'BLOCKED_MISSING_INPUTS'
    assert manifest['missing_inputs'] == ['source/' + relative]
    assert not (args[2] / 'accounting_source_inputs.zip').exists()


def test_modified_tracked_bytes_rejects_before_copy(tmp_path):
    args = fixture(tmp_path); (args[0] / 'reference/corporate_actions_official.csv').write_text('changed\n')
    with pytest.raises(subprocess.CalledProcessError):
        run(args)
    assert not args[2].exists()


def test_untracked_replacement_is_not_bound_source(tmp_path):
    args = fixture(tmp_path)
    git(args[0], 'rm', '--cached', 'raw/prices_raw_2015.parquet')
    git(args[0], 'commit', '-qm', 'Untrack input')
    args = (*args[:3], git(args[0], 'rev-parse', 'HEAD'), args[4])
    with pytest.raises(subprocess.CalledProcessError):
        run(args)
    assert not args[2].exists()


def test_path_escape_cannot_export_external_bytes(tmp_path):
    args = fixture(tmp_path); p = args[0] / 'reference/tradability.parquet'
    p.unlink(); outside = tmp_path / 'outside.parquet'; outside.write_bytes(b'outside'); p.symlink_to(outside)
    with pytest.raises((ValueError, SystemExit)):
        run(args)
    assert not args[2].exists()


def test_stale_destination_is_not_reused(tmp_path):
    args = fixture(tmp_path); args[2].mkdir(); marker = args[2] / 'stale'; marker.write_text('preserve')
    with pytest.raises(SystemExit, match='destination already exists'):
        run(args)
    assert marker.read_text() == 'preserve' and not (args[2] / 'accounting_source_inputs.zip').exists()


def test_authorized_dispatcher_rejects_wrong_source_before_helper(tmp_path):
    scope = load_export(); scope.update(SOURCE_REVISION='different', ROOT=tmp_path,
                                        SOURCE_ROOT=tmp_path, OUT_ROOT=tmp_path)
    with pytest.raises(SystemExit, match='fixed source revision changed'):
        scope['_s3_accounting_inputs']()


def test_dispatcher_cannot_accidentally_rebuild_panel(monkeypatch, tmp_path):
    scope = load_export(); scope.update(SOURCE_REVISION='3e7c4b6d9cde3b18942710fa977db02f89bffa0d', ROOT=tmp_path,
                                        SOURCE_ROOT=tmp_path, OUT_ROOT=tmp_path)
    monkeypatch.setenv('BUILD_ELIGIBILITY_PANEL', '1')
    with pytest.raises(SystemExit, match='cannot share'):
        scope['_s3_accounting_inputs']()


def test_only_existing_workflow_dispatch_stage_and_artifact_paths():
    root = SCRIPT.parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/source_pit_feature_matrix_layer1.yml').read_text())
    trigger = workflow.get('on', workflow.get(True))
    assert set(trigger) == {'workflow_dispatch'}
    assert 's3_accounting_inputs' in trigger['workflow_dispatch']['inputs']['stage']['options']
    steps = workflow['jobs']['build']['steps']
    export = next(s for s in steps if s.get('env', {}).get('S3_ACCOUNTING_INPUTS') == '1')
    assert "inputs.stage == 's3_accounting_inputs'" in export['if']
    assert export['run'] == 'python scripts/source_pit_feature_matrix_layer1.py'
    assert not any(key in export['env'] for key in ['BUILD_ELIGIBILITY_PANEL', 'S3_LIMIT_INPUTS', 'FINMIND_TOKEN'])
    upload = next(s for s in steps if s.get('uses', '').startswith('actions/upload-artifact@'))
    assert 'always()' in upload['if']
    for path in ['data/panel/eligibility_panel.parquet', 'out/limit_rule_inputs/',
                 'out/s3_accounting_inputs/accounting_source_inputs.zip', 'out/s3_accounting_inputs/input_manifest.json',
                 'out/s3_accounting_inputs/archive_receipt.json']:
        assert 'AstraQuant/' + path in upload['with']['path']
    assert workflow['permissions'] == {'contents': 'read'}
    assert not any('git push' in s.get('run', '') or 'docs/' in s.get('run', '') for s in steps)


def test_export_cannot_write_into_immutable_source(tmp_path):
    args = list(fixture(tmp_path)); args[2] = args[0] / 'export'
    with pytest.raises(SystemExit, match='cannot export into immutable source'):
        run(args)
    assert not args[2].exists()


def test_copy_corruption_cannot_claim_complete_export(monkeypatch, tmp_path):
    import shutil
    args = fixture(tmp_path)
    original = shutil.copyfile
    def corrupt(src, dst):
        original(src, dst)
        Path(dst).write_bytes(b'corrupted export')
    monkeypatch.setattr(shutil, 'copyfile', corrupt)
    with pytest.raises(SystemExit, match='changed during immutable export'):
        run(args)
    manifest = json.loads((args[2] / 'input_manifest.json').read_text())
    assert manifest['status'] == 'VERIFIED_INPUTS_AWAITING_ARCHIVE'
    assert not (args[2] / 'accounting_source_inputs.zip').exists()
    assert not (args[2] / 'archive_receipt.json').exists()
