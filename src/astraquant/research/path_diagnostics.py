from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from astraquant.portfolio.corporate_actions import CashEntitlementBasis, CorporateActionType
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction


WINDOW_SESSIONS = (5, 10, 20)


class PathDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderState(str, Enum):
    MFE_FIRST = "MFE_FIRST"
    MAE_FIRST = "MAE_FIRST"
    SAME_DAY_UNKNOWN = "SAME_DAY_UNKNOWN"


class PathStatus(str, Enum):
    OK = "OK"
    CROSS_EPOCH = "CROSS_EPOCH"
    TRUNCATED_SOURCE_CALENDAR = "TRUNCATED_SOURCE_CALENDAR"
    NO_VALID_ENTRY_REF = "NO_VALID_ENTRY_REF"
    MISSING_PATH_PRICE = "MISSING_PATH_PRICE"
    MULTI_LEG_INTRADAY_UNRESOLVED = "MULTI_LEG_INTRADAY_UNRESOLVED"
    UNSUPPORTED_CA_EVENT = "UNSUPPORTED_CA_EVENT"
    INSUFFICIENT_DEMEAN_CROSS_SECTION = "INSUFFICIENT_DEMEAN_CROSS_SECTION"


@dataclass(frozen=True)
class RawBar:
    ticker: str
    session: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    observed_trade: bool
    valid_ohlc: bool

    @property
    def valid(self) -> bool:
        values = (self.open, self.high, self.low, self.close)
        return (
            self.observed_trade
            and self.valid_ohlc
            and all(np.isfinite(v) and v > 0 for v in values)
            and self.high >= max(self.open, self.close, self.low)
            and self.low <= min(self.open, self.close, self.high)
        )


@dataclass(frozen=True)
class PriceLimitObservation:
    upper: float | None = None
    lower: float | None = None
    no_limit: bool = False
    known: bool = False


@dataclass(frozen=True)
class WindowDiagnostic:
    window_sessions: int
    status: PathStatus
    raw_mfe: float | None = None
    raw_mae: float | None = None
    days_to_mfe: int | None = None
    days_to_mae: int | None = None
    order_state: OrderState | None = None
    terminal_event: bool = False
    unresolved_reason: str | None = None
    limit_touch_up_days: int = 0
    limit_touch_down_days: int = 0
    limit_close_up_days: int = 0
    limit_close_down_days: int = 0
    all_trade_at_limit_days: int = 0
    no_price_limit_days: int = 0
    limit_price_unknown_days: int = 0


def directional_extrema(
    value_high: Sequence[float],
    value_low: Sequence[float],
    *,
    direction: PathDirection | str,
) -> tuple[float, float, int, int, OrderState]:
    direction = PathDirection(direction)
    highs = np.asarray(value_high, dtype=float)
    lows = np.asarray(value_low, dtype=float)
    if len(highs) == 0 or len(highs) != len(lows):
        raise ValueError("value_high/value_low must be non-empty and aligned")
    if not np.isfinite(highs).all() or not np.isfinite(lows).all():
        raise ValueError("path values must be finite")
    if direction is PathDirection.LONG:
        favorable = highs - 1.0
        adverse = lows - 1.0
    else:
        favorable = 1.0 - lows
        adverse = 1.0 - highs
    mfe_index = int(np.argmax(favorable))
    mae_index = int(np.argmin(adverse))
    days_to_mfe = mfe_index + 1
    days_to_mae = mae_index + 1
    if days_to_mfe < days_to_mae:
        state = OrderState.MFE_FIRST
    elif days_to_mae < days_to_mfe:
        state = OrderState.MAE_FIRST
    else:
        state = OrderState.SAME_DAY_UNKNOWN
    return (
        float(favorable[mfe_index]),
        float(adverse[mae_index]),
        days_to_mfe,
        days_to_mae,
        state,
    )


def count_limit_states(
    bars: Sequence[RawBar | None],
    limits: Sequence[PriceLimitObservation],
) -> dict[str, int]:
    if len(bars) != len(limits):
        raise ValueError("bars and limits must be aligned")
    out = {
        "limit_touch_up_days": 0,
        "limit_touch_down_days": 0,
        "limit_close_up_days": 0,
        "limit_close_down_days": 0,
        "all_trade_at_limit_days": 0,
        "no_price_limit_days": 0,
        "limit_price_unknown_days": 0,
    }
    for bar, limit in zip(bars, limits):
        if limit.no_limit:
            out["no_price_limit_days"] += 1
            continue
        if not limit.known or limit.upper is None or limit.lower is None:
            out["limit_price_unknown_days"] += 1
            continue
        if bar is None or not bar.valid:
            continue
        upper = float(limit.upper)
        lower = float(limit.lower)
        at_up_high = bool(np.isclose(bar.high, upper, rtol=0.0, atol=1e-9))
        at_down_low = bool(np.isclose(bar.low, lower, rtol=0.0, atol=1e-9))
        at_up_close = bool(np.isclose(bar.close, upper, rtol=0.0, atol=1e-9))
        at_down_close = bool(np.isclose(bar.close, lower, rtol=0.0, atol=1e-9))
        if at_up_high:
            out["limit_touch_up_days"] += 1
        if at_down_low:
            out["limit_touch_down_days"] += 1
        if at_up_close:
            out["limit_close_up_days"] += 1
        if at_down_close:
            out["limit_close_down_days"] += 1
        if (
            np.isclose(bar.open, bar.high, rtol=0.0, atol=1e-9)
            and np.isclose(bar.open, bar.low, rtol=0.0, atol=1e-9)
            and np.isclose(bar.open, bar.close, rtol=0.0, atol=1e-9)
            and (
                np.isclose(bar.open, upper, rtol=0.0, atol=1e-9)
                or np.isclose(bar.open, lower, rtol=0.0, atol=1e-9)
            )
        ):
            out["all_trade_at_limit_days"] += 1
    return out


def _event_is_terminal(item: HistoricalCorporateActionInstruction) -> bool:
    return (
        item.event.event_type is CorporateActionType.MERGER
        or item.extinguish_position
        or item.successor_ticker is not None
        or bool(item.successor_legs)
        or "TERMINAL" in str(item.component or "").upper()
    )


def _apply_open_event(
    item: HistoricalCorporateActionInstruction,
    positions: dict[str, float],
    cash: float,
) -> tuple[float, bool, str | None]:
    event = item.event
    ticker = str(event.ticker)
    quantity = float(positions.get(ticker, 0.0))
    if quantity <= 0:
        return cash, False, None

    if (
        event.cash_per_share is not None
        and item.cash_share_basis_mode is CashEntitlementBasis.EXPLICIT
    ):
        return cash, _event_is_terminal(item), "UNSUPPORTED_EXPLICIT_CASH_BASIS"

    if event.cash_per_share is not None:
        cash += quantity * float(event.cash_per_share)

    if event.share_multiplier is not None:
        quantity *= float(event.share_multiplier)
        positions[ticker] = quantity

    if item.successor_ticker is not None and item.successor_legs:
        return cash, True, "INVALID_SUCCESSOR_DECLARATION"
    if item.successor_legs:
        return cash, True, PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED.value
    if item.successor_ticker is not None:
        if item.successor_multiplier is None:
            return cash, True, "MISSING_SUCCESSOR_MULTIPLIER"
        positions.pop(ticker, None)
        target = str(item.successor_ticker)
        positions[target] = positions.get(target, 0.0) + (
            quantity * float(item.successor_multiplier)
        )

    if item.extinguish_position:
        positions.pop(ticker, None)

    return cash, _event_is_terminal(item), None


def evaluate_ca_aware_unit_path(
    *,
    sessions: Sequence[pd.Timestamp],
    entry_ticker: str,
    entry_ref: float,
    direction: PathDirection | str,
    bars: Mapping[tuple[str, pd.Timestamp], RawBar],
    price_limits: Mapping[tuple[str, pd.Timestamp], PriceLimitObservation],
    open_events_by_day: Mapping[pd.Timestamp, Sequence[HistoricalCorporateActionInstruction]],
    close_events_by_day: Mapping[pd.Timestamp, Sequence[HistoricalCorporateActionInstruction]],
    terminal_stale_windows: Mapping[str, tuple[pd.Timestamp, pd.Timestamp]],
    prior_valid_close: Mapping[tuple[str, pd.Timestamp], float],
    unsupported_event_days: Mapping[str, frozenset[pd.Timestamp]] | None = None,
) -> WindowDiagnostic:
    if len(sessions) not in WINDOW_SESSIONS:
        raise ValueError("sessions must be one of the governed 5/10/20 windows")
    if not np.isfinite(entry_ref) or entry_ref <= 0:
        return WindowDiagnostic(
            window_sessions=len(sessions),
            status=PathStatus.NO_VALID_ENTRY_REF,
        )

    direction = PathDirection(direction)
    positions: dict[str, float] = {str(entry_ticker): 1.0}
    cash = 0.0
    value_high: list[float] = []
    value_low: list[float] = []
    observed_bars: list[RawBar | None] = []
    observed_limits: list[PriceLimitObservation] = []
    terminal_event = False
    unsupported_event_days = unsupported_event_days or {}

    for day_index, raw_day in enumerate(sessions):
        day = pd.Timestamp(raw_day).normalize()

        for ticker in tuple(positions):
            if day in unsupported_event_days.get(ticker, frozenset()):
                return WindowDiagnostic(
                    window_sessions=len(sessions),
                    status=PathStatus.UNSUPPORTED_CA_EVENT,
                    terminal_event=terminal_event,
                    unresolved_reason="PIT_UNSAFE_CORPORATE_ACTION",
                )

        if day_index > 0:
            for item in sorted(
                open_events_by_day.get(day, ()),
                key=lambda x: x.event.event_id,
            ):
                cash, is_terminal, reason = _apply_open_event(item, positions, cash)
                terminal_event = terminal_event or is_terminal
                if reason == PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED.value:
                    return WindowDiagnostic(
                        window_sessions=len(sessions),
                        status=PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED,
                        terminal_event=True,
                        unresolved_reason=reason,
                    )
                if reason is not None:
                    return WindowDiagnostic(
                        window_sessions=len(sessions),
                        status=PathStatus.UNSUPPORTED_CA_EVENT,
                        terminal_event=terminal_event,
                        unresolved_reason=reason,
                    )

        if len(positions) > 1:
            return WindowDiagnostic(
                window_sessions=len(sessions),
                status=PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED,
                terminal_event=True,
                unresolved_reason=PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED.value,
            )

        if not positions:
            day_high = cash
            day_low = cash
            observed_bars.append(None)
            observed_limits.append(PriceLimitObservation(known=False))
        else:
            ticker, quantity = next(iter(positions.items()))
            key = (ticker, day)
            bar = bars.get(key)
            if bar is not None and bar.valid:
                px_high = float(bar.high)
                px_low = float(bar.low)
                observed_bar = bar
            else:
                stale = terminal_stale_windows.get(ticker)
                stale_close = prior_valid_close.get(key)
                if (
                    stale is not None
                    and stale[0] <= day < stale[1]
                    and stale_close is not None
                    and np.isfinite(stale_close)
                    and stale_close > 0
                ):
                    px_high = float(stale_close)
                    px_low = float(stale_close)
                    observed_bar = None
                else:
                    return WindowDiagnostic(
                        window_sessions=len(sessions),
                        status=PathStatus.MISSING_PATH_PRICE,
                        terminal_event=terminal_event,
                        unresolved_reason="MISSING_OR_INVALID_RAW_PATH_PRICE",
                    )
            day_high = cash + float(quantity) * px_high
            day_low = cash + float(quantity) * px_low
            observed_bars.append(observed_bar)
            observed_limits.append(
                price_limits.get(key, PriceLimitObservation(known=False))
            )

        value_high.append(day_high / entry_ref)
        value_low.append(day_low / entry_ref)

        for item in sorted(
            close_events_by_day.get(day, ()),
            key=lambda x: x.event.event_id,
        ):
            cash, is_terminal, reason = _apply_open_event(item, positions, cash)
            terminal_event = terminal_event or is_terminal
            if reason == PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED.value:
                return WindowDiagnostic(
                    window_sessions=len(sessions),
                    status=PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED,
                    terminal_event=True,
                    unresolved_reason=reason,
                )
            if reason is not None:
                return WindowDiagnostic(
                    window_sessions=len(sessions),
                    status=PathStatus.UNSUPPORTED_CA_EVENT,
                    terminal_event=terminal_event,
                    unresolved_reason=reason,
                )

    raw_mfe, raw_mae, days_to_mfe, days_to_mae, order_state = directional_extrema(
        value_high,
        value_low,
        direction=direction,
    )
    limits = count_limit_states(observed_bars, observed_limits)
    return WindowDiagnostic(
        window_sessions=len(sessions),
        status=PathStatus.OK,
        raw_mfe=raw_mfe,
        raw_mae=raw_mae,
        days_to_mfe=days_to_mfe,
        days_to_mae=days_to_mae,
        order_state=order_state,
        terminal_event=terminal_event,
        **limits,
    )
