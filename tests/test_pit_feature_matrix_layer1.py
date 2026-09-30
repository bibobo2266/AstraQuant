from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from astraquant.research.feature_cache import FeatureCache
from pit_feature_matrix_layer1 import (
    Layer1Parameters,
    _percentile,
    add_random_controls_and_ranks,
    attach_industry_pit,
    build_market_context,
    build_stock_features,
)


def _market_context(dates: pd.DatetimeIndex) -> pd.DataFrame:
    tri = pd.Series(
        1000.0 * np.cumprod(1.0 + np.linspace(-0.001, 0.0015, len(dates))),
        index=dates,
    )
    return build_market_context(tri, p=Layer1Parameters())


def _panel(n: int = 320, stock_id: str = "2330") -> pd.DataFrame:
    dates = pd.bdate_range("2015-06-01", periods=n)
    base = 100.0 + np.linspace(0.0, 25.0, n) + np.sin(np.arange(n) / 8.0)
    high = base * 1.01
    low = base * 0.99
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": [stock_id] * n,
            "open": base * 0.999,
            "max": high,
            "min": low,
            "close": base,
            "Trading_Volume": 1_000_000.0 + np.arange(n) * 100.0,
            "Trading_money": 50_000_000.0 + np.arange(n) * 1000.0,
            "observed_trade": True,
            "valid_ohlc": True,
            "market_value": 500_000_000_000.0 + np.arange(n) * 1_000_000.0,
            "industry": "半導體",
            "industry_valid_from": pd.Timestamp("2015-01-01"),
        }
    )


def test_future_mutation_does_not_rewrite_past_features():
    p = Layer1Parameters()
    panel = _panel()
    market = _market_context(pd.DatetimeIndex(panel["date"]))
    a, _ = build_stock_features(
        panel,
        source_revision="fixture-a",
        market_context=market,
        cache=FeatureCache(),
        p=p,
    )
    changed = panel.copy()
    changed.loc[changed.index[-20]:, "close"] *= 3.0
    changed.loc[changed.index[-20]:, "max"] *= 3.0
    changed.loc[changed.index[-20]:, "min"] *= 3.0
    changed.loc[changed.index[-20]:, "open"] *= 3.0
    b, _ = build_stock_features(
        changed,
        source_revision="fixture-b",
        market_context=market,
        cache=FeatureCache(),
        p=p,
    )
    cutoff = panel.index[-21]
    cols = [
        "close_to_ma20",
        "atr21_pct",
        "rsi14",
        "bollinger_bandwidth_14_2",
        "rv20",
    ]
    pd.testing.assert_frame_equal(
        a.loc[:cutoff, cols],
        b.loc[:cutoff, cols],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_warmup_and_missing_values_remain_null():
    panel = _panel(40)
    panel.loc[10, "Trading_money"] = np.nan
    market = _market_context(pd.DatetimeIndex(panel["date"]))
    out, _ = build_stock_features(
        panel,
        source_revision="fixture",
        market_context=market,
        cache=FeatureCache(),
    )
    assert out.loc[10, "amount_mean20_twd"] != 0
    assert pd.isna(out.loc[10, "amount_mean20_twd"])
    assert out["close_to_ma250"].isna().all()
    assert out["rv60"].isna().all()


def test_adjusted_price_constant_scale_preserves_ratio_features():
    panel = _panel()
    market = _market_context(pd.DatetimeIndex(panel["date"]))
    a, _ = build_stock_features(
        panel,
        source_revision="scale-a",
        market_context=market,
        cache=FeatureCache(),
    )
    scaled = panel.copy()
    for col in ("open", "max", "min", "close"):
        scaled[col] *= 0.5
    b, _ = build_stock_features(
        scaled,
        source_revision="scale-b",
        market_context=market,
        cache=FeatureCache(),
    )
    cols = [
        "close_to_ma20",
        "close_to_ma250",
        "atr21_pct",
        "rsi14",
        "kd_k_9_3_3",
        "kd_d_9_3_3",
        "bollinger_bandwidth_14_2",
        "bollinger_channel_position_14_2",
    ]
    for col in cols:
        np.testing.assert_allclose(
            a[col].to_numpy(float),
            b[col].to_numpy(float),
            equal_nan=True,
            rtol=1e-10,
            atol=1e-10,
        )


def test_cross_section_ties_use_average_rank_and_missing_stays_null():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2020-01-02", "2020-01-02", "2020-01-02", "2020-01-02"]
            ),
            "x": [1.0, 1.0, 3.0, np.nan],
        }
    )
    pct, n = _percentile(frame, "x")
    assert n.tolist() == [3, 3, 3, 3]
    assert pct.iloc[0] == pytest.approx(0.5)
    assert pct.iloc[1] == pytest.approx(0.5)
    assert pct.iloc[2] == pytest.approx(1.0)
    assert pd.isna(pct.iloc[3])


def test_random_controls_are_order_invariant_and_fixed_seed():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-02", "2020-01-03"]
            ),
            "stock_id": ["2330", "2330", "2317", "2317"],
        }
    )
    a, _ = add_random_controls_and_ranks(frame, seeds=[1001, 1002])
    shuffled = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)
    b, _ = add_random_controls_and_ranks(shuffled, seeds=[1001, 1002])
    cols = ["date", "stock_id", "random_control_01", "random_control_02"]
    a = a[cols].sort_values(["date", "stock_id"]).reset_index(drop=True)
    b = b[cols].sort_values(["date", "stock_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_industry_pit_does_not_backfill_before_first_known_date():
    rows = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2019-12-31", "2020-01-02", "2020-06-30", "2020-07-01"]
            ),
            "stock_id": ["2330"] * 4,
        }
    )
    pit = pd.DataFrame(
        {
            "stock_id": ["2330", "2330"],
            "valid_from": pd.to_datetime(["2020-01-02", "2020-07-01"]),
            "valid_to": pd.to_datetime(["2020-06-30", None]),
            "industry": ["半導體A", "半導體B"],
        }
    )
    out = attach_industry_pit(rows, pit)
    assert pd.isna(out.loc[0, "industry"])
    assert out.loc[1, "industry"] == "半導體A"
    assert out.loc[2, "industry"] == "半導體A"
    assert out.loc[3, "industry"] == "半導體B"


def test_feature_cache_repeat_hit_is_exercised():
    panel = _panel()
    market = _market_context(pd.DatetimeIndex(panel["date"]))
    cache = FeatureCache()
    _, cache = build_stock_features(
        panel,
        source_revision="cache-fixture",
        market_context=market,
        cache=cache,
    )
    assert cache.misses > 0
    assert cache.hits > 0


def test_market_context_is_single_market_series_not_cross_section_rank():
    dates = pd.bdate_range("2019-01-02", periods=300)
    market = _market_context(dates)
    assert "market_to_ma200" in market
    assert "market_rv20" in market
    assert "market_position252" in market
    assert not any(c.endswith("_pct") for c in market.columns)
    assert market["date"].is_unique


def test_industry_pit_normalizes_mixed_datetime_resolutions():
    rows = pd.DataFrame(
        {
            "date": pd.Series(
                pd.to_datetime(["2020-01-02", "2020-01-03"]),
                dtype="datetime64[us]",
            ),
            "stock_id": ["2330", "2330"],
        }
    )
    pit = pd.DataFrame(
        {
            "stock_id": ["2330"],
            "valid_from": pd.Series(
                pd.to_datetime(["2020-01-02"]),
                dtype="datetime64[us]",
            ),
            "valid_to": pd.Series([pd.NaT], dtype="datetime64[us]"),
            "industry": ["半導體"],
        }
    )
    out = attach_industry_pit(rows, pit)
    assert out["industry"].tolist() == ["半導體", "半導體"]
