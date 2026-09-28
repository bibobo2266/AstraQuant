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

