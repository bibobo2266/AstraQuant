from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
import math
from typing import Iterable, Sequence

from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import Fill


ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
LOW_WINDOW = 20


class BaselineExitStateError(RuntimeError):
    pass


class BaselineTriState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class BaselineEvaluationStatus(str, Enum):
    EVALUATED = "EVALUATED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
    NO_POSITION = "NO_POSITION"


class BaselineExitReason(str, Enum):
    ATR = "ATR"
    LOW20 = "LOW20"
    BOTH = "BOTH"


class BaselineOpenExecutionOutcome(str, Enum):
    FILLED = "FILLED"
    SELL_BLOCKED = "SELL_BLOCKED"
    NO_VALID_OPEN = "NO_VALID_OPEN"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"


class BaselineTerminalDisposition(str, Enum):
    EXTINGUISHED = "EXTINGUISHED"
    CANONICAL_LIFECYCLE_REQUIRED = "CANONICAL_LIFECYCLE_REQUIRED"
    NO_CHANGE = "NO_CHANGE"


class BaselineCAApplyStatus(str, Enum):
    APPLIED = "APPLIED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    BLOCKED = "BLOCKED"
    NOT_EFFECTIVE = "NOT_EFFECTIVE"


@dataclass(frozen=True)
class BaselineBarInput:
    """One caller-supplied session observation.

    session_index must come from a trusted session contract.  The exit-state
    module never derives a supposedly-complete calendar from ticker rows.
    """

    ticker: str
    session_date: date
    session_index: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    observed_trade: bool
    valid_ohlc: bool
    gap_reason: str | None = None


@dataclass(frozen=True)
class BaselineObservedBar:
    ticker: str
    session_date: date
    session_index: int
    open: float
    high: float
    low: float
    close: float
    gap_sessions_before: int = 0
    gap_reason: str | None = None


@dataclass(frozen=True)
class BaselineWindowAudit:
    observation_count: int
    session_span: int | None
    skipped_sessions: int
    gap_reasons: tuple[str, ...]


@dataclass(frozen=True)
class BaselinePendingExit:
    ticker: str
    trigger_date: date
    trigger_session_index: int
    earliest_execution_session_index: int
    reason: BaselineExitReason
    trigger_close: float
    atr_value: float | None
    atr_threshold: float | None
    low20_reference: float | None
    intent_id: str


@dataclass
class BaselineHoldingExitState:
    ticker: str
    entry_fill_id: str
    entry_session_index: int
    entry_anchor: float
    entry_quantity: float
    entry_fee_audit: float
    pending_exit: BaselinePendingExit | None = None
    blocked_reason: str | None = None
    open_attempts: int = 0


@dataclass(frozen=True)
class BaselineExitEvaluation:
    ticker: str
    session_date: date
    session_index: int
    status: BaselineEvaluationStatus
    observation_accepted: bool
    observation_reason: str
    atr_state: BaselineTriState
    low20_state: BaselineTriState
    atr_value: float | None
    atr_threshold: float | None
    low20_reference: float | None
    atr_window: BaselineWindowAudit
    low20_window: BaselineWindowAudit
    pending_exit: BaselinePendingExit | None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class BaselineCorporateActionInput:
    """Adapter around the canonical historical CA instruction.

    approved_for_technical_transform is an explicit evidence decision supplied
    by the caller.  This module does not infer historical cutoff reliability
    from event type or current source values.
    """

    instruction: HistoricalCorporateActionInstruction
    approved_for_technical_transform: bool


@dataclass(frozen=True)
class BaselineCorporateActionResult:
    ticker: str
    event_ids: tuple[str, ...]
    status: BaselineCAApplyStatus
    reason: str
    cash_per_share: float = 0.0
    share_multiplier: float = 1.0


@dataclass(frozen=True)
class BaselineOpenExecutionResult:
    ticker: str
    session_index: int
    outcome: BaselineOpenExecutionOutcome
    reason: str
    fill: Fill | None = None


@dataclass(frozen=True)
class BaselineTerminalResult:
    ticker: str
    session_date: date
    disposition: BaselineTerminalDisposition
    reason: str


@dataclass(frozen=True)
class BaselineTerminalAudit:
    ticker: str
    session_date: date
    disposition: BaselineTerminalDisposition
    reason: str
    superseded_pending: BaselinePendingExit | None


@dataclass
class Baseline60DExitState:
    """Standalone close-confirmed exit-state module for baseline_60d_breakout_v1.

    It maintains technical state and exit intent only.  It never creates a Fill,
    never mutates canonical accounting, and is not wired into the canonical
    simulator in this module.
    """

    histories: dict[str, list[BaselineObservedBar]] = field(default_factory=dict)
    holdings: dict[str, BaselineHoldingExitState] = field(default_factory=dict)
    applied_ca_event_ids: set[str] = field(default_factory=set)
    terminal_audit: list[BaselineTerminalAudit] = field(default_factory=list)

    @staticmethod
    def _finite_positive(value: float | None) -> bool:
        return value is not None and math.isfinite(float(value)) and float(value) > 0

    @classmethod
    def _validate_bar(cls, bar: BaselineBarInput) -> str | None:
        if not str(bar.ticker).strip():
            return "MISSING_TICKER"
        if bar.session_index < 0:
            return "INVALID_SESSION_INDEX"
        if not bar.observed_trade:
            return "NOT_OBSERVED"
        if not bar.valid_ohlc:
            return "INVALID_OHLC_FLAG"
        values = (bar.open, bar.high, bar.low, bar.close)
        if not all(cls._finite_positive(value) for value in values):
            return "NONFINITE_OR_NONPOSITIVE_OHLC"
        open_, high, low, close = (float(value) for value in values)
        if high < max(open_, close, low) or low > min(open_, close, high):
            return "INVALID_OHLC_GEOMETRY"
        return None

    @staticmethod
    def _window_audit(bars: Sequence[BaselineObservedBar]) -> BaselineWindowAudit:
        if not bars:
            return BaselineWindowAudit(
                observation_count=0,
                session_span=None,
                skipped_sessions=0,
                gap_reasons=(),
            )
        skipped = sum(max(0, int(bar.gap_sessions_before)) for bar in bars)
        reasons = tuple(
            str(bar.gap_reason)
            for bar in bars
            if bar.gap_sessions_before > 0 and bar.gap_reason
        )
        return BaselineWindowAudit(
            observation_count=len(bars),
            session_span=bars[-1].session_index - bars[0].session_index + 1,
            skipped_sessions=skipped,
            gap_reasons=reasons,
        )

    @staticmethod
    def _true_ranges(bars: Sequence[BaselineObservedBar]) -> list[float]:
        out: list[float] = []
        previous_close: float | None = None
        for bar in bars:
            if previous_close is None:
                tr = bar.high - bar.low
            else:
                tr = max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            out.append(float(tr))
            previous_close = bar.close
        return out

    def register_entry(self, fill: Fill, *, session_index: int) -> BaselineHoldingExitState:
        if fill.side.lower() != "buy":
            raise BaselineExitStateError("baseline entry requires a canonical buy Fill")
        if not self._finite_positive(fill.price) or fill.quantity <= 0:
            raise BaselineExitStateError("entry Fill must have positive price and quantity")
        ticker = str(fill.ticker)
        if ticker in self.holdings:
            raise BaselineExitStateError(f"active baseline holding already exists: {ticker}")
        state = BaselineHoldingExitState(
            ticker=ticker,
            entry_fill_id=fill.fill_id,
            entry_session_index=int(session_index),
            entry_anchor=float(fill.price),
            entry_quantity=float(fill.quantity),
            entry_fee_audit=float(fill.fees),
        )
        self.holdings[ticker] = state
        return state

    def _append_valid_bar(self, bar: BaselineBarInput) -> BaselineObservedBar:
        ticker = str(bar.ticker)
        history = self.histories.setdefault(ticker, [])
        if history:
            previous = history[-1]
            if bar.session_index <= previous.session_index:
                raise BaselineExitStateError(
                    f"non-increasing session_index for {ticker}: "
                    f"{bar.session_index} <= {previous.session_index}"
                )
            if bar.session_date <= previous.session_date:
                raise BaselineExitStateError(
                    f"non-increasing session_date for {ticker}: "
                    f"{bar.session_date} <= {previous.session_date}"
                )
            gap_sessions = bar.session_index - previous.session_index - 1
        else:
            gap_sessions = 0
        gap_reason = bar.gap_reason
        if gap_sessions > 0 and not gap_reason:
            gap_reason = "MISSING_OR_INVALID_SESSION_OBSERVATION"
        observed = BaselineObservedBar(
            ticker=ticker,
            session_date=bar.session_date,
            session_index=int(bar.session_index),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            gap_sessions_before=max(0, int(gap_sessions)),
            gap_reason=gap_reason,
        )
        history.append(observed)
        return observed

    @staticmethod
    def _unknown_evaluation(
        *,
        bar: BaselineBarInput,
        reason: str,
        holding: BaselineHoldingExitState | None,
        atr_window: BaselineWindowAudit | None = None,
        low_window: BaselineWindowAudit | None = None,
    ) -> BaselineExitEvaluation:
        pending = None if holding is None else holding.pending_exit
        status = (
            BaselineEvaluationStatus.NO_POSITION
            if holding is None
            else BaselineEvaluationStatus.PENDING
            if pending is not None
            else BaselineEvaluationStatus.BLOCKED
            if holding.blocked_reason is not None
            else BaselineEvaluationStatus.UNKNOWN
        )
        return BaselineExitEvaluation(
            ticker=str(bar.ticker),
            session_date=bar.session_date,
            session_index=int(bar.session_index),
            status=status,
            observation_accepted=False,
            observation_reason=reason,
            atr_state=BaselineTriState.UNKNOWN,
            low20_state=BaselineTriState.UNKNOWN,
            atr_value=None,
            atr_threshold=None,
            low20_reference=None,
            atr_window=atr_window or BaselineWindowAudit(0, None, 0, ()),
            low20_window=low_window or BaselineWindowAudit(0, None, 0, ()),
            pending_exit=pending,
            blocked_reason=None if holding is None else holding.blocked_reason,
        )

    def observe_bar(self, bar: BaselineBarInput) -> BaselineExitEvaluation:
        reason = self._validate_bar(bar)
        holding = self.holdings.get(str(bar.ticker))
        if reason is not None:
            return self._unknown_evaluation(
                bar=bar,
                reason=reason,
                holding=holding,
            )

        current = self._append_valid_bar(bar)
        history = self.histories[str(bar.ticker)]
        atr_bars = history[-ATR_PERIOD:]
        prior_low_bars = history[-(LOW_WINDOW + 1):-1] if len(history) > 1 else []
        atr_window = self._window_audit(atr_bars)
        low_window = self._window_audit(prior_low_bars)

        if holding is None:
            return BaselineExitEvaluation(
                ticker=current.ticker,
                session_date=current.session_date,
                session_index=current.session_index,
                status=BaselineEvaluationStatus.NO_POSITION,
                observation_accepted=True,
                observation_reason="VALID_OBSERVED_BAR",
                atr_state=BaselineTriState.UNKNOWN,
                low20_state=BaselineTriState.UNKNOWN,
                atr_value=None,
                atr_threshold=None,
                low20_reference=None,
                atr_window=atr_window,
                low20_window=low_window,
                pending_exit=None,
            )

        if holding.blocked_reason is not None:
            return BaselineExitEvaluation(
                ticker=current.ticker,
                session_date=current.session_date,
                session_index=current.session_index,
                status=BaselineEvaluationStatus.BLOCKED,
                observation_accepted=True,
                observation_reason="VALID_OBSERVED_BAR",
                atr_state=BaselineTriState.UNKNOWN,
                low20_state=BaselineTriState.UNKNOWN,
                atr_value=None,
                atr_threshold=None,
                low20_reference=None,
                atr_window=atr_window,
                low20_window=low_window,
                pending_exit=holding.pending_exit,
                blocked_reason=holding.blocked_reason,
            )

        true_ranges = self._true_ranges(history)
        atr_value: float | None = None
        atr_threshold: float | None = None
        atr_state = BaselineTriState.UNKNOWN
        if len(true_ranges) >= ATR_PERIOD:
            atr_value = float(sum(true_ranges[-ATR_PERIOD:]) / ATR_PERIOD)
            atr_threshold = float(holding.entry_anchor - ATR_MULTIPLIER * atr_value)
            atr_state = (
                BaselineTriState.TRUE
                if current.close <= atr_threshold
                else BaselineTriState.FALSE
            )

        low_reference: float | None = None
        low_state = BaselineTriState.UNKNOWN
        if len(prior_low_bars) == LOW_WINDOW:
            low_reference = min(item.close for item in prior_low_bars)
            low_state = (
                BaselineTriState.TRUE
                if current.close < low_reference
                else BaselineTriState.FALSE
            )

        if holding.pending_exit is not None:
            return BaselineExitEvaluation(
                ticker=current.ticker,
                session_date=current.session_date,
                session_index=current.session_index,
                status=BaselineEvaluationStatus.PENDING,
                observation_accepted=True,
                observation_reason="VALID_OBSERVED_BAR_PENDING_STICKY",
                atr_state=atr_state,
                low20_state=low_state,
                atr_value=atr_value,
                atr_threshold=atr_threshold,
                low20_reference=low_reference,
                atr_window=atr_window,
                low20_window=low_window,
                pending_exit=holding.pending_exit,
            )

        reason_value: BaselineExitReason | None = None
        if atr_state is BaselineTriState.TRUE and low_state is BaselineTriState.TRUE:
            reason_value = BaselineExitReason.BOTH
        elif atr_state is BaselineTriState.TRUE:
            reason_value = BaselineExitReason.ATR
        elif low_state is BaselineTriState.TRUE:
            reason_value = BaselineExitReason.LOW20

        if reason_value is not None:
            pending = BaselinePendingExit(
                ticker=current.ticker,
                trigger_date=current.session_date,
                trigger_session_index=current.session_index,
                earliest_execution_session_index=current.session_index + 1,
                reason=reason_value,
                trigger_close=current.close,
                atr_value=atr_value,
                atr_threshold=atr_threshold,
                low20_reference=low_reference,
                intent_id=(
                    f"baseline60d:{current.ticker}:"
                    f"{current.session_date.isoformat()}:{reason_value.value}"
                ),
            )
            holding.pending_exit = pending
            return BaselineExitEvaluation(
                ticker=current.ticker,
                session_date=current.session_date,
                session_index=current.session_index,
                status=BaselineEvaluationStatus.PENDING,
                observation_accepted=True,
                observation_reason="VALID_OBSERVED_BAR_EXIT_TRIGGERED",
                atr_state=atr_state,
                low20_state=low_state,
                atr_value=atr_value,
                atr_threshold=atr_threshold,
                low20_reference=low_reference,
                atr_window=atr_window,
                low20_window=low_window,
                pending_exit=pending,
            )

        status = (
            BaselineEvaluationStatus.EVALUATED
            if (
                atr_state is not BaselineTriState.UNKNOWN
                and low_state is not BaselineTriState.UNKNOWN
            )
            else BaselineEvaluationStatus.UNKNOWN
        )
        return BaselineExitEvaluation(
            ticker=current.ticker,
            session_date=current.session_date,
            session_index=current.session_index,
            status=status,
            observation_accepted=True,
            observation_reason=(
                "VALID_OBSERVED_BAR"
                if status is BaselineEvaluationStatus.EVALUATED
                else "WARMUP_INSUFFICIENT"
            ),
            atr_state=atr_state,
            low20_state=low_state,
            atr_value=atr_value,
            atr_threshold=atr_threshold,
            low20_reference=low_reference,
            atr_window=atr_window,
            low20_window=low_window,
            pending_exit=None,
        )

    def pending_for_open(
        self,
        ticker: str,
        *,
        session_index: int,
    ) -> BaselinePendingExit | None:
        holding = self.holdings.get(str(ticker))
        if holding is None or holding.pending_exit is None:
            return None
        if holding.blocked_reason is not None:
            return None
        if session_index < holding.pending_exit.earliest_execution_session_index:
            return None
        return holding.pending_exit

    def record_open_execution(self, result: BaselineOpenExecutionResult) -> None:
        holding = self.holdings.get(str(result.ticker))
        if holding is None or holding.pending_exit is None:
            raise BaselineExitStateError(
                f"no pending baseline exit for {result.ticker}"
            )
        if result.session_index < holding.pending_exit.earliest_execution_session_index:
            raise BaselineExitStateError("pending baseline exit cannot fill on trigger session")
        holding.open_attempts += 1

        if result.outcome is not BaselineOpenExecutionOutcome.FILLED:
            return

        fill = result.fill
        if fill is None:
            raise BaselineExitStateError("FILLED outcome requires canonical Fill")
        if fill.side.lower() != "sell" or str(fill.ticker) != str(result.ticker):
            raise BaselineExitStateError("exit Fill must be matching ticker sell")
        if not self._finite_positive(fill.price):
            raise BaselineExitStateError("exit Fill price must be finite and positive")
        self.holdings.pop(str(result.ticker), None)

    @staticmethod
    def _transform_price(value: float, *, cash: float, multiplier: float) -> float:
        transformed = (float(value) - cash) / multiplier
        if not math.isfinite(transformed) or transformed <= 0:
            raise BaselineExitStateError(
                "CA-transformed technical price must remain finite and positive"
            )
        return transformed

    def _block_ticker(self, ticker: str, reason: str) -> None:
        holding = self.holdings.get(str(ticker))
        if holding is not None and holding.blocked_reason is None:
            holding.blocked_reason = reason

    @staticmethod
    def _requires_canonical_lifecycle(
        item: HistoricalCorporateActionInstruction,
    ) -> bool:
        event = item.event
        return bool(
            item.successor_ticker is not None
            or item.successor_legs
            or item.extinguish_position
            or event.event_type
            in {
                CorporateActionType.MERGER,
                CorporateActionType.RIGHTS,
                CorporateActionType.OTHER,
            }
        )

    def apply_opening_corporate_actions(
        self,
        items: Iterable[BaselineCorporateActionInput],
        *,
        session_start: datetime,
        decision_cutoff: datetime,
    ) -> tuple[BaselineCorporateActionResult, ...]:
        """Apply approved simple cash/share transforms before pending-open attempts.

        Callers must pass all same-opening events together.  Same-session cash
        and share components are aggregated as P_post=(P_pre-sum(c))/prod(m),
        with no per-event rounding.
        """

        new_items = [
            item
            for item in items
            if item.instruction.event.event_id not in self.applied_ca_event_ids
        ]
        duplicate_items = [
            item
            for item in items
            if item.instruction.event.event_id in self.applied_ca_event_ids
        ]
        results: list[BaselineCorporateActionResult] = []
        for item in duplicate_items:
            event = item.instruction.event
            results.append(
                BaselineCorporateActionResult(
                    ticker=str(event.ticker),
                    event_ids=(event.event_id,),
                    status=BaselineCAApplyStatus.DUPLICATE_IGNORED,
                    reason="EVENT_ID_ALREADY_SEEN",
                )
            )

        grouped: dict[tuple[str, date], list[BaselineCorporateActionInput]] = {}
        for item in new_items:
            event = item.instruction.event
            effective_day = event.effective_at.date()
            grouped.setdefault((str(event.ticker), effective_day), []).append(item)

        for (ticker, _effective_day), group in grouped.items():
            event_ids = tuple(item.instruction.event.event_id for item in group)
            events = [item.instruction.event for item in group]

            not_effective = [
                item
                for item in group
                if item.instruction.applied_at > session_start
                or item.instruction.event.effective_at > session_start
            ]
            if not_effective:
                results.append(
                    BaselineCorporateActionResult(
                        ticker=ticker,
                        event_ids=event_ids,
                        status=BaselineCAApplyStatus.NOT_EFFECTIVE,
                        reason="CA_NOT_EFFECTIVE_AT_OPEN",
                    )
                )
                continue

            block_reason: str | None = None
            if any(not item.approved_for_technical_transform for item in group):
                block_reason = "CA_TECHNICAL_TRANSFORM_NOT_APPROVED"
            elif any(event.known_at is None for event in events):
                block_reason = "CA_KNOWN_AT_UNKNOWN"
            elif any(event.known_at > decision_cutoff for event in events if event.known_at):
                block_reason = "CA_NOT_KNOWN_BY_CUTOFF"
            elif any(not str(event.source).strip() for event in events):
                block_reason = "CA_SOURCE_UNDECLARED"
            elif any(
                self._requires_canonical_lifecycle(item.instruction)
                for item in group
            ):
                block_reason = "CANONICAL_LIFECYCLE_REQUIRED"
            elif all(
                event.cash_per_share is None and event.share_multiplier is None
                for event in events
            ):
                block_reason = "CA_PRICE_TRANSFORM_UNDEFINED"

            history = self.histories.get(ticker, [])
            if history and any(
                bar.session_date >= min(event.effective_at.date() for event in events)
                for bar in history[-1:]
            ):
                raise BaselineExitStateError(
                    "opening CA must be applied before same-session technical bar"
                )

            if block_reason is not None:
                self.applied_ca_event_ids.update(event_ids)
                self._block_ticker(ticker, block_reason)
                results.append(
                    BaselineCorporateActionResult(
                        ticker=ticker,
                        event_ids=event_ids,
                        status=BaselineCAApplyStatus.BLOCKED,
                        reason=block_reason,
                    )
                )
                continue

            cash = sum(float(event.cash_per_share or 0.0) for event in events)
            multiplier = 1.0
            for event in events:
                multiplier *= float(event.share_multiplier or 1.0)
            if not math.isfinite(cash) or cash < 0:
                block_reason = "CA_CASH_COMPONENT_INVALID"
            if not math.isfinite(multiplier) or multiplier <= 0:
                block_reason = "CA_SHARE_MULTIPLIER_INVALID"

            transformed_history: list[BaselineObservedBar] = []
            if block_reason is None:
                try:
                    for bar in history:
                        transformed_history.append(
                            replace(
                                bar,
                                open=self._transform_price(
                                    bar.open, cash=cash, multiplier=multiplier
                                ),
                                high=self._transform_price(
                                    bar.high, cash=cash, multiplier=multiplier
                                ),
                                low=self._transform_price(
                                    bar.low, cash=cash, multiplier=multiplier
                                ),
                                close=self._transform_price(
                                    bar.close, cash=cash, multiplier=multiplier
                                ),
                            )
                        )
                    holding = self.holdings.get(ticker)
                    transformed_anchor = (
                        None
                        if holding is None
                        else self._transform_price(
                            holding.entry_anchor,
                            cash=cash,
                            multiplier=multiplier,
                        )
                    )
                except BaselineExitStateError:
                    block_reason = "CA_TRANSFORM_NONPOSITIVE_OR_NONFINITE"

            self.applied_ca_event_ids.update(event_ids)
            if block_reason is not None:
                self._block_ticker(ticker, block_reason)
                results.append(
                    BaselineCorporateActionResult(
                        ticker=ticker,
                        event_ids=event_ids,
                        status=BaselineCAApplyStatus.BLOCKED,
                        reason=block_reason,
                        cash_per_share=cash,
                        share_multiplier=multiplier,
                    )
                )
                continue

            self.histories[ticker] = transformed_history
            holding = self.holdings.get(ticker)
            if holding is not None and transformed_anchor is not None:
                holding.entry_anchor = transformed_anchor
            results.append(
                BaselineCorporateActionResult(
                    ticker=ticker,
                    event_ids=event_ids,
                    status=BaselineCAApplyStatus.APPLIED,
                    reason="CA_TECHNICAL_COORDINATE_TRANSFORM_APPLIED",
                    cash_per_share=cash,
                    share_multiplier=multiplier,
                )
            )

        return tuple(results)

    def record_terminal_result(
        self,
        result: BaselineTerminalResult,
    ) -> BaselineTerminalAudit:
        holding = self.holdings.get(str(result.ticker))
        pending = None if holding is None else holding.pending_exit

        if result.disposition is BaselineTerminalDisposition.EXTINGUISHED:
            self.holdings.pop(str(result.ticker), None)
        elif result.disposition is BaselineTerminalDisposition.CANONICAL_LIFECYCLE_REQUIRED:
            self._block_ticker(str(result.ticker), "CANONICAL_LIFECYCLE_REQUIRED")

        audit = BaselineTerminalAudit(
            ticker=str(result.ticker),
            session_date=result.session_date,
            disposition=result.disposition,
            reason=result.reason,
            superseded_pending=(
                pending
                if result.disposition is BaselineTerminalDisposition.EXTINGUISHED
                else None
            ),
        )
        self.terminal_audit.append(audit)
        return audit

    def holding_state(self, ticker: str) -> BaselineHoldingExitState | None:
        return self.holdings.get(str(ticker))

    def history(self, ticker: str) -> tuple[BaselineObservedBar, ...]:
        return tuple(self.histories.get(str(ticker), ()))
