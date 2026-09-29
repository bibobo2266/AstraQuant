import pandas as pd
import pytest

from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalCompiler, SignalContext
from astraquant.research.strategy_config import ComponentSpec, SignalConfig
from astraquant.research.technical_components import (
    anchor_reversal,
    bollinger_compression_breakout,
    overnight_market_context,
    vcp_breakout,
)


CTX = SignalContext(source_revision="fixture")


def test_anchor_up_waits_for_confirmed_local_low_and_two_closes():
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=9),
            "stock_id": ["2330"] * 9,
            "max": [11, 10, 9, 6, 9, 10, 11, 12, 13],
            "min": [10, 9, 8, 5, 8, 9, 10, 11, 12],
            "close": [10.5, 9.5, 8.5, 5.5, 8.2, 9.2, 10.2, 11.2, 12.2],
        }
    )
    result = anchor_reversal(
        panel=panel,
        spec=ComponentSpec(
            type="ANCHOR_REVERSAL",
            params={
                "direction": "UP",
                "left_confirm_sessions": 2,
                "right_confirm_sessions": 2,
                "required_closes": 2,
                "max_wait_sessions": 10,
            },
        ),
        cache=FeatureCache(),
        context=CTX,
    )
    # Local low is index 3; anchor-up is prior bar high=9.
    # It is only confirmed after index 5. The first PIT-safe pair of closes
    # above 9 ending on/after confirmation is indices 5 and 6.
    assert not result.iloc[:6].any()
    assert bool(result.iloc[6])


def test_vcp_breakout_requires_contraction_dryup_and_caps_chase():
    n = 20
    highs = [110.0] * 8 + [104.0] * 4 + [101.0] * 7 + [103.0]
    lows = [90.0] * 8 + [96.0] * 4 + [99.0] * 7 + [101.0]
    closes = [100.0] * 8 + [101.0] * 4 + [100.0] * 6 + [100.5, 103.0]
    volumes = [1000.0] * 12 + [400.0] * 7 + [1800.0]
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=n),
            "stock_id": ["2330"] * n,
            "max": highs,
            "min": lows,
            "close": closes,
            "Trading_Volume": volumes,
        }
    )
    spec = ComponentSpec(
        type="VCP_BREAKOUT",
        params={
            "contraction_windows": [12, 8, 4],
            "pivot_lookback": 4,
            "volume_base_lookback": 12,
            "volume_dryup_lookback": 4,
            "max_dryup_volume_ratio": 0.8,
            "max_chase_pct": 0.05,
        },
    )
    result = vcp_breakout(
        panel=panel, spec=spec, cache=FeatureCache(), context=CTX
    )
    assert bool(result.iloc[-1])

    too_far = panel.copy()
    too_far.loc[too_far.index[-1], "close"] = 107.0
    blocked = vcp_breakout(
        panel=too_far, spec=spec, cache=FeatureCache(), context=CTX
    )
    assert not bool(blocked.iloc[-1])


def test_bollinger_compression_breakout_requires_volume_and_recent_squeeze():
    close = [90, 110, 91, 109, 92, 108, 93, 107, 94, 106] + [100] * 14 + [110]
    volume = [1000.0] * 24 + [3000.0]
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=len(close)),
            "stock_id": ["2330"] * len(close),
            "close": close,
            "Trading_Volume": volume,
        }
    )
    spec = ComponentSpec(
        type="BOLLINGER_COMPRESSION_BREAKOUT",
        params={
            "window": 5,
            "stddev": 2.0,
            "percentile_lookback": 10,
            "max_bandwidth_percentile": 0.5,
            "recent_compression_sessions": 5,
            "volume_lookback": 10,
            "volume_multiplier": 1.5,
            "require_mid_slope_up": False,
        },
    )
    result = bollinger_compression_breakout(
        panel=panel, spec=spec, cache=FeatureCache(), context=CTX
    )
    assert bool(result.iloc[-1])

    no_volume = panel.copy()
    no_volume.loc[no_volume.index[-1], "Trading_Volume"] = 1000.0
    blocked = bollinger_compression_breakout(
        panel=no_volume, spec=spec, cache=FeatureCache(), context=CTX
    )
    assert not bool(blocked.iloc[-1])


def test_overnight_context_requires_explicit_premarket_columns():
    panel = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-02")],
            "stock_id": ["2330"],
            "close": [100.0],
        }
    )
    with pytest.raises(ValueError, match="taifex_night_close_0500"):
        overnight_market_context(
            panel=panel,
            spec=ComponentSpec(type="OVERNIGHT_MARKET_CONTEXT", params={}),
            cache=FeatureCache(),
            context=CTX,
        )


def test_new_observation_components_are_registered():
    compiler = SignalCompiler()
    for trigger in ["BOLLINGER_COMPRESSION_BREAKOUT", "VCP_BREAKOUT", "ANCHOR_REVERSAL"]:
        cfg = SignalConfig(
            name=trigger.lower(),
            trigger=ComponentSpec(type=trigger, params={}),
        )
        compiler.compile(cfg)
