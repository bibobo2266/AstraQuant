from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from astraquant.research.config_io import (
    load_parameter_sweep_config,
    load_signal_config,
)
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import ComponentSpec
from astraquant.research.technical_components import vcp_three_segment_details
from astraquant.research.vcp_round1 import ConfigTradeSimulation
from astraquant.research.vcp_round2 import (
    build_entry_liquidity_features,
    enrich_entry_liquidity,
    round2_summary_row,
)


def _zero_third_segment_panel() -> pd.DataFrame:
    n = 70
    dates = pd.bdate_range("2020-01-02", periods=n)
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)
    close = np.full(n, 99.0)
    volume = np.full(n, 1000.0)
    amount = np.full(n, 30_000_000.0)

    # Signal row index 60; prior base_len=30 occupies rows 30..59.
    high[30:40], low[30:40] = 100.0, 80.0
    high[40:50], low[40:50] = 100.0, 90.0
    high[50:60], low[50:60] = 100.0, 100.0
    close[50:60] = 100.0
    volume[55:60] = 500.0
    close[59] = 100.0
    close[60] = 101.0
    high[60], low[60] = 102.0, 99.0
    volume[60] = 2000.0

    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * n,
            "open": close,
            "max": high,
            "min": low,
            "close": close,
            "Trading_Volume": volume,
            "Trading_money": amount,
            "observed_trade": True,
            "valid_ohlc": True,
        }
    )


def _spec(*, min_amplitude_3: float | None) -> ComponentSpec:
    params = {
        "base_len": 30,
        "contraction_ratio": 0.75,
        "last_contraction": 0.08,
        "dry_up": 0.65,
        "dry_up_window": 5,
        "breakout_volume_lookback": 50,
        "breakout_vol": 1.5,
        "liquidity_lookback": 20,
        "min_prior_avg_amount_twd": 20_000_000,
    }
    if min_amplitude_3 is not None:
        params["min_amplitude_3"] = min_amplitude_3
    return ComponentSpec(type="VCP_THREE_SEGMENT", params=params)


def test_zero_amplitude3_preserves_round1_and_is_rejected_by_round2():
    panel = _zero_third_segment_panel()

    round1 = vcp_three_segment_details(
        panel=panel,
        spec=_spec(min_amplitude_3=None),
        cache=FeatureCache(),
        context=SignalContext(source_revision="round1-fixture"),
    ).iloc[60]
    round2 = vcp_three_segment_details(
        panel=panel,
        spec=_spec(min_amplitude_3=0.01),
        cache=FeatureCache(),
        context=SignalContext(source_revision="round2-fixture"),
    ).iloc[60]

    assert round1["amplitude_3"] == pytest.approx(0.0)
    assert bool(round1["signal"])
    assert not bool(round2["signal"])
    assert round2["diagnostic_reason"] == "AMPLITUDE_3_BELOW_MIN"


def test_round2_config_adds_only_explicit_amplitude_floor_to_signal():
    round1 = load_signal_config(
        "configs/examples/signals/vcp_round1_three_segment_v1.yaml"
    )
    round2 = load_signal_config(
        "configs/examples/signals/vcp_round2_three_segment_v1.yaml"
    )
    assert "min_amplitude_3" not in round1.trigger.params
    assert round2.trigger.params["min_amplitude_3"] == pytest.approx(0.01)

    sweep1 = load_parameter_sweep_config(
        "configs/research/vcp_round1_three_segment_v1.yaml"
    )
    sweep2 = load_parameter_sweep_config(
        "configs/research/vcp_round2_three_segment_v1.yaml"
    )
    assert sweep1.combination_count == sweep2.combination_count == 108
    assert [
        (axis.target, list(axis.values)) for axis in sweep1.axes
    ] == [
        (axis.target, list(axis.values)) for axis in sweep2.axes
    ]
    assert dict(sweep1.fixed_settings) == dict(sweep2.fixed_settings)
    assert sweep1.exit == sweep2.exit


def test_entry_liquidity_uses_prior_20_common_sessions_and_keeps_entry_day_separate():
    dates = pd.bdate_range("2020-01-02", periods=21)
    panel = pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * 21,
            "Trading_money": np.arange(1, 22, dtype=float) * 1_000_000,
        }
    )
    features = build_entry_liquidity_features(panel, lookback=20)
    last = features.iloc[-1]
    assert last["entry_prior_avg_amount_twd"] == pytest.approx(
        np.mean(np.arange(1, 21, dtype=float) * 1_000_000)
    )
    assert last["entry_day_amount_twd"] == pytest.approx(21_000_000)
    assert last["entry_prior_avg_amount_missing_reason"] == ""
    assert last["entry_day_amount_missing_reason"] == ""

    trades = pd.DataFrame(
        [
            {
                "stock_id": "2330",
                "entry_date": dates[-1].date().isoformat(),
            }
        ]
    )
    enriched = enrich_entry_liquidity(trades, features=features).iloc[0]
    assert enriched["entry_prior_avg_amount_twd"] == pytest.approx(
        last["entry_prior_avg_amount_twd"]
    )
    assert enriched["entry_day_amount_twd"] == pytest.approx(21_000_000)


def test_entry_liquidity_missing_value_is_reason_tagged_not_zero_filled():
    dates = pd.bdate_range("2020-01-02", periods=21)
    amount = np.arange(1, 22, dtype=float) * 1_000_000
    amount[5] = np.nan
    panel = pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * 21,
            "Trading_money": amount,
        }
    )
    features = build_entry_liquidity_features(panel, lookback=20)
    last = features.iloc[-1]
    assert pd.isna(last["entry_prior_avg_amount_twd"])
    assert (
        last["entry_prior_avg_amount_missing_reason"]
        == "MISSING_PRIOR_20_COMMON_SESSION_AMOUNT"
    )


def test_round2_exit_distribution_keeps_terminal_lifecycle_separate():
    trades = pd.DataFrame(
        [
            {
                "stock_id": "1101",
                "entry_date": "2020-01-02",
                "exit_reason": "ATR",
                "net_return": 0.10,
            },
            {
                "stock_id": "1102",
                "entry_date": "2020-01-03",
                "exit_reason": "D21",
                "net_return": -0.05,
            },
            {
                "stock_id": "1103",
                "entry_date": "2020-01-06",
                "exit_reason": "BOTH",
                "net_return": 0.00,
            },
            {
                "stock_id": "1104",
                "entry_date": "2020-01-07",
                "exit_reason": "TERMINAL:UNVERIFIED_TERMINAL_CASHOUT",
                "net_return": 0.02,
            },
        ]
    )
    opens = pd.DataFrame(
        [{"stock_id": "1105", "entry_date": "2020-01-08"}]
    )
    simulation = ConfigTradeSimulation(
        trades=trades,
        open_positions=opens,
        signal_count=5,
        entry_count=5,
        ignored_while_holding=0,
        chase_reject_count=0,
        other_unfilled_count=0,
        unfilled_reason_counts={},
        unverified_terminal_trade_count=1,
    )
    row = round2_summary_row(
        config_id="R2-001",
        params={
            "trigger.base_len": 25,
            "trigger.last_contraction": 0.08,
            "trigger.dry_up": 0.50,
            "trigger.breakout_vol": 1.5,
        },
        simulation=simulation,
        low_n_threshold=100,
    )
    assert row["exit_atr_count"] == 1
    assert row["exit_ma21_count"] == 1
    assert row["exit_both_count"] == 1
    assert row["exit_open_count"] == 1
    assert row["exit_terminal_count"] == 1
    assert (
        row["exit_atr_count"]
        + row["exit_ma21_count"]
        + row["exit_both_count"]
        + row["exit_open_count"]
        + row["exit_terminal_count"]
        == row["n_closed"] + row["n_open"]
    )
