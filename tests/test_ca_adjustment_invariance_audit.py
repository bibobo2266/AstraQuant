from __future__ import annotations

import numpy as np
import pandas as pd

from astraquant.research.ca_adjustment_audit import (
    current_price_feature_frame,
    future_factor_for_rows,
    normalize_dividend_events,
    online_asof_price_features,
    synthetic_uniform_scale_case,
    universe_masks,
)

def test_uniform_positive_scale_preserves_ma120_and_n60_but_not_absolute_gate():
    out = synthetic_uniform_scale_case()
    assert out["max_ma120_abs_diff"] < 1e-12
    assert out["ma120_gate_flips"] == 0
    assert out["n60_flips"] == 0
    assert out["absolute_close_threshold_flips"] is True

def test_event_on_t_is_not_a_future_factor_and_same_day_events_multiply():
    events = normalize_dividend_events(pd.DataFrame({
        "date":["2020-02-01","2020-02-01","2020-03-01"],
        "stock_id":["2330","2330","2330"],
        "before_price":[100,100,100],
        "after_price":[90,80,50],
    }))
    # 0.5 is accepted; same-day product is 0.72.
    assert len(events) == 2
    rows = pd.DataFrame({"date":pd.to_datetime(["2020-02-01","2020-02-29"]), "stock_id":["2330","2330"]})
    f = future_factor_for_rows(rows, events)
    assert np.isclose(f[0], 0.5)
    assert np.isclose(f[1], 0.5)

def test_factor_only_strict_breakout_has_no_tolerance_flip():
    dates = pd.bdate_range("2020-01-01", periods=130)
    close = np.arange(1,131,dtype=float)
    panel = pd.DataFrame({"date":dates,"stock_id":"2330","close":close})
    events = normalize_dividend_events(pd.DataFrame({
        "date":[dates[-1] + pd.Timedelta(days=10)],"stock_id":["2330"],
        "before_price":[100.0],"after_price":[80.0],
    }))
    scaled = panel.copy()
    scaled["close"] *= 0.8
    f = future_factor_for_rows(scaled,events)
    result = current_price_feature_frame(scaled,future_factor=f)
    assert not result["ma120_gate_flip"].any()
    assert not result["n60_flip"].any()

def test_online_event_day_scales_history_before_appending_current_raw():
    dates = pd.bdate_range("2020-01-01", periods=125)
    raw = pd.DataFrame({"date":dates,"stock_id":"2330","raw_close":np.linspace(100,124,125)})
    event_day = dates[120]
    events = normalize_dividend_events(pd.DataFrame({
        "date":[event_day],"stock_id":["2330"],"before_price":[100.0],"after_price":[50.0],
    }))
    out = online_asof_price_features(raw,events)
    # The event-day ratio applies to previous history, while event-day raw is appended unscaled.
    assert out.loc[120,"close_to_ma120_online_asof"] > 0

def test_raw_close_threshold_can_change_final_turnover_membership():
    frame = pd.DataFrame({
        "date":pd.to_datetime(["2020-01-02"]*4),
        "stock_id":["1101","1102","1103","1104"],
        "adjusted_close":[9.0,20.0,20.0,20.0],
        "raw_close":[11.0,20.0,20.0,20.0],
        "Trading_money":[1000.0,900.0,800.0,700.0],
        "observed_trade":[True]*4,"valid_ohlc":[True]*4,
    })
    u = universe_masks(frame,excluded=set(),turnover_top_fraction=0.25)
    assert not bool(u.loc[u.stock_id.eq("1101"),"adjusted_base_pass"].iloc[0])
    assert bool(u.loc[u.stock_id.eq("1101"),"raw_base_pass"].iloc[0])
    assert bool((u["adjusted_counts"] != u["raw_counts"]).any())
