from datetime import datetime

import pytest

from astraquant.portfolio.models import Fill, OrderIntent
from astraquant.portfolio.orders import OrderBook, OrderStatus


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=100,
        created_at=datetime(2026, 1, 1, 9, 0),
        rationale="test",
    )


def test_partial_then_full_fill_lifecycle():
    book = OrderBook()
    order = book.create_from_intent(_intent(), "O1")
    assert order.status is OrderStatus.CREATED

    book.submit("O1", datetime(2026, 1, 1, 9, 1))
    book.apply_fill(
        Fill(
            fill_id="F1",
            order_id="O1",
            ticker="2330",
            side="buy",
            quantity=40,
            price=1000,
            filled_at=datetime(2026, 1, 1, 9, 2),
        )
    )
    assert order.status is OrderStatus.PARTIALLY_FILLED
    assert order.remaining_quantity == 60

    book.apply_fill(
        Fill(
            fill_id="F2",
            order_id="O1",
            ticker="2330",
            side="buy",
            quantity=60,
            price=1001,
            filled_at=datetime(2026, 1, 1, 9, 3),
        )
    )
    assert order.status is OrderStatus.FILLED
    assert order.remaining_quantity == 0


def test_overfill_is_rejected():
    book = OrderBook()
    book.create_from_intent(_intent(), "O1")
    book.submit("O1", datetime(2026, 1, 1, 9, 1))

    with pytest.raises(ValueError):
        book.apply_fill(
            Fill(
                fill_id="F1",
                order_id="O1",
                ticker="2330",
                side="buy",
                quantity=101,
                price=1000,
                filled_at=datetime(2026, 1, 1, 9, 2),
            )
        )
