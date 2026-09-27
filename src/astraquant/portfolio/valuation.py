from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.market_data import ExecutionAvailability, ExecutionPriceDecision
from astraquant.portfolio.cash import CashAccount
from astraquant.portfolio.models import Position


class ValuationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PositionValuation:
    ticker: str
    quantity: float
    raw_mark: float
    market_value: float


@dataclass(frozen=True)
class PortfolioValuation:
    settled_cash: float
    pending_receivables: float
    pending_payables: float
    market_value: float
    nav: float
    positions: tuple[PositionValuation, ...]


def value_portfolio(
    *,
    cash: CashAccount,
    positions: Mapping[str, Position],
    raw_mark_decisions: Mapping[str, ExecutionPriceDecision],
) -> PortfolioValuation:
    """Value open positions only from executable RAW MARK decisions."""

    valued: list[PositionValuation] = []
    market_value = 0.0

    for ticker, position in positions.items():
        if position.quantity == 0:
            continue
        if position.quantity < 0:
            raise ValuationError(f"negative position quantity is unsupported: {ticker}")

        decision = raw_mark_decisions.get(ticker)
        if decision is None:
            raise ValuationError(f"missing RAW mark decision for {ticker}")
        if decision.use is not PriceUse.MARK:
            raise ValuationError(f"mark decision for {ticker} has use={decision.use.value}")
        if decision.availability is not ExecutionAvailability.EXECUTABLE:
            raise ValuationError(
                f"RAW mark for {ticker} is not available: {decision.reason}"
            )
        if decision.price is None or decision.price <= 0:
            raise ValuationError(f"RAW mark for {ticker} is non-positive or missing")
        if decision.bar is not None and decision.bar.ticker != str(ticker):
            raise ValuationError(
                f"RAW mark ticker mismatch: expected {ticker}, got {decision.bar.ticker}"
            )

        mv = position.quantity * decision.price
        valued.append(
            PositionValuation(
                ticker=str(ticker),
                quantity=position.quantity,
                raw_mark=decision.price,
                market_value=mv,
            )
        )
        market_value += mv

    nav = (
        cash.settled_cash
        + cash.pending_receivables
        - cash.pending_payables
        + market_value
    )

    return PortfolioValuation(
        settled_cash=cash.settled_cash,
        pending_receivables=cash.pending_receivables,
        pending_payables=cash.pending_payables,
        market_value=market_value,
        nav=nav,
        positions=tuple(valued),
    )
