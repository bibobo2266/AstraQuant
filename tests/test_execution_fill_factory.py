from datetime import date, datetime

import pytest

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory, NotExecutableError
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
    RawExecutionBar,
    TradabilityState,
)


def _decision(*, availability=ExecutionAvailability.EXECUTABLE, use=PriceUse.ENTRY, side="buy", price=100.0):
    bar = RawExecutionBar(
        ticker="2330",
        session_date=date(2026, 9, 24),
        open=100.0,
        high=110.0,
        low=99.0,
        close=108.0,
    )
    trad = TradabilityState(
        ticker="2330",
        session_date=date(2026, 9, 24),
        observed_trade=True,
        valid_ohlc=True,
        buy_blocked=False,
        sell_blocked=False,
        reason="OBSERVED",
    )
    return ExecutionPriceDecision(
        availability=availability,
        use=use,
        side=side,
        field="open",
        price=price if availability is ExecutionAvailability.EXECUTABLE else None,
        reason="OK" if availability is ExecutionAvailability.EXECUTABLE else "BLOCKED",
        bar=bar,
        tradability=trad,
    )


def test_fill_factory_creates_fill_from_executable_raw_decision():
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=10),
    )

    fill = factory.create_fill(
        fill_id="f1",
        order_id="o1",
        ticker="2330",
        side="buy",
        quantity=100,
        filled_at=datetime(2026, 9, 24, 9, 0),
        decision=_decision(),
    )

    assert fill.price == pytest.approx(100.1)
    assert fill.fees == 0.0
    assert fill.quantity == 100


def test_fill_factory_rejects_non_executable_decision():
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )

    with pytest.raises(NotExecutableError):
        factory.create_fill(
            fill_id="f1",
            order_id="o1",
            ticker="2330",
            side="buy",
            quantity=100,
            filled_at=datetime(2026, 9, 24, 9, 0),
            decision=_decision(availability=ExecutionAvailability.NOT_EXECUTABLE),
        )


def test_fill_factory_rejects_non_fill_price_use():
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )

    with pytest.raises(ValueError):
        factory.create_fill(
            fill_id="f1",
            order_id="o1",
            ticker="2330",
            side="buy",
            quantity=100,
            filled_at=datetime(2026, 9, 24, 9, 0),
            decision=_decision(use=PriceUse.MARK),
        )


def test_fill_factory_rejects_side_mismatch():
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )

    with pytest.raises(ValueError):
        factory.create_fill(
            fill_id="f1",
            order_id="o1",
            ticker="2330",
            side="sell",
            quantity=100,
            filled_at=datetime(2026, 9, 24, 9, 0),
            decision=_decision(side="buy"),
        )
