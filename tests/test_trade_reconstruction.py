from datetime import datetime

import pytest

from astraquant.portfolio.corporate_actions import CorporateActionCashReceivable
from astraquant.portfolio.models import (
    Fill,
    PositionExtinguishment,
    PositionSecurityConversion,
    PositionShareMutation,
)
from astraquant.portfolio.trade_reconstruction import reconstruct_fifo_trades


def _fill(fill_id, ticker, side, quantity, price, when, fees=0.0):
    return Fill(
        fill_id=fill_id,
        order_id=f"order-{fill_id}",
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        filled_at=when,
        fees=fees,
    )


def test_fifo_reconstruction_follows_successor_conversion():
    result = reconstruct_fifo_trades(
        fills=[
            _fill(
                "buy-6251",
                "6251",
                "buy",
                1000,
                20.0,
                datetime(2022, 8, 12, 9),
            ),
            _fill(
                "sell-3715",
                "3715",
                "sell",
                1000,
                25.0,
                datetime(2022, 9, 1, 9),
            ),
        ],
        security_conversions=[
            PositionSecurityConversion(
                event_id="6251-to-3715",
                from_ticker="6251",
                to_ticker="3715",
                quantity_multiplier=1.0,
                effective_at=datetime(2022, 8, 25),
                source="test",
            )
        ],
    )

    assert result.open_lots == ()
    assert len(result.closed_lots) == 1
    trade = result.closed_lots[0]
    assert trade.entry_ticker == "6251"
    assert trade.exit_ticker == "3715"
    assert trade.quantity == 1000
    assert trade.realized_pnl == pytest.approx(5000.0)
    assert trade.return_on_cost == pytest.approx(0.25)


def test_fifo_reconstruction_rescales_lot_for_share_mutation():
    result = reconstruct_fifo_trades(
        fills=[
            _fill(
                "buy",
                "2330",
                "buy",
                1000,
                100.0,
                datetime(2026, 1, 2, 9),
            ),
            _fill(
                "sell",
                "2330",
                "sell",
                2000,
                60.0,
                datetime(2026, 1, 6, 9),
            ),
        ],
        share_mutations=[
            PositionShareMutation(
                event_id="split",
                ticker="2330",
                share_multiplier=2.0,
                effective_at=datetime(2026, 1, 5),
                source="test",
            )
        ],
    )

    trade = result.closed_lots[0]
    assert trade.quantity == 2000
    assert trade.entry_price_with_fees == pytest.approx(50.0)
    assert trade.realized_pnl == pytest.approx(20000.0)
    assert result.open_lots == ()


def test_fifo_reconstruction_preserves_original_fifo_across_conversion():
    result = reconstruct_fifo_trades(
        fills=[
            _fill("old-target", "3715", "buy", 100, 30.0, datetime(2022, 8, 1, 9)),
            _fill("source", "6251", "buy", 100, 20.0, datetime(2022, 8, 12, 9)),
            _fill("sell", "3715", "sell", 150, 40.0, datetime(2022, 9, 1, 9)),
        ],
        security_conversions=[
            PositionSecurityConversion(
                event_id="convert",
                from_ticker="6251",
                to_ticker="3715",
                quantity_multiplier=1.0,
                effective_at=datetime(2022, 8, 25),
                source="test",
            )
        ],
    )

    assert [x.source_fill_id for x in result.closed_lots] == [
        "old-target",
        "source",
    ]
    assert [x.quantity for x in result.closed_lots] == [100, 50]
    assert len(result.open_lots) == 1
    assert result.open_lots[0].ticker == "3715"
    assert result.open_lots[0].quantity == 50


def test_fifo_reconstruction_rejects_unmatched_successor_sell():
    with pytest.raises(ValueError, match="cannot match sell"):
        reconstruct_fifo_trades(
            fills=[
                _fill(
                    "sell",
                    "3715",
                    "sell",
                    1000,
                    25.0,
                    datetime(2022, 9, 1, 9),
                )
            ]
        )


def test_fifo_reconstruction_closes_cash_extinguishment_from_entitlement():
    event_id = "cash-merger"
    result = reconstruct_fifo_trades(
        fills=[
            _fill(
                "buy-5305",
                "5305",
                "buy",
                1000,
                30.0,
                datetime(2020, 11, 2, 9),
            )
        ],
        position_extinguishments=[
            PositionExtinguishment(
                event_id=event_id,
                ticker="5305",
                effective_at=datetime(2020, 11, 30),
                source="test",
            )
        ],
        cash_entitlements=[
            CorporateActionCashReceivable(
                event_id=event_id,
                ticker="5305",
                component="MERGER_CASHOUT",
                shares_entitled=1000,
                cash_per_share=42.5,
                amount=42500.0,
                accrued_at=datetime(2020, 11, 30),
                payment_at=datetime(2020, 12, 4),
            )
        ],
    )

    assert result.open_lots == ()
    assert len(result.closed_lots) == 1
    trade = result.closed_lots[0]
    assert trade.exit_fill_id is None
    assert trade.exit_event_id == event_id
    assert trade.exit_kind == "CASH_EXTINGUISHMENT"
    assert trade.exit_price == pytest.approx(42.5)
    assert trade.realized_pnl == pytest.approx(12500.0)
    assert trade.return_on_cost == pytest.approx(12.5 / 30.0)


def test_fifo_reconstruction_rejects_cash_extinguishment_without_entitlement():
    with pytest.raises(ValueError, match="no cash entitlement"):
        reconstruct_fifo_trades(
            fills=[
                _fill(
                    "buy-5305",
                    "5305",
                    "buy",
                    1000,
                    30.0,
                    datetime(2020, 11, 2, 9),
                )
            ],
            position_extinguishments=[
                PositionExtinguishment(
                    event_id="cash-merger",
                    ticker="5305",
                    effective_at=datetime(2020, 11, 30),
                    source="test",
                )
            ],
        )
