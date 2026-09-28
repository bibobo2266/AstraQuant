import pytest

from astraquant.execution.assumptions import FixedBpsFeeModel, FixedBpsSlippage, ZeroFeeModel


def test_buy_slippage_moves_price_against_buyer():
    model = FixedBpsSlippage(bps=10)
    assert model.execution_price(side="buy", quantity=1, reference_price=100) == pytest.approx(100.1)


def test_sell_slippage_moves_price_against_seller():
    model = FixedBpsSlippage(bps=10)
    assert model.execution_price(side="sell", quantity=1, reference_price=100) == pytest.approx(99.9)


def test_zero_fee_model_is_explicit():
    assert ZeroFeeModel().fee(side="buy", quantity=100, price=50) == 0.0


def test_fixed_bps_fee_model():
    model = FixedBpsFeeModel(bps=25)
    assert model.fee(side="buy", quantity=1000, price=50) == pytest.approx(125.0)
    assert model.fee(side="sell", quantity=1000, price=50) == pytest.approx(125.0)


def test_fixed_bps_fee_rejects_negative_bps():
    with pytest.raises(ValueError):
        FixedBpsFeeModel(bps=-1)
