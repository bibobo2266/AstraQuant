from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Iterable


class CalendarMappingError(RuntimeError):
    pass


class NonSessionEventPolicy(str, Enum):
    NEXT_SESSION = "NEXT_SESSION"
    REQUIRE_SESSION = "REQUIRE_SESSION"


@dataclass(frozen=True)
class TradingCalendar:
    """Canonical ordered trading-session calendar.

    Economic events are never mapped backward. A non-session effective date may
    either hard-fail or map to the first configured trading session strictly
    after that date.
    """

    sessions: tuple[date, ...]

    def __init__(self, sessions: Iterable[date | datetime]) -> None:
        normalized = tuple(
            sorted(
                {
                    value.date() if isinstance(value, datetime) else value
                    for value in sessions
                }
            )
        )
        if not normalized:
            raise ValueError("trading calendar must contain at least one session")
        object.__setattr__(self, "sessions", normalized)

    def contains(self, value: date | datetime) -> bool:
        day = value.date() if isinstance(value, datetime) else value
        idx = bisect_left(self.sessions, day)
        return idx < len(self.sessions) and self.sessions[idx] == day

    def next_session(
        self,
        value: date | datetime,
        *,
        include_same: bool = False,
    ) -> date:
        day = value.date() if isinstance(value, datetime) else value
        idx = bisect_left(self.sessions, day)
        if idx < len(self.sessions) and self.sessions[idx] == day and not include_same:
            idx += 1
        if idx >= len(self.sessions):
            raise CalendarMappingError(
                f"no trading session available after {day.isoformat()}"
            )
        return self.sessions[idx]

    def shift_sessions(self, session: date | datetime, offset: int) -> date:
        day = session.date() if isinstance(session, datetime) else session
        idx = bisect_left(self.sessions, day)
        if idx >= len(self.sessions) or self.sessions[idx] != day:
            raise CalendarMappingError(
                f"{day.isoformat()} is not a configured trading session"
            )
        target = idx + offset
        if target < 0 or target >= len(self.sessions):
            raise CalendarMappingError(
                f"session shift {offset} from {day.isoformat()} is outside calendar"
            )
        return self.sessions[target]

    def map_effective_date(
        self,
        effective_at: date | datetime,
        *,
        policy: NonSessionEventPolicy = NonSessionEventPolicy.NEXT_SESSION,
    ) -> date:
        day = effective_at.date() if isinstance(effective_at, datetime) else effective_at
        if self.contains(day):
            return day
        if policy is NonSessionEventPolicy.REQUIRE_SESSION:
            raise CalendarMappingError(
                f"economic effective date {day.isoformat()} is not a trading session"
            )
        return self.next_session(day, include_same=True)
