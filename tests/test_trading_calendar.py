from datetime import date, datetime

import pytest

from astraquant.portfolio.calendar import (
    CalendarMappingError,
    NonSessionEventPolicy,
    TradingCalendar,
)


def test_non_session_event_maps_forward_never_backward():
    cal = TradingCalendar(
        [
            date(2026, 9, 25),  # Friday
            date(2026, 9, 28),  # Monday
            date(2026, 9, 29),
        ]
    )

    assert cal.map_effective_date(date(2026, 9, 26)) == date(2026, 9, 28)
    assert cal.map_effective_date(date(2026, 9, 27)) == date(2026, 9, 28)
    assert cal.map_effective_date(date(2026, 9, 28)) == date(2026, 9, 28)


def test_require_session_policy_hard_fails_weekend_event():
    cal = TradingCalendar([date(2026, 9, 25), date(2026, 9, 28)])

    with pytest.raises(CalendarMappingError, match="not a trading session"):
        cal.map_effective_date(
            date(2026, 9, 26),
            policy=NonSessionEventPolicy.REQUIRE_SESSION,
        )


def test_shift_sessions_uses_calendar_not_calendar_days():
    cal = TradingCalendar(
        [
            date(2026, 9, 25),
            date(2026, 9, 28),
            date(2026, 9, 29),
        ]
    )

    assert cal.shift_sessions(date(2026, 9, 25), 1) == date(2026, 9, 28)
    assert cal.shift_sessions(date(2026, 9, 25), 2) == date(2026, 9, 29)


def test_mapping_after_calendar_horizon_hard_fails():
    cal = TradingCalendar([date(2026, 9, 25), date(2026, 9, 28)])

    with pytest.raises(CalendarMappingError, match="no trading session"):
        cal.map_effective_date(datetime(2026, 9, 30, 0, 0))
