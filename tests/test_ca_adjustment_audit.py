from __future__ import annotations

import numpy as np
import pandas as pd

from astraquant.research.ca_adjustment_audit import (
    asof_metrics_from_raw_and_events,
    close_to_ma,
    future_factor,
    metrics_for_close,
    n_session_high_details,
    valid_adjustment_events,
)


def test_common_positive_scale_cancels_close_to_ma():
    x = pd.Series(np.linspace(80.0, 130.0, 140))
    a = close_to_ma(x, 120)
    b = close_to_ma(x * 0.73, 120)
    np.testing.assert_allclose(a.dropna(), b.dropna(), atol=1e-12, rtol=1e-12)


def test_common_positive_scale_preserves_n_session_high_boolean():
    x = pd.Series([float(i) for i in range(1, 65)] + [64.0, 70.0, 69.0])
    a = n_session_high_details(x, 60)["signal"]
    b = n_session_high_details(x * 0.61, 60)["signal"]
    assert a.tolist() == b.tolist()


def test_absolute_ten_twd_threshold_can_flip_under_scale():
    raw = pd.Series([9.9, 10.0, 10.5, 11.0])
    adjusted = raw * 0.9
    assert raw.ge(10).tolist() == [False, True, True, True]
    assert adjusted.ge(10).tolist() == [False, False, False, False]


def test_future_factor_uses_events_strictly_after_decision_date():
    dates = pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]))
    events = np.array(pd.to_datetime(["2020-01-02", "2020-01-04"]), dtype="datetime64[ns]")
    ratios = np.array([0.9, 0.8])
    got = future_factor(dates, events, ratios)
    np.testing.assert_allclose(got, [0.72, 0.8, 0.8])


def test_event_filter_matches_source_ratio_rules_and_multiplies_same_day():
    raw = pd.DataFrame(
        {
            "date": ["2020-01-03", "2020-01-03", "2020-01-04", "2020-01-05"],
            "stock_id": ["2330", "2330", "2330", "2330"],
            "before_price": [100, 100, 100, 100],
            "after_price": [90, 80, 40, 130],
        }
    )
    got = valid_adjustment_events(raw, ratio_min=0.5, ratio_max=1.2)
    assert len(got) == 1
    assert got.iloc[0]["ratio"] == 0.72


def test_asof_reconstruction_preserves_boolean_even_when_rounding_changes_value():
    dates = pd.Series(pd.date_range("2019-01-01", periods=140, freq="D"))
    raw = pd.Series(np.linspace(20.0, 35.0, 140))
    factors = np.full(140, 0.83)
    target = np.ones(140, dtype=bool)
    full = np.round(raw.to_numpy() * factors, 4)
    full_metrics = metrics_for_close(pd.Series(full), ma_window=120, breakout_lookback=60)
    asof = asof_metrics_from_raw_and_events(
        dates=dates,
        raw_close=raw,
        full_factor=factors,
        ma_window=120,
        breakout_lookback=60,
        round_decimals=4,
        target_mask=target,
    )
    assert full_metrics["ma_pass"].tolist() == asof["ma_pass"].tolist()
    assert full_metrics["breakout_signal"].tolist() == asof["breakout_signal"].tolist()
