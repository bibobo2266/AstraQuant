from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.calendar import NonSessionEventPolicy, TradingCalendar
from astraquant.portfolio.corporate_actions import (
    CashEntitlementBasis,
    CorporateActionEvent,
    CorporateActionType,
)
from astraquant.portfolio.models import OrderIntent, SecurityConversionLeg
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay, ReplaySnapshot


@dataclass(frozen=True)
class HistoricalTradeInstruction:
    intent: OrderIntent
    signal: SignalDeclaration
    order_id: str
    fill_id: str
    submitted_at: datetime
    session_date: date
    use: PriceUse
    field: str
    settlement_id: str
    settlement_due: datetime


@dataclass(frozen=True)
class HistoricalCorporateActionInstruction:
    event: CorporateActionEvent
    applied_at: datetime
    component: str | None = None
    cash_share_basis: float | None = None
    cash_share_basis_mode: CashEntitlementBasis = CashEntitlementBasis.EXPLICIT
    terminal_stale_from: date | None = None
    extinguish_position: bool = False
    successor_ticker: str | None = None
    successor_multiplier: float | None = None
    successor_legs: tuple[SecurityConversionLeg, ...] = ()
    cash_value_weight: float = 0.0


@dataclass(frozen=True)
class HistoricalSessionResult:
    session_date: date
    trades_executed: int
    corporate_actions_applied: int
    settlements_completed: int
    snapshot: ReplaySnapshot


@dataclass(frozen=True)
class HistoricalReplayResult:
    sessions: tuple[HistoricalSessionResult, ...]
    total_trades: int
    total_corporate_actions: int
    total_settlements: int


class HistoricalReplayError(RuntimeError):
    pass


class HistoricalPortfolioRunner:
    """Chronological session runner over CanonicalPortfolioReplay.

    Event ordering for a session:
      1. settle previously-due trade settlements;
      2. apply effective corporate actions to opening holdings;
      3. execute scheduled trades;
      4. take an end-of-session RAW NAV snapshot.

    It does not generate signals, select securities, optimize parameters, or
    compute performance metrics.
    """

    def __init__(
        self,
        replay: CanonicalPortfolioReplay,
        *,
        non_session_ca_policy: NonSessionEventPolicy = NonSessionEventPolicy.NEXT_SESSION,
    ) -> None:
        self.replay = replay
        self.non_session_ca_policy = non_session_ca_policy

    @staticmethod
    def _day(value: date | datetime) -> date:
        return value.date() if isinstance(value, datetime) else value

    def run(
        self,
        *,
        sessions: Iterable[date],
        trades: Iterable[HistoricalTradeInstruction] = (),
        corporate_actions: Iterable[HistoricalCorporateActionInstruction] = (),
    ) -> HistoricalReplayResult:
        trading_calendar = TradingCalendar(sessions)
        calendar = trading_calendar.sessions

        trade_by_day: dict[date, list[HistoricalTradeInstruction]] = {}
        for trade in trades:
            if trade.use not in {PriceUse.ENTRY, PriceUse.STOP_FILL, PriceUse.EXIT}:
                raise ValueError(f"unsupported historical fill use: {trade.use.value}")
            trade_by_day.setdefault(trade.session_date, []).append(trade)

        ca_by_day: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        close_ca_by_day: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        for item in corporate_actions:
            if item.applied_at < item.event.effective_at:
                raise ValueError(
                    f"corporate action {item.event.event_id} cannot apply before effective date"
                )
            mapped_day = trading_calendar.map_effective_date(
                item.event.effective_at,
                policy=self.non_session_ca_policy,
            )
            target = close_ca_by_day if item.apply_at_close else ca_by_day
            target.setdefault(mapped_day, []).append(item)

        known_days = set(calendar)
        unknown_trade_days = set(trade_by_day) - known_days
        if unknown_trade_days:
            raise HistoricalReplayError(
                f"trade instructions outside session calendar: {sorted(unknown_trade_days)}"
            )
        results: list[HistoricalSessionResult] = []
        total_trades = 0
        total_ca = 0
        total_settlements = 0

        for session_day in calendar:
            session_start = datetime.combine(session_day, datetime.min.time())

            due_ids = sorted(
                settlement_id
                for settlement_id, settlement in self.replay.portfolio.settlements.pending.items()
                if settlement.due_at <= session_start
            )
            for settlement_id in due_ids:
                self.replay.settle(settlement_id, session_start)
            total_settlements += len(due_ids)

            ca_count = 0
            for item in ca_by_day.get(session_day, ()):
                event = item.event
                economic_apply_at = max(item.applied_at, session_start)
                position = self.replay.portfolio.positions.positions.get(event.ticker)
                opening_shares = 0.0 if position is None else position.quantity

                # Cash entitlements are accrued from opening/pre-mutation shares
                # before any same-event share multiplier changes quantity.
                if event.cash_per_share is not None:
                    if event.event_type is CorporateActionType.CASH_DIVIDEND:
                        self.replay.accrue_cash_dividend(
                            event=event,
                            accrued_at=economic_apply_at,
                        )
                    else:
                        if not item.component:
                            raise HistoricalReplayError(
                                f"cash component required for event {event.event_id}"
                            )
                        if item.cash_share_basis_mode is CashEntitlementBasis.OPENING_POSITION:
                            shares_entitled = opening_shares
                        else:
                            if item.cash_share_basis is None:
                                raise HistoricalReplayError(
                                    f"cash_share_basis required for event {event.event_id}"
                                )
                            shares_entitled = item.cash_share_basis
                        self.replay.portfolio.corporate_actions.accrue_cash_entitlement(
                            event=event,
                            shares_entitled=shares_entitled,
                            accrued_at=economic_apply_at,
                            component=item.component,
                        )

                if event.share_multiplier is not None:
                    self.replay.apply_share_mutation(
                        event=event,
                        applied_at=economic_apply_at,
                    )
                if item.successor_ticker is not None and item.successor_legs:
                    raise HistoricalReplayError(
                        f"event {event.event_id} cannot declare both single and composite successors"
                    )
                if item.successor_ticker is not None:
                    if item.successor_multiplier is None:
                        raise HistoricalReplayError(
                            f"successor_multiplier required for event {event.event_id}"
                        )
                    self.replay.portfolio.corporate_actions.convert_security(
                        event=event,
                        positions=self.replay.portfolio.positions,
                        to_ticker=item.successor_ticker,
                        quantity_multiplier=item.successor_multiplier,
                        applied_at=economic_apply_at,
                    )
                if item.successor_legs:
                    self.replay.portfolio.corporate_actions.convert_security_composite(
                        event=event,
                        positions=self.replay.portfolio.positions,
                        legs=item.successor_legs,
                        cash_value_weight=item.cash_value_weight,
                        applied_at=economic_apply_at,
                    )
                if item.extinguish_position:
                    self.replay.portfolio.corporate_actions.extinguish_position(
                        event=event,
                        positions=self.replay.portfolio.positions,
                        applied_at=economic_apply_at,
                    )
                ca_count += 1
            trade_count = 0
            for trade in sorted(
                trade_by_day.get(session_day, ()),
                key=lambda x: (x.submitted_at, x.order_id),
            ):
                self.replay.execute_trade(
                    intent=trade.intent,
                    signal=trade.signal,
                    order_id=trade.order_id,
                    fill_id=trade.fill_id,
                    submitted_at=trade.submitted_at,
                    session_date=trade.session_date,
                    use=trade.use,
                    field=trade.field,
                    settlement_id=trade.settlement_id,
                    settlement_due=trade.settlement_due,
                )
                trade_count += 1
            total_trades += trade_count

            for item in sorted(
                close_ca_by_day.get(session_day, ()),
                key=lambda x: x.event.event_id,
            ):
                event = item.event
                if (
                    not item.extinguish_position
                    or event.cash_per_share is None
                    or not item.component
                    or item.successor_ticker is not None
                    or item.successor_legs
                    or event.share_multiplier is not None
                ):
                    raise HistoricalReplayError(
                        "close-applied corporate actions are restricted to "
                        f"cash extinguishments: {event.event_id}"
                    )
                close_at = datetime.combine(session_day, datetime.max.time())
                economic_apply_at = max(item.applied_at, close_at)
                position = self.replay.portfolio.positions.positions.get(event.ticker)
                closing_shares = 0.0 if position is None else position.quantity
                self.replay.portfolio.corporate_actions.accrue_cash_entitlement(
                    event=event,
                    shares_entitled=closing_shares,
                    accrued_at=economic_apply_at,
                    component=item.component,
                )
                self.replay.portfolio.corporate_actions.extinguish_position(
                    event=event,
                    positions=self.replay.portfolio.positions,
                    applied_at=economic_apply_at,
                )
                ca_count += 1

            total_ca += ca_count

            snapshot = self.replay.snapshot(
                at=datetime.combine(session_day, datetime.max.time()),
            )
            results.append(
                HistoricalSessionResult(
                    session_date=session_day,
                    trades_executed=trade_count,
                    corporate_actions_applied=ca_count,
                    settlements_completed=len(due_ids),
                    snapshot=snapshot,
                )
            )

        return HistoricalReplayResult(
            sessions=tuple(results),
            total_trades=total_trades,
            total_corporate_actions=total_ca,
            total_settlements=total_settlements,
        )
