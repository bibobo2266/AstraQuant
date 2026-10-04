from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from astraquant.portfolio.corporate_actions import (
    CorporateActionEvent,
    CorporateActionType,
)
from astraquant.portfolio.historical_runner import (
    HistoricalCorporateActionInstruction,
)
from astraquant.portfolio.models import Fill
from astraquant.research.baseline_60d_exit_state import (
    Baseline60DExitState,
    BaselineBarInput,
    BaselineCAApplyStatus,
    BaselineCorporateActionInput,
    BaselineEvaluationStatus,
    BaselineExitReason,
    BaselineExitStateError,
    BaselineOpenExecutionOutcome,
    BaselineOpenExecutionResult,
    BaselineTerminalDisposition,
    BaselineTerminalResult,
    BaselineTriState,
)


BASE_DAY = date(2026, 1, 2)


def _day(index: int) -> date:
    return BASE_DAY + timedelta(days=index)


def _bar(
    index: int,
    *,
    ticker: str = "2330",
    close: float = 100.0,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    observed_trade: bool = True,
    valid_ohlc: bool = True,
    gap_reason: str | None = None,
) -> BaselineBarInput:
    open_value = close if open_ is None else open_
    high_value = close + 1.0 if high is None else high
    low_value = close - 1.0 if low is None else low
    return BaselineBarInput(
        ticker=ticker,
        session_date=_day(index),
        session_index=index,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close,
        observed_trade=observed_trade,
        valid_ohlc=valid_ohlc,
        gap_reason=gap_reason,
    )


def _fill(
    *,
    ticker: str = "2330",
    price: float = 100.0,
    fees: float = 0.0,
    side: str = "buy",
    suffix: str = "entry",
    quantity: float = 1000.0,
    filled_index: int = 0,
) -> Fill:
    return Fill(
        fill_id=f"{suffix}-{ticker}",
        order_id=f"order-{suffix}-{ticker}",
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        filled_at=datetime.combine(_day(filled_index), datetime.min.time()),
    )


def _seed_flat(
    state: Baseline60DExitState,
    count: int,
    *,
    ticker: str = "2330",
    start_index: int = 0,
    close: float = 100.0,
) -> None:
    for index in range(start_index, start_index + count):
        result = state.observe_bar(_bar(index, ticker=ticker, close=close))
        assert result.observation_accepted is True


def _ca(
    *,
    event_id: str,
    ticker: str = "2330",
    effective_index: int,
    event_type: CorporateActionType,
    cash_per_share: float | None = None,
    share_multiplier: float | None = None,
    known_index: int | None = None,
    successor_ticker: str | None = None,
    successor_multiplier: float | None = None,
    extinguish_position: bool = False,
    source: str = "synthetic-approved",
    approved: bool = True,
) -> BaselineCorporateActionInput:
    effective_at = datetime.combine(_day(effective_index), datetime.min.time())
    known_at = (
        None
        if known_index is None
        else datetime.combine(_day(known_index), datetime.min.time())
    )
    event = CorporateActionEvent(
        event_id=event_id,
        ticker=ticker,
        event_type=event_type,
        effective_at=effective_at,
        known_at=known_at,
        cash_per_share=cash_per_share,
        share_multiplier=share_multiplier,
        source=source,
    )
    return BaselineCorporateActionInput(
        instruction=HistoricalCorporateActionInstruction(
            event=event,
            applied_at=effective_at,
            successor_ticker=successor_ticker,
            successor_multiplier=successor_multiplier,
            extinguish_position=extinguish_position,
        ),
        approved_for_technical_transform=approved,
    )


def _apply_ca(
    state: Baseline60DExitState,
    *items: BaselineCorporateActionInput,
    effective_index: int,
):
    return state.apply_opening_corporate_actions(
        items,
        session_start=datetime.combine(
            _day(effective_index),
            datetime.min.time(),
        ),
        decision_cutoff=datetime.combine(
            _day(effective_index),
            datetime.min.time(),
        ),
    )


def _make_both_pending(
    state: Baseline60DExitState,
    *,
    ticker: str = "2330",
    entry_index: int = 20,
) -> None:
    _seed_flat(state, 20, ticker=ticker, close=100.0)
    state.register_entry(
        _fill(ticker=ticker, price=100.0),
        session_index=entry_index,
    )
    result = state.observe_bar(
        _bar(
            entry_index,
            ticker=ticker,
            close=90.0,
            open_=100.0,
            high=101.0,
            low=89.0,
        )
    )
    assert result.pending_exit is not None
    assert result.pending_exit.reason is BaselineExitReason.BOTH


def _open_result(
    state: Baseline60DExitState,
    *,
    session_index: int,
    outcome: BaselineOpenExecutionOutcome,
    ticker: str = "2330",
    report_id: str | None = None,
    fill_quantity: float = 1000.0,
    canonical_before: float | None = None,
    canonical_after: float | None = None,
    pending_intent_id: str | None = None,
    entry_fill_id: str | None = None,
) -> BaselineOpenExecutionResult:
    holding = state.holding_state(ticker)
    assert holding is not None
    assert holding.pending_exit is not None
    pending = holding.pending_exit
    fill = None
    if outcome is BaselineOpenExecutionOutcome.FILLED:
        fill = _fill(
            ticker=ticker,
            price=89.0,
            side="sell",
            suffix=f"exit-{session_index}",
            quantity=fill_quantity,
            filled_index=session_index,
        )
        if canonical_before is None:
            canonical_before = fill_quantity
        if canonical_after is None:
            canonical_after = 0.0
    return BaselineOpenExecutionResult(
        report_id=report_id or f"report-{ticker}-{session_index}-{outcome.value}",
        ticker=ticker,
        session_date=_day(session_index),
        session_index=session_index,
        outcome=outcome,
        reason=outcome.value,
        pending_intent_id=pending_intent_id or pending.intent_id,
        entry_fill_id=entry_fill_id or holding.entry_fill_id,
        canonical_position_quantity_before=canonical_before,
        canonical_position_quantity_after=canonical_after,
        fill=fill,
    )


def test_atr14_sma_includes_current_and_low20_excludes_current_with_strict_boundary():
    state = Baseline60DExitState()
    state.register_entry(_fill(price=50.0), session_index=0)

    evaluations = [
        state.observe_bar(_bar(index, close=100.0))
        for index in range(21)
    ]

    day14 = evaluations[13]
    assert day14.atr_value == pytest.approx(2.0)
    assert day14.atr_window.observation_count == 14
    assert day14.atr_state is BaselineTriState.FALSE

    equality = evaluations[20]
    assert equality.low20_reference == pytest.approx(100.0)
    assert equality.low20_state is BaselineTriState.FALSE
    assert equality.low20_window.observation_count == 20
    assert equality.low20_window.session_span == 20

    strict_below = state.observe_bar(
        _bar(21, close=99.0, open_=100.0, high=101.0, low=98.0)
    )
    assert strict_below.low20_reference == pytest.approx(100.0)
    assert strict_below.low20_state is BaselineTriState.TRUE
    assert strict_below.pending_exit is not None
    assert strict_below.pending_exit.reason is BaselineExitReason.LOW20


def test_warmup_suspension_invalid_bar_and_gap_audit_remain_unknown():
    state = Baseline60DExitState()
    state.register_entry(_fill(price=50.0), session_index=0)

    for index in range(5):
        result = state.observe_bar(_bar(index))
        assert result.status is BaselineEvaluationStatus.UNKNOWN

    suspended = state.observe_bar(
        _bar(
            5,
            observed_trade=False,
            valid_ohlc=False,
        )
    )
    assert suspended.observation_accepted is False
    assert suspended.observation_reason == "NOT_OBSERVED"
    assert suspended.atr_state is BaselineTriState.UNKNOWN

    invalid = state.observe_bar(
        _bar(
            6,
            high=95.0,
            low=99.0,
            valid_ohlc=True,
        )
    )
    assert invalid.observation_accepted is False
    assert invalid.observation_reason == "INVALID_OHLC_GEOMETRY"

    resumed = state.observe_bar(_bar(7))
    assert resumed.status is BaselineEvaluationStatus.UNKNOWN
    assert resumed.atr_window.skipped_sessions == 2
    assert resumed.atr_window.gap_reasons == (
        "NOT_OBSERVED|INVALID_OHLC_GEOMETRY",
    )
    assert len(state.history("2330")) == 6


@pytest.mark.parametrize(
    "event_type,cash,share,expected_anchor,expected_atr",
    [
        (CorporateActionType.CASH_DIVIDEND, 10.0, None, 90.0, 2.0),
        (CorporateActionType.SPLIT, None, 2.0, 50.0, 1.0),
    ],
)
def test_cash_and_share_ca_transform_anchor_and_whole_rolling_state_without_false_trigger(
    event_type,
    cash,
    share,
    expected_anchor,
    expected_atr,
):
    state = Baseline60DExitState()
    state.register_entry(_fill(price=100.0), session_index=0)
    _seed_flat(state, 21)

    item = _ca(
        event_id=f"ca-{event_type.value}",
        effective_index=21,
        event_type=event_type,
        cash_per_share=cash,
        share_multiplier=share,
        known_index=20,
    )
    result = _apply_ca(state, item, effective_index=21)
    assert result[0].status is BaselineCAApplyStatus.APPLIED
    assert state.holding_state("2330").entry_anchor == pytest.approx(
        expected_anchor
    )
    assert state.history("2330")[-1].close == pytest.approx(expected_anchor)

    observed = state.observe_bar(
        _bar(
            21,
            close=expected_anchor,
            open_=expected_anchor,
            high=expected_anchor + expected_atr / 2,
            low=expected_anchor - expected_atr / 2,
        )
    )
    assert observed.atr_value == pytest.approx(expected_atr)
    assert observed.atr_state is BaselineTriState.FALSE
    assert observed.low20_state is BaselineTriState.FALSE
    assert observed.pending_exit is None


def test_same_open_cash_plus_share_is_one_coordinate_transform_without_per_event_rounding():
    state = Baseline60DExitState()
    state.register_entry(_fill(price=100.0), session_index=0)
    _seed_flat(state, 21)

    share = _ca(
        event_id="share",
        effective_index=21,
        event_type=CorporateActionType.SPLIT,
        share_multiplier=2.0,
        known_index=20,
    )
    cash = _ca(
        event_id="cash",
        effective_index=21,
        event_type=CorporateActionType.CASH_DIVIDEND,
        cash_per_share=10.0,
        known_index=20,
    )

    results = _apply_ca(state, share, cash, effective_index=21)
    assert len(results) == 1
    assert set(results[0].event_ids) == {"share", "cash"}
    assert results[0].cash_per_share == pytest.approx(10.0)
    assert results[0].share_multiplier == pytest.approx(2.0)
    assert state.holding_state("2330").entry_anchor == pytest.approx(45.0)
    assert state.history("2330")[0].high == pytest.approx(45.5)

    observed = state.observe_bar(
        _bar(21, close=45.0, open_=45.0, high=45.5, low=44.5)
    )
    assert observed.atr_value == pytest.approx(1.0)
    assert observed.atr_state is BaselineTriState.FALSE
    assert observed.low20_state is BaselineTriState.FALSE


def test_entry_fee_is_not_in_anchor_and_duplicate_ca_is_not_reapplied():
    state = Baseline60DExitState()
    state.register_entry(
        _fill(price=100.10, fees=142.64),
        session_index=0,
    )
    assert state.holding_state("2330").entry_anchor == pytest.approx(100.10)
    assert state.holding_state("2330").entry_fee_audit == pytest.approx(142.64)

    _seed_flat(state, 1, close=100.10)
    cash = _ca(
        event_id="cash-once",
        effective_index=1,
        event_type=CorporateActionType.CASH_DIVIDEND,
        cash_per_share=5.0,
        known_index=0,
    )
    first = _apply_ca(state, cash, effective_index=1)
    assert first[0].status is BaselineCAApplyStatus.APPLIED
    assert state.holding_state("2330").entry_anchor == pytest.approx(95.10)

    duplicate = _apply_ca(state, cash, effective_index=1)
    assert duplicate[0].status is BaselineCAApplyStatus.DUPLICATE_IGNORED
    assert state.holding_state("2330").entry_anchor == pytest.approx(95.10)


def test_entry_day_close_can_create_pending_but_same_session_open_cannot_fill():
    state = Baseline60DExitState()
    _seed_flat(state, 20)
    state.register_entry(_fill(price=100.0), session_index=20)

    close_eval = state.observe_bar(
        _bar(20, close=90.0, open_=100.0, high=101.0, low=89.0)
    )
    assert close_eval.pending_exit is not None
    assert close_eval.pending_exit.reason is BaselineExitReason.BOTH
    assert state.pending_for_open("2330", session_index=20) is None
    assert state.pending_for_open("2330", session_index=21) is close_eval.pending_exit

    with pytest.raises(BaselineExitStateError, match="cannot execute on trigger session"):
        state.record_open_execution(
            _open_result(
                state,
                session_index=20,
                outcome=BaselineOpenExecutionOutcome.FILLED,
                report_id="same-session-invalid",
            )
        )
    assert state.holding_state("2330").open_attempts == 0


def test_sell_blocked_and_missing_open_keep_original_pending_sticky():
    state = Baseline60DExitState()
    _make_both_pending(state)
    original = state.holding_state("2330").pending_exit

    state.record_open_execution(
        _open_result(
            state,
            session_index=21,
            outcome=BaselineOpenExecutionOutcome.SELL_BLOCKED,
            report_id="blocked-21",
        )
    )
    state.record_open_execution(
        _open_result(
            state,
            session_index=22,
            outcome=BaselineOpenExecutionOutcome.NO_VALID_OPEN,
            report_id="missing-open-22",
        )
    )
    rebound = state.observe_bar(
        _bar(21, close=110.0, open_=110.0, high=111.0, low=109.0)
    )

    holding = state.holding_state("2330")
    assert holding.pending_exit is original
    assert holding.pending_exit.reason is BaselineExitReason.BOTH
    assert holding.open_attempts == 2
    assert rebound.status is BaselineEvaluationStatus.PENDING


def test_later_secondary_trigger_does_not_rewrite_original_pending_reason():
    state = Baseline60DExitState()
    state.register_entry(_fill(price=100.0), session_index=0)

    for index in range(13):
        state.observe_bar(_bar(index, close=100.0))

    atr_only = state.observe_bar(
        _bar(13, close=90.0, open_=100.0, high=101.0, low=89.0)
    )
    assert atr_only.atr_state is BaselineTriState.TRUE
    assert atr_only.low20_state is BaselineTriState.UNKNOWN
    assert atr_only.pending_exit.reason is BaselineExitReason.ATR
    original = atr_only.pending_exit

    for index in range(14, 21):
        state.observe_bar(_bar(index, close=100.0))
    later = state.observe_bar(
        _bar(21, close=80.0, open_=90.0, high=91.0, low=79.0)
    )

    assert later.low20_state is BaselineTriState.TRUE
    assert state.holding_state("2330").pending_exit is original
    assert state.holding_state("2330").pending_exit.reason is BaselineExitReason.ATR


def test_successful_canonical_sell_fill_is_the_only_open_result_that_clears_holding():
    state = Baseline60DExitState()
    _make_both_pending(state)

    state.record_open_execution(
        _open_result(
            state,
            session_index=21,
            outcome=BaselineOpenExecutionOutcome.FILLED,
            report_id="full-exit-21",
            fill_quantity=1000.0,
            canonical_before=1000.0,
            canonical_after=0.0,
        )
    )
    assert state.holding_state("2330") is None


def test_terminal_extinguishment_supersedes_pending_without_strategy_sell():
    state = Baseline60DExitState()
    _make_both_pending(state)
    pending = state.holding_state("2330").pending_exit

    audit = state.record_terminal_result(
        BaselineTerminalResult(
            ticker="2330",
            session_date=_day(21),
            disposition=BaselineTerminalDisposition.EXTINGUISHED,
            reason="canonical terminal cashout",
        )
    )
    assert audit.superseded_pending is pending
    assert state.holding_state("2330") is None

    with pytest.raises(BaselineExitStateError, match="STALE_OPEN_EXECUTION_REPORT"):
        state.record_open_execution(
            BaselineOpenExecutionResult(
                report_id="terminal-stale-report",
                ticker="2330",
                session_date=_day(21),
                session_index=21,
                outcome=BaselineOpenExecutionOutcome.FILLED,
                reason="must not duplicate terminal",
                pending_intent_id=pending.intent_id,
                entry_fill_id="entry-2330",
                canonical_position_quantity_before=1000.0,
                canonical_position_quantity_after=0.0,
                fill=_fill(
                    ticker="2330",
                    price=90.0,
                    side="sell",
                    suffix="duplicate-exit",
                    quantity=1000.0,
                    filled_index=21,
                ),
            )
        )


def test_successor_and_unknown_ca_block_technical_evaluation_without_losing_state():
    state = Baseline60DExitState()
    _make_both_pending(state)
    original = state.holding_state("2330").pending_exit

    successor = _ca(
        event_id="successor",
        effective_index=21,
        event_type=CorporateActionType.MERGER,
        known_index=20,
        successor_ticker="3715",
        successor_multiplier=1.0,
        approved=True,
    )
    result = _apply_ca(state, successor, effective_index=21)
    assert result[0].status is BaselineCAApplyStatus.BLOCKED
    assert result[0].reason == "CANONICAL_LIFECYCLE_REQUIRED"
    holding = state.holding_state("2330")
    assert holding is not None
    assert holding.pending_exit is original
    assert holding.blocked_reason == "CANONICAL_LIFECYCLE_REQUIRED"
    assert state.pending_for_open("2330", session_index=21) is None

    audit = state.record_terminal_result(
        BaselineTerminalResult(
            ticker="2330",
            session_date=_day(21),
            disposition=BaselineTerminalDisposition.CANONICAL_LIFECYCLE_REQUIRED,
            reason="successor mapping stays canonical",
        )
    )
    assert audit.superseded_pending is None
    assert state.holding_state("2330") is holding


def test_unknown_ca_mapping_is_blocked_without_destroying_holding():
    state = Baseline60DExitState()
    state.register_entry(_fill(price=100.0), session_index=0)
    _seed_flat(state, 1)

    unknown = _ca(
        event_id="unknown-other",
        effective_index=1,
        event_type=CorporateActionType.OTHER,
        cash_per_share=1.0,
        known_index=0,
        approved=True,
    )
    result = _apply_ca(state, unknown, effective_index=1)

    assert result[0].status is BaselineCAApplyStatus.BLOCKED
    assert result[0].reason == "CANONICAL_LIFECYCLE_REQUIRED"
    holding = state.holding_state("2330")
    assert holding is not None
    assert holding.entry_anchor == pytest.approx(100.0)
    assert holding.blocked_reason == "CANONICAL_LIFECYCLE_REQUIRED"


def test_late_known_or_nonpositive_ca_blocks_without_partial_transform():
    late_state = Baseline60DExitState()
    late_state.register_entry(_fill(price=100.0), session_index=0)
    _seed_flat(late_state, 1)
    late = _ca(
        event_id="late",
        effective_index=1,
        event_type=CorporateActionType.CASH_DIVIDEND,
        cash_per_share=5.0,
        known_index=2,
    )
    late_result = _apply_ca(late_state, late, effective_index=1)
    assert late_result[0].status is BaselineCAApplyStatus.BLOCKED
    assert late_result[0].reason == "CA_NOT_KNOWN_BY_CUTOFF"
    assert late_state.holding_state("2330").entry_anchor == pytest.approx(100.0)
    assert late_state.history("2330")[0].close == pytest.approx(100.0)

    invalid_state = Baseline60DExitState()
    invalid_state.register_entry(_fill(price=100.0), session_index=0)
    _seed_flat(invalid_state, 1)
    invalid = _ca(
        event_id="invalid-price",
        effective_index=1,
        event_type=CorporateActionType.CASH_DIVIDEND,
        cash_per_share=150.0,
        known_index=0,
    )
    invalid_result = _apply_ca(invalid_state, invalid, effective_index=1)
    assert invalid_result[0].status is BaselineCAApplyStatus.BLOCKED
    assert invalid_result[0].reason == "CA_TRANSFORM_NONPOSITIVE_OR_NONFINITE"
    assert invalid_state.holding_state("2330").entry_anchor == pytest.approx(100.0)
    assert invalid_state.history("2330")[0].close == pytest.approx(100.0)


def test_multi_stock_state_and_ca_transforms_are_isolated():
    state = Baseline60DExitState()
    state.register_entry(_fill(ticker="2330", price=100.0), session_index=0)
    state.register_entry(_fill(ticker="2317", price=50.0), session_index=0)
    _seed_flat(state, 21, ticker="2330", close=100.0)
    _seed_flat(state, 21, ticker="2317", close=50.0)

    cash = _ca(
        event_id="2330-only",
        ticker="2330",
        effective_index=21,
        event_type=CorporateActionType.CASH_DIVIDEND,
        cash_per_share=10.0,
        known_index=20,
    )
    _apply_ca(state, cash, effective_index=21)

    assert state.holding_state("2330").entry_anchor == pytest.approx(90.0)
    assert state.holding_state("2317").entry_anchor == pytest.approx(50.0)
    assert state.history("2330")[-1].close == pytest.approx(90.0)
    assert state.history("2317")[-1].close == pytest.approx(50.0)


def test_period_end_leaves_pending_open_without_forced_close_or_future_read():
    state = Baseline60DExitState()
    _make_both_pending(state)
    holding = state.holding_state("2330")
    pending = holding.pending_exit

    assert pending.earliest_execution_session_index == 21
    assert state.pending_for_open("2330", session_index=21) is pending
    assert state.holding_state("2330") is holding
