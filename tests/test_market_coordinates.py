import pytest

from astraquant.data.market_coordinates import (
    CoordinateViolation,
    PriceCoordinate,
    PriceUse,
    SignalPriceSemantics,
    require_price_coordinate,
)


@pytest.mark.parametrize(
    "use",
    [
        PriceUse.ENTRY,
        PriceUse.STOP_OBSERVATION,
        PriceUse.STOP_FILL,
        PriceUse.EXIT,
        PriceUse.SIZING,
        PriceUse.MARK,
        PriceUse.CASH_PNL,
    ],
)
def test_execution_and_accounting_uses_require_raw(use):
    require_price_coordinate(use=use, coordinate=PriceCoordinate.RAW_EXECUTION)

    with pytest.raises(CoordinateViolation):
        require_price_coordinate(
            use=use,
            coordinate=PriceCoordinate.ADJUSTED_RESEARCH,
        )


def test_signal_requires_declared_semantics():
    with pytest.raises(CoordinateViolation):
        require_price_coordinate(
            use=PriceUse.SIGNAL,
            coordinate=PriceCoordinate.ADJUSTED_RESEARCH,
        )


def test_adjusted_signal_allowed_when_not_raw_required():
    require_price_coordinate(
        use=PriceUse.SIGNAL,
        coordinate=PriceCoordinate.ADJUSTED_RESEARCH,
        signal_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )
    require_price_coordinate(
        use=PriceUse.SIGNAL,
        coordinate=PriceCoordinate.ADJUSTED_RESEARCH,
        signal_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
    )


def test_raw_required_signal_rejects_adjusted():
    with pytest.raises(CoordinateViolation):
        require_price_coordinate(
            use=PriceUse.SIGNAL,
            coordinate=PriceCoordinate.ADJUSTED_RESEARCH,
            signal_semantics=SignalPriceSemantics.RAW_REQUIRED,
        )

    require_price_coordinate(
        use=PriceUse.SIGNAL,
        coordinate=PriceCoordinate.RAW_EXECUTION,
        signal_semantics=SignalPriceSemantics.RAW_REQUIRED,
    )
