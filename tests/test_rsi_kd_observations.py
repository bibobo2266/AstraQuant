import pandas as pd

from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalCompiler, SignalContext
from astraquant.research.strategy_config import ComponentSpec, SignalConfig
from astraquant.research.technical_components import (
    kd_saturation_state,
    rsi_pullback_reclaim,
)


CTX = SignalContext(source_revision="rsi-kd-fixture")


def test_rsi_pullback_reclaim_requires_hold_then_reclaim():
    close = [
        100, 102, 103, 106, 103, 102, 101, 98,
        99, 100, 103, 105, 107, 108, 105, 106,
    ]
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=len(close)),
            "stock_id": ["2330"] * len(close),
            "close": close,
        }
    )
    result = rsi_pullback_reclaim(
        panel=panel,
        spec=ComponentSpec(
            type="RSI_PULLBACK_RECLAIM",
            params={
                "lookback": 5,
                "hold_floor": 50,
                "pullback_ceiling": 58,
                "reclaim_level": 60,
                "pullback_window": 4,
            },
        ),
        cache=FeatureCache(),
        context=CTX,
    )
    assert bool(result.iloc[-1])


def test_rsi_pullback_reclaim_rejects_broken_floor():
    close = [
        100, 102, 103, 106, 103, 102, 101, 98,
        99, 100, 103, 105, 107, 108, 101, 106,
    ]
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=len(close)),
            "stock_id": ["2330"] * len(close),
            "close": close,
        }
    )
    result = rsi_pullback_reclaim(
        panel=panel,
        spec=ComponentSpec(
            type="RSI_PULLBACK_RECLAIM",
            params={
                "lookback": 5,
                "hold_floor": 50,
                "pullback_ceiling": 58,
                "reclaim_level": 60,
                "pullback_window": 4,
            },
        ),
        cache=FeatureCache(),
        context=CTX,
    )
    assert not bool(result.iloc[-1])


def test_kd_high_saturation_is_state_not_sell_signal():
    close = list(range(100, 140))
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=len(close)),
            "stock_id": ["2330"] * len(close),
            "close": close,
            "max": [x + 1 for x in close],
            "min": [x - 1 for x in close],
        }
    )
    state = kd_saturation_state(
        panel=panel,
        spec=ComponentSpec(
            type="KD_SATURATION_STATE",
            params={
                "lookback": 9,
                "k_smooth": 3,
                "d_smooth": 3,
                "zone": "HIGH",
                "high_level": 80,
                "min_sessions": 3,
            },
        ),
        cache=FeatureCache(),
        context=CTX,
    )
    assert bool(state.iloc[-1])
    assert state.tail(5).all()


def test_rsi_kd_components_are_registered():
    compiler = SignalCompiler()
    trigger_cfg = SignalConfig(
        name="rsi_reclaim",
        trigger=ComponentSpec(
            type="RSI_PULLBACK_RECLAIM",
            params={},
        ),
    )
    compiler.compile(trigger_cfg)

    filter_cfg = SignalConfig(
        name="kd_state_filter",
        trigger=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 20}),
        filters=(
            ComponentSpec(
                type="KD_SATURATION_STATE",
                params={"zone": "HIGH"},
            ),
        ),
    )
    compiler.compile(filter_cfg)
