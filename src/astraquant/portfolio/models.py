from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    ticker: str
    side: str
    quantity: float
    created_at: datetime
    rationale: str
    source_packet_id: str | None = None
    source_review_id: str | None = None


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    ticker: str
    side: str
    quantity: float
    price: float
    filled_at: datetime
    fees: float = 0.0


@dataclass
class Position:
    ticker: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    fills: list[Fill] = field(default_factory=list)


@dataclass(frozen=True)
class PositionShareMutation:
    event_id: str
    ticker: str
    share_multiplier: float
    effective_at: datetime
    source: str = ""

    def __post_init__(self) -> None:
        if self.share_multiplier <= 0:
            raise ValueError("share_multiplier must be positive")


@dataclass(frozen=True)
class PositionExtinguishment:
    event_id: str
    ticker: str
    effective_at: datetime
    source: str = ""



@dataclass(frozen=True)
class PositionSecurityConversion:
    event_id: str
    from_ticker: str
    to_ticker: str
    quantity_multiplier: float
    effective_at: datetime
    source: str = ""

    def __post_init__(self) -> None:
        if not self.from_ticker or not self.to_ticker:
            raise ValueError("security conversion tickers must be non-empty")
        if self.from_ticker == self.to_ticker:
            raise ValueError("security conversion requires distinct tickers")
        if self.quantity_multiplier <= 0:
            raise ValueError("quantity_multiplier must be positive")


@dataclass(frozen=True)
class SecurityConversionLeg:
    to_ticker: str
    quantity_multiplier: float
    value_weight: float

    def __post_init__(self) -> None:
        if not self.to_ticker:
            raise ValueError("successor ticker must be non-empty")
        if self.quantity_multiplier <= 0:
            raise ValueError("quantity_multiplier must be positive")
        if not 0 < self.value_weight <= 1:
            raise ValueError("value_weight must be in (0, 1]")


@dataclass(frozen=True)
class PositionCompositeConversion:
    event_id: str
    from_ticker: str
    legs: tuple[SecurityConversionLeg, ...]
    effective_at: datetime
    cash_per_source_share: float = 0.0
    cash_value_weight: float = 0.0
    source: str = ""

    def __post_init__(self) -> None:
        if not self.from_ticker:
            raise ValueError("from_ticker must be non-empty")
        if len(self.legs) < 2:
            raise ValueError("composite conversion requires at least two successor legs")
        tickers = [leg.to_ticker for leg in self.legs]
        if len(set(tickers)) != len(tickers):
            raise ValueError("composite conversion successor tickers must be unique")
        if self.from_ticker in tickers:
            raise ValueError("composite conversion successor must differ from source")
        if self.cash_per_source_share < 0:
            raise ValueError("cash_per_source_share must be non-negative")
        if not 0 <= self.cash_value_weight < 1:
            raise ValueError("cash_value_weight must be in [0, 1)")
        total = self.cash_value_weight + sum(leg.value_weight for leg in self.legs)
        if abs(total - 1.0) > 1e-9:
            raise ValueError("composite conversion value weights must sum to 1")
        if (self.cash_per_source_share > 0) != (self.cash_value_weight > 0):
            raise ValueError("cash consideration and cash_value_weight must be jointly declared")
