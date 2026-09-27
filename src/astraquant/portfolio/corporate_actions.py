from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from astraquant.portfolio.cash import CashAccount
from astraquant.portfolio.models import PositionShareMutation

if TYPE_CHECKING:
    from astraquant.portfolio.ledger import PortfolioLedger


class CorporateActionType(str, Enum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    SPLIT = "SPLIT"
    RIGHTS = "RIGHTS"
    CAPITAL_REDUCTION = "CAPITAL_REDUCTION"
    MERGER = "MERGER"
    OTHER = "OTHER"


@dataclass(frozen=True)
class CorporateActionEvent:
    event_id: str
    ticker: str
    event_type: CorporateActionType
    effective_at: datetime
    known_at: datetime | None = None
    record_at: datetime | None = None
    payment_at: datetime | None = None
    cash_per_share: float | None = None
    share_multiplier: float | None = None
    source: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.cash_per_share is not None and self.cash_per_share < 0:
            raise ValueError("cash_per_share must be non-negative")
        if self.share_multiplier is not None and self.share_multiplier <= 0:
            raise ValueError("share_multiplier must be positive")


@dataclass
class DividendReceivable:
    event_id: str
    ticker: str
    shares_entitled: float
    cash_per_share: float
    amount: float
    accrued_at: datetime
    payment_at: datetime | None
    paid_at: datetime | None = None


class CorporateActionAccounting:
    """Economic corporate-action accounting independent of adjusted prices.

    Current implemented mutation: cash-dividend receivable at effective/ex date,
    then receivable -> settled cash at payment. Unknown payment dates remain
    outstanding and are never guessed.
    """

    def __init__(self, cash: CashAccount) -> None:
        self.cash = cash
        self.dividend_receivables: dict[str, DividendReceivable] = {}
        self.completed_dividends: dict[str, DividendReceivable] = {}
        self.share_mutations: dict[str, PositionShareMutation] = {}

    def accrue_cash_dividend(
        self,
        *,
        event: CorporateActionEvent,
        shares_entitled: float,
        accrued_at: datetime,
    ) -> DividendReceivable:
        if event.event_type is not CorporateActionType.CASH_DIVIDEND:
            raise ValueError("event is not a cash dividend")
        if shares_entitled < 0:
            raise ValueError("shares_entitled must be non-negative")
        if accrued_at < event.effective_at:
            raise ValueError("cannot accrue before corporate-action effective date")
        if event.event_id in self.dividend_receivables or event.event_id in self.completed_dividends:
            raise ValueError(f"duplicate corporate-action event id: {event.event_id}")
        if event.cash_per_share is None:
            raise ValueError("cash dividend requires cash_per_share")

        amount = shares_entitled * event.cash_per_share
        receivable = DividendReceivable(
            event_id=event.event_id,
            ticker=event.ticker,
            shares_entitled=shares_entitled,
            cash_per_share=event.cash_per_share,
            amount=amount,
            accrued_at=accrued_at,
            payment_at=event.payment_at,
        )
        self.dividend_receivables[event.event_id] = receivable
        self.cash.pending_receivables += amount
        return receivable

    def pay_cash_dividend(
        self,
        event_id: str,
        *,
        paid_at: datetime,
    ) -> DividendReceivable:
        receivable = self.dividend_receivables[event_id]
        if receivable.payment_at is None:
            raise ValueError("payment_at is UNKNOWN; cannot guess settlement date")
        if paid_at < receivable.payment_at:
            raise ValueError("cannot pay dividend before declared payment date")

        self.dividend_receivables.pop(event_id)
        self.cash.pending_receivables -= receivable.amount
        self.cash.settled_cash += receivable.amount
        receivable.paid_at = paid_at
        self.completed_dividends[event_id] = receivable
        return receivable


    def apply_share_multiplier(
        self,
        *,
        event: CorporateActionEvent,
        positions: "PortfolioLedger",
        applied_at: datetime,
    ) -> PositionShareMutation:
        """Apply an explicit corporate-action share multiplier.

        Quantity changes only through this exogenous economic-event path, never
        from signals, recommendations, or human decisions.
        """

        if event.share_multiplier is None:
            raise ValueError("corporate action requires share_multiplier")
        if applied_at < event.effective_at:
            raise ValueError("cannot apply share mutation before effective date")
        if event.event_id in self.share_mutations:
            raise ValueError(f"duplicate share-mutation event id: {event.event_id}")

        mutation = PositionShareMutation(
            event_id=event.event_id,
            ticker=event.ticker,
            share_multiplier=event.share_multiplier,
            effective_at=event.effective_at,
            source=event.source,
        )
        positions.apply_share_mutation(mutation)
        self.share_mutations[event.event_id] = mutation
        return mutation
