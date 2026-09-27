from __future__ import annotations

from enum import Enum


class PriceCoordinate(str, Enum):
    RAW_EXECUTION = "RAW_EXECUTION"
    ADJUSTED_RESEARCH = "ADJUSTED_RESEARCH"


class PriceUse(str, Enum):
    SIGNAL = "SIGNAL"
    ENTRY = "ENTRY"
    STOP_OBSERVATION = "STOP_OBSERVATION"
    STOP_FILL = "STOP_FILL"
    EXIT = "EXIT"
    SIZING = "SIZING"
    MARK = "MARK"
    CASH_PNL = "CASH_PNL"


class SignalPriceSemantics(str, Enum):
    SCALE_INVARIANT = "SCALE_INVARIANT"
    SCALE_SENSITIVE = "SCALE_SENSITIVE"
    RAW_REQUIRED = "RAW_REQUIRED"


class CoordinateViolation(ValueError):
    pass


_EXECUTION_USES = {
    PriceUse.ENTRY,
    PriceUse.STOP_OBSERVATION,
    PriceUse.STOP_FILL,
    PriceUse.EXIT,
    PriceUse.SIZING,
    PriceUse.MARK,
    PriceUse.CASH_PNL,
}


def require_price_coordinate(
    *,
    use: PriceUse,
    coordinate: PriceCoordinate,
    signal_semantics: SignalPriceSemantics | None = None,
) -> None:
    """Enforce AstraQuant's RAW/adjusted coordinate boundary.

    Execution/accounting uses are RAW-only. Signal use may use adjusted research
    prices unless the feature explicitly declares RAW_REQUIRED.
    """

    if use in _EXECUTION_USES:
        if coordinate is not PriceCoordinate.RAW_EXECUTION:
            raise CoordinateViolation(
                f"{use.value} requires RAW_EXECUTION; got {coordinate.value}"
            )
        return

    if use is PriceUse.SIGNAL:
        if signal_semantics is None:
            raise CoordinateViolation("SIGNAL requires explicit signal_semantics")
        if (
            signal_semantics is SignalPriceSemantics.RAW_REQUIRED
            and coordinate is not PriceCoordinate.RAW_EXECUTION
        ):
            raise CoordinateViolation(
                "RAW_REQUIRED signal semantics require RAW_EXECUTION"
            )
        return

    raise CoordinateViolation(f"unsupported price use: {use}")
