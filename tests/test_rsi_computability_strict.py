from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astraquant.portfolio.calendar import TradingCalendar
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.config_engine import ResearchConfigEngine
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.rsi_computability import (
    SignalComputabilityContext,
    TriState,
    combine_tristate,
)
from astraquant.research.signal_engine import (
    SignalCompiler,
    SignalContext,
    SignalEvaluator,
)
from astraquant.research.strategy_config import (
    ComponentSpec,
    LogicalOp,
    SignalConfig,
)
from astraquant.research.universe_engine import UniverseContext, UniverseMask


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _panel(
    closes,
    *,
    ticker: str = "2330",
    flag: float = 1.0,
) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    volumes = [100.0] * len(closes)
    if volumes:
        volumes[-1] = 300.0
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ticker,
            "close": pd.Series(closes, dtype=float),
            "Trading_Volume": volumes,
            "Trading_money": 10_000_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
            "flag": flag,
        }
    )


def _prepared(panel: pd.DataFrame, counts: bool = True) -> pd.DataFrame:
    out = panel.copy()
    out["counts"] = counts
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(
        drop=True
    )


def _mask(panel: pd.DataFrame, counts: bool = True) -> UniverseMask:
    frame = panel[["date", "stock_id"]].copy()
    frame["base_pass"] = counts
    frame["counts"] = counts
    return UniverseMask(frame=frame, config_name="strict-rsi-test")


def _strict_context(panel: pd.DataFrame) -> SignalComputabilityContext:
    calendar = TradingCalendar(
        pd.to_datetime(panel["date"]).dt.date.drop_duplicates().tolist()
    )
    return SignalComputabilityContext(
        expected_sessions=calendar.sessions,
        expected_sessions_source="TradingCalendar(test fixture)",
    )


def _volume_trigger() -> ComponentSpec:
    return ComponentSpec(
        type="VOLUME_SPIKE",
        params={"lookback": 3, "multiplier": 1.5},
    )


def _signal_plan(
    *,
    filters=(),
    combine: LogicalOp = LogicalOp.AND,
    ranking=(),
):
    config = SignalConfig(
        name="strict-rsi-fixture",
        trigger=_volume_trigger(),
        filters=filters,
        filter_combine=combine,
        ranking=ranking,
    )
    return SignalCompiler().compile(config)


def test_tristate_filter_rules_match_contract():
    assert combine_tristate(
        [TriState.TRUE, TriState.UNKNOWN], "OR"
    ) is TriState.TRUE
    assert combine_tristate(
        [TriState.FALSE, TriState.UNKNOWN], "OR"
    ) is TriState.UNKNOWN
    assert combine_tristate(
        [TriState.FALSE, TriState.UNKNOWN], "AND"
    ) is TriState.FALSE
    assert combine_tristate(
        [TriState.TRUE, TriState.UNKNOWN], "AND"
    ) is TriState.UNKNOWN


def test_current_missing_is_blocked_in_evaluate_and_evaluate_prepared():
    panel = _panel(
        [100, 102, 101, 103, 104, 102, 105, 104, 106, 107, np.nan]
    )
    plan = _signal_plan(
        filters=(
            ComponentSpec(type="RSI", params={"lookback": 3, "min": 0}),
        )
    )
    strict = _strict_context(panel)

    direct = SignalEvaluator().evaluate(
        plan,
        panel,
        _mask(panel),
        SignalContext(source_revision="strict-current-direct"),
        computability_context=strict,
    )
    prepared = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(panel),
        SignalContext(source_revision="strict-current-prepared"),
        computability_context=strict,
    )

    for frame in (direct, prepared):
        row = frame.iloc[-1]
        assert bool(row["counts_as_candidate"]) is True
        assert row["strict_filter_condition_state"] == "UNKNOWN"
        assert row["strict_filter_0_reason"] == "CURRENT_INPUT_MISSING"
        assert row["strict_candidate_state"] == "UNKNOWN"
        assert bool(row["strict_counts_as_candidate"]) is False


def test_warmup_unknown_and_valid_false_are_distinct():
    plan = _signal_plan(
        filters=(
            ComponentSpec(type="RSI", params={"lookback": 3, "min": 50}),
        )
    )

    warm = _panel([100, 99, 98])
    warm_out = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(warm),
        SignalContext(source_revision="strict-warmup"),
        computability_context=_strict_context(warm),
    )
    assert warm_out.iloc[-1]["strict_filter_condition_state"] == "UNKNOWN"
    assert warm_out.iloc[-1]["strict_filter_0_reason"] == "WARMUP_INSUFFICIENT"

    down = _panel([110, 109, 108, 107, 106, 105, 104, 103])
    down_out = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(down),
        SignalContext(source_revision="strict-valid-false"),
        computability_context=_strict_context(down),
    )
    assert down_out.iloc[-1]["strict_filter_condition_state"] == "FALSE"
    assert down_out.iloc[-1]["strict_filter_0_reason"] == "OK"


@pytest.mark.parametrize(
    "combine,flag,expected",
    [
        (LogicalOp.OR, 1.0, "TRUE"),
        (LogicalOp.OR, 0.0, "UNKNOWN"),
        (LogicalOp.AND, 0.0, "FALSE"),
        (LogicalOp.AND, 1.0, "UNKNOWN"),
    ],
)
def test_real_multi_filter_and_or_preserves_three_state_logic(
    combine,
    flag,
    expected,
):
    panel = _panel(
        [100, 102, 101, 103, 104, 102, 105, 104, np.nan],
        flag=flag,
    )
    plan = _signal_plan(
        filters=(
            ComponentSpec(
                type="COLUMN_THRESHOLD",
                params={"column": "flag", "min": 1},
            ),
            ComponentSpec(
                type="RSI",
                params={"lookback": 3, "min": 0},
            ),
        ),
        combine=combine,
    )
    out = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(panel),
        SignalContext(source_revision=f"strict-{combine.value}-{flag}"),
        computability_context=_strict_context(panel),
    )
    row = out.iloc[-1]
    assert row["strict_filter_condition_state"] == expected
    assert bool(row["strict_all_filter_components_computable"]) is False


def test_non_close_component_is_not_globally_gated_and_ranking_is_diagnostic():
    panel = _panel(
        [100, 102, 101, 103, 104, 102, 105, 104, np.nan]
    )
    ranking = (
        ComponentSpec(
            type="RSI",
            params={"lookback": 3, "name": "rsi3"},
        ),
    )
    out = SignalEvaluator().evaluate_prepared(
        _signal_plan(ranking=ranking),
        _prepared(panel),
        SignalContext(source_revision="strict-ranking"),
        computability_context=_strict_context(panel),
    )
    row = out.iloc[-1]
    assert row["strict_trigger_state"] == "TRUE"
    assert row["strict_filter_condition_state"] == "TRUE"
    assert bool(row["strict_counts_as_candidate"]) is True
    assert pd.isna(row["strict_rank_rsi3"])
    assert row["strict_rank_rsi3_reason"] == "CURRENT_INPUT_MISSING"


def test_cross_relative_history_gap_and_stock_state_are_isolated():
    cross_panel = _panel([100, 102, 101, 103, 104, 102, 105])
    cross_config = SignalConfig(
        name="strict-cross",
        trigger=ComponentSpec(
            type="RSI_CROSS",
            params={"lookback": 3, "level": 50},
        ),
        filters=(),
    )
    cross = SignalEvaluator().evaluate_prepared(
        SignalCompiler().compile(cross_config),
        _prepared(cross_panel),
        SignalContext(source_revision="strict-cross"),
        computability_context=_strict_context(cross_panel),
    )
    assert cross.loc[3, "strict_trigger_state"] == "UNKNOWN"
    assert str(cross.loc[3, "strict_trigger_reason"]).startswith(
        "PREVIOUS_RSI_"
    )

    relative_panel = _panel([100, 101, 102, 103, 104])
    relative_plan = _signal_plan(
        filters=(
            ComponentSpec(
                type="RSI_RELATIVE",
                params={"fast_lookback": 3, "slow_lookback": 5},
            ),
        )
    )
    relative = SignalEvaluator().evaluate_prepared(
        relative_plan,
        _prepared(relative_panel),
        SignalContext(source_revision="strict-relative"),
        computability_context=_strict_context(relative_panel),
    )
    assert relative.iloc[-1]["strict_filter_condition_state"] == "UNKNOWN"
    assert str(relative.iloc[-1]["strict_filter_0_reason"]).startswith("SLOW_")

    stock_a = _panel(
        [100, 102, 101, 103, 104, 102, 105, 104, 106, 107, 108],
        ticker="1001",
    )
    stock_b = _panel(
        [100, 102, 101, 103, 104, np.nan, 105, 104, 106, 107, 108],
        ticker="1002",
    )
    multi = (
        pd.concat([stock_a, stock_b], ignore_index=True)
        .sort_values(["stock_id", "date"], kind="stable")
        .reset_index(drop=True)
    )
    out = SignalEvaluator().evaluate_prepared(
        _signal_plan(
            filters=(
                ComponentSpec(
                    type="RSI",
                    params={"lookback": 3, "min": 0},
                ),
            )
        ),
        _prepared(multi),
        SignalContext(source_revision="strict-multi"),
        computability_context=_strict_context(multi),
    )
    last = out.groupby("stock_id", sort=False).tail(1).set_index("stock_id")
    assert last.loc["1001", "strict_filter_0_reason"] == "OK"
    assert (
        last.loc["1002", "strict_filter_0_reason"]
        == "HISTORY_GAP_POLICY_UNRESOLVED"
    )


def test_missing_expected_session_and_missing_calendar_evidence_stay_unknown():
    full = _panel([100, 102, 101, 103, 104, 102, 105, 104, 106, 107])
    calendar = TradingCalendar(pd.to_datetime(full["date"]).dt.date.tolist())
    dropped = full.drop(index=full.index[5]).reset_index(drop=True)
    strict = SignalComputabilityContext(
        expected_sessions=calendar.sessions,
        expected_sessions_source="TradingCalendar(test fixture)",
    )
    out = SignalEvaluator().evaluate_prepared(
        _signal_plan(
            filters=(
                ComponentSpec(
                    type="RSI",
                    params={"lookback": 3, "min": 0},
                ),
            )
        ),
        _prepared(dropped),
        SignalContext(source_revision="strict-missing-row"),
        computability_context=strict,
    )
    assert (
        out.iloc[-1]["strict_filter_0_reason"]
        == "HISTORY_GAP_POLICY_UNRESOLVED"
    )

    no_calendar = SignalEvaluator().evaluate_prepared(
        _signal_plan(
            filters=(
                ComponentSpec(
                    type="RSI",
                    params={"lookback": 3, "min": 0},
                ),
            )
        ),
        _prepared(full),
        SignalContext(source_revision="strict-no-calendar"),
        computability_context=SignalComputabilityContext(),
    )
    assert (
        no_calendar.iloc[-1]["strict_filter_0_reason"]
        == "SESSION_GAP_NOT_AUDITABLE"
    )


def test_opt_in_preserves_all_legacy_signal_columns_on_valid_input():
    panel = _panel([100, 102, 101, 103, 104, 102, 105, 104, 106, 107, 108])
    plan = _signal_plan(
        filters=(
            ComponentSpec(type="RSI", params={"lookback": 3, "min": 50}),
        )
    )
    legacy = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(panel),
        SignalContext(source_revision="legacy-unchanged-a"),
    )
    strict = SignalEvaluator().evaluate_prepared(
        plan,
        _prepared(panel),
        SignalContext(source_revision="legacy-unchanged-b"),
        computability_context=_strict_context(panel),
    )
    columns = [
        "signal_date",
        "stock_id",
        "triggered",
        "filter_pass",
        "universe_counts",
        "counts_as_candidate",
    ]
    pd.testing.assert_frame_equal(legacy[columns], strict[columns])
    assert bool(strict.iloc[-1]["strict_counts_as_candidate"]) is bool(
        legacy.iloc[-1]["counts_as_candidate"]
    )


def _strict_runner_configs(root: Path) -> tuple[Path, Path]:
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
name: strict_rsi
trigger:
  type: VOLUME_SPIKE
  params: {lookback: 3, multiplier: 1.5}
filters:
  - type: RSI
    params: {lookback: 3, min: 0}
filter_combine: AND
ranking: []
""",
    )
    _write(
        root / "configs/exits/e.yaml",
        """
schema_version: "1"
name: stop_time
rules:
  - type: FIXED_STOP_TARGET
    params: {stop_pct: 0.12, target_pct: null}
  - type: TIME_EXIT
    params: {sessions: 250}
""",
    )
    run = root / "configs/runs/r.yaml"
    _write(
        run,
        """
schema_version: "1"
run_name: strict_rsi_run
strategy_version: strict_rsi_run_v1
universe: configs/universes/u.yaml
signal: configs/signals/s.yaml
exit: configs/exits/e.yaml
execution_assumptions_id: zero-cost
report_trade_stats_first: true
""",
    )
    sweep = root / "configs/sweeps/s.yaml"
    _write(
        sweep,
        """
schema_version: "1"
name: strict_rsi_sweep
universes:
  - configs/universes/u.yaml
signal: configs/signals/s.yaml
exit: configs/exits/e.yaml
axes:
  - target: trigger.multiplier
    values: [1.5]
execution_assumptions_id: zero-cost
max_combinations: 10
report_trade_stats_first: true
""",
    )
    return run, sweep


def _runner_panel() -> pd.DataFrame:
    panel = _panel(
        [100, 102, 101, 103, 104, np.nan, 105, 106, 107, 108, 109, 110]
    )
    panel["stock_id"] = "2330"
    return panel


def _universe_context() -> UniverseContext:
    return UniverseContext(
        p2_060_excluded_tickers=frozenset(),
        p2_060_exclusion_sha256=P2_SHA,
    )


def _base_policy() -> PortfolioPolicyConfig:
    return PortfolioPolicyConfig(
        position_fraction=0.10,
        max_positions=10,
    )


def test_config_engine_uses_strict_candidate_mask_end_to_end(tmp_path):
    run, _ = _strict_runner_configs(tmp_path)
    panel = _runner_panel()
    context = _strict_context(panel)

    legacy = ResearchConfigEngine().prepare(
        run_config_path=run,
        root=tmp_path,
        panel=panel,
        universe_context=_universe_context(),
        signal_context=SignalContext(source_revision="runner-legacy"),
        base_policy=_base_policy(),
    )
    strict = ResearchConfigEngine().prepare(
        run_config_path=run,
        root=tmp_path,
        panel=panel,
        universe_context=_universe_context(),
        signal_context=SignalContext(source_revision="runner-strict"),
        base_policy=_base_policy(),
        signal_computability_context=context,
    )

    assert bool(legacy.signal_frame.iloc[-1]["counts_as_candidate"]) is True
    assert list(legacy.candidates["stock_id"]) == ["2330"]
    assert bool(strict.signal_frame.iloc[-1]["counts_as_candidate"]) is True
    assert (
        strict.signal_frame.iloc[-1]["strict_filter_0_reason"]
        == "HISTORY_GAP_POLICY_UNRESOLVED"
    )
    assert bool(strict.signal_frame.iloc[-1]["strict_counts_as_candidate"]) is False
    assert strict.candidates.empty


def test_parameter_sweep_propagates_strict_mask_to_candidate_adapter(tmp_path):
    _, sweep = _strict_runner_configs(tmp_path)
    panel = _runner_panel()
    kwargs = dict(
        sweep_config_path=sweep,
        root=tmp_path,
        panel=panel,
        universe_context=_universe_context(),
        base_policy=_base_policy(),
    )

    legacy = ResearchParameterSweepRunner().prepare_sweep(
        **kwargs,
        signal_context=SignalContext(source_revision="sweep-legacy"),
    )
    strict = ResearchParameterSweepRunner().prepare_sweep(
        **kwargs,
        signal_context=SignalContext(source_revision="sweep-strict"),
        signal_computability_context=_strict_context(panel),
    )

    assert int(legacy.summary.iloc[0]["signal_candidates"]) == 1
    assert list(legacy.runs[0].candidates["stock_id"]) == ["2330"]
    assert int(strict.summary.iloc[0]["signal_candidates"]) == 0
    assert strict.runs[0].candidates.empty
    assert bool(
        strict.runs[0].signal_frame.iloc[-1]["strict_counts_as_candidate"]
    ) is False


def test_strict_runner_rejects_configured_ranking_until_downstream_support_exists(
    tmp_path,
):
    run, _ = _strict_runner_configs(tmp_path)
    _write(
        tmp_path / "configs/signals/s.yaml",
        """
schema_version: "1"
name: strict_rsi_ranked
trigger:
  type: VOLUME_SPIKE
  params: {lookback: 3, multiplier: 1.5}
filters: []
ranking:
  - type: RSI
    params: {lookback: 3, name: rsi3}
""",
    )
    panel = _runner_panel()

    with pytest.raises(ValueError, match="no canonical downstream"):
        ResearchConfigEngine().prepare(
            run_config_path=run,
            root=tmp_path,
            panel=panel,
            universe_context=_universe_context(),
            signal_context=SignalContext(source_revision="strict-ranked"),
            base_policy=_base_policy(),
            signal_computability_context=_strict_context(panel),
        )


def test_expected_sessions_contract_rejects_unordered_or_unproven_input():
    sessions = (
        pd.Timestamp("2026-01-05"),
        pd.Timestamp("2026-01-02"),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        SignalComputabilityContext(
            expected_sessions=sessions,
            expected_sessions_source="bad-order",
        )
    with pytest.raises(ValueError, match="expected_sessions_source"):
        SignalComputabilityContext(
            expected_sessions=(pd.Timestamp("2026-01-02"),),
        )
