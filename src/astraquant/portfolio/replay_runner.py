from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.service import (
    CanonicalExecutionService,
    ExecutedOrder,
    SignalDeclaration,
)
from astraquant.portfolio.corporate_actions import CorporateActionEvent
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.valuation import PortfolioValuation, value_portfolio


@dataclass(frozen=True)
class ReplaySnapshot:
    at: datetime
    valuation: PortfolioValuation


class CanonicalPortfolioReplay:
    """Small event-driven accounting replay over the canonical execution path.

    This runner does not generate signals or strategy decisions. It consumes
    externally supplied intents and explicit corporate-action events.
    """

    def __init__(
        self,
        *,
        execution: CanonicalExecutionService,
        portfolio: PortfolioEngine,
    ) -> None:
        if execution.portfolio is not portfolio:
            raise ValueError("execution service and replay must share one PortfolioEngine")
        self.execution = execution
        self.portfolio = portfolio
        self.executed_orders: list[ExecutedOrder] = []
        self.snapshots: list[ReplaySnapshot] = []

    def execute_trade(
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
        settlement_id: str,
        settlement_due: datetime,
    ) -> ExecutedOrder:
        out = self.execution.execute(
            intent=intent,
            signal=signal,
            order_id=order_id,
            fill_id=fill_id,
            submitted_at=submitted_at,
            session_date=session_date,
            use=use,
            field=field,
            settlement=SettlementInstruction(
                settlement_id=settlement_id,
                due_at=settlement_due,
            ),
        )
        self.executed_orders.append(out)
        return out

    def settle(self, settlement_id: str, settled_at: datetime) -> None:
        self.portfolio.settlements.settle(settlement_id, settled_at)

    def accrue_cash_dividend(
        self,
        *,
        event: CorporateActionEvent,
        accrued_at: datetime,
    ):
        position = self.portfolio.positions.positions.get(event.ticker)
        shares = 0.0 if position is None else position.quantity
        return self.portfolio.corporate_actions.accrue_cash_dividend(
            event=event,
            shares_entitled=shares,
            accrued_at=accrued_at,
        )

    def pay_cash_dividend(self, event_id: str, paid_at: datetime):
        return self.portfolio.corporate_actions.pay_cash_dividend(
            event_id,
            paid_at=paid_at,
        )

    def apply_share_mutation(
        self,
        *,
        event: CorporateActionEvent,
        applied_at: datetime,
    ):
        return self.portfolio.corporate_actions.apply_share_multiplier(
            event=event,
            positions=self.portfolio.positions,
            applied_at=applied_at,
        )

    def snapshot(
        self,
        *,
        at: datetime,
        mark_fields: Mapping[str, str] | None = None,
        mark_not_before: Mapping[str, date | datetime] | None = None,
        terminal_stale_tickers: set[str] | None = None,
        mark_ca_transforms: Mapping[str, tuple[tuple[float, float], ...]] | None = None,
    ) -> ReplaySnapshot:
        decisions = {}
        mark_fields = mark_fields or {}
        mark_not_before = mark_not_before or {}
        terminal_stale_tickers = terminal_stale_tickers or set()
        mark_ca_transforms = mark_ca_transforms or {}
        for ticker, position in self.portfolio.positions.positions.items():
            if position.quantity == 0:
                continue
            transforms = mark_ca_transforms.get(ticker, ())
            if transforms:
                decisions[ticker] = self.execution.mark_after_corporate_actions(
                    ticker=ticker,
                    session_date=at,
                    field=mark_fields.get(ticker, "close"),
                    not_before=mark_not_before.get(ticker),
                    allow_terminal_stale_without_tradability=ticker in terminal_stale_tickers,
                    transformations=transforms,
                )
            else:
                decisions[ticker] = self.execution.mark(
                    ticker=ticker,
                    session_date=at,
                    side="sell",
                    field=mark_fields.get(ticker, "close"),
                    not_before=mark_not_before.get(ticker),
                    allow_terminal_stale_without_tradability=ticker in terminal_stale_tickers,
                )

        snap = ReplaySnapshot(
            at=at,
            valuation=value_portfolio(
                cash=self.portfolio.cash,
                positions=self.portfolio.positions.positions,
                raw_mark_decisions=decisions,
            ),
        )
        self.snapshots.append(snap)
        return snap
