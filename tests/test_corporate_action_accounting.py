from datetime import datetime

import pytest

from astraquant.portfolio.cash import CashAccount
from astraquant.portfolio.corporate_actions import (
    CorporateActionAccounting,
    CorporateActionEvent,
    CorporateActionType,
)


def test_cash_dividend_accrues_receivable_then_moves_to_cash():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA1",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 6, 1),
        known_at=datetime(2026, 4, 15),
        payment_at=datetime(2026, 7, 1),
        cash_per_share=5.0,
        source="test",
    )

    r = accounting.accrue_cash_dividend(
        event=event,
        shares_entitled=100,
        accrued_at=datetime(2026, 6, 1),
    )

    assert r.amount == 500.0
    assert cash.settled_cash == 1000.0
    assert cash.pending_receivables == 500.0

    accounting.pay_cash_dividend("CA1", paid_at=datetime(2026, 7, 1))

    assert cash.pending_receivables == 0.0
    assert cash.settled_cash == 1500.0


def test_unknown_payment_date_remains_receivable():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA2",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 6, 1),
        cash_per_share=5.0,
    )

    accounting.accrue_cash_dividend(
        event=event,
        shares_entitled=100,
        accrued_at=datetime(2026, 6, 1),
    )

    with pytest.raises(ValueError, match="UNKNOWN"):
        accounting.pay_cash_dividend("CA2", paid_at=datetime(2026, 7, 1))

    assert cash.pending_receivables == 500.0
    assert cash.settled_cash == 1000.0


def test_cannot_accrue_before_effective_date():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA3",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 6, 1),
        payment_at=datetime(2026, 7, 1),
        cash_per_share=5.0,
    )

    with pytest.raises(ValueError):
        accounting.accrue_cash_dividend(
            event=event,
            shares_entitled=100,
            accrued_at=datetime(2026, 5, 31),
        )


def test_duplicate_event_cannot_double_accrue():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA4",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 6, 1),
        payment_at=datetime(2026, 7, 1),
        cash_per_share=5.0,
    )

    accounting.accrue_cash_dividend(
        event=event,
        shares_entitled=100,
        accrued_at=datetime(2026, 6, 1),
    )

    with pytest.raises(ValueError, match="duplicate"):
        accounting.accrue_cash_dividend(
            event=event,
            shares_entitled=100,
            accrued_at=datetime(2026, 6, 1),
        )
