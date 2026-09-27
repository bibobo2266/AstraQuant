from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .cash import CashAccount, Settlement, SettlementDirection, SettlementLedger
from .corporate_actions import CorporateActionAccounting
from .ledger import PortfolioLedger
from .models import Fill
from .orders import OrderBook


@dataclass(frozen=True)
class SettlementInstruction:
    settlement_id: str
    due_at: datetime


class PortfolioEngine:
    """Coordinates fill effects across orders, positions, and settlement.

    Position state changes only through PortfolioLedger.apply_fill.
    Cash is not settled at fill time; a pending settlement is scheduled instead.
    """

    def __init__(self, *, opening_cash: float) -> None:
        self.orders = OrderBook()
        self.positions = PortfolioLedger()
        self.cash = CashAccount(settled_cash=opening_cash)
        self.settlements = SettlementLedger(self.cash)
        self.corporate_actions = CorporateActionAccounting(self.cash)
        self._applied_fill_ids: set[str] = set()

    def apply_fill(
        self,
        fill: Fill,
        settlement: SettlementInstruction,
    ) -> None:
        """Apply a fill only after all known failure conditions pass preflight."""

        if fill.fill_id in self._applied_fill_ids:
            raise ValueError(f"duplicate fill id: {fill.fill_id}")
        if settlement.settlement_id in self.settlements.pending or settlement.settlement_id in self.settlements.completed:
            raise ValueError(f"duplicate settlement id: {settlement.settlement_id}")
        if fill.order_id not in self.orders.orders:
            raise KeyError(fill.order_id)

        order = self.orders.orders[fill.order_id]
        if order.status.value not in {"SUBMITTED", "PARTIALLY_FILLED"}:
            raise ValueError(f"cannot fill order from status {order.status}")
        if fill.ticker != order.ticker or fill.side.lower() != order.side:
            raise ValueError("fill does not match order ticker/side")
        if fill.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if fill.quantity > order.remaining_quantity:
            raise ValueError("fill exceeds remaining order quantity")
        if fill.price <= 0:
            raise ValueError("fill price must be positive")
        if fill.fees < 0:
            raise ValueError("fill fees must be non-negative")

        gross = fill.quantity * fill.price
        side = order.side.lower()

        if side == "buy":
            direction = SettlementDirection.PAYABLE
            amount = gross + fill.fees
        elif side == "sell":
            current = self.positions.positions.get(fill.ticker)
            current_qty = current.quantity if current is not None else 0.0
            if fill.quantity > current_qty:
                raise ValueError("Cannot sell more than current position")
            direction = SettlementDirection.RECEIVABLE
            amount = gross - fill.fees
            if amount < 0:
                raise ValueError("sell fees cannot exceed gross proceeds")
        else:
            raise ValueError(f"unsupported side: {order.side}")

        pending_settlement = Settlement(
            settlement_id=settlement.settlement_id,
            amount=amount,
            direction=direction,
            due_at=settlement.due_at,
            source_fill_id=fill.fill_id,
        )

        self.orders.apply_fill(fill)
        self.positions.apply_fill(fill)
        self.settlements.schedule(pending_settlement)
        self._applied_fill_ids.add(fill.fill_id)
