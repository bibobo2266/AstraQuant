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

    def apply_normalized_action(self, action, *, applied_at: datetime):
        """Apply a source-normalized dividend through the canonical account.

        This opt-in boundary requires source knowledge by the application time
        and the effective date. It supplies no research approval or S3 receipt.
        """
        from astraquant.data.corporate_actions import NormalizedCorporateActionKind
        from astraquant.portfolio.corporate_actions import CorporateActionType
        import math

        if (action.known_at is None
                or action.known_at > applied_at
                or action.known_at.date() > action.effective_date):
            raise ValueError("normalized action is not point-in-time safe")
        if applied_at.date() < action.effective_date:
            raise ValueError("normalized action cannot apply before effective date")
        event_id = f"normalized:{action.ticker}:{action.effective_date}:{action.kind.value}"
        event = CorporateActionEvent(
            event_id=event_id, ticker=action.ticker,
            event_type=(CorporateActionType.CASH_DIVIDEND
                        if action.kind is NormalizedCorporateActionKind.CASH_DIVIDEND
                        else CorporateActionType.STOCK_DIVIDEND),
            effective_at=datetime.combine(action.effective_date, datetime.min.time()),
            known_at=action.known_at, payment_at=action.payment_at,
            cash_per_share=action.cash_per_share, share_multiplier=action.share_multiplier,
            source=action.source_name, notes=action.unit_semantics)
        if action.kind is NormalizedCorporateActionKind.CASH_DIVIDEND:
            if (action.cash_per_share is None or not math.isfinite(action.cash_per_share)
                    or action.cash_per_share <= 0 or action.share_multiplier is not None):
                raise ValueError("incomplete normalized cash dividend")
            if action.payment_at is not None and action.payment_at < event.effective_at:
                raise ValueError("normalized payment precedes entitlement")
            return self.accrue_cash_dividend(event=event, accrued_at=applied_at)
        if action.kind is not NormalizedCorporateActionKind.STOCK_DIVIDEND:
            raise ValueError("unsupported normalized action kind")
        multiplier = action.share_multiplier
        position = self.portfolio.positions.positions.get(action.ticker)
        quantity = 0 if position is None else position.quantity
        if (multiplier is None or not math.isfinite(multiplier) or multiplier <= 0
                or action.cash_per_share is not None):
            raise ValueError("incomplete normalized stock dividend")
        if not math.isclose(quantity * multiplier, round(quantity * multiplier), abs_tol=1e-8, rel_tol=0):
            raise ValueError("normalized fractional-share terms are UNKNOWN")
        return self.apply_share_mutation(event=event, applied_at=applied_at)

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
