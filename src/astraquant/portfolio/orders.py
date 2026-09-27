from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .models import Fill, OrderIntent


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    order_id: str
    intent_id: str
    ticker: str
    side: str
    quantity: float
    created_at: datetime
    status: OrderStatus = OrderStatus.CREATED
    submitted_at: datetime | None = None
    closed_at: datetime | None = None
    reject_reason: str | None = None
    fills: list[Fill] = field(default_factory=list)

    @property
    def filled_quantity(self) -> float:
        return sum(fill.quantity for fill in self.fills)

    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity


class OrderBook:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def create_from_intent(self, intent: OrderIntent, order_id: str) -> Order:
        if order_id in self.orders:
            raise ValueError(f"duplicate order id: {order_id}")
        if intent.quantity <= 0:
            raise ValueError("order intent quantity must be positive")
        if intent.side.lower() not in {"buy", "sell"}:
            raise ValueError(f"unsupported side: {intent.side}")

        order = Order(
            order_id=order_id,
            intent_id=intent.intent_id,
            ticker=intent.ticker,
            side=intent.side.lower(),
            quantity=float(intent.quantity),
            created_at=intent.created_at,
        )
        self.orders[order_id] = order
        return order

    def submit(self, order_id: str, submitted_at: datetime) -> Order:
        order = self.orders[order_id]
        if order.status is not OrderStatus.CREATED:
            raise ValueError(f"cannot submit order from status {order.status}")
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = submitted_at
        return order

    def apply_fill(self, fill: Fill) -> Order:
        order = self.orders[fill.order_id]
        if order.status not in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError(f"cannot fill order from status {order.status}")
        if fill.ticker != order.ticker or fill.side.lower() != order.side:
            raise ValueError("fill does not match order ticker/side")
        if fill.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if fill.quantity > order.remaining_quantity:
            raise ValueError("fill exceeds remaining order quantity")

        order.fills.append(fill)
        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED
            order.closed_at = fill.filled_at
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        return order

    def cancel(self, order_id: str, cancelled_at: datetime) -> Order:
        order = self.orders[order_id]
        if order.status not in {OrderStatus.CREATED, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
            raise ValueError(f"cannot cancel order from status {order.status}")
        order.status = OrderStatus.CANCELLED
        order.closed_at = cancelled_at
        return order

    def reject(self, order_id: str, rejected_at: datetime, reason: str) -> Order:
        order = self.orders[order_id]
        if order.status is not OrderStatus.CREATED:
            raise ValueError(f"cannot reject order from status {order.status}")
        order.status = OrderStatus.REJECTED
        order.closed_at = rejected_at
        order.reject_reason = reason
        return order
