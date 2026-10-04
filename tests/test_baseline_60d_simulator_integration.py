from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

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
from astraquant.research.feature_panel_integration import (
    AvailabilityStatus,
    EligibilityEvidenceScope,
    FeaturePanelIntegrationError,
    FeaturePanelIntegrator,
    load_feature_panel_integration_config,
)
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
    dates = pd.to_datetime(sessions)
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": "2330",
            "close": closes,
            "Trading_money": 50_000_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
            "__decision_cutoff_at": dates + pd.Timedelta(days=1, hours=8, minutes=45),
        }
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hydrate_feature_fixture(
    tmp_path: Path,
    *,
    sessions: list[date],
    closes: list[float],
    status: str = "VERIFIED",
    source_revision: str = "synthetic-baseline-source-v1",
    formula_version: str = "synthetic-baseline-features-v1",
    epoch: str = "SYNTHETIC_E2E",
):
    dates = pd.to_datetime(sessions)
    feature = pd.DataFrame(
        {
            "date": dates,
            "stock_id": "2330",
            "close_to_ma120": 0.10,
            "prior20_amount_twd": 30_000_000.0,
            "available_at_date": dates,
            "source_available_at": dates + pd.Timedelta(hours=18),
            "bars_seen": list(range(200, 200 + len(dates))),
        }
    )
    artifact_root = tmp_path / "feature-artifact"
    artifact_root.mkdir(parents=True, exist_ok=True)
    parquet = artifact_root / "stock_features_2026.parquet"
    feature.to_parquet(parquet, index=False)

    manifest = {
        "artifact_name": "synthetic-baseline-feature-artifact",
        "source_revision": source_revision,
        "formula_version": formula_version,
        "epoch": epoch,
        "period": [str(sessions[0]), str(sessions[-1])],
        "stock_files": [
            {
                "path": "stock_features_2026.parquet",
                "rows": len(feature),
                "sha256": _sha256(parquet),
            }
        ],
    }
    manifest_path = tmp_path / "feature-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    config = {
        "schema_version": "1",
        "name": "synthetic-baseline-feature-hydration",
        "epoch": epoch,
        "artifact": {
            "manifest_path": str(manifest_path),
            "artifact_name": manifest["artifact_name"],
            "source_revision": source_revision,
            "formula_version": formula_version,
            "epoch": epoch,
        },
        "policy": {"strategy_required_status": "VERIFIED"},
        "availability_groups": {
            "synthetic_verified": {"status": status},
        },
        "requested_features": [
            {
                "column": "close_to_ma120",
                "kind": "RAW",
                "required": True,
                "warmup_sessions": 120,
                "dependencies": ["synthetic_verified"],
                "expected_status": status,
            },
            {
                "column": "prior20_amount_twd",
                "kind": "RAW",
                "required": True,
                "warmup_sessions": 20,
                "dependencies": ["synthetic_verified"],
                "expected_status": status,
            },
        ],
    }
    config_path = tmp_path / "feature-integration.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    integrator = FeaturePanelIntegrator(
        config=load_feature_panel_integration_config(config_path),
        artifact_root=artifact_root,
        manifest_path=manifest_path,
        evidence_scope=EligibilityEvidenceScope.SYNTHETIC_FIXTURE,
        evidence_source="test_baseline_60d_simulator_integration fixture",
    )
    joined = integrator.hydrate(_panel(sessions, closes))
    return integrator, joined, manifest_path, parquet


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


def _prepare_with_evidence_parts(
    tmp_path: Path,
    *,
    closes: list[float],
    sessions: list[date],
    baseline: bool = True,
    status: str = "VERIFIED",
    source_revision: str = "synthetic-baseline-source-v1",
    formula_version: str = "synthetic-baseline-features-v1",
):
    root = tmp_path / "research"
    run = _write_configs(root, baseline=baseline)
    integrator, joined, manifest_path, parquet = _hydrate_feature_fixture(
        tmp_path,
        sessions=sessions,
        closes=closes,
        status=status,
        source_revision=source_revision,
        formula_version=formula_version,
    )
    engine = ResearchConfigEngine()
    prepared = engine.prepare_hydrated(
        run_config_path=run,
        root=root,
        feature_integrator=integrator,
        feature_join_result=joined,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(
            source_revision=source_revision
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
    return (
        engine,
        prepared,
        integrator,
        joined,
        manifest_path,
        parquet,
        run,
        root,
    )


def _prepare(
    tmp_path: Path,
    *,
    closes: list[float],
    sessions: list[date],
    baseline: bool = True,
):
    engine, prepared, *_ = _prepare_with_evidence_parts(
        tmp_path,
        closes=closes,
        sessions=sessions,
        baseline=baseline,
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


def test_prepared_run_carries_fixture_evidence_from_real_hydration(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    (
        engine,
        prepared,
        _integrator,
        _joined,
        _manifest_path,
        _parquet,
        _run,
        _root,
    ) = _prepare_with_evidence_parts(
        tmp_path,
        closes=closes,
        sessions=sessions,
    )

    evidence = prepared.eligibility_evidence
    assert evidence is not None
    assert (
        evidence.feature_evidence.scope
        is EligibilityEvidenceScope.SYNTHETIC_FIXTURE
    )
    assert (
        evidence.feature_evidence.source_revision
        == "synthetic-baseline-source-v1"
    )
    assert (
        evidence.feature_evidence.formula_version
        == "synthetic-baseline-features-v1"
    )
    assert evidence.feature_evidence.artifacts[0].filename == (
        "stock_features_2026.parquet"
    )
    assert "source_available_at<decision_cutoff_at" in (
        evidence.feature_evidence.cutoff_contracts
    )
    engine.validate_prepared_eligibility(prepared)


def test_missing_prepared_evidence_blocks_synthetic_before_market_read(tmp_path, monkeypatch):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)
    prepared = replace(prepared, eligibility_evidence=None)
    raw = _default_raw(sessions, closes)
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, _ = _simulator(source, prepared)

    def unexpected_market_read(*args, **kwargs):
        pytest.fail("missing evidence must fail before canonical market-data read")

    monkeypatch.setattr(
        simulator.execution.market_data.source,
        "read_parquet",
        unexpected_market_read,
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="has no eligibility evidence",
    ):
        engine.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            baseline_context=_synthetic_context(),
        )
    assert portfolio.orders.orders == {}
    assert portfolio.positions.positions == {}


@pytest.mark.parametrize("status", ["UNKNOWN", "UNAVAILABLE"])
def test_unknown_or_unavailable_feature_status_cannot_create_fixture_evidence(
    tmp_path,
    status,
):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    with pytest.raises(
        FeaturePanelIntegrationError,
        match=f"close_to_ma120:{status}",
    ):
        _hydrate_feature_fixture(
            tmp_path,
            sessions=sessions,
            closes=closes,
            status=status,
        )


def test_modified_hydrated_panel_invalidates_old_evidence_before_prepare(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    integrator, joined, _manifest, _parquet = _hydrate_feature_fixture(
        tmp_path,
        sessions=sessions,
        closes=closes,
    )
    joined.frame.loc[0, "close_to_ma120"] = 999.0

    root = tmp_path / "research"
    run = _write_configs(root, baseline=True)
    engine = ResearchConfigEngine()
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="hydrated panel fingerprint mismatch",
    ):
        engine.prepare_hydrated(
            run_config_path=run,
            root=root,
            feature_integrator=integrator,
            feature_join_result=joined,
            universe_context=UniverseContext(
                p2_060_excluded_tickers=frozenset(),
                p2_060_exclusion_sha256=P2_SHA,
            ),
            signal_context=SignalContext(
                source_revision="synthetic-baseline-source-v1"
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


def test_changed_artifact_bytes_invalidate_prepared_evidence_before_trading(
    tmp_path,
    monkeypatch,
):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    (
        engine,
        prepared,
        _integrator,
        _joined,
        _manifest,
        parquet,
        _run,
        _root,
    ) = _prepare_with_evidence_parts(
        tmp_path,
        closes=closes,
        sessions=sessions,
    )
    changed = pd.read_parquet(parquet)
    changed.loc[0, "close_to_ma120"] = 777.0
    changed.to_parquet(parquet, index=False)

    raw = _default_raw(sessions, closes)
    source = _write_source(tmp_path, sessions=sessions, raw_rows=raw)
    simulator, portfolio, _ = _simulator(source, prepared)

    def unexpected_market_read(*args, **kwargs):
        pytest.fail("stale artifact evidence must fail before execution data read")

    monkeypatch.setattr(
        simulator.execution.market_data.source,
        "read_parquet",
        unexpected_market_read,
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="artifact checksum changed",
    ):
        engine.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            baseline_context=_synthetic_context(),
        )
    assert portfolio.orders.orders == {}
    assert portfolio.positions.positions == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_revision", "changed-source-revision"),
        ("formula_version", "changed-formula-version"),
        ("epoch", "OTHER_EPOCH"),
        ("period", ["2026-01-02", "2026-01-15"]),
    ],
)
def test_manifest_dependency_change_invalidates_old_prepared_evidence(
    tmp_path,
    field,
    value,
):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    (
        engine,
        prepared,
        _integrator,
        _joined,
        manifest_path,
        _parquet,
        _run,
        _root,
    ) = _prepare_with_evidence_parts(
        tmp_path,
        closes=closes,
        sessions=sessions,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        FeaturePanelIntegrationError,
        match="manifest checksum changed",
    ):
        engine.validate_prepared_eligibility(prepared)


def test_out_of_evidence_date_range_is_rejected_before_run_preparation(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    integrator, joined, _manifest, _parquet = _hydrate_feature_fixture(
        tmp_path,
        sessions=sessions,
        closes=closes,
    )
    joined.frame.loc[0, "date"] = pd.Timestamp("2030-01-02")

    with pytest.raises(FeaturePanelIntegrationError):
        integrator.validate_join_result(joined)


def test_run_a_evidence_cannot_be_reused_for_mismatched_run_b(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine_a, prepared_a = _prepare(
        tmp_path / "a",
        closes=closes,
        sessions=sessions,
        baseline=True,
    )
    engine_b, prepared_b = _prepare(
        tmp_path / "b",
        closes=closes,
        sessions=sessions,
        baseline=False,
    )
    mismatched = replace(
        prepared_b,
        eligibility_evidence=prepared_a.eligibility_evidence,
    )

    with pytest.raises(
        FeaturePanelIntegrationError,
        match="prepared config fingerprint mismatch",
    ):
        engine_b.validate_prepared_eligibility(mismatched)


def test_signal_source_revision_change_invalidates_bound_run_evidence(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=90.0)
    engine, prepared = _prepare(tmp_path, closes=closes, sessions=sessions)

    with pytest.raises(
        FeaturePanelIntegrationError,
        match="prepared config fingerprint mismatch",
    ):
        engine.validate_prepared_eligibility(
            replace(prepared, signal_source_revision="other-source-revision")
        )


@pytest.mark.parametrize(
    "mode,status",
    [
        (BaselineSimulationMode.FORMAL_RESEARCH, AvailabilityStatus.UNAVAILABLE),
        ("FORMAL_RESEARCH", "UNKNOWN"),
        (" formal_research ", AvailabilityStatus.UNKNOWN),
    ],
)
def test_formal_baseline_modes_block_before_market_read_or_portfolio_mutation(
    tmp_path,
    monkeypatch,
    mode,
    status,
):
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

    def unexpected_market_read(*args, **kwargs):
        pytest.fail("formal gate must stop before canonical market-data read")

    monkeypatch.setattr(
        simulator.execution.market_data.source,
        "read_parquet",
        unexpected_market_read,
    )
    context = BaselineSimulationContext(
        mode=mode,
        pit_data_gate_status=status,
        pit_data_gate_source="existing-layer1-status-for-audit-only",
    )
    assert context.mode is BaselineSimulationMode.FORMAL_RESEARCH
    assert prepared.eligibility_evidence is not None
    assert (
        prepared.eligibility_evidence.feature_evidence.scope
        is EligibilityEvidenceScope.SYNTHETIC_FIXTURE
    )

    with pytest.raises(RuntimeError, match="BASELINE_FORMAL_DATA_GATE_BLOCKED"):
        engine.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            baseline_context=context,
        )

    assert portfolio.positions.positions == {}
    assert portfolio.orders.orders == {}
    assert portfolio.settlements.pending == {}


def test_caller_declared_verified_and_arbitrary_source_cannot_unlock_formal():
    context = BaselineSimulationContext(
        mode="FORMAL_RESEARCH",
        pit_data_gate_status="VERIFIED",
        pit_data_gate_source="caller says verified",
    )
    assert context.pit_data_gate_status is AvailabilityStatus.VERIFIED
    with pytest.raises(
        RuntimeError,
        match="no canonical eligibility evidence object",
    ):
        context.require_runnable()


@pytest.mark.parametrize("mode", [None, "", "production", object()])
def test_baseline_context_rejects_unknown_or_null_mode(mode):
    with pytest.raises(ValueError, match="baseline simulation mode"):
        BaselineSimulationContext(mode=mode)


@pytest.mark.parametrize("status", [None, "", "PASS", object()])
def test_baseline_context_rejects_unknown_or_null_availability(status):
    with pytest.raises(ValueError, match="baseline availability status"):
        BaselineSimulationContext(
            mode="SYNTHETIC_FIXTURE",
            pit_data_gate_status=status,
        )


def test_baseline_context_normalizes_legal_synthetic_strings():
    context = BaselineSimulationContext(
        mode=" synthetic_fixture ",
        pit_data_gate_status=" unknown ",
    )
    assert context.mode is BaselineSimulationMode.SYNTHETIC_FIXTURE
    assert context.pit_data_gate_status is AvailabilityStatus.UNKNOWN
    context.require_runnable()


def test_legacy_exit_plan_still_uses_existing_stop_and_max_hold_path(tmp_path):
    sessions = _sessions(64)
    closes = _baseline_closes(count=64, entry_close=105.0)
    root = tmp_path / "research"
    run = _write_configs(root, baseline=False)
    legacy_panel = _panel(sessions, closes)
    legacy_panel["close_to_ma120"] = 0.10
    legacy_panel["prior20_amount_twd"] = 30_000_000.0
    engine = ResearchConfigEngine()
    prepared = engine.prepare(
        run_config_path=run,
        root=root,
        panel=legacy_panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(source_revision="legacy-no-evidence"),
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
    assert prepared.eligibility_evidence is None
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
    period: object = 14,
    multiplier: object = 3.0,
    low_window: object = 20,
    exclude_current: object = True,
    strict: object = True,
    include_low: bool = True,
    first_trigger_wins: bool = False,
    extra_rules: tuple[ExitRuleConfig, ...] = (),
) -> ExitConfig:
    rules = [
        ExitRuleConfig(
            type="ATR_FROM_ENTRY_STOP",
            params={
                "period": period,
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
                    "window": low_window,
                    "field": "CLOSE",
                    "exclude_current": exclude_current,
                    "strict": strict,
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


    with pytest.raises(ValueError, match="period must be an integer"):
        compiler.compile(_baseline_exit_config(period=14.9))

    with pytest.raises(ValueError, match="window must be an integer"):
        compiler.compile(_baseline_exit_config(low_window=20.9))

    with pytest.raises(ValueError, match="exclude_current must be a YAML boolean"):
        compiler.compile(_baseline_exit_config(exclude_current="false"))

    with pytest.raises(ValueError, match="strict must be a YAML boolean"):
        compiler.compile(_baseline_exit_config(strict=1))

    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="multiplier must be finite"):
            compiler.compile(_baseline_exit_config(multiplier=nonfinite))


def test_ca_technical_approval_requires_explicit_source():
    with pytest.raises(ValueError, match="explicit source"):
        BaselineCATechnicalApproval(
            event_id="event",
            approved=True,
            source="",
        )
