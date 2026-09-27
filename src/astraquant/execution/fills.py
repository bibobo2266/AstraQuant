from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
)
from astraquant.portfolio.models import Fill


class NotExecutableError(RuntimeError):
    pass


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


_FILL_USES = {PriceUse.ENTRY, PriceUse.STOP_FILL, PriceUse.EXIT}


@dataclass(frozen=True)
class ExecutionFillFactory:
    fee_model: FeeModel
    slippage_model: SlippageModel

    def create_fill(
        self,
        *,
        fill_id: str,
        order_id: str,
        ticker: str,
        side: str,
        quantity: float,
        filled_at: datetime,
        decision: ExecutionPriceDecision,
    ) -> Fill:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        side_norm = side.lower()
        if side_norm not in {"buy", "sell"}:
            raise ValueError(f"unsupported side: {side}")

        if decision.use not in _FILL_USES:
            raise ValueError(
                f"price decision use {decision.use.value} cannot create a fill"
            )

        if decision.side != side_norm:
            raise ValueError(
                f"decision side {decision.side} does not match fill side {side_norm}"
            )

        if decision.availability is not ExecutionAvailability.EXECUTABLE:
            raise NotExecutableError(
                f"cannot create fill from non-executable decision: {decision.reason}"
            )

        if decision.price is None or decision.price <= 0:
            raise NotExecutableError("executable decision must contain a positive RAW price")

        execution_price = self.slippage_model.execution_price(
            side=side_norm,
            quantity=quantity,
            reference_price=decision.price,
        )
        if execution_price <= 0:
            raise ValueError("slippage model returned non-positive execution price")

        fees = self.fee_model.fee(
            side=side_norm,
            quantity=quantity,
            price=execution_price,
        )
        if fees < 0:
            raise ValueError("fee model returned negative fees")

        return Fill(
            fill_id=fill_id,
            order_id=order_id,
            ticker=str(ticker),
            side=side_norm,
            quantity=quantity,
            price=execution_price,
            filled_at=filled_at,
            fees=fees,
        )
