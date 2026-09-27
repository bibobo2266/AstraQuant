from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SettlementDirection(str, Enum):
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"


@dataclass
class CashAccount:
    settled_cash: float
    pending_receivables: float = 0.0
    pending_payables: float = 0.0

    @property
    def projected_cash(self) -> float:
        return self.settled_cash + self.pending_receivables - self.pending_payables

    @property
    def available_settled_cash(self) -> float:
        return self.settled_cash


@dataclass
class Settlement:
    settlement_id: str
    amount: float
    direction: SettlementDirection
    due_at: datetime
    source_fill_id: str | None = None
    settled_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("settlement amount must be non-negative")


class SettlementLedger:
    def __init__(self, cash: CashAccount) -> None:
        self.cash = cash
        self.pending: dict[str, Settlement] = {}
        self.completed: dict[str, Settlement] = {}

    def schedule(self, settlement: Settlement) -> None:
        if settlement.settlement_id in self.pending or settlement.settlement_id in self.completed:
            raise ValueError(f"duplicate settlement id: {settlement.settlement_id}")
        self.pending[settlement.settlement_id] = settlement
        if settlement.direction is SettlementDirection.RECEIVABLE:
            self.cash.pending_receivables += settlement.amount
        else:
            self.cash.pending_payables += settlement.amount

    def settle(self, settlement_id: str, settled_at: datetime) -> Settlement:
        settlement = self.pending.pop(settlement_id)
        settlement.settled_at = settled_at

        if settlement.direction is SettlementDirection.RECEIVABLE:
            self.cash.pending_receivables -= settlement.amount
            self.cash.settled_cash += settlement.amount
        else:
            self.cash.pending_payables -= settlement.amount
            self.cash.settled_cash -= settlement.amount

        self.completed[settlement_id] = settlement
        return settlement
