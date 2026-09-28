import pandas as pd
import pytest

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.features.registry import CAWindowRequirement
from astraquant.features.technical import (
    BreakoutSignalConfig,
    build_simple_breakout_signals,
    simple_breakout_feature_definition,
)


def _adjusted(rows):
    return pd.DataFrame(rows)


def _tradability(dates, *, stock_id="2330", observed=True, valid=True):
    return pd.DataFrame(
        [
            {
                "date": d,
                "stock_id": stock_id,
                "observed_trade": observed,
                "valid_ohlc": valid,
            }
            for d in dates
        ]
    )


def test_feature_definition_declares_adjusted_semantics():
    feature = simple_breakout_feature_definition(
        BreakoutSignalConfig(lookback=3, universe_fraction=1.0)
    )
    assert feature.price_semantics is SignalPriceSemantics.SCALE_SENSITIVE
    assert (
        feature.ca_window_requirement
        is CAWindowRequirement.CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK
    )
    assert feature.point_in_time_safe


def test_simple_breakout_matches_prior_high_rule():
    dates = pd.to_datetime(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    )
    closes = [10.0, 12.0, 11.0, 11.5, 13.0]
    rows = []
    for d, close in zip(dates, closes):
        rows.append(
            {
                "date": d,
                "stock_id": "2330",
                "open": close,
                "max": close,
                "min": close,
                "close": close,
                "Trading_money": 1000.0,
            }
        )

    signals = build_simple_breakout_signals(
        _adjusted(rows),
        _tradability(dates),
        config=BreakoutSignalConfig(lookback=3, universe_fraction=1.0),
    )

    assert signals["stock_id"].tolist() == ["2330"]
    assert signals["signal_date"].tolist() == [pd.Timestamp("2026-01-08")]
    assert signals["adjusted_close"].tolist() == [13.0]
    assert signals["breakout_prior_high"].tolist() == [12.0]
    assert signals["breakout_excess"].iloc[0] == pytest.approx(13.0 / 12.0 - 1.0)
    assert signals["price_semantics"].tolist() == ["SCALE_SENSITIVE"]


def test_invalid_adjusted_ohlc_is_masked_before_signal():
    dates = pd.to_datetime(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    )
    rows = [
        {
            "date": dates[0],
            "stock_id": "2330",
            "open": 10.0,
            "max": 10.0,
            "min": 10.0,
            "close": 10.0,
            "Trading_money": 1000.0,
        },
        {
            "date": dates[1],
            "stock_id": "2330",
            "open": 11.0,
            "max": 11.0,
            "min": 11.0,
            "close": 11.0,
            "Trading_money": 1000.0,
        },
        {
            "date": dates[2],
            "stock_id": "2330",
            "open": 12.0,
            "max": 11.0,
            "min": 10.0,
            "close": 12.0,
            "Trading_money": 1000.0,
        },
        {
            "date": dates[3],
            "stock_id": "2330",
            "open": 13.0,
            "max": 13.0,
            "min": 13.0,
            "close": 13.0,
            "Trading_money": 1000.0,
        },
    ]

    signals = build_simple_breakout_signals(
        _adjusted(rows),
        _tradability(dates),
        config=BreakoutSignalConfig(lookback=3, universe_fraction=1.0),
    )

    assert signals.empty


def test_unobserved_tradability_row_is_masked():
    dates = pd.to_datetime(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    )
    rows = [
        {
            "date": d,
            "stock_id": "2330",
            "open": close,
            "max": close,
            "min": close,
            "close": close,
            "Trading_money": 1000.0,
        }
        for d, close in zip(dates, [10.0, 11.0, 12.0, 13.0])
    ]
    trad = _tradability(dates)
    trad.loc[trad["date"].eq(dates[2]), "observed_trade"] = False

    signals = build_simple_breakout_signals(
        _adjusted(rows),
        trad,
        config=BreakoutSignalConfig(lookback=3, universe_fraction=1.0),
    )

    assert signals.empty


def test_duplicate_adjusted_keys_hard_fail():
    row = {
        "date": "2026-01-02",
        "stock_id": "2330",
        "open": 10.0,
        "max": 10.0,
        "min": 10.0,
        "close": 10.0,
        "Trading_money": 1000.0,
    }
    adjusted = pd.DataFrame([row, row])
    trad = _tradability(pd.to_datetime(["2026-01-02"]))

    with pytest.raises(ValueError, match="duplicate"):
        build_simple_breakout_signals(
            adjusted,
            trad,
            config=BreakoutSignalConfig(lookback=3, universe_fraction=1.0),
        )
