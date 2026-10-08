from dataclasses import replace
from datetime import date, datetime
import importlib.util
import json
import os
from pathlib import Path

import pytest

from astraquant.data.corporate_actions import NormalizedCorporateAction, NormalizedCorporateActionKind
from astraquant.data.market_coordinates import PriceUse
from astraquant.portfolio.models import OrderIntent
from test_historical_portfolio_runner import _runner, _signal


def _probe_module():
    path = Path(__file__).resolve().parents[1]/'scripts/source_accounting_smoke_replay.py'
    spec = importlib.util.spec_from_file_location('accounting_process_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _held(tmp_path):
    runner, portfolio = _runner(tmp_path)
    replay = runner.replay
    at = datetime(2026,1,2,9)
    replay.execute_trade(intent=OrderIntent('n-buy','2330','buy',100,at,'engineering case'),
        signal=_signal(),order_id='n-order',fill_id='n-fill',submitted_at=at,
        session_date=date(2026,1,2),use=PriceUse.ENTRY,field='open',
        settlement_id='n-settle',settlement_due=datetime(2026,1,5))
    replay.settle('n-settle',datetime(2026,1,5))
    return replay, portfolio


def _action():
    return NormalizedCorporateAction('2330',date(2026,1,5),NormalizedCorporateActionKind.CASH_DIVIDEND,
        datetime(2026,1,2,16),datetime(2026,1,6),2.,None,'engineering dividend',0,'cash_per_pre_event_share')


@pytest.mark.parametrize('known_at', [None,datetime(2026,1,6),datetime(2026,1,5,10)])
def test_normalized_pit_rejection_preserves_actual_held_account(tmp_path, known_at):
    replay, portfolio = _held(tmp_path)
    before = (portfolio.cash.settled_cash,portfolio.cash.pending_receivables,
              portfolio.positions.positions['2330'].quantity)
    with pytest.raises(ValueError,match='point-in-time'):
        replay.apply_normalized_action(replace(_action(),known_at=known_at),applied_at=datetime(2026,1,5,9))
    assert before == (portfolio.cash.settled_cash,portfolio.cash.pending_receivables,
                      portfolio.positions.positions['2330'].quantity)
    assert not portfolio.corporate_actions.dividend_receivables
    assert not portfolio.corporate_actions.share_mutations


def test_normalized_cash_payment_and_source_row_alias_cannot_double_accrue(tmp_path):
    replay, portfolio = _held(tmp_path)
    cash = portfolio.cash.settled_cash
    action = _action()
    receivable = replay.apply_normalized_action(action,applied_at=datetime(2026,1,5,9))
    assert receivable.amount==200 and portfolio.cash.pending_receivables==200
    assert portfolio.cash.settled_cash==cash
    with pytest.raises(ValueError,match='duplicate'):
        replay.apply_normalized_action(replace(action,source_row=55),applied_at=datetime(2026,1,5,9))
    with pytest.raises(ValueError,match='before declared'):
        replay.pay_cash_dividend(receivable.event_id,datetime(2026,1,5,18))
    assert portfolio.cash.settled_cash==cash and portfolio.cash.pending_receivables==200
    replay.pay_cash_dividend(receivable.event_id,datetime(2026,1,6))
    with pytest.raises(KeyError):
        replay.pay_cash_dividend(receivable.event_id,datetime(2026,1,6))
    with pytest.raises(ValueError,match='duplicate'):
        replay.apply_normalized_action(action,applied_at=datetime(2026,1,6))
    assert portfolio.cash.settled_cash==cash+200 and portfolio.cash.pending_receivables==0


def test_normalized_unknown_payment_remains_receivable(tmp_path):
    replay, portfolio = _held(tmp_path)
    receivable = replay.apply_normalized_action(replace(_action(),payment_at=None),applied_at=datetime(2026,1,5,9))
    with pytest.raises(ValueError,match='UNKNOWN'):
        replay.pay_cash_dividend(receivable.event_id,datetime(2026,2,1))
    assert portfolio.cash.pending_receivables==200


def test_normalized_stock_fraction_rejects_before_share_mutation(tmp_path):
    replay, portfolio = _held(tmp_path)
    action = replace(_action(),kind=NormalizedCorporateActionKind.STOCK_DIVIDEND,
                     cash_per_share=None,share_multiplier=1.001,payment_at=None)
    with pytest.raises(ValueError,match='fractional'):
        replay.apply_normalized_action(action,applied_at=datetime(2026,1,5,9))
    assert portfolio.positions.positions['2330'].quantity==100
    assert not portfolio.corporate_actions.share_mutations
    replay.apply_normalized_action(replace(action,share_multiplier=1.01),applied_at=datetime(2026,1,5,9))
    assert portfolio.positions.positions['2330'].quantity==101


def test_new_probe_rejects_wrong_manifest_before_source_read_or_output(tmp_path):
    manifest = tmp_path/'manifest.json'
    manifest.write_text('{}')
    output = tmp_path/'result.json'
    with pytest.raises(ValueError,match='unreviewed accounting export manifest'):
        _probe_module().run_real_flow_probe(source_root=tmp_path/'absent',manifest_path=manifest,
            archive=tmp_path/'absent.zip',panel=tmp_path/'absent.parquet',output=output)
    assert not output.exists()


@pytest.fixture(scope='module')
def actual_result(tmp_path_factory):
    root = os.environ.get('ASTRAQUANT_REAL_CASE_ROOT')
    if root is None:
        pytest.skip('requires independently fixed original accounting export and S1 panel')
    workspace = Path(root)
    output = tmp_path_factory.mktemp('actual-flow')/'cases.json'
    result = _probe_module().run_real_flow_probe(
        source_root=workspace/'accounting-canonical-source',
        manifest_path=workspace/'accounting-export-37769333701/input_manifest.json',
        archive=workspace/'accounting-export-37769333701/accounting_source_inputs.zip',
        panel=workspace/'s1-37708776526/data/panel/eligibility_panel.parquet',output=output)
    # Save the actually rerun case evidence only after the bounded probe completes.
    destination = os.environ.get('ASTRAQUANT_REAL_CASE_OUTPUT')
    if destination:
        path = Path(destination); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(output.read_bytes())
    assert json.loads(output.read_text())['accounting_gate_passed'] is False
    return result


def test_actual_sizing_raw_stop_and_sma_next_open_accounting(actual_result):
    stop, sma = actual_result['cases']
    assert (stop['quantity'],sma['quantity'])==(393,473)
    assert stop['sell']['price']==pytest.approx(165.075)
    assert stop['sell']['fees']==pytest.approx(393*165.075*.005855)
    assert stop['pnl']==pytest.approx(-5462.022713625)
    assert sma['signal_day']=='2019-09-23' and sma['exit_day']=='2019-09-24'
    assert sma['sell']['price']==165 and sma['pnl']==pytest.approx(7621.3603125)
    for case in [stop,sma]:
        assert case['buy']['fees']==pytest.approx(case['buy']['price']*case['quantity']*.002855)
        assert case['final_cash']==pytest.approx(1_000_000+case['pnl'])


def test_actual_normalizer_source_row_entitlement_and_payment(actual_result):
    case = actual_result['normalized_cash']
    assert case['action']['source_row']==3334 and case['action']['cash_per_share']==6
    assert case['entitlement']['amount']==6000
    assert case['cash_after_payment']-case['cash_before']==6000
    assert set(case['rejected'])=={'duplicate_accrual','early_payment','duplicate_payment'}


def test_actual_late_announcements_rejected_while_shares_held(actual_result):
    cases = actual_result['pit_rejections']
    assert [x['action']['ticker'] for x in cases]==['3234','4550','5234']
    for case in cases:
        assert case['account_before']==case['account_after']
        assert case['account_before'][-1]==100
        assert case['rejected_before_ca_mutation']
    assert not actual_result['four_cells_executed']
