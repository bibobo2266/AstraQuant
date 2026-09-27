from datetime import datetime

import pytest

from astraquant.portfolio.cash import CashAccount
from astraquant.portfolio.ledger import PortfolioLedger
from astraquant.portfolio.models import Fill
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


def test_share_multiplier_preserves_total_cost_basis():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    positions = PortfolioLedger()
    positions.apply_fill(
        Fill(
            fill_id="seed",
            order_id="seed-order",
            ticker="2330",
            side="buy",
            quantity=100,
            price=1000,
            filled_at=datetime(2026, 5, 1),
        )
    )
    event = CorporateActionEvent(
        event_id="CA-SPLIT",
        ticker="2330",
        event_type=CorporateActionType.SPLIT,
        effective_at=datetime(2026, 6, 1),
        share_multiplier=2.0,
        source="official",
    )

    accounting.apply_share_multiplier(
        event=event,
        positions=positions,
        applied_at=datetime(2026, 6, 1),
    )

    pos = positions.positions["2330"]
    assert pos.quantity == 200
    assert pos.avg_cost == 500
    assert pos.quantity * pos.avg_cost == 100000


def test_capital_reduction_multiplier_reduces_quantity_and_preserves_cost_basis():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    positions = PortfolioLedger()
    positions.apply_fill(
        Fill(
            fill_id="seed2",
            order_id="seed-order2",
            ticker="2330",
            side="buy",
            quantity=100,
            price=1000,
            filled_at=datetime(2026, 5, 1),
        )
    )
    event = CorporateActionEvent(
        event_id="CA-REDUCE",
        ticker="2330",
        event_type=CorporateActionType.CAPITAL_REDUCTION,
        effective_at=datetime(2026, 6, 1),
        share_multiplier=0.5,
        source="official",
    )

    accounting.apply_share_multiplier(
        event=event,
        positions=positions,
        applied_at=datetime(2026, 6, 1),
    )

    pos = positions.positions["2330"]
    assert pos.quantity == 50
    assert pos.avg_cost == 2000
    assert pos.quantity * pos.avg_cost == 100000


def test_duplicate_share_mutation_is_rejected():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    positions = PortfolioLedger()
    event = CorporateActionEvent(
        event_id="CA-DUP",
        ticker="2330",
        event_type=CorporateActionType.SPLIT,
        effective_at=datetime(2026, 6, 1),
        share_multiplier=2.0,
    )

    accounting.apply_share_multiplier(
        event=event,
        positions=positions,
        applied_at=datetime(2026, 6, 1),
    )

    with pytest.raises(ValueError, match="duplicate"):
        accounting.apply_share_multiplier(
            event=event,
            positions=positions,
            applied_at=datetime(2026, 6, 1),
        )


def test_share_mutation_cannot_apply_before_effective_date():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    positions = PortfolioLedger()
    event = CorporateActionEvent(
        event_id="CA-EARLY",
        ticker="2330",
        event_type=CorporateActionType.SPLIT,
        effective_at=datetime(2026, 6, 1),
        share_multiplier=2.0,
    )

    with pytest.raises(ValueError, match="before effective"):
        accounting.apply_share_multiplier(
            event=event,
            positions=positions,
            applied_at=datetime(2026, 5, 31),
        )


def test_capital_reduction_cash_entitlement_uses_explicit_share_basis():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA-CASH-REDUCE",
        ticker="2330",
        event_type=CorporateActionType.CAPITAL_REDUCTION,
        effective_at=datetime(2026, 6, 1),
        payment_at=None,
        cash_per_share=2.0,
        share_multiplier=0.5,
        source="official",
    )

    receivable = accounting.accrue_cash_entitlement(
        event=event,
        shares_entitled=100,
        accrued_at=datetime(2026, 6, 1),
        component="CAPITAL_REDUCTION_REFUND",
    )

    assert receivable.amount == 200.0
    assert receivable.shares_entitled == 100
    assert cash.pending_receivables == 200.0
    assert cash.settled_cash == 1000.0

    with pytest.raises(ValueError, match="UNKNOWN"):
        accounting.pay_cash_entitlement(
            "CA-CASH-REDUCE",
            paid_at=datetime(2026, 7, 1),
        )


def test_cash_entitlement_requires_declared_component():
    cash = CashAccount(settled_cash=1000.0)
    accounting = CorporateActionAccounting(cash)
    event = CorporateActionEvent(
        event_id="CA-COMPONENT",
        ticker="2330",
        event_type=CorporateActionType.CAPITAL_REDUCTION,
        effective_at=datetime(2026, 6, 1),
        cash_per_share=2.0,
    )

    with pytest.raises(ValueError, match="component"):
        accounting.accrue_cash_entitlement(
            event=event,
            shares_entitled=100,
            accrued_at=datetime(2026, 6, 1),
            component="",
        )
