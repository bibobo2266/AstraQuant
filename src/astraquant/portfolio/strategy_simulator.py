from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

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
from astraquant.research.baseline_60d_exit_state import (
    Baseline60DExitState,
    BaselineBarInput,
    BaselineCorporateActionInput,
    BaselineOpenExecutionOutcome,
    BaselineOpenExecutionResult,
    BaselineTerminalDisposition,
    BaselineTerminalResult,
)
from astraquant.research.baseline_60d_simulation import BaselineSimulationContext
from astraquant.research.candidates import (
    declaration_from_candidate,
    legacy_signals_to_candidates,
    normalize_candidates,
)
from astraquant.research.exit_engine import CompiledExitPlan
from astraquant.research.feature_panel_integration import (
    EligibilityEvidenceScope,
    FeaturePanelIntegrationError,
)
from astraquant.research.prepared_run_evidence import (
    PreparedRunEligibilityEvidence,
    validate_prepared_execution_binding,
)


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
    capacity_rejections: int
    stop_exits: int
    max_hold_exits: int
    settlements_completed: int
    corporate_actions_applied: int
    corporate_cash_payments: int
    snapshot: ReplaySnapshot
    baseline_exit_fills: int = 0
    baseline_blocked_exit_attempts: int = 0
    baseline_pending_count: int = 0
    baseline_terminal_superseded: int = 0


@dataclass(frozen=True)
class StrategySimulationResult:
    sessions: tuple[StrategySessionAudit, ...]
    total_entries: int
    total_stop_exits: int
    total_max_hold_exits: int
    total_entry_skips: int
    total_capacity_overflow_sessions: int
    total_capacity_rejections: int
    total_blocked_exits: int
    total_corporate_actions: int
    total_corporate_cash_payments: int
    total_baseline_exit_fills: int = 0
    total_baseline_blocked_exit_attempts: int = 0
    total_baseline_terminal_superseded: int = 0
    baseline_exit_state: Baseline60DExitState | None = None
    data_censored_at: date | None = None


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
        baseline_data_guard: Callable[[date, str], bool] | None = None,
    ) -> None:
        if execution.portfolio is not portfolio:
            raise ValueError("execution and simulator must share PortfolioEngine")
        self.execution = execution
        self.portfolio = portfolio
        self.policy = policy
        self.signal = signal
        self.config = config or StrategySimulationConfig()
        self.baseline_data_guard = baseline_data_guard
        self.replay = CanonicalPortfolioReplay(
            execution=execution,
            portfolio=portfolio,
        )

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

    def _opening_nav(
        self,
        day: date,
        *,
        mark_not_before: dict[str, date] | None = None,
        terminal_stale_tickers: set[str] | None = None,
        mark_ca_transforms: dict[str, tuple[tuple[float, float], ...]] | None = None,
    ) -> float:
        decisions = {}
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
                    session_date=day,
                    field="open",
                    not_before=mark_not_before.get(ticker),
                    allow_terminal_stale_without_tradability=ticker in terminal_stale_tickers,
                    transformations=transforms,
                )
            else:
                decisions[ticker] = self.execution.mark(
                    ticker=ticker,
                    session_date=day,
                    side="sell",
                    field="open",
                    not_before=mark_not_before.get(ticker),
                    allow_terminal_stale_without_tradability=ticker in terminal_stale_tickers,
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
        candidates: pd.DataFrame | None = None,
        signals: pd.DataFrame | None = None,
        corporate_actions: list[HistoricalCorporateActionInstruction] | None = None,
        exit_plan: CompiledExitPlan | None = None,
        baseline_context: BaselineSimulationContext | None = None,
        eligibility_evidence: PreparedRunEligibilityEvidence | None = None,
    ) -> StrategySimulationResult:
        baseline_enabled = bool(
            exit_plan is not None and exit_plan.baseline_60d_enabled
        )
        if baseline_context is not None and not baseline_enabled:
            raise ValueError(
                "baseline_context requires the exact baseline_60d compiled exit plan"
            )
        if eligibility_evidence is not None and not baseline_enabled:
            raise ValueError(
                "eligibility_evidence is only supported by the baseline path"
            )
        if baseline_enabled:
            if baseline_context is None:
                raise ValueError(
                    "baseline_60d compiled exit plan requires baseline_context"
                )
            # Formal mode is rejected before any artifact/execution-data read.
            baseline_context.require_runnable()
            if eligibility_evidence is None:
                raise FeaturePanelIntegrationError(
                    "direct baseline simulator entry requires prepared-run "
                    "eligibility evidence"
                )
            if candidates is None or signals is not None:
                raise FeaturePanelIntegrationError(
                    "baseline execution binding requires prepared candidates"
                )
            if (
                eligibility_evidence.feature_evidence.scope
                is not EligibilityEvidenceScope.SYNTHETIC_FIXTURE
            ):
                raise FeaturePanelIntegrationError(
                    "synthetic baseline simulator requires "
                    "SYNTHETIC_FIXTURE eligibility evidence"
                )
            validate_prepared_execution_binding(
                evidence=eligibility_evidence,
                exit_plan=exit_plan,
                actual_policy=self.policy.config,
                sessions=sessions,
                candidates=candidates,
            )

        if self.baseline_data_guard is not None and not baseline_enabled:
            raise ValueError("baseline_data_guard requires baseline execution")

        trading_calendar = TradingCalendar(sessions)
        calendar = trading_calendar.sessions

        if (candidates is None) == (signals is None):
            raise ValueError("provide exactly one of candidates or legacy signals")
        normalized_candidates = (
            normalize_candidates(candidates)
            if candidates is not None
            else legacy_signals_to_candidates(signals, declaration=self.signal)
        )
        session_index = {day: i for i, day in enumerate(calendar)}

        if baseline_enabled:
            if (
                self.policy.config.stop_fraction is not None
                or self.policy.config.max_hold_sessions is not None
            ):
                raise ValueError(
                    "baseline_60d must run with legacy fixed stop/max-hold disabled"
                )
            baseline_exit_state: Baseline60DExitState | None = Baseline60DExitState()
        else:
            baseline_exit_state = None

        baseline_tickers = {
            str(value) for value in normalized_candidates["stock_id"].astype(str).tolist()
        } if baseline_enabled else set()

        entry_signals: dict[date, list[dict[str, object]]] = {}
        for row in normalized_candidates.to_dict("records"):
            signal_day = pd.Timestamp(row["signal_date"]).date()
            idx = session_index.get(signal_day)
            if idx is None or idx + 1 >= len(calendar):
                continue
            entry_day = calendar[idx + 1]
            available_at = pd.Timestamp(row["available_at"]).to_pydatetime()
            if available_at >= self._session_start(entry_day):
                raise ValueError(
                    f"candidate {row['stock_id']} on {signal_day} was not available "
                    f"before next-session entry: available_at={available_at}"
                )
            entry_signals.setdefault(entry_day, []).append(row)

        ca_by_day: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        close_ca_by_day: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        terminal_stale_windows: dict[str, tuple[date, date]] = {}
        for item in corporate_actions or []:
            if item.applied_at < item.event.effective_at:
                raise ValueError(
                    f"corporate action {item.event.event_id} cannot apply before effective date"
                )
            day = trading_calendar.map_effective_date(item.event.effective_at)
            target = close_ca_by_day if item.apply_at_close else ca_by_day
            target.setdefault(day, []).append(item)
            if item.terminal_stale_from is not None:
                terminal_stale_windows[str(item.event.ticker)] = (
                    item.terminal_stale_from,
                    day,
                )

        audits: list[StrategySessionAudit] = []
        total_entries = 0
        total_stop_exits = 0
        total_max_hold_exits = 0
        total_entry_skips = 0
        total_capacity_overflow_sessions = 0
        total_capacity_rejections = 0
        total_blocked_exits = 0
        total_ca = 0
        total_ca_payments = 0
        total_baseline_exit_fills = 0
        total_baseline_blocked_exit_attempts = 0
        total_baseline_terminal_superseded = 0
        latest_ca_session: dict[str, date] = {}
        held_at_prior_close: set[str] = set()

        data_censored_at = None
        for idx, day in enumerate(calendar):
            # Stop before any settlement, CA, exit, sizing or NAV mutation.
            if self.baseline_data_guard is not None and not self.baseline_data_guard(day, "BEFORE_OPEN"):
                data_censored_at = day
                break
            start = self._session_start(day)
            terminal_stale_tickers = {
                ticker
                for ticker, (stale_from, effective_day) in terminal_stale_windows.items()
                if stale_from <= day < effective_day
            }

            due = sorted(
                settlement_id
                for settlement_id, settlement in self.portfolio.settlements.pending.items()
                if settlement.due_at <= start
            )
            for settlement_id in due:
                self.replay.settle(settlement_id, start)

            ca_payment_count = 0
            due_dividends = sorted(
                event_id
                for event_id, receivable in self.portfolio.corporate_actions.dividend_receivables.items()
                if receivable.payment_at is not None and receivable.payment_at <= start
            )
            for event_id in due_dividends:
                self.portfolio.corporate_actions.pay_cash_dividend(
                    event_id,
                    paid_at=start,
                )
                ca_payment_count += 1

            due_entitlements = sorted(
                event_id
                for event_id, receivable in self.portfolio.corporate_actions.cash_entitlement_receivables.items()
                if receivable.payment_at is not None and receivable.payment_at <= start
            )
            for event_id in due_entitlements:
                self.portfolio.corporate_actions.pay_cash_entitlement(
                    event_id,
                    paid_at=start,
                )
                ca_payment_count += 1
            total_ca_payments += ca_payment_count

            ca_count = 0
            current_ca_mark_transforms: dict[str, list[tuple[float, float]]] = {}
            opening_ca_items = tuple(sorted(
                ca_by_day.get(day, []),
                key=lambda x: x.event.event_id,
            ))
            for item in opening_ca_items:
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
                if item.successor_ticker is not None and item.successor_legs:
                    raise ValueError(
                        f"event {event.event_id} cannot declare both single and composite successors"
                    )
                if item.successor_ticker is not None:
                    if item.successor_multiplier is None:
                        raise ValueError(
                            f"successor_multiplier missing for {event.event_id}"
                        )
                    self.portfolio.corporate_actions.convert_security(
                        event=event,
                        positions=self.portfolio.positions,
                        to_ticker=item.successor_ticker,
                        quantity_multiplier=item.successor_multiplier,
                        applied_at=economic_apply_at,
                    )
                    self.policy.convert_security(
                        from_ticker=str(event.ticker),
                        to_ticker=str(item.successor_ticker),
                        quantity_multiplier=item.successor_multiplier,
                    )
                    latest_ca_session[str(item.successor_ticker)] = day
                if item.successor_legs:
                    self.portfolio.corporate_actions.convert_security_composite(
                        event=event,
                        positions=self.portfolio.positions,
                        legs=item.successor_legs,
                        cash_value_weight=item.cash_value_weight,
                        applied_at=economic_apply_at,
                    )
                    self.policy.convert_security_composite(
                        from_ticker=str(event.ticker),
                        legs=item.successor_legs,
                        cash_per_source_share=float(event.cash_per_share or 0.0),
                        cash_value_weight=item.cash_value_weight,
                    )
                    for leg in item.successor_legs:
                        latest_ca_session[str(leg.to_ticker)] = day
                cash_for_mark = float(event.cash_per_share or 0.0)
                multiplier_for_mark = float(event.share_multiplier or 1.0)
                if cash_for_mark != 0.0 or multiplier_for_mark != 1.0:
                    current_ca_mark_transforms.setdefault(str(event.ticker), []).append(
                        (cash_for_mark, multiplier_for_mark)
                    )
                if item.extinguish_position:
                    self.portfolio.corporate_actions.extinguish_position(
                        event=event,
                        positions=self.portfolio.positions,
                        applied_at=economic_apply_at,
                    )
                    if str(event.ticker) in self.policy.managed_positions:
                        self.policy.register_exit(str(event.ticker))
                latest_ca_session[str(event.ticker)] = day
                ca_count += 1

            baseline_exit_fills = 0
            baseline_blocked_exit_attempts = 0
            baseline_terminal_superseded = 0

            if baseline_exit_state is not None:
                relevant_opening_ca = tuple(
                    item
                    for item in opening_ca_items
                    if (
                        str(item.event.ticker) in baseline_tickers
                        or baseline_exit_state.holding_state(str(item.event.ticker)) is not None
                    )
                )
                if relevant_opening_ca:
                    baseline_exit_state.apply_opening_corporate_actions(
                        tuple(
                            BaselineCorporateActionInput(
                                instruction=item,
                                approved_for_technical_transform=(
                                    baseline_context.ca_approval(
                                        item.event.event_id
                                    ).approved
                                ),
                            )
                            for item in relevant_opening_ca
                        ),
                        session_start=start,
                        decision_cutoff=start,
                    )

                    for item in relevant_opening_ca:
                        ticker = str(item.event.ticker)
                        holding = baseline_exit_state.holding_state(ticker)
                        if item.extinguish_position and holding is not None:
                            position = self.portfolio.positions.positions.get(ticker)
                            canonical_quantity = (
                                0.0 if position is None else float(position.quantity)
                            )
                            if canonical_quantity == 0.0:
                                audit = baseline_exit_state.record_terminal_result(
                                    BaselineTerminalResult(
                                        ticker=ticker,
                                        session_date=day,
                                        disposition=BaselineTerminalDisposition.EXTINGUISHED,
                                        reason=(
                                            "CANONICAL_OPENING_TERMINAL_EXTINGUISHMENT"
                                        ),
                                    )
                                )
                                if audit.superseded_pending is not None:
                                    baseline_terminal_superseded += 1
                                    total_baseline_terminal_superseded += 1
                        elif (
                            item.successor_ticker is not None
                            or item.successor_legs
                        ) and (
                            holding is not None
                            or baseline_exit_state.technical_block_reason(ticker)
                            is not None
                        ):
                            baseline_exit_state.record_terminal_result(
                                BaselineTerminalResult(
                                    ticker=ticker,
                                    session_date=day,
                                    disposition=(
                                        BaselineTerminalDisposition.CANONICAL_LIFECYCLE_REQUIRED
                                    ),
                                    reason="CANONICAL_SUCCESSOR_MAPPING_REQUIRED",
                                )
                            )

                for ticker in sorted(list(baseline_exit_state.holdings)):
                    pending = baseline_exit_state.pending_for_open(
                        ticker,
                        session_index=idx,
                    )
                    if pending is None:
                        continue
                    holding = baseline_exit_state.holding_state(ticker)
                    position = self.portfolio.positions.positions.get(ticker)
                    before_quantity = (
                        0.0 if position is None else float(position.quantity)
                    )
                    if before_quantity <= 0:
                        audit = baseline_exit_state.record_terminal_result(
                            BaselineTerminalResult(
                                ticker=ticker,
                                session_date=day,
                                disposition=BaselineTerminalDisposition.EXTINGUISHED,
                                reason="CANONICAL_POSITION_ZERO_BEFORE_PENDING_EXIT",
                            )
                        )
                        if audit.superseded_pending is not None:
                            baseline_terminal_superseded += 1
                            total_baseline_terminal_superseded += 1
                        continue

                    decision = self.execution.market_data.resolve(
                        ticker=ticker,
                        session_date=day,
                        side="sell",
                        use=PriceUse.EXIT,
                        field="open",
                    )
                    report_id = f"baseline-exit-report:{day}:{ticker}:{pending.intent_id}"
                    if decision.availability is not ExecutionAvailability.EXECUTABLE:
                        if (
                            decision.tradability is not None
                            and decision.tradability.sell_blocked
                        ):
                            outcome = BaselineOpenExecutionOutcome.SELL_BLOCKED
                        elif decision.reason in {
                            "RAW_MISSING_OR_NONUNIQUE",
                            "RAW_INVALID_OHLC",
                            "TRADABILITY_MISSING_OR_NONUNIQUE",
                        }:
                            outcome = BaselineOpenExecutionOutcome.NO_VALID_OPEN
                        else:
                            outcome = BaselineOpenExecutionOutcome.NOT_EXECUTABLE
                        baseline_exit_state.record_open_execution(
                            BaselineOpenExecutionResult(
                                report_id=report_id,
                                ticker=ticker,
                                session_date=day,
                                session_index=idx,
                                outcome=outcome,
                                reason=decision.reason,
                                pending_intent_id=pending.intent_id,
                                entry_fill_id=holding.entry_fill_id,
                                canonical_position_quantity_before=before_quantity,
                                canonical_position_quantity_after=before_quantity,
                                fill=None,
                            )
                        )
                        baseline_blocked_exit_attempts += 1
                        total_baseline_blocked_exit_attempts += 1
                        total_blocked_exits += 1
                        continue

                    intent = OrderIntent(
                        intent_id=f"baseline-exit:{day}:{ticker}",
                        ticker=ticker,
                        side="sell",
                        quantity=before_quantity,
                        created_at=start,
                        rationale=f"baseline_60d pending {pending.reason.value}",
                    )
                    out = self.execution.execute(
                        intent=intent,
                        signal=self.signal,
                        order_id=f"order:baseline-exit:{day}:{ticker}",
                        fill_id=f"fill:baseline-exit:{day}:{ticker}",
                        submitted_at=start,
                        session_date=day,
                        use=PriceUse.EXIT,
                        field="open",
                        settlement=SettlementInstruction(
                            settlement_id=f"settle:baseline-exit:{day}:{ticker}",
                            due_at=self._settlement_due(
                                sessions=calendar,
                                session_index=idx,
                            ),
                        ),
                    )
                    after_position = self.portfolio.positions.positions.get(ticker)
                    after_quantity = (
                        0.0
                        if after_position is None
                        else float(after_position.quantity)
                    )
                    baseline_exit_state.record_open_execution(
                        BaselineOpenExecutionResult(
                            report_id=report_id,
                            ticker=ticker,
                            session_date=day,
                            session_index=idx,
                            outcome=BaselineOpenExecutionOutcome.FILLED,
                            reason="CANONICAL_EXIT_FILL",
                            pending_intent_id=pending.intent_id,
                            entry_fill_id=holding.entry_fill_id,
                            canonical_position_quantity_before=before_quantity,
                            canonical_position_quantity_after=after_quantity,
                            fill=out.fill,
                        )
                    )
                    if ticker in self.policy.managed_positions:
                        self.policy.register_exit(ticker)
                    baseline_exit_fills += 1
                    total_baseline_exit_fills += 1

            held_before_open = set(self.policy.managed_positions)

            signal_rows = sorted(
                entry_signals.get(day, []),
                key=lambda row: str(row["stock_id"]),
            )
            tickers = [str(row["stock_id"]) for row in signal_rows]
            entry_candidates: list[EntryCandidate] = []
            candidate_signal_by_ticker: dict[str, SignalDeclaration] = {}
            baseline_pre_entry_skips: dict[str, str] = {}
            for row in signal_rows:
                ticker = str(row["stock_id"])
                if baseline_exit_state is not None:
                    if ticker in held_at_prior_close:
                        baseline_pre_entry_skips[ticker] = (
                            "BASELINE_SIGNAL_FORMED_WHILE_HELD"
                        )
                        continue
                    if baseline_exit_state.technical_block_reason(ticker) is not None:
                        baseline_pre_entry_skips[ticker] = (
                            "BASELINE_TECHNICAL_STATE_BLOCKED"
                        )
                        continue

                candidate_signal = declaration_from_candidate(row)
                candidate_signal_by_ticker[ticker] = candidate_signal
                sizing = self.execution.sizing_price(
                    ticker=ticker,
                    session_date=day,
                    side="buy",
                    field="open",
                    signal=candidate_signal,
                )
                entry_candidates.append(
                    EntryCandidate(
                        ticker=ticker,
                        sizing_decision=sizing,
                        signal_date=str(pd.Timestamp(row["signal_date"]).date()),
                        turnover_value=(
                            None
                            if pd.isna(row.get("turnover_value"))
                            else float(row["turnover_value"])
                        ),
                        breakout_excess=(
                            None
                            if pd.isna(row.get("breakout_excess"))
                            else float(row["breakout_excess"])
                        ),
                    )
                )

            try:
                opening_nav = self._opening_nav(
                    day,
                    mark_not_before=latest_ca_session,
                    terminal_stale_tickers=terminal_stale_tickers,
                    mark_ca_transforms={
                        ticker: tuple(values)
                        for ticker, values in current_ca_mark_transforms.items()
                    },
                )
            except Exception as exc:
                raise type(exc)(f"opening NAV failed on {day}: {exc}") from exc
            planned, skipped = self.policy.plan_entries(
                candidates=entry_candidates,
                session_index=idx,
                current_nav=opening_nav,
                available_cash=self.portfolio.cash.available_to_commit_cash,
            )
            entry_skips = len(skipped) + len(baseline_pre_entry_skips)
            capacity_rejections = sum(
                reason == "NO_POSITION_SLOT" or reason.startswith("CAPACITY_")
                for reason in skipped.values()
            )
            if capacity_rejections:
                total_capacity_overflow_sessions += 1
                total_capacity_rejections += capacity_rejections

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
                        signal=candidate_signal_by_ticker[plan.ticker],
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
                if baseline_exit_state is not None:
                    baseline_exit_state.register_entry(
                        out.fill,
                        session_index=idx,
                    )
                entries += 1
            total_entries += entries
            total_entry_skips += entry_skips

            # Preserve same-day entry fills, but never value an unreliable holding.
            if self.baseline_data_guard is not None and not self.baseline_data_guard(day, "BEFORE_CLOSE"):
                data_censored_at = day
                break

            stop_exits = 0
            max_hold_exits = 0

            # Stops are evaluated after open-entry decisions, so intraday lows
            # cannot free same-open capacity/cash. New entries start stop checks
            # on the following session, preserving the legacy one-session delay.
            for ticker in sorted(held_before_open):
                state = self.policy.managed_positions.get(ticker)
                if state is None or state.stop_price is None:
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

            if baseline_exit_state is not None:
                close_tickers = baseline_tickers | set(baseline_exit_state.holdings)
                for ticker in sorted(close_tickers):
                    decision = self.execution.market_data.resolve(
                        ticker=ticker,
                        session_date=day,
                        side="sell",
                        use=PriceUse.MARK,
                        field="close",
                    )
                    raw_bar = decision.bar
                    tradability = decision.tradability
                    baseline_exit_state.observe_bar(
                        BaselineBarInput(
                            ticker=ticker,
                            session_date=day,
                            session_index=idx,
                            open=(None if raw_bar is None else raw_bar.open),
                            high=(None if raw_bar is None else raw_bar.high),
                            low=(None if raw_bar is None else raw_bar.low),
                            close=(None if raw_bar is None else raw_bar.close),
                            observed_trade=(
                                False
                                if tradability is None
                                else bool(tradability.observed_trade)
                            ),
                            valid_ohlc=(
                                False
                                if tradability is None
                                else bool(tradability.valid_ohlc)
                            ),
                            gap_reason=(
                                None if decision.reason == "OK" else decision.reason
                            ),
                        )
                    )

            # Conservative terminal fallback events are close-applied so the
            # final RAW trading session remains fully executable. They use the
            # observed final RAW close as cash consideration and never create a
            # synthetic sell fill or stale post-terminal mark.
            for item in sorted(
                close_ca_by_day.get(day, []),
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
                    raise ValueError(
                        "close-applied corporate actions are restricted to "
                        f"cash extinguishments: {event.event_id}"
                    )
                close_at = datetime.combine(day, datetime.max.time())
                economic_apply_at = max(item.applied_at, close_at)
                position = self.portfolio.positions.positions.get(event.ticker)
                closing_shares = 0.0 if position is None else position.quantity
                self.portfolio.corporate_actions.accrue_cash_entitlement(
                    event=event,
                    shares_entitled=closing_shares,
                    accrued_at=economic_apply_at,
                    component=item.component,
                )
                self.policy.apply_corporate_action(event)
                self.portfolio.corporate_actions.extinguish_position(
                    event=event,
                    positions=self.portfolio.positions,
                    applied_at=economic_apply_at,
                )
                if str(event.ticker) in self.policy.managed_positions:
                    self.policy.register_exit(str(event.ticker))
                if baseline_exit_state is not None:
                    ticker = str(event.ticker)
                    if baseline_exit_state.holding_state(ticker) is not None:
                        audit = baseline_exit_state.record_terminal_result(
                            BaselineTerminalResult(
                                ticker=ticker,
                                session_date=day,
                                disposition=BaselineTerminalDisposition.EXTINGUISHED,
                                reason="CANONICAL_CLOSE_TERMINAL_EXTINGUISHMENT",
                            )
                        )
                        if audit.superseded_pending is not None:
                            baseline_terminal_superseded += 1
                            total_baseline_terminal_superseded += 1
                latest_ca_session[str(event.ticker)] = day
                ca_count += 1

            total_ca += ca_count
            held_at_prior_close = set(self.policy.managed_positions)

            snapshot = self.replay.snapshot(
                at=datetime.combine(day, datetime.max.time()),
                mark_not_before=latest_ca_session,
                terminal_stale_tickers=terminal_stale_tickers,
                mark_ca_transforms={
                    ticker: tuple(values)
                    for ticker, values in current_ca_mark_transforms.items()
                },
            )
            audits.append(
                StrategySessionAudit(
                    session_date=day,
                    signals_for_open=len(tickers),
                    entries_executed=entries,
                    entries_skipped=entry_skips,
                    capacity_rejections=capacity_rejections,
                    stop_exits=stop_exits,
                    max_hold_exits=max_hold_exits,
                    settlements_completed=len(due),
                    corporate_actions_applied=ca_count,
                    corporate_cash_payments=ca_payment_count,
                    snapshot=snapshot,
                    baseline_exit_fills=baseline_exit_fills,
                    baseline_blocked_exit_attempts=baseline_blocked_exit_attempts,
                    baseline_pending_count=(
                        0
                        if baseline_exit_state is None
                        else sum(
                            holding.pending_exit is not None
                            for holding in baseline_exit_state.holdings.values()
                        )
                    ),
                    baseline_terminal_superseded=baseline_terminal_superseded,
                )
            )

        return StrategySimulationResult(
            sessions=tuple(audits),
            total_entries=total_entries,
            total_stop_exits=total_stop_exits,
            total_max_hold_exits=total_max_hold_exits,
            total_entry_skips=total_entry_skips,
            total_capacity_overflow_sessions=total_capacity_overflow_sessions,
            total_capacity_rejections=total_capacity_rejections,
            total_blocked_exits=total_blocked_exits,
            total_corporate_actions=total_ca,
            total_corporate_cash_payments=total_ca_payments,
            total_baseline_exit_fills=total_baseline_exit_fills,
            total_baseline_blocked_exit_attempts=(
                total_baseline_blocked_exit_attempts
            ),
            total_baseline_terminal_superseded=(
                total_baseline_terminal_superseded
            ),
            baseline_exit_state=baseline_exit_state,
            data_censored_at=data_censored_at,
        )
