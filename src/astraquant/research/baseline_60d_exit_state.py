from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
import math
from typing import Iterable, Sequence

from astraquant.portfolio.corporate_actions import CorporateActionType
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import Fill


ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0
LOW_WINDOW = 20
ROLLING_BAR_LIMIT = LOW_WINDOW + 1
_FLOAT_TOLERANCE = 1e-9


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

    session_index must come from a trusted session contract. The exit-state
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
class BaselineTickerTechnicalBlock:
    ticker: str
    reason: str
    event_ids: tuple[str, ...]


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
    by the caller. This module does not infer cutoff reliability.
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
    """Canonical open-attempt report bound to one pending exit and holding.

    canonical_position_quantity_before/after are authoritative canonical
    position quantities for FILLED reports. entry_quantity in local technical
    state is deliberately not used to prove liquidation.
    """

    report_id: str
    ticker: str
    session_date: date
    session_index: int
    outcome: BaselineOpenExecutionOutcome
    reason: str
    pending_intent_id: str
    entry_fill_id: str
    canonical_position_quantity_before: float | None = None
    canonical_position_quantity_after: float | None = None
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


@dataclass(frozen=True)
class _CAPlan:
    ticker: str
    opening_key: tuple[str, date]
    items: tuple[BaselineCorporateActionInput, ...]
    event_ids: tuple[str, ...]
    status: BaselineCAApplyStatus
    reason: str
    cash_per_share: float
    share_multiplier: float
    transformed_history: tuple[BaselineObservedBar, ...] | None
    transformed_anchor: float | None


@dataclass
class Baseline60DExitState:
    """Standalone close-confirmed state module for baseline_60d_breakout_v1.

    It maintains technical state and exit intent only. It never creates a Fill,
    mutates canonical accounting, or wires itself into the canonical simulator.
    """

    histories: dict[str, list[BaselineObservedBar]] = field(default_factory=dict)
    holdings: dict[str, BaselineHoldingExitState] = field(default_factory=dict)
    processed_ca_inputs: dict[str, BaselineCorporateActionInput] = field(default_factory=dict)
    finalized_opening_batches: dict[tuple[str, date], tuple[str, ...]] = field(default_factory=dict)
    technical_blocks: dict[str, BaselineTickerTechnicalBlock] = field(default_factory=dict)
    terminal_audit: list[BaselineTerminalAudit] = field(default_factory=list)
    skipped_session_reasons: dict[str, list[str]] = field(default_factory=dict)
    retired_observation_counts: dict[str, int] = field(default_factory=dict)
    processed_open_report_ids: set[str] = field(default_factory=set)

    @property
    def applied_ca_event_ids(self) -> set[str]:
        """Compatibility/read-only view of CA ids already consumed."""
        return set(self.processed_ca_inputs)

    @staticmethod
    def _finite_positive(value: float | None) -> bool:
        return value is not None and math.isfinite(float(value)) and float(value) > 0

    @staticmethod
    def _finite_nonnegative(value: float | None) -> bool:
        return value is not None and math.isfinite(float(value)) and float(value) >= 0

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
            return BaselineWindowAudit(0, None, 0, ())
        skipped = sum(max(0, int(bar.gap_sessions_before)) for bar in bars[1:])
        reasons = tuple(
            str(bar.gap_reason)
            for bar in bars[1:]
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

    def technical_block_reason(self, ticker: str) -> str | None:
        block = self.technical_blocks.get(str(ticker))
        return None if block is None else block.reason

    def register_entry(self, fill: Fill, *, session_index: int) -> BaselineHoldingExitState:
        if fill.side.lower() != "buy":
            raise BaselineExitStateError("baseline entry requires a canonical buy Fill")
        if not self._finite_positive(fill.price) or fill.quantity <= 0:
            raise BaselineExitStateError("entry Fill must have positive price and quantity")
        ticker = str(fill.ticker)
        if ticker in self.holdings:
            raise BaselineExitStateError(f"active baseline holding already exists: {ticker}")
        block_reason = self.technical_block_reason(ticker)
        state = BaselineHoldingExitState(
            ticker=ticker,
            entry_fill_id=fill.fill_id,
            entry_session_index=int(session_index),
            entry_anchor=float(fill.price),
            entry_quantity=float(fill.quantity),
            entry_fee_audit=float(fill.fees),
            blocked_reason=block_reason,
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

        pending_gap_reasons = self.skipped_session_reasons.pop(ticker, [])
        gap_reason = bar.gap_reason
        if gap_sessions > 0 and not gap_reason:
            gap_reason = (
                "|".join(pending_gap_reasons)
                if pending_gap_reasons
                else "MISSING_OR_INVALID_SESSION_OBSERVATION"
            )

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
        excess = max(0, len(history) - ROLLING_BAR_LIMIT)
        if excess:
            del history[:excess]
            self.retired_observation_counts[ticker] = (
                self.retired_observation_counts.get(ticker, 0) + excess
            )
        return observed

    def _current_windows(
        self,
        ticker: str,
    ) -> tuple[BaselineWindowAudit, BaselineWindowAudit]:
        history = self.histories.get(str(ticker), [])
        atr_bars = history[-ATR_PERIOD:]
        prior_low_bars = history[-(LOW_WINDOW + 1):-1] if len(history) > 1 else []
        return self._window_audit(atr_bars), self._window_audit(prior_low_bars)

    def _unknown_evaluation(
        self,
        *,
        bar: BaselineBarInput,
        reason: str,
        holding: BaselineHoldingExitState | None,
        blocked_reason: str | None = None,
    ) -> BaselineExitEvaluation:
        atr_window, low_window = self._current_windows(str(bar.ticker))
        pending = None if holding is None else holding.pending_exit
        effective_block = blocked_reason or self.technical_block_reason(str(bar.ticker))
        if effective_block is not None:
            status = BaselineEvaluationStatus.BLOCKED
        elif holding is None:
            status = BaselineEvaluationStatus.NO_POSITION
        elif pending is not None:
            status = BaselineEvaluationStatus.PENDING
        else:
            status = BaselineEvaluationStatus.UNKNOWN
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
            atr_window=atr_window,
            low20_window=low_window,
            pending_exit=pending,
            blocked_reason=effective_block,
        )

    def observe_bar(self, bar: BaselineBarInput) -> BaselineExitEvaluation:
        ticker = str(bar.ticker)
        holding = self.holdings.get(ticker)
        reason = self._validate_bar(bar)
        if reason is not None:
            self.skipped_session_reasons.setdefault(ticker, []).append(reason)
            return self._unknown_evaluation(
                bar=bar,
                reason=reason,
                holding=holding,
            )

        block_reason = self.technical_block_reason(ticker)
        if block_reason is not None:
            return self._unknown_evaluation(
                bar=bar,
                reason="TICKER_TECHNICAL_BLOCKED",
                holding=holding,
                blocked_reason=block_reason,
            )

        current = self._append_valid_bar(bar)
        history = self.histories[ticker]
        atr_bars = history[-ATR_PERIOD:]
        prior_low_bars = history[-(LOW_WINDOW + 1):-1] if len(history) > 1 else []
        atr_window = self._window_audit(atr_bars)
        low_window = self._window_audit(prior_low_bars)

        if holding is None:
            return BaselineExitEvaluation(
                ticker=ticker,
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
                ticker=ticker,
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
                ticker=ticker,
                trigger_date=current.session_date,
                trigger_session_index=current.session_index,
                earliest_execution_session_index=current.session_index + 1,
                reason=reason_value,
                trigger_close=current.close,
                atr_value=atr_value,
                atr_threshold=atr_threshold,
                low20_reference=low_reference,
                intent_id=(
                    f"baseline60d:{ticker}:"
                    f"{current.session_date.isoformat()}:{reason_value.value}"
                ),
            )
            holding.pending_exit = pending
            return BaselineExitEvaluation(
                ticker=ticker,
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
            ticker=ticker,
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
        ticker = str(ticker)
        holding = self.holdings.get(ticker)
        if holding is None or holding.pending_exit is None:
            return None
        if self.technical_block_reason(ticker) is not None:
            return None
        if session_index < holding.pending_exit.earliest_execution_session_index:
            return None
        return holding.pending_exit

    def record_open_execution(self, result: BaselineOpenExecutionResult) -> None:
        if not str(result.report_id).strip():
            raise BaselineExitStateError("open execution report_id is required")
        if result.report_id in self.processed_open_report_ids:
            raise BaselineExitStateError(
                f"DUPLICATE_OPEN_EXECUTION_REPORT:{result.report_id}"
            )

        ticker = str(result.ticker)
        holding = self.holdings.get(ticker)
        if holding is None or holding.pending_exit is None:
            raise BaselineExitStateError(
                f"STALE_OPEN_EXECUTION_REPORT:no pending baseline exit for {ticker}"
            )
        pending = holding.pending_exit

        if self.technical_block_reason(ticker) is not None:
            raise BaselineExitStateError(
                f"TICKER_TECHNICAL_BLOCKED:{ticker}"
            )
        if result.pending_intent_id != pending.intent_id:
            raise BaselineExitStateError("open execution pending intent mismatch")
        if result.entry_fill_id != holding.entry_fill_id:
            raise BaselineExitStateError("open execution holding identity mismatch")
        if result.session_index < pending.earliest_execution_session_index:
            raise BaselineExitStateError(
                "pending baseline exit cannot execute on trigger session"
            )
        if result.session_date <= pending.trigger_date:
            raise BaselineExitStateError(
                "open execution session_date must follow trigger_date"
            )

        if result.outcome is BaselineOpenExecutionOutcome.FILLED:
            fill = result.fill
            if fill is None:
                raise BaselineExitStateError("FILLED outcome requires canonical Fill")
            if fill.side.lower() != "sell" or str(fill.ticker) != ticker:
                raise BaselineExitStateError(
                    "exit Fill must be matching ticker sell"
                )
            if fill.filled_at.date() != result.session_date:
                raise BaselineExitStateError(
                    "exit Fill date must match reported open session"
                )
            if not self._finite_positive(fill.price) or fill.quantity <= 0:
                raise BaselineExitStateError(
                    "exit Fill price and quantity must be finite and positive"
                )
            before = result.canonical_position_quantity_before
            after = result.canonical_position_quantity_after
            if not self._finite_positive(before):
                raise BaselineExitStateError(
                    "FILLED report requires positive canonical quantity before"
                )
            if not self._finite_nonnegative(after):
                raise BaselineExitStateError(
                    "FILLED report requires non-negative canonical quantity after"
                )
            if abs(float(fill.quantity) - float(before)) > _FLOAT_TOLERANCE:
                raise BaselineExitStateError(
                    "PARTIAL_EXIT_NOT_SUPPORTED:fill quantity does not equal "
                    "canonical quantity before"
                )
            if abs(float(after)) > _FLOAT_TOLERANCE:
                raise BaselineExitStateError(
                    "PARTIAL_EXIT_NOT_SUPPORTED:canonical position remains open"
                )
        else:
            if result.fill is not None:
                raise BaselineExitStateError(
                    "non-FILLED open result must not include a Fill"
                )

        self.processed_open_report_ids.add(result.report_id)
        holding.open_attempts += 1
        if result.outcome is BaselineOpenExecutionOutcome.FILLED:
            self.holdings.pop(ticker, None)

    @staticmethod
    def _transform_price(value: float, *, cash: float, multiplier: float) -> float:
        transformed = (float(value) - cash) / multiplier
        if not math.isfinite(transformed) or transformed <= 0:
            raise BaselineExitStateError(
                "CA-transformed technical price must remain finite and positive"
            )
        return transformed

    def _block_ticker(
        self,
        ticker: str,
        reason: str,
        *,
        event_ids: Sequence[str] = (),
    ) -> None:
        ticker = str(ticker)
        if ticker not in self.technical_blocks:
            self.technical_blocks[ticker] = BaselineTickerTechnicalBlock(
                ticker=ticker,
                reason=reason,
                event_ids=tuple(event_ids),
            )
        holding = self.holdings.get(ticker)
        if holding is not None:
            holding.blocked_reason = self.technical_blocks[ticker].reason

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

    def _materialize_and_dedupe_ca(
        self,
        items: Iterable[BaselineCorporateActionInput],
    ) -> tuple[
        tuple[BaselineCorporateActionInput, ...],
        tuple[BaselineCorporateActionInput, ...],
    ]:
        materialized = tuple(items)
        by_id: dict[str, BaselineCorporateActionInput] = {}
        for item in materialized:
            event_id = str(item.instruction.event.event_id)
            if not event_id.strip():
                raise BaselineExitStateError("corporate-action event_id is required")
            previous = by_id.get(event_id)
            if previous is not None:
                if previous != item:
                    raise BaselineExitStateError(
                        f"CONFLICTING_CA_EVENT_ID_IN_BATCH:{event_id}"
                    )
                continue
            prior_processed = self.processed_ca_inputs.get(event_id)
            if prior_processed is not None and prior_processed != item:
                raise BaselineExitStateError(
                    f"CONFLICTING_CA_EVENT_ID_ALREADY_PROCESSED:{event_id}"
                )
            by_id[event_id] = item

        new_items = tuple(
            item
            for event_id, item in by_id.items()
            if event_id not in self.processed_ca_inputs
        )
        duplicates = tuple(
            item
            for event_id, item in by_id.items()
            if event_id in self.processed_ca_inputs
        )
        return new_items, duplicates

    def _plan_ca_group(
        self,
        *,
        ticker: str,
        opening_key: tuple[str, date],
        group: tuple[BaselineCorporateActionInput, ...],
        session_start: datetime,
        decision_cutoff: datetime,
    ) -> _CAPlan:
        event_ids = tuple(item.instruction.event.event_id for item in group)
        events = tuple(item.instruction.event for item in group)

        if opening_key in self.finalized_opening_batches:
            raise BaselineExitStateError(
                "OPENING_CA_BATCH_ALREADY_FINALIZED:"
                f"{ticker}:{session_start.date().isoformat()}"
            )
        if any(
            item.instruction.applied_at > session_start
            or item.instruction.event.effective_at > session_start
            for item in group
        ):
            raise BaselineExitStateError(
                f"CA_NOT_EFFECTIVE_AT_OPEN:{ticker}"
            )

        history = self.histories.get(ticker, [])
        if history and history[-1].session_date >= session_start.date():
            raise BaselineExitStateError(
                "opening CA must be applied before same-session technical bar"
            )

        block_reason: str | None = None
        if self.technical_block_reason(ticker) is not None:
            block_reason = "TICKER_TECHNICAL_STATE_ALREADY_BLOCKED"
        elif any(not item.approved_for_technical_transform for item in group):
            block_reason = "CA_TECHNICAL_TRANSFORM_NOT_APPROVED"
        elif any(event.known_at is None for event in events):
            block_reason = "CA_KNOWN_AT_UNKNOWN"
        elif any(
            event.known_at > decision_cutoff
            for event in events
            if event.known_at is not None
        ):
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

        cash = sum(float(event.cash_per_share or 0.0) for event in events)
        multiplier = 1.0
        for event in events:
            multiplier *= float(event.share_multiplier or 1.0)

        if block_reason is None and (not math.isfinite(cash) or cash < 0):
            block_reason = "CA_CASH_COMPONENT_INVALID"
        if block_reason is None and (
            not math.isfinite(multiplier) or multiplier <= 0
        ):
            block_reason = "CA_SHARE_MULTIPLIER_INVALID"

        if block_reason is not None:
            return _CAPlan(
                ticker=ticker,
                opening_key=opening_key,
                items=group,
                event_ids=event_ids,
                status=BaselineCAApplyStatus.BLOCKED,
                reason=block_reason,
                cash_per_share=cash,
                share_multiplier=multiplier,
                transformed_history=None,
                transformed_anchor=None,
            )

        transformed_history: list[BaselineObservedBar] = []
        transformed_anchor: float | None = None
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
            if holding is not None:
                transformed_anchor = self._transform_price(
                    holding.entry_anchor,
                    cash=cash,
                    multiplier=multiplier,
                )
        except BaselineExitStateError:
            return _CAPlan(
                ticker=ticker,
                opening_key=opening_key,
                items=group,
                event_ids=event_ids,
                status=BaselineCAApplyStatus.BLOCKED,
                reason="CA_TRANSFORM_NONPOSITIVE_OR_NONFINITE",
                cash_per_share=cash,
                share_multiplier=multiplier,
                transformed_history=None,
                transformed_anchor=None,
            )

        return _CAPlan(
            ticker=ticker,
            opening_key=opening_key,
            items=group,
            event_ids=event_ids,
            status=BaselineCAApplyStatus.APPLIED,
            reason="CA_TECHNICAL_COORDINATE_TRANSFORM_APPLIED",
            cash_per_share=cash,
            share_multiplier=multiplier,
            transformed_history=tuple(transformed_history),
            transformed_anchor=transformed_anchor,
        )

    def apply_opening_corporate_actions(
        self,
        items: Iterable[BaselineCorporateActionInput],
        *,
        session_start: datetime,
        decision_cutoff: datetime,
    ) -> tuple[BaselineCorporateActionResult, ...]:
        """Atomically consume one complete opening CA batch.

        The iterable is materialized before validation. Equal duplicate event IDs
        are deduplicated; conflicting definitions reject the whole call. A
        ticker/opening is finalized on first new batch so later split-batch
        additions are rejected instead of silently creating a different price
        coordinate.
        """

        new_items, duplicates = self._materialize_and_dedupe_ca(items)
        duplicate_results = tuple(
            BaselineCorporateActionResult(
                ticker=str(item.instruction.event.ticker),
                event_ids=(item.instruction.event.event_id,),
                status=BaselineCAApplyStatus.DUPLICATE_IGNORED,
                reason="EVENT_ID_ALREADY_SEEN",
            )
            for item in duplicates
        )
        if not new_items:
            return duplicate_results

        grouped: dict[str, list[BaselineCorporateActionInput]] = {}
        for item in new_items:
            ticker = str(item.instruction.event.ticker)
            grouped.setdefault(ticker, []).append(item)

        plans: list[_CAPlan] = []
        for ticker, group_items in grouped.items():
            opening_key = (ticker, session_start.date())
            plans.append(
                self._plan_ca_group(
                    ticker=ticker,
                    opening_key=opening_key,
                    group=tuple(group_items),
                    session_start=session_start,
                    decision_cutoff=decision_cutoff,
                )
            )

        # Commit only after every group has been fully validated/planned.
        results: list[BaselineCorporateActionResult] = list(duplicate_results)
        for plan in plans:
            for item in plan.items:
                event_id = item.instruction.event.event_id
                self.processed_ca_inputs[event_id] = item
            self.finalized_opening_batches[plan.opening_key] = plan.event_ids

            if plan.status is BaselineCAApplyStatus.BLOCKED:
                self._block_ticker(
                    plan.ticker,
                    plan.reason,
                    event_ids=plan.event_ids,
                )
            else:
                self.histories[plan.ticker] = list(plan.transformed_history or ())
                holding = self.holdings.get(plan.ticker)
                if holding is not None and plan.transformed_anchor is not None:
                    holding.entry_anchor = plan.transformed_anchor

            results.append(
                BaselineCorporateActionResult(
                    ticker=plan.ticker,
                    event_ids=plan.event_ids,
                    status=plan.status,
                    reason=plan.reason,
                    cash_per_share=plan.cash_per_share,
                    share_multiplier=plan.share_multiplier,
                )
            )

        return tuple(results)

    def record_terminal_result(
        self,
        result: BaselineTerminalResult,
    ) -> BaselineTerminalAudit:
        ticker = str(result.ticker)
        holding = self.holdings.get(ticker)
        pending = None if holding is None else holding.pending_exit

        if result.disposition is BaselineTerminalDisposition.EXTINGUISHED:
            self.holdings.pop(ticker, None)
        elif result.disposition is BaselineTerminalDisposition.CANONICAL_LIFECYCLE_REQUIRED:
            self._block_ticker(
                ticker,
                "CANONICAL_LIFECYCLE_REQUIRED",
            )

        audit = BaselineTerminalAudit(
            ticker=ticker,
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
        """Return only the active rolling technical window (max 21 valid bars)."""
        return tuple(self.histories.get(str(ticker), ()))

    def retired_observation_count(self, ticker: str) -> int:
        return int(self.retired_observation_counts.get(str(ticker), 0))
