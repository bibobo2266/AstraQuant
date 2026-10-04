from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import (
    FixedBpsSlippage,
    SideAwareBpsFeeModel,
    ZeroFeeModel,
)
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.corporate_actions import (
    CashEntitlementBasis,
    CorporateActionEvent,
    CorporateActionType,
)
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import (
    CanonicalStrategySimulator,
    StrategySimulationConfig,
)
from astraquant.research.baseline_60d_exit_state import BaselineExitReason
from astraquant.research.baseline_60d_simulation import (
    BaselineCATechnicalApproval,
    BaselineSimulationContext,
    BaselineSimulationMode,
)
from astraquant.research.config_engine import ResearchConfigEngine
from astraquant.research.exit_engine import ExitCompiler
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import ExitConfig, ExitRuleConfig
from astraquant.research.universe_engine import UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sessions(count: int = 66) -> list[date]:
    return [ts.date() for ts in pd.bdate_range("2026-01-02", periods=count)]


def _baseline_closes(
    *,
    count: int = 66,
    entry_close: float = 105.0,
    tail: dict[int, float] | None = None,
) -> list[float]:
    if count < 63:
        raise ValueError("baseline fixture needs at least 63 sessions")
    closes = [100.0] * count
    closes[61] = 110.0
    closes[62] = float(entry_close)
    for index, value in (tail or {}).items():
        closes[index] = float(value)
    return closes


def _panel(sessions: list[date], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(sessions),
            "stock_id": "2330",
            "close": closes,
            "Trading_money": 50_000_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
            "close_to_ma120": 0.10,
            "prior20_amount_twd": 30_000_000.0,
        }
    )


def _write_configs(root: Path, *, baseline: bool = True) -> Path:
    _write(
        root / "configs/universes/u.yaml",
        f"""
schema_version: "1"
name: all
base:
  ticker_pattern: '^[1-9]\\d{{3}}$'
  min_close_twd: 10
  require_observed_trade: true
  require_valid_ohlc: true
  p2_060_exclusion_sha256: "{P2_SHA}"
combine: AND
pools:
  - type: ALL
    turnover_top_fraction: 1.0
""",
    )
    _write(
        root / "configs/signals/s.yaml",
        """
schema_version: "1"
name: baseline60d_signal_fixture
trigger:
  type: N_SESSION_HIGH
  params: {lookback: 60}
filters:
  - type: COLUMN_THRESHOLD
    params: {column: close_to_ma120, min: 0.0}
  - type: COLUMN_THRESHOLD
    params: {column: prior20_amount_twd, min: 20000000}
filter_combine: AND
ranking: []
""",
    )
    if baseline:
        exit_text = """
schema_version: "1"
name: baseline60d_exit_fixture
first_trigger_wins: false
rules:
  - type: ATR_FROM_ENTRY_STOP
    params:
      period: 14
      multiplier: 3.0
      smoothing: SMA
      trigger_field: CLOSE
      execution: NEXT_OPEN
      observation_basis: VALID_OBSERVED_OHLC
  - type: BREAK_N_DAY_LOW
    params:
      window: 20
      field: CLOSE
      exclude_current: true
      strict: true
      execution: NEXT_OPEN
      observation_basis: VALID_OBSERVED_OHLC
"""
    else:
        exit_text = """
schema_version: "1"
name: legacy_exit_fixture
rules:
  - type: FIXED_STOP_TARGET
    params: {stop_pct: 0.12, target_pct: null}
  - type: TIME_EXIT
    params: {sessions: 250}
"""
    _write(root / "configs/exits/e.yaml", exit_text)
    run = root / "configs/runs/r.yaml"
    _write(
        run,
        """
schema_version: "1"
run_name: baseline60d_synthetic_e2e
strategy_version: baseline_60d_breakout_v1_synthetic_acceptance
universe: configs/universes/u.yaml
signal: configs/signals/s.yaml
exit: configs/exits/e.yaml
execution_assumptions_id: synthetic
report_trade_stats_first: true
""",
    )
    return run


def _prepare(
    tmp_path: Path,
    *,
    closes: list[float],
    sessions: list[date],
    baseline: bool = True,
):
    root = tmp_path / "research"
    run = _write_configs(root, baseline=baseline)
    engine = ResearchConfigEngine()
    prepared = engine.prepare(
        run_config_path=run,
        root=root,
        panel=_panel(sessions, closes),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(
            source_revision=f"baseline-e2e-{len(closes)}-{closes[62]}"
        ),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.20,
            max_positions=1,
            stop_fraction=0.20,
            reentry_gap_sessions=0,
            max_hold_sessions=20,
            lot_size=1000,
            random_seed=1,
        ),
    )
    return engine, prepared


def _default_raw(
    sessions: list[date],
    closes: list[float],
    *,
    overrides: dict[int, tuple[float, float, float, float]] | None = None,
    ticker: str = "2330",
) -> list[dict[str, object]]:
    overrides = overrides or {}
    rows: list[dict[str, object]] = []
    for index, (day, close) in enumerate(zip(sessions, closes)):
        if index in overrides:
            open_, high, low, close_value = overrides[index]
        else:
            open_ = close
            high = close + 1.0
            low = close - 1.0
            close_value = close
        rows.append(
            {
                "date": day,
                "stock_id": ticker,
                "open": float(open_),
                "max": float(high),
                "min": float(low),
                "close": float(close_value),
            }
        )
    return rows


def _write_source(
    tmp_path: Path,
    *,
    sessions: list[date],
    raw_rows: list[dict[str, object]],
    sell_blocked: set[int] | None = None,
    extra_rows: list[dict[str, object]] | None = None,
) -> Path:
    root = tmp_path / "source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)
    all_raw = raw_rows + list(extra_rows or [])
    pd.DataFrame(all_raw).to_parquet(
        root / "raw" / "prices_raw_2026.parquet",
        index=False,
    )

    sell_blocked = sell_blocked or set()
    tradability: list[dict[str, object]] = []
    tickers = sorted({str(row["stock_id"]) for row in all_raw})
    raw_keys = {
        (pd.Timestamp(row["date"]).date(), str(row["stock_id"]))
        for row in all_raw
    }
    for ticker in tickers:
        for index, day in enumerate(sessions):
            if (day, ticker) not in raw_keys:
                continue
            blocked = ticker == "2330" and index in sell_blocked
            tradability.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "observed_trade": True,
                    "valid_ohlc": True,
                    "buy_blocked": False,
                    "sell_blocked": blocked,
                    "reason": "SELL_BLOCKED" if blocked else "OBSERVED",
                }
            )
    pd.DataFrame(tradability).to_parquet(
        root / "reference" / "tradability.parquet",
        index=False,
    )
    return root


def _simulator(
    source_root: Path,
    prepared,
    *,
    fee_model=None,
    slippage_bps: float = 0.0,
):
    portfolio = PortfolioEngine(opening_cash=10_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(source_root)),
        fill_factory=ExecutionFillFactory(
            fee_model=fee_model or ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=slippage_bps),
        ),
        portfolio=portfolio,
    )
    policy = PortfolioIntentPolicy(prepared.portfolio_policy)
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source="baseline_60d_synthetic_e2e",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=1),
    )
    return simulator, portfolio, policy


def _synthetic_context(
    *approvals: BaselineCATechnicalApproval,
) -> BaselineSimulationContext:
    return BaselineSimulationContext(
        mode=BaselineSimulationMode.SYNTHETIC_FIXTURE,
        ca_approvals=tuple(approvals),
    )


def _ca_approval(event_id: str) -> BaselineCATechnicalApproval:
    return BaselineCATechnicalApproval(
        event_id=event_id,
        approved=True,
        source="SYNTHETIC_FIXTURE_EXPLICIT_APPROVAL",
    )


def _instruction(
    *,
    event_id: str,
    sessions: list[date],
    effective_index: int,
    event_type: CorporateActionType,
    cash_per_share: float | None = None,
    share_multiplier: float | None = None,
    extinguish_position: bool = False,
    successor_ticker: str | None = None,
    successor_multiplier: float | None = None,
    component: str | None = None,
) -> HistoricalCorporateActionInstruction:
    event = CorporateActionEvent(
        event_id=event_id,
        ticker="2330",
        event_type=event_type,
        effective_at=datetime.combine(
            sessions[effective_index],
            datetime.min.time(),
        ),
        known_at=datetime.combine(
            sessions[effective_index - 1],
            datetime.min.time(),
        ),
        payment_at=(
            datetime.combine(
                sessions[min(effective_index + 2, len(sessions) - 1)],
                datetime.min.time(),
            )
            if cash_per_share is not None
            else None
        ),
        cash_per_share=cash_per_share,
        share_multiplier=share_multiplier,
        source="synthetic-ca-fixture",
    )
    return HistoricalCorporateActionInstruction(
        event=event,
        applied_at=event.effective_at,
        component=component,
        cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
        extinguish_position=extinguish_position,
        successor_ticker=successor_ticker,
        successor_multiplier=successor_multiplier,
    )


@pytest.mark.parametrize(
    "reason,entry_bar",
    [
        (
            BaselineExitReason.ATR,
            (120.0, 121.0, 100.0, 101.0),
        ),
        (
            BaselineExitReason.LOW20,
            (102.0, 103.0, 99.0, 99.0),
        ),
        (
            BaselineExitReason.BOTH,
            (120.0, 121.0, 89.0, 90.0),
        ),
    ],
    ids=["ATR", "LOW20", "BOTH"],
)
def test_baseline_full_paths_compile_prepare_and_sell_next_open(
    tmp_path,
    reason,
    entry_bar,
):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=entry_bar[3])
    engine, prepared = _prepare(
        tmp_path,
        closes=closes,
        sessions=sessions,
    )
    assert prepared.exit_plan.baseline_60d_enabled is True
    assert prepared.portfolio_policy.stop_fraction is None
    assert prepared.portfolio_policy.max_hold_sessions is None
    assert list(prepared.candidates["signal_date"]) == [
        pd.Timestamp(sessions[61])
    ]

    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: entry_bar,
            63: (100.0, 101.0, 99.0, 100.0),
        },
    )
    source = _write_source(
        tmp_path,
        sessions=sessions,
        raw_rows=raw,
    )
    simulator, portfolio, policy = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        baseline_context=_synthetic_context(),
    )

    assert result.total_baseline_exit_fills == 1
    assert result.total_stop_exits == 0
    assert result.total_max_hold_exits == 0
    assert result.sessions[62].baseline_pending_count == 1
    assert result.sessions[63].baseline_exit_fills == 1
    assert result.baseline_exit_state is not None
    assert result.baseline_exit_state.completed_exit_intents[-1].reason is reason
    assert portfolio.positions.positions["2330"].quantity == 0
    assert "2330" not in policy.managed_positions
    assert f"order:baseline-exit:{sessions[63]}:2330" in portfolio.orders.orders


def test_sell_blocked_keeps_original_pending_until_later_canonical_open(tmp_path):
    sessions = _sessions(66)
    closes = _baseline_closes(
        count=66,
        entry_close=90.0,
        tail={63: 100.0, 64: 105.0, 65: 100.0},
    )
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (120.0, 121.0, 89.0, 90.0),
            63: (95.0, 101.0, 94.0, 100.0),
            64: (98.0, 106.0, 97.0, 105.0),
            65: (99.0, 101.0, 98.0, 100.0),
        },
    )
    source = _write_source(
        tmp_path,
        sessions=sessions,
        raw_rows=raw,
        sell_blocked={63, 64},
    )
    simulator, portfolio, _ = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        baseline_context=_synthetic_context(),
    )

    assert result.total_baseline_blocked_exit_attempts == 2
    assert result.total_baseline_exit_fills == 1
    assert result.sessions[63].baseline_blocked_exit_attempts == 1
    assert result.sessions[64].baseline_blocked_exit_attempts == 1
    assert result.sessions[65].baseline_exit_fills == 1
    assert result.baseline_exit_state.completed_exit_intents[-1].reason is BaselineExitReason.BOTH
    assert portfolio.positions.positions["2330"].quantity == 0


@pytest.mark.parametrize("kind", ["cash", "split"])
def test_cash_and_split_keep_technical_coordinate_and_canonical_accounting_consistent(
    tmp_path,
    kind,
):
    sessions = _sessions(64)
    closes = _baseline_closes(
        count=64,
        entry_close=105.0,
        tail={63: 95.0 if kind == "cash" else 52.5},
    )
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    if kind == "cash":
        event_id = "cash-ca"
        ca = _instruction(
            event_id=event_id,
            sessions=sessions,
            effective_index=63,
            event_type=CorporateActionType.CASH_DIVIDEND,
            cash_per_share=10.0,
        )
        day63 = (95.0, 96.0, 94.0, 95.0)
    else:
        event_id = "split-ca"
        ca = _instruction(
            event_id=event_id,
            sessions=sessions,
            effective_index=63,
            event_type=CorporateActionType.SPLIT,
            share_multiplier=2.0,
        )
        day63 = (52.5, 53.0, 52.0, 52.5)

    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (110.0, 111.0, 104.0, 105.0),
            63: day63,
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, policy = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        corporate_actions=[ca],
        baseline_context=_synthetic_context(_ca_approval(event_id)),
    )

    holding = result.baseline_exit_state.holding_state("2330")
    assert holding is not None
    assert holding.pending_exit is None
    assert event_id in result.baseline_exit_state.processed_ca_inputs
    canonical = portfolio.positions.positions["2330"]
    entry_fill = canonical.fills[0]
    entry_quantity = entry_fill.quantity

    if kind == "cash":
        assert holding.entry_anchor == pytest.approx(100.0)
        assert canonical.quantity == pytest.approx(entry_quantity)
        receivable = portfolio.corporate_actions.dividend_receivables[event_id]
        assert receivable.amount == pytest.approx(entry_quantity * 10.0)
        assert policy.managed_positions["2330"].quantity == pytest.approx(
            entry_quantity
        )
    else:
        assert holding.entry_anchor == pytest.approx(55.0)
        assert canonical.quantity == pytest.approx(entry_quantity * 2.0)
        assert event_id in portfolio.corporate_actions.share_mutations
        assert policy.managed_positions["2330"].quantity == pytest.approx(
            entry_quantity * 2.0
        )


def test_terminal_opening_event_supersedes_pending_without_strategy_sell(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (120.0, 121.0, 89.0, 90.0),
            63: (90.0, 91.0, 89.0, 90.0),
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    event_id = "terminal-merger"
    ca = _instruction(
        event_id=event_id,
        sessions=sessions,
        effective_index=63,
        event_type=CorporateActionType.MERGER,
        cash_per_share=90.0,
        extinguish_position=True,
        component="terminal_cash",
    )
    simulator, portfolio, _ = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        corporate_actions=[ca],
        baseline_context=_synthetic_context(_ca_approval(event_id)),
    )

    assert result.total_baseline_exit_fills == 0
    assert result.total_baseline_terminal_superseded == 1
    assert result.sessions[63].baseline_terminal_superseded == 1
    assert result.baseline_exit_state.holding_state("2330") is None
    assert portfolio.positions.positions["2330"].quantity == 0
    assert not any(
        order_id.startswith("order:baseline-exit:")
        for order_id in portfolio.orders.orders
    )


def test_successor_remains_traceable_blocked_in_baseline_state(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=105.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (110.0, 111.0, 104.0, 105.0),
            63: (105.0, 106.0, 104.0, 105.0),
        },
    )
    successor_rows = _default_raw(
        sessions,
        [80.0] * len(sessions),
        ticker="3715",
    )
    source = _write_source(
        tmp_path,
        sessions=sessions,
        raw_rows=raw,
        extra_rows=successor_rows,
    )
    event_id = "successor-merger"
    ca = _instruction(
        event_id=event_id,
        sessions=sessions,
        effective_index=63,
        event_type=CorporateActionType.MERGER,
        successor_ticker="3715",
        successor_multiplier=1.0,
    )
    simulator, portfolio, policy = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        corporate_actions=[ca],
        baseline_context=_synthetic_context(_ca_approval(event_id)),
    )

    state = result.baseline_exit_state
    assert state.technical_block_reason("2330") == "CANONICAL_LIFECYCLE_REQUIRED"
    assert state.holding_state("2330") is not None
    assert state.holding_state("2330").blocked_reason == "CANONICAL_LIFECYCLE_REQUIRED"
    assert portfolio.positions.positions["2330"].quantity == 0
    assert portfolio.positions.positions["3715"].quantity > 0
    assert "3715" in policy.managed_positions
    assert result.total_baseline_exit_fills == 0


def test_signal_formed_while_held_cannot_sell_then_reenter_same_open(tmp_path):
    sessions = _sessions(66)
    closes = _baseline_closes(
        count=66,
        entry_close=105.0,
        tail={63: 90.0, 64: 111.0, 65: 100.0},
    )
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    assert list(prepared.candidates["signal_date"]) == [
        pd.Timestamp(sessions[61]),
        pd.Timestamp(sessions[64]),
    ]
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (110.0, 111.0, 104.0, 105.0),
            63: (105.0, 106.0, 89.0, 90.0),
            64: (90.0, 112.0, 89.0, 111.0),
            65: (111.0, 112.0, 99.0, 100.0),
        },
    )
    source = _write_source(
        tmp_path,
        sessions=sessions,
        raw_rows=raw,
        sell_blocked={64},
    )
    simulator, portfolio, _ = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        baseline_context=_synthetic_context(),
    )

    assert result.total_entries == 1
    assert result.total_baseline_exit_fills == 1
    assert result.total_entry_skips >= 1
    fills = portfolio.positions.positions["2330"].fills
    assert [fill.side for fill in fills] == ["buy", "sell"]
    assert fills[-1].filled_at.date() == sessions[65]


def test_fees_tax_proxy_and_slippage_are_applied_once_by_canonical_fill_factory(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (120.0, 121.0, 89.0, 90.0),
            63: (100.0, 101.0, 99.0, 100.0),
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    fees = SideAwareBpsFeeModel(buy_bps=14.25, sell_bps=44.25)
    simulator, portfolio, _ = _simulator(
        source,
        prepared,
        fee_model=fees,
        slippage_bps=10.0,
    )

    executed = engine.execute_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        baseline_context=_synthetic_context(),
    )

    fills = portfolio.positions.positions["2330"].fills
    assert len(fills) == 2
    buy, sell = fills
    assert buy.price == pytest.approx(120.0 * 1.001)
    assert sell.price == pytest.approx(100.0 * 0.999)
    assert buy.fees == pytest.approx(
        buy.quantity * buy.price * 14.25 / 10_000.0
    )
    assert sell.fees == pytest.approx(
        sell.quantity * sell.price * 44.25 / 10_000.0
    )
    assert executed.simulation.total_baseline_exit_fills == 1


def test_period_end_preserves_pending_without_forced_exit_or_future_read(tmp_path):
    sessions = _sessions(63)
    closes = _baseline_closes(count=63, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (120.0, 121.0, 89.0, 90.0),
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, _ = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
        baseline_context=_synthetic_context(),
    )

    holding = result.baseline_exit_state.holding_state("2330")
    assert result.total_baseline_exit_fills == 0
    assert holding is not None
    assert holding.pending_exit is not None
    assert portfolio.positions.positions["2330"].quantity > 0
    assert result.sessions[-1].baseline_pending_count == 1


def test_formal_baseline_entry_remains_blocked_without_verified_data_gate(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (120.0, 121.0, 89.0, 90.0),
            63: (100.0, 101.0, 99.0, 100.0),
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, _ = _simulator(source, prepared)

    with pytest.raises(RuntimeError, match="BASELINE_FORMAL_DATA_GATE_BLOCKED"):
        engine.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            baseline_context=BaselineSimulationContext(
                mode=BaselineSimulationMode.FORMAL_RESEARCH,
                pit_data_gate_verified=False,
            ),
        )

    assert portfolio.positions.positions == {}
    assert portfolio.orders.orders == {}


def test_legacy_exit_plan_still_uses_existing_stop_and_max_hold_path(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=105.0)
    engine, prepared = _prepare(
        tmp_path,
        closes=closes,
        sessions=sessions,
        baseline=False,
    )
    assert prepared.exit_plan.baseline_60d_enabled is False
    assert prepared.portfolio_policy.stop_fraction == pytest.approx(0.12)
    assert prepared.portfolio_policy.max_hold_sessions == 250

    raw = _default_raw(
        sessions,
        closes,
        overrides={
            61: (100.0, 111.0, 99.0, 110.0),
            62: (110.0, 111.0, 104.0, 105.0),
            63: (100.0, 101.0, 90.0, 95.0),
        },
    )
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, _ = _simulator(source, prepared)

    result = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=sessions,
    )

    assert result.baseline_exit_state is None
    assert result.total_baseline_exit_fills == 0
    assert result.total_stop_exits == 1
    assert portfolio.positions.positions["2330"].quantity == 0


def _baseline_exit_config(
    *,
    multiplier: float = 3.0,
    include_low: bool = True,
    first_trigger_wins: bool = False,
    extra_rules: tuple[ExitRuleConfig, ...] = (),
) -> ExitConfig:
    rules = [
        ExitRuleConfig(
            type="ATR_FROM_ENTRY_STOP",
            params={
                "period": 14,
                "multiplier": multiplier,
                "smoothing": "SMA",
                "trigger_field": "CLOSE",
                "execution": "NEXT_OPEN",
                "observation_basis": "VALID_OBSERVED_OHLC",
            },
        )
    ]
    if include_low:
        rules.append(
            ExitRuleConfig(
                type="BREAK_N_DAY_LOW",
                params={
                    "window": 20,
                    "field": "CLOSE",
                    "exclude_current": True,
                    "strict": True,
                    "execution": "NEXT_OPEN",
                    "observation_basis": "VALID_OBSERVED_OHLC",
                },
            )
        )
    rules.extend(extra_rules)
    return ExitConfig(
        name="baseline-compiler-test",
        first_trigger_wins=first_trigger_wins,
        rules=tuple(rules),
    )


def test_exit_compiler_accepts_only_exact_baseline_pair_and_rejects_mixes():
    compiler = ExitCompiler()
    plan = compiler.compile(_baseline_exit_config())
    assert plan.baseline_60d_enabled is True
    assert plan.stop_fraction is None
    assert plan.max_hold_sessions is None

    with pytest.raises(ValueError, match="only supports baseline multiplier"):
        compiler.compile(_baseline_exit_config(multiplier=2.5))

    with pytest.raises(ValueError, match="require ATR_FROM_ENTRY_STOP and BREAK_N_DAY_LOW"):
        compiler.compile(_baseline_exit_config(include_low=False))

    with pytest.raises(ValueError, match="cannot mix with fixed stop or max-hold"):
        compiler.compile(
            _baseline_exit_config(
                extra_rules=(
                    ExitRuleConfig(
                        type="TIME_EXIT",
                        params={"sessions": 250},
                    ),
                )
            )
        )

    with pytest.raises(ValueError, match="first_trigger_wins=false"):
        compiler.compile(_baseline_exit_config(first_trigger_wins=True))


def test_ca_technical_approval_requires_explicit_source():
    with pytest.raises(ValueError, match="explicit source"):
        BaselineCATechnicalApproval(
            event_id="event",
            approved=True,
            source="",
        )
