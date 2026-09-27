from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FeeModel(Protocol):
    def fee(self, *, side: str, quantity: float, price: float) -> float: ...


class SlippageModel(Protocol):
    def execution_price(
        self,
        *,
        side: str,
        quantity: float,
        reference_price: float,
    ) -> float: ...


@dataclass(frozen=True)
class ZeroFeeModel:
    def fee(self, *, side: str, quantity: float, price: float) -> float:
        return 0.0


@dataclass(frozen=True)
class FixedBpsSlippage:
    bps: float

    def execution_price(
        self,
        *,
        side: str,
        quantity: float,
        reference_price: float,
    ) -> float:
        if reference_price <= 0 or quantity <= 0:
            raise ValueError("reference_price and quantity must be positive")
        if side.lower() == "buy":
            direction = 1.0
        elif side.lower() == "sell":
            direction = -1.0
        else:
            raise ValueError(f"unsupported side: {side}")
        return reference_price * (1.0 + direction * self.bps / 10_000.0)


@dataclass(frozen=True)
class ExecutionAssumptions:
    price_source: str
    timing_rule: str
    liquidity_rule: str | None = None
    limit_rule: str | None = None
    partial_fill_rule: str | None = None
    settlement_rule: str | None = None
    notes: tuple[str, ...] = ()
