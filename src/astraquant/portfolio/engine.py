from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .cash import CashAccount, Settlement, SettlementDirection, SettlementLedger
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

    def apply_fill(
        self,
        fill: Fill,
        settlement: SettlementInstruction,
    ) -> None:
        order = self.orders.orders[fill.order_id]
        self.orders.apply_fill(fill)
        self.positions.apply_fill(fill)

        gross = fill.quantity * fill.price
        side = order.side.lower()

        if side == "buy":
            direction = SettlementDirection.PAYABLE
            amount = gross + fill.fees
        elif side == "sell":
            direction = SettlementDirection.RECEIVABLE
            amount = gross - fill.fees
            if amount < 0:
                raise ValueError("sell fees cannot exceed gross proceeds")
        else:
            raise ValueError(f"unsupported side: {order.side}")

        self.settlements.schedule(
            Settlement(
                settlement_id=settlement.settlement_id,
                amount=amount,
                direction=direction,
                due_at=settlement.due_at,
                source_fill_id=fill.fill_id,
            )
        )
