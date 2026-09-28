from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.fills import NotExecutableError
from astraquant.execution.market_data import ExecutionAvailability
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.calendar import TradingCalendar
from astraquant.portfolio.corporate_actions import CashEntitlementBasis, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.policy import EntryCandidate, PortfolioIntentPolicy
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay, ReplaySnapshot
from astraquant.portfolio.valuation import value_portfolio


@dataclass(frozen=True)
class StrategySimulationConfig:
    settlement_lag_sessions: int = 2

    def __post_init__(self) -> None:
        if self.settlement_lag_sessions < 0:
            raise ValueError("settlement_lag_sessions must be non-negative")


@dataclass(frozen=True)
class StrategySessionAudit:
    session_date: date
    signals_for_open: int
    entries_executed: int
    entries_skipped: int
    stop_exits: int
    max_hold_exits: int
    settlements_completed: int
    corporate_actions_applied: int
    snapshot: ReplaySnapshot


@dataclass(frozen=True)
class StrategySimulationResult:
    sessions: tuple[StrategySessionAudit, ...]
    total_entries: int
    total_stop_exits: int
    total_max_hold_exits: int
    total_entry_skips: int
    total_blocked_exits: int
    total_corporate_actions: int


class CanonicalStrategySimulator:
    """Causal strategy-intent simulator over canonical RAW accounting.

    Causal session ordering:
      1. settle due cash movements;
      2. apply effective corporate actions to opening holdings;
      3. at the open, size/execute candidates from the prior signal session;
      4. during the session, evaluate RAW stops for positions held before today;
      5. at the close, apply max-hold exits;
      6. take a RAW close NAV snapshot.

    Intraday stop outcomes never free capacity or cash for the same session's
    opening entries.
    """

    def __init__(
        self,
        *,
        execution: CanonicalExecutionService,
        portfolio: PortfolioEngine,
        policy: PortfolioIntentPolicy,
        signal: SignalDeclaration,
        config: StrategySimulationConfig | None = None,
    ) -> None:
        if execution.portfolio is not portfolio:
            raise ValueError("execution and simulator must share PortfolioEngine")
        self.execution = execution
        self.portfolio = portfolio
        self.policy = policy
        self.signal = signal
        self.config = config or StrategySimulationConfig()
        self.replay = CanonicalPortfolioReplay(
            execution=execution,
            portfolio=portfolio,
        )

    @staticmethod
    def _normalize_signals(signals: pd.DataFrame) -> pd.DataFrame:
        required = {"signal_date", "stock_id"}
        missing = sorted(required - set(signals.columns))
        if missing:
            raise ValueError(f"signals missing columns: {missing}")

        out = signals[["signal_date", "stock_id"]].copy()
        out["signal_date"] = pd.to_datetime(
            out["signal_date"], errors="coerce"
        ).dt.normalize()
        out["stock_id"] = out["stock_id"].astype(str)
        if out[["signal_date", "stock_id"]].isna().any(axis=1).any():
            raise ValueError("signals contain null logical keys")
        if out.duplicated(["signal_date", "stock_id"]).any():
            raise ValueError("signals contain duplicate (signal_date, stock_id)")
        return out.sort_values(["signal_date", "stock_id"]).reset_index(drop=True)

    @staticmethod
    def _session_start(day: date) -> datetime:
        return datetime.combine(day, datetime.min.time())

    def _settlement_due(
        self,
        *,
        sessions: tuple[date, ...],
        session_index: int,
    ) -> datetime:
        target = session_index + self.config.settlement_lag_sessions
        if target < len(sessions):
            return self._session_start(sessions[target])
        return self._session_start(sessions[-1]) + timedelta(
            days=self.config.settlement_lag_sessions + 7
        )

    def _opening_nav(self, day: date) -> float:
        decisions = {}
        for ticker, position in self.portfolio.positions.positions.items():
            if position.quantity == 0:
                continue
            decisions[ticker] = self.execution.mark(
                ticker=ticker,
                session_date=day,
                side="sell",
                field="open",
            )
        return value_portfolio(
            cash=self.portfolio.cash,
            positions=self.portfolio.positions.positions,
            raw_mark_decisions=decisions,
        ).nav

    def run(
        self,
        *,
        sessions: list[date],
        signals: pd.DataFrame,
        corporate_actions: list[HistoricalCorporateActionInstruction] | None = None,
    ) -> StrategySimulationResult:
        trading_calendar = TradingCalendar(sessions)
        calendar = trading_calendar.sessions

        normalized_signals = self._normalize_signals(signals)
        session_index = {day: i for i, day in enumerate(calendar)}

        entry_signals: dict[date, list[str]] = {}
        for row in normalized_signals.itertuples(index=False):
            signal_day = pd.Timestamp(row.signal_date).date()
            idx = session_index.get(signal_day)
            if idx is None or idx + 1 >= len(calendar):
                continue
            entry_signals.setdefault(calendar[idx + 1], []).append(str(row.stock_id))

        ca_by_day: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        for item in corporate_actions or []:
            if item.applied_at < item.event.effective_at:
                raise ValueError(
                    f"corporate action {item.event.event_id} cannot apply before effective date"
                )
            day = trading_calendar.map_effective_date(item.event.effective_at)
            ca_by_day.setdefault(day, []).append(item)

        audits: list[StrategySessionAudit] = []
        total_entries = 0
        total_stop_exits = 0
        total_max_hold_exits = 0
        total_entry_skips = 0
        total_blocked_exits = 0
        total_ca = 0

        for idx, day in enumerate(calendar):
            start = self._session_start(day)

            due = sorted(
                settlement_id
                for settlement_id, settlement in self.portfolio.settlements.pending.items()
                if settlement.due_at <= start
            )
            for settlement_id in due:
                self.replay.settle(settlement_id, start)

            ca_count = 0
            for item in sorted(
                ca_by_day.get(day, []),
                key=lambda x: x.event.event_id,
            ):
                event = item.event
                economic_apply_at = max(item.applied_at, start)
                position = self.portfolio.positions.positions.get(event.ticker)
                opening_shares = 0.0 if position is None else position.quantity

                if event.cash_per_share is not None:
                    if event.event_type is CorporateActionType.CASH_DIVIDEND:
                        self.portfolio.corporate_actions.accrue_cash_dividend(
                            event=event,
                            shares_entitled=opening_shares,
                            accrued_at=economic_apply_at,
                        )
                    else:
                        if not item.component:
                            raise ValueError(
                                f"cash component missing for {event.event_id}"
                            )
                        if item.cash_share_basis_mode is CashEntitlementBasis.OPENING_POSITION:
                            shares_entitled = opening_shares
                        else:
                            if item.cash_share_basis is None:
                                raise ValueError(
                                    f"cash_share_basis missing for {event.event_id}"
                                )
                            shares_entitled = item.cash_share_basis
                        self.portfolio.corporate_actions.accrue_cash_entitlement(
                            event=event,
                            shares_entitled=shares_entitled,
                            accrued_at=economic_apply_at,
                            component=item.component,
                        )

                if event.share_multiplier is not None:
                    self.portfolio.corporate_actions.apply_share_multiplier(
                        event=event,
                        positions=self.portfolio.positions,
                        applied_at=economic_apply_at,
                    )

                self.policy.apply_corporate_action(event)
                ca_count += 1
            total_ca += ca_count

            held_before_open = set(self.policy.managed_positions)

            tickers = sorted(set(entry_signals.get(day, [])))
            candidates: list[EntryCandidate] = []
            for ticker in tickers:
                sizing = self.execution.sizing_price(
                    ticker=ticker,
                    session_date=day,
                    side="buy",
                    field="open",
                    signal=self.signal,
                )
                candidates.append(
                    EntryCandidate(
                        ticker=ticker,
                        sizing_decision=sizing,
                    )
                )

            opening_nav = self._opening_nav(day)
            planned, skipped = self.policy.plan_entries(
                candidates=candidates,
                session_index=idx,
                current_nav=opening_nav,
                available_cash=self.portfolio.cash.available_to_commit_cash,
            )
            entry_skips = len(skipped)

            entries = 0
            for n, plan in enumerate(planned):
                intent = OrderIntent(
                    intent_id=f"entry:{day}:{plan.ticker}:{n}",
                    ticker=plan.ticker,
                    side="buy",
                    quantity=plan.quantity,
                    created_at=start,
                    rationale="canonical breakout entry",
                )
                try:
                    out = self.execution.execute(
                        intent=intent,
                        signal=self.signal,
                        order_id=f"order:entry:{day}:{plan.ticker}:{n}",
                        fill_id=f"fill:entry:{day}:{plan.ticker}:{n}",
                        submitted_at=start,
                        session_date=day,
                        use=PriceUse.ENTRY,
                        field="open",
                        settlement=SettlementInstruction(
                            settlement_id=f"settle:entry:{day}:{plan.ticker}:{n}",
                            due_at=self._settlement_due(
                                sessions=calendar,
                                session_index=idx,
                            ),
                        ),
                    )
                except NotExecutableError:
                    entry_skips += 1
                    continue

                self.policy.register_entry(
                    ticker=plan.ticker,
                    quantity=out.fill.quantity,
                    fill_price=out.fill.price,
                    session_index=idx,
                )
                entries += 1
            total_entries += entries
            total_entry_skips += entry_skips

            stop_exits = 0
            max_hold_exits = 0

            # Stops are evaluated after open-entry decisions, so intraday lows
            # cannot free same-open capacity/cash. New entries start stop checks
            # on the following session, preserving the legacy one-session delay.
            for ticker in sorted(held_before_open):
                state = self.policy.managed_positions.get(ticker)
                if state is None:
                    continue
                decision = self.execution.market_data.resolve_stop_fill(
                    ticker=ticker,
                    session_date=day,
                    stop_price=state.stop_price,
                    side="sell",
                )
                if decision.availability is ExecutionAvailability.EXECUTABLE:
                    intent = OrderIntent(
                        intent_id=f"stop:{day}:{ticker}",
                        ticker=ticker,
                        side="sell",
                        quantity=state.quantity,
                        created_at=start,
                        rationale="canonical RAW stop",
                    )
                    try:
                        self.execution.execute_stop(
                            intent=intent,
                            signal=self.signal,
                            order_id=f"order:stop:{day}:{ticker}",
                            fill_id=f"fill:stop:{day}:{ticker}",
                            submitted_at=start,
                            session_date=day,
                            stop_price=state.stop_price,
                            settlement=SettlementInstruction(
                                settlement_id=f"settle:stop:{day}:{ticker}",
                                due_at=self._settlement_due(
                                    sessions=calendar,
                                    session_index=idx,
                                ),
                            ),
                        )
                    except NotExecutableError:
                        total_blocked_exits += 1
                    else:
                        self.policy.register_exit(ticker)
                        stop_exits += 1
                        continue
                elif decision.reason != "STOP_NOT_TRIGGERED":
                    total_blocked_exits += 1

            for ticker in sorted(list(self.policy.managed_positions)):
                if not self.policy.max_hold_due(ticker, idx):
                    continue
                state = self.policy.managed_positions[ticker]
                intent = OrderIntent(
                    intent_id=f"maxhold:{day}:{ticker}",
                    ticker=ticker,
                    side="sell",
                    quantity=state.quantity,
                    created_at=datetime.combine(day, datetime.max.time()),
                    rationale="canonical max-hold exit",
                )
                try:
                    self.execution.execute(
                        intent=intent,
                        signal=self.signal,
                        order_id=f"order:maxhold:{day}:{ticker}",
                        fill_id=f"fill:maxhold:{day}:{ticker}",
                        submitted_at=datetime.combine(day, datetime.max.time()),
                        session_date=day,
                        use=PriceUse.EXIT,
                        field="close",
                        settlement=SettlementInstruction(
                            settlement_id=f"settle:maxhold:{day}:{ticker}",
                            due_at=self._settlement_due(
                                sessions=calendar,
                                session_index=idx,
                            ),
                        ),
                    )
                except NotExecutableError:
                    total_blocked_exits += 1
                else:
                    self.policy.register_exit(ticker)
                    max_hold_exits += 1

            total_stop_exits += stop_exits
            total_max_hold_exits += max_hold_exits

            snapshot = self.replay.snapshot(
                at=datetime.combine(day, datetime.max.time()),
            )
            audits.append(
                StrategySessionAudit(
                    session_date=day,
                    signals_for_open=len(tickers),
                    entries_executed=entries,
                    entries_skipped=entry_skips,
                    stop_exits=stop_exits,
                    max_hold_exits=max_hold_exits,
                    settlements_completed=len(due),
                    corporate_actions_applied=ca_count,
                    snapshot=snapshot,
                )
            )

        return StrategySimulationResult(
            sessions=tuple(audits),
            total_entries=total_entries,
            total_stop_exits=total_stop_exits,
            total_max_hold_exits=total_max_hold_exits,
            total_entry_skips=total_entry_skips,
            total_blocked_exits=total_blocked_exits,
            total_corporate_actions=total_ca,
        )
