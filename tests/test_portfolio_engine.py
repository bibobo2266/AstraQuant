from datetime import datetime

from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import Fill, OrderIntent
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType


def test_buy_fill_changes_position_and_schedules_payable():
    engine = PortfolioEngine(opening_cash=100000.0)
    intent = OrderIntent(
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 1, 1, 9, 0),
        rationale="test",
    )
    engine.orders.create_from_intent(intent, "O1")
    engine.orders.submit("O1", datetime(2026, 1, 1, 9, 1))

    fill = Fill(
        fill_id="F1",
        order_id="O1",
        ticker="2330",
        side="buy",
        quantity=10,
        price=1000,
        fees=20,
        filled_at=datetime(2026, 1, 1, 9, 2),
    )
    engine.apply_fill(
        fill,
        SettlementInstruction(
            settlement_id="S1",
            due_at=datetime(2026, 1, 3),
        ),
    )

    assert engine.positions.positions["2330"].quantity == 10
    assert engine.cash.pending_payables == 10020
    assert engine.cash.settled_cash == 100000


def test_sell_fill_schedules_receivable_net_of_fees():
    engine = PortfolioEngine(opening_cash=100000.0)
    buy_intent = OrderIntent(
        intent_id="IB",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 1, 1, 9, 0),
        rationale="seed",
    )
    engine.orders.create_from_intent(buy_intent, "OB")
    engine.orders.submit("OB", datetime(2026, 1, 1, 9, 1))
    engine.apply_fill(
        Fill(
            fill_id="FB",
            order_id="OB",
            ticker="2330",
            side="buy",
            quantity=10,
            price=900,
            filled_at=datetime(2026, 1, 1, 9, 2),
        ),
        SettlementInstruction("SB", datetime(2026, 1, 3)),
    )

    sell_intent = OrderIntent(
        intent_id="IS",
        ticker="2330",
        side="sell",
        quantity=10,
        created_at=datetime(2026, 1, 2, 9, 0),
        rationale="exit",
    )
    engine.orders.create_from_intent(sell_intent, "OS")
    engine.orders.submit("OS", datetime(2026, 1, 2, 9, 1))
    engine.apply_fill(
        Fill(
            fill_id="FS",
            order_id="OS",
            ticker="2330",
            side="sell",
            quantity=10,
            price=1000,
            fees=30,
            filled_at=datetime(2026, 1, 2, 9, 2),
        ),
        SettlementInstruction("SS", datetime(2026, 1, 4)),
    )

    assert engine.positions.positions["2330"].quantity == 0
    assert engine.cash.pending_receivables == 9970


def test_portfolio_engine_dividend_receivable_shares_cash_account():
    engine = PortfolioEngine(opening_cash=100000.0)
    event = CorporateActionEvent(
        event_id="CA1",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 6, 1),
        payment_at=datetime(2026, 7, 1),
        cash_per_share=5.0,
    )

    engine.corporate_actions.accrue_cash_dividend(
        event=event,
        shares_entitled=100,
        accrued_at=datetime(2026, 6, 1),
    )

    assert engine.cash.pending_receivables == 500.0
    assert engine.cash.projected_cash == 100500.0

    engine.corporate_actions.pay_cash_dividend(
        "CA1",
        paid_at=datetime(2026, 7, 1),
    )

    assert engine.cash.pending_receivables == 0.0
    assert engine.cash.settled_cash == 100500.0
