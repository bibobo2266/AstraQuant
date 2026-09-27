from datetime import datetime

from astraquant.data.contracts import PointInTimeRecord
from astraquant.portfolio.ledger import PortfolioLedger
from astraquant.portfolio.models import Fill


def test_point_in_time_availability():
    record = PointInTimeRecord(
        ticker="2330",
        effective_at=datetime(2026, 3, 31),
        available_at=datetime(2026, 5, 10),
        recorded_at=datetime(2026, 5, 10),
        field="example",
        value=1.0,
        source="test",
    )
    assert not record.is_available(datetime(2026, 5, 9))
    assert record.is_available(datetime(2026, 5, 10))


def test_only_fill_changes_position_state():
    ledger = PortfolioLedger()
    fill = Fill(
        fill_id="f1",
        order_id="o1",
        ticker="2330",
        side="buy",
        quantity=100,
        price=1000,
        filled_at=datetime(2026, 1, 1),
    )
    position = ledger.apply_fill(fill)
    assert position.quantity == 100
    assert position.avg_cost == 1000
