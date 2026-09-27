from datetime import datetime

import pytest

from astraquant.portfolio.cash import (
    CashAccount,
    Settlement,
    SettlementDirection,
    SettlementLedger,
)


def test_receivable_moves_from_pending_to_settled_cash():
    cash = CashAccount(settled_cash=1000.0)
    ledger = SettlementLedger(cash)
    settlement = Settlement(
        settlement_id="S1",
        amount=500.0,
        direction=SettlementDirection.RECEIVABLE,
        due_at=datetime(2026, 1, 3),
    )
    ledger.schedule(settlement)
    assert cash.settled_cash == 1000.0
    assert cash.pending_receivables == 500.0
    assert cash.projected_cash == 1500.0

    ledger.settle("S1", datetime(2026, 1, 3))
    assert cash.settled_cash == 1500.0
    assert cash.pending_receivables == 0.0


def test_payable_is_not_spendable_settled_cash_before_settlement():
    cash = CashAccount(settled_cash=1000.0)
    ledger = SettlementLedger(cash)
    ledger.schedule(
        Settlement(
            settlement_id="S2",
            amount=300.0,
            direction=SettlementDirection.PAYABLE,
            due_at=datetime(2026, 1, 3),
        )
    )
    assert cash.available_settled_cash == 1000.0
    assert cash.projected_cash == 700.0


def test_negative_settlement_rejected():
    with pytest.raises(ValueError):
        Settlement(
            settlement_id="bad",
            amount=-1.0,
            direction=SettlementDirection.PAYABLE,
            due_at=datetime(2026, 1, 3),
        )
