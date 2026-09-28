from datetime import datetime

import pytest

from astraquant.portfolio.ledger import PortfolioLedger
from astraquant.portfolio.models import (
    Fill,
    PositionCompositeConversion,
    SecurityConversionLeg,
)
from astraquant.portfolio.trade_reconstruction import reconstruct_fifo_trades


def _fill(fill_id, ticker, side, quantity, price, when):
    return Fill(
        fill_id=fill_id,
        order_id=f"order-{fill_id}",
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        filled_at=when,
        fees=0.0,
    )


def _conversion():
    return PositionCompositeConversion(
        event_id="2823-to-2883-bundle",
        from_ticker="2823",
        legs=(
            SecurityConversionLeg(
                to_ticker="2883",
                quantity_multiplier=0.8,
                value_weight=0.3681,
            ),
            SecurityConversionLeg(
                to_ticker="2883B",
                quantity_multiplier=0.73,
                value_weight=0.2454,
            ),
        ),
        cash_per_source_share=11.5,
        cash_value_weight=0.3865,
        effective_at=datetime(2021, 12, 30),
        source="test",
    )


def test_composite_conversion_splits_position_without_fake_fill():
    ledger = PortfolioLedger()
    ledger.apply_fill(
        _fill(
            "buy-2823",
            "2823",
            "buy",
            1000,
            30.0,
            datetime(2021, 12, 1, 9),
        )
    )

    created = ledger.apply_composite_conversion(_conversion())

    assert ledger.positions["2823"].quantity == 0
    assert ledger.positions["2883"].quantity == pytest.approx(800.0)
    assert ledger.positions["2883B"].quantity == pytest.approx(730.0)
    assert len(created) == 2

    carried_cost = (
        ledger.positions["2883"].avg_cost * ledger.positions["2883"].quantity
        + ledger.positions["2883B"].avg_cost * ledger.positions["2883B"].quantity
    )
    assert carried_cost == pytest.approx(30000.0 * (0.3681 + 0.2454))


def test_composite_conversion_fifo_preserves_total_entry_basis():
    result = reconstruct_fifo_trades(
        fills=[
            _fill(
                "buy-2823",
                "2823",
                "buy",
                1000,
                30.0,
                datetime(2021, 12, 1, 9),
            ),
            _fill(
                "sell-2883",
                "2883",
                "sell",
                800,
                18.0,
                datetime(2022, 2, 1, 9),
            ),
            _fill(
                "sell-2883B",
                "2883B",
                "sell",
                730,
                11.0,
                datetime(2022, 2, 1, 9),
            ),
        ],
        composite_conversions=[_conversion()],
    )

    assert result.open_lots == ()
    assert len(result.closed_lots) == 3
    cash = [x for x in result.closed_lots if x.exit_kind == "COMPOSITE_CASH_CONSIDERATION"]
    assert len(cash) == 1

    total_entry_basis = sum(
        x.entry_price_with_fees * x.quantity for x in result.closed_lots
    )
    assert total_entry_basis == pytest.approx(30000.0)

    total_realized = sum(x.realized_pnl for x in result.closed_lots)
    expected_proceeds = 1000 * 11.5 + 800 * 18.0 + 730 * 11.0
    assert total_realized == pytest.approx(expected_proceeds - 30000.0)


def test_composite_conversion_requires_complete_value_weights():
    with pytest.raises(ValueError, match="weights must sum to 1"):
        PositionCompositeConversion(
            event_id="bad",
            from_ticker="2823",
            legs=(
                SecurityConversionLeg("2883", 0.8, 0.5),
                SecurityConversionLeg("2883B", 0.73, 0.2),
            ),
            cash_per_source_share=11.5,
            cash_value_weight=0.1,
            effective_at=datetime(2021, 12, 30),
        )
