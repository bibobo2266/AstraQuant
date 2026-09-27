from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.execution.fills import ExecutionFillFactory, NotExecutableError
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionMarketData,
    ExecutionPriceDecision,
)
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import Fill, OrderIntent


@dataclass(frozen=True)
class SignalDeclaration:
    source: str
    price_semantics: SignalPriceSemantics

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("signal source must be declared")


@dataclass(frozen=True)
class ExecutedOrder:
    intent_id: str
    order_id: str
    fill: Fill
    raw_decision: ExecutionPriceDecision


class CanonicalExecutionService:
    """Canonical AstraQuant execution path.

    Signal generation is external. Once an approved/simulated intent reaches
    this service, every economic price is resolved from RAW market data with
    tradability enforcement, then converted into a Fill through the governed
    fill factory and applied through PortfolioEngine.
    """

    def __init__(
        self,
        *,
        market_data: ExecutionMarketData,
        fill_factory: ExecutionFillFactory,
        portfolio: PortfolioEngine,
    ) -> None:
        self.market_data = market_data
        self.fill_factory = fill_factory
        self.portfolio = portfolio

    def sizing_price(
        self,
        *,
        ticker: str,
        session_date: date | datetime,
        side: str,
        field: str,
        signal: SignalDeclaration,
    ) -> ExecutionPriceDecision:
        _ = signal
        return self.market_data.resolve(
            ticker=ticker,
            session_date=session_date,
            side=side,
            use=PriceUse.SIZING,
            field=field,
        )

    def stop_observation(
        self,
        *,
        ticker: str,
        session_date: date | datetime,
        side: str,
        field: str = "low",
    ) -> ExecutionPriceDecision:
        return self.market_data.resolve(
            ticker=ticker,
            session_date=session_date,
            side=side,
            use=PriceUse.STOP_OBSERVATION,
            field=field,
        )

    def mark(
        self,
        *,
        ticker: str,
        session_date: date | datetime,
        side: str = "sell",
        field: str = "close",
    ) -> ExecutionPriceDecision:
        return self.market_data.resolve(
            ticker=ticker,
            session_date=session_date,
            side=side,
            use=PriceUse.MARK,
            field=field,
        )

    def execute(
        self,
        *,
        intent: OrderIntent,
        signal: SignalDeclaration,
        order_id: str,
        fill_id: str,
        submitted_at: datetime,
        session_date: date | datetime,
        use: PriceUse,
        field: str,
        settlement: SettlementInstruction,
    ) -> ExecutedOrder:
        if use not in {PriceUse.ENTRY, PriceUse.STOP_FILL, PriceUse.EXIT}:
            raise ValueError(f"{use.value} cannot execute an order")

        _ = signal
        decision = self.market_data.resolve(
            ticker=intent.ticker,
            session_date=session_date,
            side=intent.side,
            use=use,
            field=field,
        )
        if decision.availability is not ExecutionAvailability.EXECUTABLE:
            raise NotExecutableError(
                f"intent {intent.intent_id} is not executable: {decision.reason}"
            )

        fill = self.fill_factory.create_fill(
            fill_id=fill_id,
            order_id=order_id,
            ticker=intent.ticker,
            side=intent.side,
            quantity=intent.quantity,
            filled_at=submitted_at,
            decision=decision,
        )

        self.portfolio.orders.create_from_intent(intent, order_id)
        self.portfolio.orders.submit(order_id, submitted_at)
        self.portfolio.apply_fill(fill, settlement)

        return ExecutedOrder(
            intent_id=intent.intent_id,
            order_id=order_id,
            fill=fill,
            raw_decision=decision,
        )
